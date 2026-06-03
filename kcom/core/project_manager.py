"""Project save/load manager (Phase 3 scaffold)."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from PyQt6.QtCore import QObject, QSettings, pyqtSignal as Signal

from kcom.models.project import ProjectData

_MAX_RECENT = 10
_MANIFEST_NAME = "manifest.json"

_NATIVE_EXT = ".kcom"   # default save extension for new projects
_LEGACY_EXTS = (".ptp", ".kcp", ".kproj", ".json")  # still load but not default-save

# ---------------------------------------------------------------------------
# Project file migration
# ---------------------------------------------------------------------------
# Map (stored_version_str → callable(raw_dict) → None) that upgrades a raw
# dict *in-place* before it is passed to ProjectData.from_dict().
_PROJECT_MIGRATIONS: dict[str, object] = {
    # "1.0" → "1.1": tap_configs key was absent in original scaffold.
    "1.0": lambda d: d.setdefault("tap_configs", []),
}
_CURRENT_PROJECT_VERSION = "1.1"


def _migrate_project_dict(d: dict) -> dict:
    """Apply forward migrations to a raw project dict and return it.

    Handles legacy schemas:
    - ``version`` stored as int (1) rather than string ("1.0")
    - ``connections`` key used instead of ``port_configs``
    - trigger ``encoding`` key used instead of ``pattern_encoding``
    """
    # Normalise integer version to string
    stored = d.get("version", "1.0")
    if isinstance(stored, int):
        stored = f"{stored}.0"
    d["version"] = stored

    # Legacy key aliases
    if "connections" in d and "port_configs" not in d:
        d["port_configs"] = d.pop("connections")

    # Triggers used "encoding" not "pattern_encoding" in early versions
    for trig in d.get("triggers", []):
        if "encoding" in trig and "pattern_encoding" not in trig:
            trig["pattern_encoding"] = trig.pop("encoding")
        trig.setdefault("enabled", True)
        trig.setdefault("match_type", "contains")

    versions = sorted(_PROJECT_MIGRATIONS.keys())
    for v in versions:
        if stored <= v:
            _PROJECT_MIGRATIONS[v](d)  # type: ignore[operator]
    d["version"] = _CURRENT_PROJECT_VERSION
    return d


class ProjectManager(QObject):
    """Saves and loads KCom project files.

    Native format is ``.kcom`` (JSON). Legacy ``.ptp`` / ``.kcp`` / ``.kproj``
    files load transparently for back-compat. ``.kproj`` archives are ZIP;
    everything else is plain JSON.
    """

    project_saved: Signal = Signal(str)    # file path
    project_loaded: Signal = Signal(str)   # file path
    error_occurred: Signal = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._settings = QSettings("KCom", "KCom")

    # ------------------------------------------------------------------
    # Recent projects
    # ------------------------------------------------------------------

    @property
    def recent_projects(self) -> list[str]:
        return self._settings.value("recent_projects", [], type=list)  # type: ignore[return-value]

    def _add_recent(self, path: str) -> None:
        recent = self.recent_projects
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        self._settings.setValue("recent_projects", recent[:_MAX_RECENT])

    # ------------------------------------------------------------------
    # Save / Load
    # ------------------------------------------------------------------

    def save(self, path: str, project: ProjectData) -> bool:
        """Save a KCom project.

        ``.ptp`` / ``.kcp`` / ``.json`` files are written as readable JSON
        (Docklight-compatible project layout). ``.kproj`` files are written as
        a ZIP archive with a JSON manifest. Returns True on success.
        """
        try:
            manifest = json.dumps(project.to_dict(), indent=2, ensure_ascii=False)
            if path.lower().endswith(".kproj"):
                with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                    zf.writestr(_MANIFEST_NAME, manifest)
            else:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(manifest)
            self._add_recent(path)
            self.project_saved.emit(path)
            return True
        except Exception as e:
            self.error_occurred.emit(f"Failed to save project: {e}")
            return False

    def load(self, path: str) -> ProjectData | None:
        """Load a KCom project, auto-detecting JSON (.ptp) vs ZIP (.kproj).

        Returns a ProjectData instance or None on failure.
        """
        try:
            if zipfile.is_zipfile(path):
                with zipfile.ZipFile(path, "r") as zf:
                    if _MANIFEST_NAME not in zf.namelist():
                        self.error_occurred.emit(
                            f"Invalid project file: missing {_MANIFEST_NAME}"
                        )
                        return None
                    raw = zf.read(_MANIFEST_NAME).decode("utf-8")
            else:
                with open(path, "r", encoding="utf-8") as fh:
                    raw = fh.read()
            data = _migrate_project_dict(json.loads(raw))
            project = ProjectData.from_dict(data)
            self._add_recent(path)
            self.project_loaded.emit(path)
            return project
        except Exception as e:
            self.error_occurred.emit(f"Failed to load project: {e}")
            return None

    def clear_recent(self) -> None:
        self._settings.setValue("recent_projects", [])
