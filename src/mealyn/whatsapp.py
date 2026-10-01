"""WhatsApp Cloud API client (Meta Graph API).

Handles the three things Mealyn needs on WhatsApp: downloading an inbound voice
note's media, sending a text message, and sending a voice note. When no token is
configured, outbound sends are logged instead of posted, so the app runs offline.

Inbound webhook payloads are parsed by :func:`parse_inbound`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from .config import WhatsAppSettings, get_settings

log = logging.getLogger("mealyn.whatsapp")


@dataclass
class InboundMessage:
    from_number: str
    kind: str                 # "text" | "audio" | "other"
    text: str = ""            # present for text
    media_id: str = ""        # present for audio
    message_id: str = ""


class WhatsAppClient:
    def __init__(self, settings: WhatsAppSettings | None = None) -> None:
        self.settings = settings or get_settings().whatsapp

    @property
    def live(self) -> bool:
        return self.settings.live

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.token}"}

    # outbound ----------------------------------------------------------- #
    def send_text(self, to: str, text: str) -> None:
        if not self.live:
            log.info("[stub→%s] %s", to, text)
            return
        url = f"{self.settings.api_base}/{self.settings.phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text},
        }
        self._post(url, payload)

    def send_voice(self, to: str, audio_media_id: str) -> None:
        """Send a voice note by media id (upload audio first via ``upload_media``)."""
        if not self.live:
            log.info("[stub→%s] (voice note, media %s)", to, audio_media_id)
            return
        url = f"{self.settings.api_base}/{self.settings.phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "audio",
            "audio": {"id": audio_media_id},
        }
        self._post(url, payload)

    def upload_media(self, audio_bytes: bytes, mime: str = "audio/ogg") -> str:
        if not self.live:
            log.info("[stub] upload_media (%d bytes)", len(audio_bytes))
            return "stub-media-id"
        url = f"{self.settings.api_base}/{self.settings.phone_number_id}/media"
        resp = httpx.post(
            url,
            headers=self._headers(),
            files={"file": ("voice.ogg", audio_bytes, mime)},
            data={"messaging_product": "whatsapp", "type": mime},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def download_media(self, media_id: str) -> bytes:
        if not self.live:
            return b""
        meta = httpx.get(
            f"{self.settings.api_base}/{media_id}", headers=self._headers(), timeout=30
        )
        meta.raise_for_status()
        media_url = meta.json()["url"]
        resp = httpx.get(media_url, headers=self._headers(), timeout=60)
        resp.raise_for_status()
        return resp.content

    def _post(self, url: str, payload: dict) -> None:
        try:
            resp = httpx.post(url, headers=self._headers(), json=payload, timeout=30)
            resp.raise_for_status()
        except Exception:  # noqa: BLE001
            log.exception("WhatsApp send failed")


# --------------------------------------------------------------------------- #
# Webhook parsing
# --------------------------------------------------------------------------- #
def parse_inbound(payload: dict) -> InboundMessage | None:
    """Extract the first message from a WhatsApp Cloud API webhook body."""
    try:
        value = payload["entry"][0]["changes"][0]["value"]
        messages = value.get("messages")
        if not messages:
            return None
        msg = messages[0]
        kind = msg.get("type", "other")
        base = InboundMessage(
            from_number=msg["from"], kind=kind, message_id=msg.get("id", "")
        )
        if kind == "text":
            base.text = msg["text"]["body"]
        elif kind == "audio":
            base.media_id = msg["audio"]["id"]
        return base
    except (KeyError, IndexError, TypeError):
        log.debug("webhook payload had no actionable message")
        return None


def verify_webhook(params: dict, settings: WhatsAppSettings | None = None) -> str | None:
    """Return the hub.challenge when the verify handshake is valid, else None."""
    settings = settings or get_settings().whatsapp
    if (
        params.get("hub.mode") == "subscribe"
        and params.get("hub.verify_token") == settings.verify_token
    ):
        return params.get("hub.challenge")
    return None
