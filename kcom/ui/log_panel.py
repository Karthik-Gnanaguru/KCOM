"""Log panel — bottom dock widget for log file management."""

from __future__ import annotations

import os
from datetime import datetime

from PyQt6.QtCore import QTimer, pyqtSignal as Signal
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class LogPanel(QWidget):
    """Controls for starting/stopping session logging.

    The panel itself does not own a LogManager; instead it emits signals
    that the MainWindow (or PortSession) acts on.

    The log folder field holds only the directory path.  The filename stem
    (kcom-session-<timestamp>) and the extension (.txt / .csv) are derived
    automatically from the selected mode so the user never has to rename a
    file just to switch formats.
    """

    log_start_requested: Signal = Signal(str, str)   # (full_path, mode)
    log_stop_requested: Signal = Signal()

    # Maps combo label → (internal mode token, file extension)
    # Only Text and CSV — the file format is now a thin wrapper; the COLUMNS
    # written are chosen by the terminal's current display mode at log start.
    _MODE_INFO: dict[str, tuple[str, str]] = {
        "Text (.txt)": ("text", ".txt"),
        "CSV (.csv)":  ("csv",  ".csv"),
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._is_logging = False
        self._active_log_path: str = ""
        self._build_ui()
        self._connect_signals()

        # Update file size display every second while logging
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_file_size)
        self._timer.start(1000)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Row 1: folder path
        path_layout = QHBoxLayout()

        path_layout.addWidget(QLabel("Log folder:"))

        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("Select folder for log files…")
        self._path_edit.setText(os.path.expanduser("~"))
        self._path_edit.setToolTip(
            "Folder where log files are saved.\n"
            "File name and extension are set automatically."
        )
        path_layout.addWidget(self._path_edit, stretch=1)

        self._browse_btn = QPushButton("Browse…")
        self._browse_btn.setFixedWidth(80)
        path_layout.addWidget(self._browse_btn)

        layout.addLayout(path_layout)

        # Row 2: mode + Start / Stop
        ctrl_layout = QHBoxLayout()

        ctrl_layout.addWidget(QLabel("Mode:"))

        self._mode_combo = QComboBox()
        self._mode_combo.setFixedWidth(120)
        self._mode_combo.addItems(list(self._MODE_INFO.keys()))
        self._mode_combo.setToolTip(
            "Log file format.\n\n"
            "The columns written match the terminal's current display mode\n"
            "(ASCII / HEX / DEC / BIN / MIXED) at the moment logging starts."
        )
        ctrl_layout.addWidget(self._mode_combo)

        ctrl_layout.addStretch()

        self._start_btn = QPushButton("Start Logging")
        self._start_btn.setObjectName("startLogBtn")
        ctrl_layout.addWidget(self._start_btn)

        self._stop_btn = QPushButton("Stop Logging")
        self._stop_btn.setEnabled(False)
        ctrl_layout.addWidget(self._stop_btn)

        layout.addLayout(ctrl_layout)

        # Row 3: status / preview label
        self._status_label = QLabel()
        self._status_label.setObjectName("infoLabel")
        layout.addWidget(self._status_label)
        self._refresh_preview()          # show initial "will save as …" hint

    def _connect_signals(self) -> None:
        self._browse_btn.clicked.connect(self._on_browse)
        self._start_btn.clicked.connect(self._on_start)
        self._stop_btn.clicked.connect(self._on_stop)
        self._mode_combo.currentIndexChanged.connect(self._refresh_preview)
        self._path_edit.textChanged.connect(self._refresh_preview)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_filename() -> str:
        """Return a timestamped stem, e.g. 'kcom-session-20260528-143000'."""
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return f"kcom-session-{stamp}"

    def _current_ext(self) -> str:
        return self._MODE_INFO[self._mode_combo.currentText()][1]

    def _current_mode_token(self) -> str:
        return self._MODE_INFO[self._mode_combo.currentText()][0]

    def _build_full_path(self, stem: str | None = None) -> str:
        """Combine folder + auto filename + mode extension into a full path."""
        folder = self._path_edit.text().strip() or os.path.expanduser("~")
        if stem is None:
            stem = self._make_filename()
        return os.path.join(folder, stem + self._current_ext())

    def _refresh_preview(self) -> None:
        """Show a 'will save as …' hint when logging is not active."""
        if self._is_logging:
            return
        preview_path = self._build_full_path("kcom-session-<timestamp>")
        self._status_label.setText(f"Will save as: {preview_path}")
        self._status_label.setObjectName("infoLabel")
        self._status_label.style().unpolish(self._status_label)
        self._status_label.style().polish(self._status_label)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_logging_active(self, path: str) -> None:
        """Update UI to reflect that logging is active."""
        import time
        self._is_logging = True
        self._active_log_path = path
        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._mode_combo.setEnabled(False)
        self._browse_btn.setEnabled(False)
        self._path_edit.setEnabled(False)
        self._status_label.setText(f"Logging active → {os.path.basename(path)}")
        self._status_label.setObjectName("successLabel")
        self._status_label.style().unpolish(self._status_label)
        self._status_label.style().polish(self._status_label)

    def set_logging_stopped(self) -> None:
        """Update UI to reflect that logging has stopped."""
        self._is_logging = False
        self._active_log_path = ""
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._mode_combo.setEnabled(True)
        self._browse_btn.setEnabled(True)
        self._path_edit.setEnabled(True)
        self._status_label.setText("Logging stopped")
        self._status_label.setObjectName("infoLabel")
        self._status_label.style().unpolish(self._status_label)
        self._status_label.style().polish(self._status_label)
        # Refresh preview with a new timestamp hint
        self._refresh_preview()

    # ------------------------------------------------------------------
    # Private slots
    # ------------------------------------------------------------------

    def _on_browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Choose Log Folder",
            self._path_edit.text().strip() or os.path.expanduser("~"),
        )
        if folder:
            self._path_edit.setText(folder)

    def _on_start(self) -> None:
        folder = self._path_edit.text().strip()
        if not folder:
            self._status_label.setText("Please select a log folder first")
            self._status_label.setObjectName("errorLabel")
            self._status_label.style().unpolish(self._status_label)
            self._status_label.style().polish(self._status_label)
            return

        full_path = self._build_full_path()   # generates fresh timestamp stem
        mode = self._current_mode_token()
        self.log_start_requested.emit(full_path, mode)

    def _on_stop(self) -> None:
        self.log_stop_requested.emit()

    def _update_file_size(self) -> None:
        if not self._is_logging or not self._active_log_path:
            return
        if os.path.exists(self._active_log_path):
            size = os.path.getsize(self._active_log_path)
            if size < 1024:
                size_str = f"{size} B"
            elif size < 1024 * 1024:
                size_str = f"{size / 1024:.1f} KB"
            else:
                size_str = f"{size / 1024 / 1024:.2f} MB"
            self._status_label.setText(
                f"Logging active → {os.path.basename(self._active_log_path)}"
                f"  [{size_str}]"
            )
