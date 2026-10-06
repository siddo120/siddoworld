"""Tests for the Saathi engine. Run with: pytest (from the saathi/ dir)."""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from saathi.conversation import ConversationSession, Intent, detect_intent  # noqa: E402
from saathi.corpus import get_corpus  # noqa: E402
from saathi.engine import Engine, parse_report  # noqa: E402
from saathi.models import Action, Band, Patient, Report, AnalyteResult, Tier  # noqa: E402
from saathi.reminders import ReminderState, build_reminder, handle_reply  # noqa: E402
from saathi.retrieval import get_retriever  # noqa: E402
from saathi.rules import classify_report  # noqa: E402
from saathi.router import route  # noqa: E402

CORPUS = get_corpus()


def _report(results, age=40, sex="M", chronic=False, panel="Panel"):
    return Report(
        report_id="T",
        patient=Patient(name="Test", age=age, sex=sex, chronic=chronic),
        panel=panel,
        results=[AnalyteResult(a, v, u) for a, v, u in results],
    )


# ---- rule engine ----
def test_normal():
    rc = classify_report(_report([("Hemoglobin", 15.0, "g/dL")]))
    assert rc.overall_tier == Tier.NORMAL


def test_borderline():
    rc = classify_report(_report([("Fasting Glucose", 108, "mg/dL")]))
    assert rc.overall_tier == Tier.BORDERLINE


def test_abnormal_noncritical():
    rc = classify_report(_report([("Total Cholesterol", 255, "mg/dL")]))
    assert rc.overall_tier == Tier.ABNORMAL


def test_critical_high():
    rc = classify_report(_report([("Potassium", 6.6, "mmol/L")]))
    assert rc.overall_tier == Tier.CRITICAL


def test_critical_takes_precedence_over_everything():
    rc = classify_report(_report([
        ("Potassium", 6.6, "mmol/L"),
        ("Total Cholesterol", 255, "mg/dL"),
        ("Serum Ferritin", 999, "ng/mL"),  # uncovered
    ]))
    assert rc.overall_tier == Tier.CRITICAL


def test_multiple_abnormal_to_grey_zone():
    rc = classify_report(_report([
        ("Total Cholesterol", 255, "mg/dL"),
        ("Fasting Glucose", 210, "mg/dL"),
    ]))
    assert rc.overall_tier == Tier.GREY_ZONE
    assert "multiple_abnormal" in rc.flags


def test_uncovered_analyte():
    rc = classify_report(_report([("Serum Ferritin", 300, "ng/mL")]))
    assert rc.overall_tier == Tier.UNCOVERED


def test_sex_specific_range():
    # Hemoglobin 12.5 is normal for F (>=12.0) but below range for M (<13.0).
    assert classify_report(_report([("Hemoglobin", 12.5, "g/dL")], sex="F")).overall_tier == Tier.NORMAL
    assert classify_report(_report([("Hemoglobin", 12.5, "g/dL")], sex="M")).overall_tier in (Tier.BORDERLINE, Tier.ABNORMAL)


def test_alias_resolution():
    rc = classify_report(_report([("K+", 6.6, "mmol/L")]))
    assert rc.overall_tier == Tier.CRITICAL  # resolved via alias to Potassium


def test_grey_zone_when_no_age_range():
    # Known analyte but patient age below the adult range -> grey zone (unsure).
    rc = classify_report(_report([("Hemoglobin", 11.0, "g/dL")], age=5))
    assert rc.overall_tier == Tier.GREY_ZONE


# ---- router ----
def test_router_critical_sla():
    rc = classify_report(_report([("Troponin I", 0.9, "ng/mL")]))
    d = route(rc)
    assert d.action == Action.ESCALATE_CRITICAL
    assert d.sla_minutes == 30
    assert d.band == Band.LOW


def test_router_normal_autonomous_high_band():
    d = route(classify_report(_report([("Hemoglobin", 15.0, "g/dL")])))
    assert d.action == Action.AI_AUTONOMOUS and d.band == Band.HIGH


def test_router_abnormal_medium_band_with_specialist():
    d = route(classify_report(_report([("Total Cholesterol", 255, "mg/dL")])))
    assert d.action == Action.AI_AUTONOMOUS and d.band == Band.MEDIUM
    assert "cardiologist" in d.specialist


# ---- retrieval ----
def test_retrieval_scoped_and_approved():
    snippets = get_retriever().retrieve(["Fasting Glucose"], Tier.BORDERLINE, k=3)
    assert snippets, "expected at least one snippet"
    ids = {s.id for s in snippets}
    # glucose-specific snippet should be retrieved; a cholesterol one should not
    assert any("glucose" in i for i in ids)
    assert not any("cholesterol" in i for i in ids)


def test_retrieval_empty_for_fixed_template_tiers():
    # Critical messages are fixed templates; the explainer retrieves nothing.
    eng = Engine()
    rc = classify_report(_report([("Potassium", 6.6, "mmol/L")]))
    text, ids = eng.explainer.build(rc, "Test", "Electrolytes")
    assert ids == []
    assert "30 minutes" in text


# ---- conversation ----
def test_intent_detection():
    assert detect_intent("can I talk to a human") == Intent.REQUEST_HUMAN
    assert detect_intent("should I stop my medication") == Intent.MEDICAL_ADVICE
    assert detect_intent("I think that's wrong") == Intent.DISPUTE
    assert detect_intent("I want to book an appointment") == Intent.BOOKING
    assert detect_intent("what does hemoglobin mean") == Intent.GENERAL


def test_dispute_capped_at_one_recheck():
    s = ConversationSession(patient_name="Test", classification=classify_report(_report([("Potassium", 6.6, "mmol/L")])))
    first = s.handle("that's wrong")
    assert "re-ran the check" in first.text
    second = s.handle("still wrong")
    assert "going in circles" in second.text  # no infinite loop


def test_human_request_always_honored_and_sticky():
    s = ConversationSession(patient_name="Test", classification=classify_report(_report([("Hemoglobin", 15, "g/dL")])))
    r = s.handle("please connect me to a real person")
    assert r.escalated
    # Once handed off, stays handed off.
    assert s.handle("ok thanks").escalated


def test_medical_advice_refused():
    s = ConversationSession(patient_name="Test", classification=classify_report(_report([("Hemoglobin", 15, "g/dL")])))
    r = s.handle("what medication should I take")
    assert r.offered_doctor and "can't advise" in r.text


def test_followup_answered_from_approved_library():
    # A relevant question is answered from an approved snippet (RAG), not invented.
    s = ConversationSession(patient_name="Test", classification=classify_report(_report([("Total Cholesterol", 255, "mg/dL")])))
    r = s.handle("what is cholesterol?")
    assert r.from_library is True
    assert r.retrieved_ids  # names the snippet(s) it used
    assert not r.escalated


def test_followup_off_topic_declines_and_offers():
    # Nothing in the approved library matches -> decline and offer a person, never guess.
    s = ConversationSession(patient_name="Test", classification=classify_report(_report([("Hemoglobin", 15, "g/dL")])))
    r = s.handle("who won the cricket match last night")
    assert r.from_library is False
    assert r.offered_doctor is True
    assert "won't guess" in r.text


# ---- reminders ----
def test_reminder_due_soon_vs_overdue():
    soon = ReminderState("Test", "HbA1c", date.today() + timedelta(days=3))
    assert "due for a repeat" in build_reminder(soon)
    overdue = ReminderState("Test", "HbA1c", date.today() - timedelta(days=5))
    assert "don't have a recent result" in build_reminder(overdue)


def test_reminder_cap():
    st = ReminderState("Test", "HbA1c", date.today() + timedelta(days=1))
    sent = [build_reminder(st) for _ in range(5)]
    assert sum(1 for s in sent if s) == 3  # MAX_REMINDERS


def test_reminder_stop():
    st = ReminderState("Test", "HbA1c", date.today())
    assert "paused" in handle_reply(st, "STOP")
    assert build_reminder(st) is None


# ---- end to end over samples ----
def test_all_samples_run_and_match_expected_tiers():
    eng = Engine()
    expected = {
        "RPT-1001": Tier.NORMAL, "RPT-1002": Tier.BORDERLINE, "RPT-1003": Tier.ABNORMAL,
        "RPT-1004": Tier.CRITICAL, "RPT-1005": Tier.GREY_ZONE, "RPT-1006": Tier.UNCOVERED,
        "RPT-1007": Tier.CRITICAL,
    }
    for data in CORPUS.sample_reports():
        msg = eng.ingest(parse_report(data))
        assert msg.text, f"{data['report_id']} produced no text"
        assert msg.tier == expected[data["report_id"]], f"{data['report_id']} tier mismatch"
