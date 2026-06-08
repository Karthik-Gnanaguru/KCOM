"""Terminal widget — the main RX/TX display and send bar."""

from __future__ import annotations

import time

from PyQt6.QtCore import Qt, pyqtSignal as Signal
from PyQt6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from kcom.utils.encoding import DisplayMode, apply_terminator, format_line, hex_str_to_bytes


# Colour palette (matches the Catppuccin dark / inverted light)
_COLOURS = {
    "rx_dark": "#a6e3a1",     # green
    "tx_dark": "#89b4fa",     # blue
    "info_dark": "#6c7086",   # subtext
    "error_dark": "#f38ba8",  # red
    "rx_light": "#166534",
    "tx_light": "#1d4ed8",
    "info_light": "#9ca3af",
    "error_light": "#dc2626",
}


class TerminalWidget(QWidget):
    """Combined RX display + TX send bar.

    Signals
    -------
    send_requested(bytes):
        Emitted when the user clicks Send or presses Enter in the input field.
        The payload is already encoded and has any terminator appended.
    """

    send_requested: Signal = Signal(bytes)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._display_mode = DisplayMode.HEX
        self._auto_scroll = True
        self._is_dark = True  # updated by theme changes
        # seq_id → (pattern_bytes, hex_color) for active running sequences
        self._seq_highlights: dict[str, tuple[bytes, str]] = {}
        # Which sub-formats to show when display mode is MIXED (user-configured)
        self._mixed_layers: list[str] = ["hex", "ascii"]

        self._build_ui()
        self._connect_signals()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # --- Terminal display ---
        self._terminal = QPlainTextEdit()
        self._terminal.setReadOnly(True)
        self._terminal.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont("Cascadia Code", 12)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._terminal.setFont(font)
        self._terminal.setMaximumBlockCount(10_000)  # prevent unbounded growth
        layout.addWidget(self._terminal, stretch=1)

        # --- Send bar ---
        send_layout = QHBoxLayout()
        send_layout.setContentsMargins(0, 0, 0, 0)
        send_layout.setSpacing(6)

        # Display mode selector  (order: ASCII HEX DEC BIN MIXED)
        self._mode_combo = QComboBox()
        self._mode_combo.setFixedWidth(90)
        self._mode_combo.addItems(["ASCII", "Hex", "Dec", "Bin", "Mixed"])
        self._mode_combo.setCurrentIndex(1)  # default Hex
        self._mode_combo.setToolTip(
            "Display mode for the terminal (TX and RX).\n"
            "Mixed shows a user-defined combination — configure in Settings → Terminal."
        )
        send_layout.addWidget(self._mode_combo)

        # Input field
        self._input = QLineEdit()
        self._input.setPlaceholderText("Type data to send…")
        self._input.setClearButtonEnabled(True)
        send_layout.addWidget(self._input, stretch=1)

        # Input format (ASCII / Hex)
        self._format_combo = QComboBox()
        self._format_combo.setFixedWidth(70)
        self._format_combo.addItems(["ASCII", "Hex"])
        self._format_combo.setToolTip("Input encoding: ASCII text or hex bytes (e.g. 41 42 43)")
        send_layout.addWidget(self._format_combo)

        # Terminator
        self._term_combo = QComboBox()
        self._term_combo.setFixedWidth(80)
        self._term_combo.addItems(["None", "CR", "LF", "CR+LF"])
        self._term_combo.setCurrentIndex(3)  # default CR+LF
        self._term_combo.setToolTip("Line terminator appended to each transmission")
        send_layout.addWidget(self._term_combo)

        # Send button
        self._send_btn = QPushButton("Send")
        self._send_btn.setObjectName("sendBtn")
        self._send_btn.setFixedWidth(70)
        self._send_btn.setToolTip("Send data (Enter)")
        send_layout.addWidget(self._send_btn)

        layout.addLayout(send_layout)

    def _connect_signals(self) -> None:
        self._send_btn.clicked.connect(self._on_send)
        self._input.returnPressed.connect(self._on_send)
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self._terminal.verticalScrollBar().valueChanged.connect(self._on_scroll_changed)

    # ------------------------------------------------------------------
    # Public API — display
    # ------------------------------------------------------------------

    def append_rx(self, data: bytes, timestamp: float = 0.0) -> None:
        """Append received data as a 'RX : <bytes>' line.

        In ASCII mode the data is split on LF (0x0A) per the ASCII chart so
        that only LF drives new lines.  CR (0x0D) is stripped from each
        segment (common in CRLF streams).  All other display modes receive the
        raw chunk as a single line unchanged.

        When running sequences have registered highlight patterns the line is
        rendered with per-byte foreground colours so the matching bytes stand
        out from the surrounding RX text.
        """
        if not data:
            return
        if self._display_mode == DisplayMode.ASCII:
            for seg in self._split_on_lf(data):
                if self._seq_highlights:
                    self._append_rx_highlighted(seg)
                else:
                    self._append_colored(f"RX : {self._format_line(seg)}\n", self._colour("rx"))
            return
        if self._seq_highlights:
            self._append_rx_highlighted(data)
        else:
            self._append_colored(f"RX : {self._format_line(data)}\n", self._colour("rx"))

    @staticmethod
    def _split_on_lf(data: bytes) -> list[bytes]:
        """Split *data* on LF (0x0A), strip CR (0x0D) from each segment.

        Empty segments (bare LF/CRLF line endings with no content) are dropped
        so they do not produce blank 'RX : ' lines.
        """
        return [
            seg
            for raw in data.split(b"\x0a")
            if (seg := raw.replace(b"\x0d", b""))
        ]

    def append_tx(self, data: bytes) -> None:
        """Append sent data as a 'TX : <bytes>' line in the TX colour."""
        if not data:
            return
        text = self._format_line(data)
        self._append_colored(f"TX : {text}\n", self._colour("tx"))

    def append_info(self, msg: str) -> None:
        """Append an informational message in grey."""
        self._append_colored(f"[INFO] {msg}\n", self._colour("info"))

    def append_error(self, msg: str) -> None:
        """Append an error message in red."""
        self._append_colored(f"[ERROR] {msg}\n", self._colour("error"))

    # ------------------------------------------------------------------
    # Sequence running highlights
    # ------------------------------------------------------------------

    def add_sequence_highlight(self, seq_id: str, pattern: bytes, color: str) -> None:
        """Register a running sequence so its bytes glow in the RX stream.

        Every new RX line will have bytes that match *pattern* rendered in
        *color* instead of the normal RX green, making it easy to see which
        device responses correspond to the active sequence.
        """
        if pattern:
            self._seq_highlights[seq_id] = (pattern, color)

    def remove_sequence_highlight(self, seq_id: str) -> None:
        """Un-register a sequence's highlight when it stops running."""
        self._seq_highlights.pop(seq_id, None)

    def _fmt_chunk(self, data: bytes) -> str:
        """Format a contiguous byte chunk for the current display mode."""
        mode = self._display_mode
        if mode == DisplayMode.HEX:
            return " ".join(f"{b:02X}" for b in data)
        if mode == DisplayMode.DECIMAL:
            return " ".join(str(b) for b in data)
        if mode == DisplayMode.BINARY:
            return " ".join(f"{b:08b}" for b in data)
        if mode == DisplayMode.ASCII:
            out = []
            for b in data:
                if 32 <= b < 127:
                    out.append(chr(b))
                elif b == 0x0D:
                    out.append("\\r")
                elif b == 0x0A:
                    out.append("\\n")
                elif b == 0x09:
                    out.append("\\t")
                else:
                    out.append(f"\\x{b:02x}")
            return "".join(out)
        if mode == DisplayMode.MIXED:
            from kcom.utils.encoding import bytes_to_mixed_custom
            return bytes_to_mixed_custom(data, self._mixed_layers)
        return " ".join(f"{b:02X}" for b in data)  # fallback

    def _append_rx_highlighted(self, data: bytes) -> None:
        """Render one RX line with per-byte colours for matched patterns.

        Each active sequence highlight contributes its colour to the bytes
        that match its pattern.  Non-matching bytes stay in the normal RX
        colour.  If multiple sequences both match the same byte the last
        registered pattern's colour wins.
        """
        rx_col = self._colour("rx")

        # Build a per-byte colour map (None = use rx_col)
        byte_col: list[str | None] = [None] * len(data)
        for _sid, (pattern, hl) in self._seq_highlights.items():
            if not pattern or len(pattern) > len(data):
                continue
            pos = 0
            while pos <= len(data) - len(pattern):
                idx = data.find(pattern, pos)
                if idx < 0:
                    break
                for k in range(idx, idx + len(pattern)):
                    byte_col[k] = hl
                pos = idx + 1

        cursor = self._terminal.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        # Modes that separate bytes with a space character
        use_space = self._display_mode in (
            DisplayMode.HEX, DisplayMode.DECIMAL, DisplayMode.BINARY
        )

        def _ins(text: str, color: str) -> None:
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            cursor.setCharFormat(fmt)
            cursor.insertText(text)

        _ins("RX : ", rx_col)

        # Group consecutive same-colour bytes into spans for efficiency
        i = 0
        while i < len(data):
            col = byte_col[i] or rx_col
            j = i + 1
            while j < len(data) and (byte_col[j] or rx_col) == col:
                j += 1

            # Space separator before this span (not before the first)
            if i > 0 and use_space:
                _ins(" ", rx_col)

            _ins(self._fmt_chunk(data[i:j]), col)
            i = j

        _ins("\n", rx_col)

        if self._auto_scroll:
            self._terminal.setTextCursor(cursor)
            self._terminal.ensureCursorVisible()

    # ------------------------------------------------------------------
    # Trigger highlight helpers (called by MainWindow on trigger events)
    # ------------------------------------------------------------------

    def highlight_all_matching(self, pattern: bytes, name: str, color: str) -> None:
        """Scan every existing terminal block and background-highlight text
        that contains the hex representation of *pattern*.

        Called when triggers are added or re-enabled so historical data is
        retroactively marked.
        """
        if not pattern:
            return
        search_str = " ".join(f"{b:02X}" for b in pattern)
        doc = self._terminal.document()
        bg = QColor(color)
        bg.setAlphaF(0.25)

        fmt = QTextCharFormat()
        fmt.setBackground(bg)

        cursor = QTextCursor(doc)
        while True:
            cursor = doc.find(search_str, cursor)
            if cursor.isNull():
                break
            cursor.mergeCharFormat(fmt)

    def highlight_last_rx(self, name: str, color: str) -> None:
        """Apply a background tint to the most recent RX line.

        Called immediately after a trigger fires so the user sees which
        incoming line caused the match.
        """
        doc = self._terminal.document()
        block = doc.lastBlock()
        while block.isValid():
            if block.text().startswith("RX : "):
                bc = QTextCursor(block)
                bc.select(QTextCursor.SelectionType.BlockUnderCursor)
                bg = QColor(color)
                bg.setAlphaF(0.20)
                fmt = QTextCharFormat()
                fmt.setBackground(bg)
                bc.mergeCharFormat(fmt)
                break
            block = block.previous()

    def set_mixed_layers(self, layers: list[str]) -> None:
        """Update which sub-formats are combined when MIXED mode is active.

        *layers* should be a non-empty subset of ``["hex", "ascii", "dec", "bin"]``.
        The change takes effect on the next incoming RX/TX line.
        """
        valid = [l for l in layers if l in ("hex", "ascii", "dec", "bin")]
        self._mixed_layers = valid if valid else ["hex", "ascii"]

    def set_display_mode(self, mode: DisplayMode) -> None:
        """Change the current display mode (does NOT re-render history)."""
        self._display_mode = mode
        idx_map = {
            DisplayMode.ASCII:   0,
            DisplayMode.HEX:     1,
            DisplayMode.DECIMAL: 2,
            DisplayMode.BINARY:  3,
            DisplayMode.MIXED:   4,
        }
        self._mode_combo.setCurrentIndex(idx_map.get(mode, 0))

    def clear(self) -> None:
        """Clear the terminal display."""
        self._terminal.clear()

    def set_theme(self, is_dark: bool) -> None:
        """Update colour palette when theme changes."""
        self._is_dark = is_dark

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _format_line(self, data: bytes) -> str:
        if self._display_mode == DisplayMode.MIXED:
            from kcom.utils.encoding import bytes_to_mixed_custom
            return bytes_to_mixed_custom(data, self._mixed_layers)
        return format_line(data, self._display_mode)

    def _colour(self, role: str) -> str:
        suffix = "dark" if self._is_dark else "light"
        return _COLOURS.get(f"{role}_{suffix}", "#cccccc")

    def _append_colored(self, text: str, color: str) -> None:
        """Insert coloured text at the end of the terminal efficiently."""
        cursor = self._terminal.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor.setCharFormat(fmt)
        cursor.insertText(text)

        if self._auto_scroll:
            self._terminal.setTextCursor(cursor)
            self._terminal.ensureCursorVisible()

    def _on_send(self) -> None:
        """Parse input, apply terminator, and emit send_requested."""
        raw = self._input.text().strip()
        if not raw:
            return

        fmt = self._format_combo.currentText()
        try:
            if fmt == "Hex":
                data = hex_str_to_bytes(raw)
            else:
                data = raw.encode("utf-8", errors="replace")
        except ValueError as e:
            self.append_error(f"Bad hex input: {e}")
            return

        term_map = {"None": "none", "CR": "cr", "LF": "lf", "CR+LF": "crlf"}
        terminator = term_map.get(self._term_combo.currentText(), "none")
        data = apply_terminator(data, terminator)

        self.send_requested.emit(data)
        self._input.clear()

    def _on_mode_changed(self, index: int) -> None:
        # Order matches combo: ASCII(0) Hex(1) Dec(2) Bin(3) Mixed(4)
        modes = [
            DisplayMode.ASCII,
            DisplayMode.HEX,
            DisplayMode.DECIMAL,
            DisplayMode.BINARY,
            DisplayMode.MIXED,
        ]
        if 0 <= index < len(modes):
            self._display_mode = modes[index]

    def _on_scroll_changed(self, value: int) -> None:
        """Disable auto-scroll when user scrolls up; re-enable at bottom."""
        sb = self._terminal.verticalScrollBar()
        self._auto_scroll = value == sb.maximum()
