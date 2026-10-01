"""Festival and fasting calendar cross-check.

A small, religion-aware lookup used by the planner so festival days get an
appropriate dish and fasting restrictions are honoured. Replace the static table
with a real calendar service; the interface (``festivals_between``) stays put.
"""

from __future__ import annotations

from datetime import date, timedelta

# (month, day) -> (name, religions it matters to)
_FESTIVALS: dict[tuple[int, int], tuple[str, tuple[str, ...]]] = {
    (1, 14): ("Makar Sankranti / Pongal", ("hindu",)),
    (3, 14): ("Holi", ("hindu",)),
    (8, 15): ("Independence Day", ("all",)),
    (8, 19): ("Raksha Bandhan", ("hindu",)),
    (9, 7): ("Ganesh Chaturthi", ("hindu",)),
    (10, 2): ("Gandhi Jayanti", ("all",)),
    (10, 20): ("Diwali", ("hindu", "jain", "sikh")),
    (11, 15): ("Guru Nanak Jayanti", ("sikh",)),
    (12, 25): ("Christmas", ("christian", "all")),
}


def festivals_between(start: date, days: int, religion: str = "") -> list[str]:
    """Festivals in the window [start, start+days) relevant to the household."""
    religion = (religion or "").lower()
    out: list[str] = []
    for offset in range(days):
        d = start + timedelta(days=offset)
        hit = _FESTIVALS.get((d.month, d.day))
        if not hit:
            continue
        name, religions = hit
        if "all" in religions or not religion or religion in religions:
            out.append(f"{name} on {d.isoformat()}")
    return out
