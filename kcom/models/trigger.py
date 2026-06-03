"""Receive trigger / auto-response model."""
from __future__ import annotations
import uuid
from dataclasses import dataclass, field


@dataclass
class RxTrigger:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    enabled: bool = True
    match_type: str = "contains"     # "contains", "starts_with", "ends_with", "exact", "regex"
    pattern: str = ""                # Pattern string
    pattern_encoding: str = "ascii"  # "ascii" or "hex"
    action: str = "log"              # "log", "send_sequence", "notify", "stop"
    action_data: str = ""            # e.g. sequence id if action == "send_sequence"
    color: str = "#f9e2af"
    description: str = ""

    def get_pattern_bytes(self) -> bytes:
        """Parse the pattern string into bytes."""
        s = self.pattern.strip()
        if not s:
            return b""
        if self.pattern_encoding == "hex":
            s = s.replace(" ", "")
            if len(s) % 2 != 0:
                s = "0" + s
            return bytes.fromhex(s)
        return s.encode("latin-1", errors="replace")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "match_type": self.match_type,
            "pattern": self.pattern,
            "pattern_encoding": self.pattern_encoding,
            "action": self.action,
            "action_data": self.action_data,
            "color": self.color,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RxTrigger":
        return cls(
            id=d.get("id", str(uuid.uuid4())),
            name=d.get("name", ""),
            enabled=d.get("enabled", True),
            match_type=d.get("match_type", "contains"),
            pattern=d.get("pattern", ""),
            pattern_encoding=d.get("pattern_encoding", "ascii"),
            action=d.get("action", "log"),
            action_data=d.get("action_data", ""),
            color=d.get("color", "#f9e2af"),
            description=d.get("description", ""),
        )
