"""FastAPI app exposing the WhatsApp Cloud API webhook for Mealyn.

- ``GET  /webhook`` — Meta's verification handshake.
- ``POST /webhook`` — inbound messages (text or voice notes) → orchestrator.
- ``GET  /health`` — liveness + which rails are live vs stubbed.

Run: ``uvicorn mealyn.app:app --reload``
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, Response

from .config import get_settings
from .orchestrator import Orchestrator
from .whatsapp import parse_inbound, verify_webhook

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Mealyn", version="0.1.0")
orchestrator = Orchestrator()


@app.get("/health")
def health() -> dict:
    s = get_settings()
    return {
        "status": "ok",
        "rails": {
            "brain_claude": s.brain_live,
            "whatsapp": s.whatsapp.live,
            "gnani_voice": s.gnani.live,
            "payment": s.payment.live,
        },
    }


@app.get("/webhook")
async def verify(request: Request) -> Response:
    challenge = verify_webhook(dict(request.query_params))
    if challenge is not None:
        return Response(content=challenge, media_type="text/plain")
    return Response(status_code=403, content="verification failed")


@app.post("/webhook")
async def receive(request: Request) -> dict:
    payload = await request.json()
    msg = parse_inbound(payload)
    if msg is not None:
        try:
            orchestrator.handle_inbound(msg)
        except Exception:  # noqa: BLE001 — always 200 so Meta doesn't retry-storm
            logging.getLogger("mealyn.app").exception("handler failed")
    return {"status": "received"}
