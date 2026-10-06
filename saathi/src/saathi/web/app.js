"use strict";

const $ = (sel) => document.querySelector(sel);
const messagesEl = $("#messages");
const inputEl = $("#input");
const sendBtn = $("#send");
const subEl = $("#chatSub");
const auditPanel = $("#auditPanel");
const auditBody = $("#auditBody");

let state = { sessionId: null, reportId: null, chronic: false };

const TIER_LABEL = {
  normal: "Normal", borderline: "Borderline", abnormal: "Abnormal",
  critical: "Critical", grey_zone: "Needs review", uncovered: "Needs review",
};
const ACTION_LABEL = {
  ai_autonomous: "AI sends autonomously",
  ai_spot_check: "AI drafts · human spot-check",
  escalate_critical: "Escalated · mandatory human call",
  human_review: "Routed to human review",
};

async function api(path, opts) {
  const res = await fetch(path, opts);
  return res.json();
}

// ---- render helpers ----
function scrollDown() { messagesEl.scrollTop = messagesEl.scrollHeight; }

function addSystem(text) {
  const el = document.createElement("div");
  el.className = "system";
  el.textContent = text;
  messagesEl.appendChild(el);
  scrollDown();
}

function addBanner(text, kind) {
  const el = document.createElement("div");
  el.className = "banner " + kind;
  el.textContent = text;
  messagesEl.appendChild(el);
  scrollDown();
}

function addBubble(text, dir, meta) {
  const el = document.createElement("div");
  el.className = "msg " + dir;
  el.textContent = text;
  if (meta) {
    const m = document.createElement("div");
    m.className = "meta";
    m.innerHTML = meta;
    el.appendChild(m);
  }
  messagesEl.appendChild(el);
  scrollDown();
}

function tierBadge(tier) {
  return `<span class="tierbadge ${tier}">${TIER_LABEL[tier] || tier}</span>`;
}

// ---- sidebar ----
async function loadReports() {
  const samples = await api("/api/samples");
  const list = $("#reportList");
  list.innerHTML = "";
  samples.forEach((s) => {
    const li = document.createElement("li");
    li.className = "report";
    li.dataset.id = s.report_id;
    li.innerHTML = `
      <div class="row">
        <span class="panel">${s.panel}</span>
        ${s.chronic ? '<span class="chip chronic">chronic</span>' : ""}
      </div>
      <div class="patient">${s.patient}</div>
      <div class="scenario">${s.scenario}</div>`;
    li.addEventListener("click", () => selectReport(s, li));
    list.appendChild(li);
  });
}

async function selectReport(sample, li) {
  document.querySelectorAll(".report").forEach((r) => r.classList.remove("active"));
  li.classList.add("active");
  state.reportId = sample.report_id;
  state.chronic = sample.chronic;

  messagesEl.innerHTML = "";
  addSystem(`Report ${sample.report_id} received — ${sample.panel} for ${sample.patient}`);

  const res = await api("/api/ingest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ report_id: sample.report_id }),
  });

  state.sessionId = res.session_id;
  subEl.textContent = `${sample.patient} · ${TIER_LABEL[res.tier]}`;

  // Escalation / review banners before the message.
  if (res.action === "escalate_critical") {
    addBanner("🔴 Critical value — mandatory clinical call within 30 minutes. AI pre-loads specialist slots.", "critical");
  } else if (res.action === "human_review") {
    addBanner("⚪ Routed to human review — AI does not explain this one.", "review");
  }

  const meta = `${tierBadge(res.tier)} <span>${ACTION_LABEL[res.action] || res.action}</span> <span>· via ${res.provider}</span>`;
  addBubble(res.text, "in", meta);

  if (state.chronic) {
    addSystem("This is a chronic patient — a repeat-test reminder can be sent (see the field below).");
  }

  renderAudit(res);
  enableComposer(res.action);
}

function enableComposer(action) {
  const canChat = action === "ai_autonomous";
  inputEl.disabled = false;
  sendBtn.disabled = false;
  inputEl.placeholder = canChat
    ? "Reply as the patient… (try: 'are you sure?' or 'should I stop my medication?')"
    : "Reply as the patient…";
  inputEl.focus();
}

// ---- conversation ----
async function sendMessage(text) {
  addBubble(text, "out");
  // Special demo command: reminder for chronic patients.
  if (/^remind$/i.test(text.trim()) && state.chronic) {
    const r = await api("/api/reminder", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ report_id: state.reportId }),
    });
    addBubble(r.text, "in", "reminder");
    return;
  }
  const res = await api("/api/message", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: state.sessionId, message: text }),
  });
  if (res.error) { addSystem("⚠️ " + res.error); return; }
  addBubble(res.text, "in", `intent: ${res.intent}`);
  if (res.escalated) addBanner("🤝 Handed off to a human agent.", "handoff");
}

$("#composer").addEventListener("submit", (e) => {
  e.preventDefault();
  const text = inputEl.value.trim();
  if (!text || !state.sessionId) return;
  inputEl.value = "";
  sendMessage(text);
});

// ---- audit panel ----
$("#auditToggle").addEventListener("click", () => {
  document.querySelector(".app").classList.toggle("audit-open");
  auditPanel.classList.toggle("hidden");
});

function renderAudit(res) {
  const c = res.classification;
  const d = res.decision;
  let html = "";

  html += `<div class="block"><h3>Decision</h3>
    <div class="kv"><span>Overall tier</span>${tierBadge(c.overall_tier)}</div>
    <div class="kv"><span>Action</span><span>${ACTION_LABEL[d.action] || d.action}</span></div>
    <div class="kv"><span>Confidence band</span><span>${d.band}</span></div>
    ${d.sla_minutes ? `<div class="kv"><span>SLA</span><span>${d.sla_minutes} min</span></div>` : ""}
    ${d.specialist ? `<div class="kv"><span>Specialist</span><span>${d.specialist}</span></div>` : ""}
    <div class="kv" style="margin-top:8px"><span class="muted">${d.reason}</span></div>
  </div>`;

  html += `<div class="block"><h3>Rule engine — per analyte</h3>`;
  c.analytes.forEach((a) => {
    html += `<div class="analyte-row">
      <div class="top"><span>${a.analyte}: <b>${a.value} ${a.unit}</b></span>${tierBadge(a.tier)}</div>
      <div class="reason">${a.reason}</div>
    </div>`;
  });
  if (c.flags && c.flags.length) {
    html += `<div class="kv" style="margin-top:8px"><span>Flags</span><span>${c.flags.join(", ")}</span></div>`;
  }
  html += `</div>`;

  html += `<div class="block"><h3>RAG — retrieved snippets</h3>`;
  if (res.retrieved_ids && res.retrieved_ids.length) {
    html += res.retrieved_ids.map((id) => `<span class="rag-id">${id}</span>`).join("");
  } else {
    html += `<span class="muted">None — fixed template (no explanation drafted).</span>`;
  }
  html += `</div>`;

  auditBody.innerHTML = html;
}

loadReports();
