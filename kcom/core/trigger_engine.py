"""Trigger engine — matches incoming bytes against RxTrigger rules.

The engine is owned per :class:`PortSession`. The UI (TriggerPanel) keeps the
authoritative list; MainWindow pushes that list into every active session via
:py:meth:`set_triggers`.

When a rule matches, the engine emits :pyattr:`trigger_fired` with the rule and
the matched bytes. Action dispatch (logging a marker, sending a sequence,
showing a notification, stopping comms) happens in MainWindow so it can reach
the sequence list and per-port runners.

Boundary matches across TCP/serial chunk boundaries are handled by keeping a
small per-trigger tail of ``len(pattern) - 1`` bytes from the previous feed.
"""

from __future__ import annotations

import re

from PyQt6.QtCore import QObject, pyqtSignal as Signal

from kcom.models.trigger import RxTrigger


class TriggerEngine(QObject):
    """Evaluates incoming data against a list of :class:`RxTrigger` rules.

    Signals
    -------
    trigger_fired(RxTrigger, bytes):
        Emitted whenever a rule matches. The bytes payload is the matched
        slice — useful for terminal markers and debugging.
    """

    trigger_fired: Signal = Signal(object, bytes)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._triggers: list[RxTrigger] = []
        # Per-trigger tail buffer for cross-chunk "contains" / "ends_with" matches
        self._tails: dict[str, bytes] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def triggers(self) -> list[RxTrigger]:
        return list(self._triggers)

    def set_triggers(self, triggers: list[RxTrigger]) -> None:
        """Replace the active rule list. Resets per-trigger tail buffers."""
        self._triggers = list(triggers)
        # Drop tails for triggers that are gone; new ones start empty.
        live_ids = {t.id for t in self._triggers}
        self._tails = {tid: buf for tid, buf in self._tails.items() if tid in live_ids}

    def clear(self) -> None:
        self._triggers.clear()
        self._tails.clear()

    def feed(self, data: bytes) -> None:
        """Check ``data`` (a freshly received RX chunk) against every enabled rule.

        Semantics by match type:

        * ``contains`` / ``regex`` — scan a rolling buffer of the previous tail
          plus the new chunk, so a pattern that straddles two chunks still
          matches exactly once.
        * ``starts_with`` / ``ends_with`` / ``exact`` — checked against the new
          chunk only. These are message-shape predicates and folding the tail
          in would mis-anchor them (e.g. ``starts_with`` would test the start
          of the residual tail, not the new chunk).
        """
        if not data or not self._triggers:
            return
        for trig in self._triggers:
            if not trig.enabled:
                continue
            try:
                pat = trig.get_pattern_bytes()
            except Exception:
                continue
            if not pat:
                continue

            mt = trig.match_type
            if mt in ("contains", "regex"):
                tail = self._tails.get(trig.id, b"")
                combined = tail + data
                if self._matches(trig, combined, pat):
                    self.trigger_fired.emit(trig, pat)
                keep = max(0, len(pat) - 1)
                self._tails[trig.id] = combined[-keep:] if keep > 0 else b""
            else:
                # starts_with / ends_with / exact: applied per RX chunk.
                if self._matches(trig, data, pat):
                    self.trigger_fired.emit(trig, pat)

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------

    @staticmethod
    def _matches(trig: RxTrigger, haystack: bytes, pat: bytes) -> bool:
        mt = trig.match_type
        try:
            if mt == "contains":
                return pat in haystack
            if mt == "starts_with":
                return haystack.startswith(pat)
            if mt == "ends_with":
                return haystack.endswith(pat)
            if mt == "exact":
                return haystack == pat
            if mt == "regex":
                # Use latin-1 so every byte round-trips losslessly to a single char.
                pat_s = trig.pattern
                hay_s = haystack.decode("latin-1", errors="replace")
                return bool(re.search(pat_s, hay_s))
        except Exception:
            return False
        return False
