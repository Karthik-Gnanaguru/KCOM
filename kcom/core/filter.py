"""Shared filter DSL — used by the terminal table AND the log writer.

When the user types a filter in the terminal toolbar, the same predicate
must decide both **which rows are visible on screen** and **which records
are written to the log file** (per the user's "log only what is visible"
requirement). Keeping the implementation in one place avoids the two
diverging.

Supported tokens (parsed in order):

* ``direction:rx`` / ``direction:tx`` — direction equality
* ``dir:rx`` / ``dir:tx``               — alias for ``direction:``
* ``hex:02 07 A5``                      — payload must contain this hex sequence
* ``kind:data`` / ``kind:info`` / ``kind:error`` — record kind
* anything else                         — plain substring (matched against
  uppercase hex string, ASCII sidebar, and the optional info / error text)

A blank filter matches everything.
"""

from __future__ import annotations


def _hex_str(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


def _ascii_sidebar(data: bytes) -> str:
    """Printable chars, ``.`` for non-printable — same scheme as the terminal."""
    return "".join(chr(b) if 32 <= b < 127 else "." for b in data)


def matches_filter(
    data: bytes,
    direction: str,
    filter_text: str,
    *,
    kind: str = "data",
    text: str = "",
) -> bool:
    """Return True if ``data`` should be shown / logged under ``filter_text``.

    Empty / whitespace filter → always True. Bad ``hex:`` input → True
    (we don't want a typo to silently swallow incoming data).
    """
    needle = (filter_text or "").strip().lower()
    if not needle:
        return True

    # DSL prefixes — single keyword:value
    if needle.startswith("direction:"):
        return direction.upper() == needle[len("direction:"):].strip().upper()
    if needle.startswith("dir:"):
        return direction.upper() == needle[4:].strip().upper()
    if needle.startswith("hex:"):
        try:
            pattern = bytes.fromhex(needle[4:].replace(" ", ""))
        except ValueError:
            # Don't hide rows on a typo — surface them so the user notices.
            return True
        return pattern in data
    if needle.startswith("kind:"):
        return kind == needle[5:].strip()

    # Plain text: search hex string, ASCII sidebar, and the info / error text
    hex_s   = _hex_str(data).lower()
    ascii_s = _ascii_sidebar(data).lower()
    text_s  = (text or "").lower()
    return needle in hex_s or needle in ascii_s or needle in text_s
