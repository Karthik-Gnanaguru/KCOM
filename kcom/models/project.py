"""Project data model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from kcom.models.port_config import PortConfig, TapConfig
from kcom.models.sequence import TxSequence
from kcom.models.trigger import RxTrigger


@dataclass
class ProjectData:
    # Always saves the CURRENT schema version. Older files are auto-migrated
    # on load (see kcom/core/project_manager.py _migrate_project_dict), but
    # any fresh save writes 1.1 so loaders never see a stale version stamp.
    version: str = "1.1"
    created: str = field(default_factory=lambda: datetime.now().isoformat())
    name: str = "Untitled"
    notes: str = ""
    port_configs: list[PortConfig] = field(default_factory=list)
    tap_configs:  list[TapConfig]  = field(default_factory=list)
    sequences:    list[TxSequence] = field(default_factory=list)
    triggers:     list[RxTrigger]  = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "created": self.created,
            "name": self.name,
            "notes": self.notes,
            "port_configs": [pc.to_dict() for pc in self.port_configs],
            "tap_configs":  [tc.to_dict() for tc in self.tap_configs],
            "sequences": [s.to_dict() for s in self.sequences],
            "triggers": [t.to_dict() for t in self.triggers],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ProjectData":
        return cls(
            version=d.get("version", "1.0"),
            created=d.get("created", datetime.now().isoformat()),
            name=d.get("name", "Untitled"),
            notes=d.get("notes", ""),
            port_configs=[PortConfig.from_dict(pc) for pc in d.get("port_configs", [])],
            tap_configs=[TapConfig.from_dict(tc) for tc in d.get("tap_configs", [])],
            sequences=[TxSequence.from_dict(s) for s in d.get("sequences", [])],
            triggers=[RxTrigger.from_dict(t) for t in d.get("triggers", [])],
        )
