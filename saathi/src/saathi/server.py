"""Zero-dependency HTTP server exposing the engine + a WhatsApp-style chat UI.

    python -m saathi.server          # serves on http://127.0.0.1:8000
    PORT=9000 python -m saathi.server

Endpoints:
    GET  /                  -> chat UI
    GET  /app.js /style.css -> static assets
    GET  /api/samples       -> list sample reports
    POST /api/ingest        -> {report_id} or a full report dict -> explanation + session
    POST /api/message       -> {session_id, message} -> conversation reply
    POST /api/reminder      -> {report_id} -> a chronic-patient reminder (demo)
    GET  /api/audit?report_id=... -> deterministic classification + decision
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from .conversation import ConversationSession
from .corpus import get_corpus
from .engine import Engine, parse_report
from .reminders import ReminderState, build_reminder, handle_reply

WEB_DIR = Path(__file__).parent / "web"
_ENGINE = Engine()
_SESSIONS: dict[str, ConversationSession] = {}
_REMINDERS: dict[str, ReminderState] = {}

_CONTENT_TYPES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}


class Handler(BaseHTTPRequestHandler):
    server_version = "Saathi/0.1"

    # ---- helpers -------------------------------------------------------
    def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj).encode("utf-8"))

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return {}

    def _static(self, name: str) -> None:
        path = (WEB_DIR / name).resolve()
        if not str(path).startswith(str(WEB_DIR.resolve())) or not path.is_file():
            self._send(404, b"not found", "text/plain")
            return
        ctype = _CONTENT_TYPES.get(path.suffix, "application/octet-stream")
        self._send(200, path.read_bytes(), ctype)

    def log_message(self, *args) -> None:  # quieter console
        pass

    # ---- routes --------------------------------------------------------
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path
        if route == "/":
            self._static("index.html")
        elif route in ("/app.js", "/style.css"):
            self._static(route.lstrip("/"))
        elif route == "/api/samples":
            self._json(self._samples())
        elif route == "/api/audit":
            qs = parse_qs(parsed.query)
            rid = (qs.get("report_id") or [""])[0]
            data = get_corpus().sample_report(rid)
            if not data:
                self._json({"error": "unknown report_id"}, 404)
                return
            self._json(_ENGINE.audit(parse_report(data)))
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:
        route = urlparse(self.path).path
        if route == "/api/ingest":
            self._ingest(self._read_json())
        elif route == "/api/message":
            self._message(self._read_json())
        elif route == "/api/reminder":
            self._reminder(self._read_json())
        else:
            self._send(404, b"not found", "text/plain")

    # ---- handlers ------------------------------------------------------
    def _samples(self) -> list[dict]:
        out = []
        for r in get_corpus().sample_reports():
            p = r["patient"]
            out.append({
                "report_id": r["report_id"],
                "scenario": r.get("scenario", ""),
                "panel": r.get("panel", ""),
                "patient": f"{p['name']}, {p['age']}/{p['sex']}",
                "chronic": bool(p.get("chronic", False)),
            })
        return out

    def _ingest(self, payload: dict) -> None:
        rid = payload.get("report_id")
        data = get_corpus().sample_report(rid) if rid else payload.get("report")
        if not data:
            self._json({"error": "provide a known report_id or a report object"}, 400)
            return
        report = parse_report(data)
        msg = _ENGINE.ingest(report)
        session_id = uuid.uuid4().hex
        _SESSIONS[session_id] = _ENGINE.session_for(report)
        resp = msg.to_dict()
        resp["session_id"] = session_id
        resp["scenario"] = data.get("scenario", "")
        self._json(resp)

    def _message(self, payload: dict) -> None:
        sid = payload.get("session_id", "")
        session = _SESSIONS.get(sid)
        if not session:
            self._json({"error": "unknown or expired session_id"}, 400)
            return
        reply = session.handle(payload.get("message", ""))
        self._json({"text": reply.text, "intent": reply.intent.value,
                    "escalated": reply.escalated, "offered_doctor": reply.offered_doctor,
                    "from_library": reply.from_library, "retrieved_ids": reply.retrieved_ids})

    def _reminder(self, payload: dict) -> None:
        rid = payload.get("report_id", "")
        data = get_corpus().sample_report(rid)
        if not data:
            self._json({"error": "unknown report_id"}, 404)
            return
        p = data["patient"]
        if not p.get("chronic"):
            self._json({"text": f"{p['name']} isn't flagged as a chronic patient, so no repeat-test reminder applies.",
                        "sent": False})
            return
        state = _REMINDERS.get(rid)
        if state is None:
            # Demo: due in 3 days for the first nudge.
            state = ReminderState(patient_name=p["name"], test=data.get("panel", "repeat test"),
                                  due_date=date.today() + timedelta(days=3))
            _REMINDERS[rid] = state
        text = build_reminder(state)
        self._json({"text": text or "(reminder cap reached — ops follow-up)",
                    "sent": text is not None, "sent_count": state.sent_count})


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "127.0.0.1")
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Saathi running on http://{host}:{port}  (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
