"""The 'G' in RAG, behind a swappable interface.

The explanation layer talks to an ``LLMProvider``. The default ``MockProvider``
is fully deterministic: it assembles the message from the pre-approved template
plus the retrieved snippets, with no free generation. That keeps the prototype
runnable with zero API keys *and* models the production safety stance, where the
LLM only ever phrases around vetted content.

``ClaudeProvider`` is the real seam. It reads ANTHROPIC_API_KEY and is only
imported lazily, so nothing here requires the SDK to be installed.
"""
from __future__ import annotations

import os
from typing import Protocol


class LLMProvider(Protocol):
    name: str

    def draft(self, system: str, prompt: str, *, fallback: str) -> str:
        """Return message text. ``fallback`` is the deterministic template
        rendering, used as-is by the mock and as a safety net by real providers.
        """
        ...


class MockProvider:
    """Deterministic, offline. Returns the pre-rendered template verbatim.

    This is intentionally *not* creative: in a clinical setting the pre-approved
    rendering is the safe answer, and a mock that invented phrasing would hide
    exactly the risk the architecture is designed to contain.
    """

    name = "mock"

    def draft(self, system: str, prompt: str, *, fallback: str) -> str:
        return fallback


class ClaudeProvider:
    """Real Claude phrasing. Grounded strictly in the template + snippets passed
    in ``prompt``; on any error it falls back to the deterministic rendering so a
    message always goes out.
    """

    name = "claude"

    def __init__(self, model: str = "claude-haiku-4-5-20251001") -> None:
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic  # lazy: only needed if this provider is actually used

            self._client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
        return self._client

    def draft(self, system: str, prompt: str, *, fallback: str) -> str:
        try:
            client = self._get_client()
            resp = client.messages.create(
                model=self.model,
                max_tokens=600,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text").strip()
            return text or fallback
        except Exception:
            # Never let a provider failure block a patient message.
            return fallback


def get_provider(name: str | None = None) -> LLMProvider:
    """Factory. Defaults to the mock unless SAATHI_LLM=claude is set and a key
    is present.
    """
    name = (name or os.environ.get("SAATHI_LLM", "mock")).lower()
    if name == "claude" and os.environ.get("ANTHROPIC_API_KEY"):
        return ClaudeProvider()
    return MockProvider()
