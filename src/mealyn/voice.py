"""Voice pipeline — Gnani Prisma (speech-to-text) and Timbre (text-to-speech).

Stubbed by default: STT passes text through, TTS returns the text as a marker.
When Gnani credentials are present, wire the real HTTP calls in ``_prisma`` /
``_timbre`` — the interface the orchestrator uses stays the same.
"""

from __future__ import annotations

import logging

import httpx

from .config import GnaniSettings, get_settings

log = logging.getLogger("mealyn.voice")


class VoicePipeline:
    def __init__(self, settings: GnaniSettings | None = None) -> None:
        self.settings = settings or get_settings().gnani

    @property
    def live(self) -> bool:
        return self.settings.live

    # speech-to-text ----------------------------------------------------- #
    def transcribe(self, audio_bytes: bytes, *, language: str = "hi") -> str:
        """Return the transcript of a voice note (Gnani Prisma)."""
        if not self.live or not self.settings.prisma_url:
            # Stub: in dev we receive text directly, so decode and pass through.
            try:
                return audio_bytes.decode("utf-8")
            except UnicodeDecodeError:
                return "[voice note received — STT stub cannot decode audio]"
        try:
            resp = httpx.post(
                self.settings.prisma_url,
                headers={"Authorization": f"Bearer {self.settings.api_key}"},
                files={"audio": audio_bytes},
                data={"language": language},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json().get("transcript", "")
        except Exception:  # noqa: BLE001
            log.exception("Prisma STT failed")
            return "[transcription failed]"

    # text-to-speech ----------------------------------------------------- #
    def synthesize(self, text: str, *, language: str = "hi") -> bytes:
        """Return audio bytes for a voice note (Gnani Timbre)."""
        if not self.live or not self.settings.timbre_url:
            # Stub: encode the text so downstream logging shows what was "spoken".
            return text.encode("utf-8")
        try:
            resp = httpx.post(
                self.settings.timbre_url,
                headers={"Authorization": f"Bearer {self.settings.api_key}"},
                json={"text": text, "language": language},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.content
        except Exception:  # noqa: BLE001
            log.exception("Timbre TTS failed")
            return text.encode("utf-8")
