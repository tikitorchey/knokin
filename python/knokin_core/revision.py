"""Data revision `YYYY-MM-DD.N` (DD48): the date of the last change plus a 0-based counter for the same day."""
from __future__ import annotations

import re
from datetime import date

_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.(\d+)$")


def parse_revision(s: object) -> tuple[str, int] | None:
    """(date, n) for a well-formed revision, else None. Compare the tuples, not the strings (n is numeric)."""
    if not isinstance(s, str):
        return None
    m = _RE.match(s)
    if not m:
        return None
    try:
        date.fromisoformat(m.group(1))
    except ValueError:
        return None
    return m.group(1), int(m.group(2))


def next_revision(today: str, prev: object = None) -> str:
    """Same day as `prev` -> N+1; otherwise `today`.0. A `prev` dated after `today` (clock skew) is continued, not reset."""
    p = parse_revision(prev)
    if p is not None:
        d, n = p
        if d >= today:
            return f"{d}.{n + 1}"
    return f"{today}.0"
