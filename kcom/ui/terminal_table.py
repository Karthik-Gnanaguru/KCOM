"""Structured terminal table — replaces the plain-text terminal display."""

from __future__ import annotations

import os
import time
from datetime import datetime

from PyQt6.QtCore import Qt, QItemSelectionModel, pyqtSignal as Signal
from PyQt6.QtGui import QBrush, QColor, QFont, QKeySequence, QPalette, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kcom.models.terminal_style import TerminalStyle, theme_defaults
from kcom.utils.encoding import apply_terminator, hex_str_to_bytes


_MODE_ASCII = "ASCII"
_MODE_HEX   = "HEX"
_MODE_MIXED = "MIXED"
_MODE_DEC   = "DEC"
_MODE_BIN   = "BIN"

_MAX_ROWS = 5000

# Fixed info/error colors (not user-customisable).
_INFO_COLOR  = {"dark": "#8b949e", "light": "#656d76"}
_ERROR_COLOR = {"dark": "#f85149", "light": "#cf222e"}


def _ascii_sidebar(data: bytes) -> str:
    """Printable chars, '.' for non-printable."""
    return "".join(chr(b) if 32 <= b < 127 else "." for b in data)


def _ascii_escaped(data: bytes) -> str:
    """ASCII text with escapes for non-printable bytes."""
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


def _hex_str(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


def _dec_str(data: bytes) -> str:
    return " ".join(str(b) for b in data)


def _bin_str(data: bytes) -> str:
    return " ".join(f"{b:08b}" for b in data)


def _ctrl_char_label(b: int) -> str | None:
    """Return a visible tag for common control characters, or None."""
    _CTRL = {
        0x00: "<NUL>", 0x01: "<SOH>", 0x02: "<STX>", 0x03: "<ETX>",
        0x04: "<EOT>", 0x05: "<ENQ>", 0x06: "<ACK>", 0x07: "<BEL>",
        0x08: "<BS>",  0x09: "<TAB>", 0x0A: "<LF>",  0x0B: "<VT>",
        0x0C: "<FF>",  0x0D: "<CR>",  0x0E: "<SO>",  0x0F: "<SI>",
        0x10: "<DLE>", 0x11: "<DC1>", 0x12: "<DC2>", 0x13: "<DC3>",
        0x14: "<DC4>", 0x15: "<NAK>", 0x16: "<SYN>", 0x17: "<ETB>",
        0x18: "<CAN>", 0x19: "<EM>",  0x1A: "<SUB>", 0x1B: "<ESC>",
        0x1C: "<FS>",  0x1D: "<GS>",  0x1E: "<RS>",  0x1F: "<US>",
        0x7F: "<DEL>",
    }
    return _CTRL.get(b)


def _ascii_with_ctrl(data: bytes) -> str:
    """ASCII text with visible `<NAME>` tags for control characters."""
    out = []
    for b in data:
        tag = _ctrl_char_label(b)
        if tag:
            out.append(tag)
        elif 32 <= b < 127:
            out.append(chr(b))
        else:
            out.append(f"\\x{b:02x}")
    return "".join(out)


def _ascii_multiline(data: bytes) -> str:
    """Docklight-style ASCII rendering — `\\r` and `\\n` become real line breaks.

    Used by the structured terminal when `TerminalStyle.ascii_render == "multiline"`.
    Each chunk is rendered in a multi-line cell so log-style output like
    `Received Data: …\\r\\n----…\\r\\nDEVICE_TYPE: ESP32\\r\\n` reads naturally
    rather than showing literal escape sequences.

    Rendering rules:
      * `0x0D 0x0A` (CRLF)  -> one `\\n`  (collapses Windows line endings)
      * `0x0D`     (CR)     -> `\\n`     (treat lone CR as newline like terminals)
      * `0x0A`     (LF)     -> `\\n`
      * `0x09`     (TAB)    -> real tab character
      * `0x08`     (BS)     -> `\\b`     (escape; visible char would be ambiguous)
      * other 0x00-0x1F / 0x7F          -> `\\xNN`
      * printable 0x20-0x7E             -> as-is
    """
    out: list[str] = []
    i = 0
    n = len(data)
    while i < n:
        b = data[i]
        if b == 0x0D:                              # \r — collapse \r\n
            if i + 1 < n and data[i + 1] == 0x0A:
                out.append("\n")
                i += 2
                continue
            out.append("\n")
        elif b == 0x0A:
            out.append("\n")
        elif b == 0x09:
            out.append("\t")
        elif b == 0x08:
            out.append("\\b")
        elif 32 <= b < 127:
            out.append(chr(b))
        else:
            out.append(f"\\x{b:02x}")
        i += 1
    return "".join(out)


# Custom item-data roles.
# Qt stylesheets override QTableWidgetItem.setBackground(), so we paint tints
# ourselves in the delegate below.
_HIGHLIGHT_ROLE = Qt.ItemDataRole.UserRole + 100   # trigger match
_FIND_ROLE      = Qt.ItemDataRole.UserRole + 101   # find-bar match
_CHANNEL_ROLE   = Qt.ItemDataRole.UserRole + 102   # tap channel tint (A=blue, B=green)
_SEQ_ROLE       = Qt.ItemDataRole.UserRole + 103   # running-sequence byte highlight

# Channel tint colors (semi-transparent blends with the background)
_CHANNEL_A_DARK  = QColor(30,  80, 160, 35)
_CHANNEL_B_DARK  = QColor(30, 140,  70, 35)
_CHANNEL_A_LIGHT = QColor(219, 234, 254, 80)   # blue-50
_CHANNEL_B_LIGHT = QColor(220, 252, 231, 80)   # green-50


class _HighlightDelegate(QStyledItemDelegate):
    """Paints trigger-match, sequence-match, and find-match tints.

    Priority (highest first):
    1. Qt selection color (current/selected rows — handled by the style engine)
    2. Find highlight (amber) for non-selected matching rows
    3. Trigger tint (_HIGHLIGHT_ROLE) for trigger-matched rows
    4. Sequence tint (_SEQ_ROLE) for rows matching a running TX sequence
    5. Channel tint (_CHANNEL_ROLE) for tap A/B rows
    """

    def initStyleOption(self, option: QStyleOptionViewItem, index) -> None:
        super().initStyleOption(option, index)
        # Qt's QSS 'color' on ancestor QWidget can override palette.Text after
        # initStyleOption reads ForegroundRole.  Re-applying it here guarantees
        # RX (green) / TX (blue) colours survive the stylesheet cascade.
        fg = index.data(Qt.ItemDataRole.ForegroundRole)
        if fg is not None:
            brush = fg if isinstance(fg, QBrush) else QBrush(fg if isinstance(fg, QColor) else QColor(fg))
            option.palette.setBrush(QPalette.ColorRole.Text, brush)
            option.palette.setBrush(QPalette.ColorRole.WindowText, brush)

    def paint(self, painter, option, index):
        is_selected = bool(
            option.state & QStyle.StateFlag.State_Selected
        )

        if not is_selected:
            find_bg = index.data(_FIND_ROLE)
            hl_bg   = index.data(_HIGHLIGHT_ROLE)
            seq_bg  = index.data(_SEQ_ROLE)
            bg = (
                find_bg if (isinstance(find_bg, QColor) and find_bg.isValid())
                else hl_bg if (isinstance(hl_bg, QColor) and hl_bg.isValid())
                else seq_bg
            )
            # Channel tint is lowest priority — only shown when no other tint
            if not (isinstance(bg, QColor) and bg.isValid()):
                ch_bg = index.data(_CHANNEL_ROLE)
                if isinstance(ch_bg, QColor) and ch_bg.isValid():
                    bg = ch_bg
            if isinstance(bg, QColor) and bg.isValid():
                painter.save()
                painter.fillRect(option.rect, bg)
                painter.restore()
                opt = QStyleOptionViewItem(option)
                self.initStyleOption(opt, index)
                opt.backgroundBrush = QBrush(bg)
                opt.features &= ~QStyleOptionViewItem.ViewItemFeature.Alternate
                super().paint(painter, opt, index)
                return
        super().paint(painter, option, index)


class TerminalTable(QWidget):
    """Structured RX/TX terminal display + send bar.

    Signals
    -------
    send_requested(bytes):
        Emitted when the user clicks Send or presses Enter; payload is encoded
        and has any terminator appended.
    """

    send_requested:            Signal = Signal(bytes)
    create_trigger_requested:  Signal = Signal(bytes)   # right-click → "Create RX Trigger"
    create_sequence_requested: Signal = Signal(bytes)   # right-click → "Create TX Sequence"
    annotation_requested:      Signal = Signal(str)     # right-click → "Insert Annotation"
    log_start_requested:       Signal = Signal()        # log toggle ON
    log_stop_requested:        Signal = Signal()        # log toggle OFF
    send_break_requested:      Signal = Signal()        # Break button
    display_mode_changed:      Signal = Signal(str)     # ASCII/HEX/DEC/BIN/MIXED — for log column selection
    filter_changed:            Signal = Signal(str)     # filter DSL text — pushed to LogManager so log mirrors the visible view

    COL_INDEX   = 0
    COL_TIME    = 1
    COL_DIR     = 2
    COL_HEX     = 3
    COL_ASCII   = 4
    COL_DEC     = 5
    COL_BIN     = 6
    COL_CHANNEL = 7

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._is_dark = False
        self._mode = _MODE_MIXED
        self._ts_format = "wall"
        self._is_logging = False
        self._auto_scroll = True
        self._paused = False
        self._tap_mode = False
        self._show_ctrl_chars = False
        self._ascii_render = "multiline"
        self._next_index = 1
        self._total_appended = 0
        self._start_mono: float = time.perf_counter()
        # records: list of dict(idx, ts, t_mono, wall, direction, data, kind)
        # kind: "data" | "info" | "error"
        self._records: list[dict] = []
        self._buffer: list[dict] = []
        # RX/TX coalescing queue — chunks accumulate here until the next 16 ms
        # drain tick. Batching many tiny chunks into one insertRow burst is
        # essential for multi-port robustness; a single QTableWidget insertRow
        # in multiline mode triggers an O(N) vertical-header re-measure.
        self._pending: list[dict] = []
        self._drain_scheduled: bool = False
        self._filter_text = ""
        self._style: TerminalStyle = TerminalStyle()
        # Running-sequence highlight rules: seq_id → (pattern_bytes, hex_color)
        self._seq_highlights: dict[str, tuple[bytes, str]] = {}
        # Sub-formats used when display mode is MIXED
        self._mixed_layers: list[str] = ["hex", "ascii"]
        # Find state
        self._find_rows: list[int] = []
        self._find_idx: int = -1
        # Visible data columns — updated by _apply_mode_columns for resize tracking
        self._visible_data_cols: list[int] = []

        self._mono = QFont("Cascadia Code")
        self._mono.setStyleHint(QFont.StyleHint.Monospace)
        self._mono.setPointSize(10)

        self._build_ui()
        self._connect_signals()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        # --- Toolbar row ---
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        header = QLabel("Terminal")
        header.setObjectName("sectionHeader")
        toolbar.addWidget(header)

        _MODE_TIPS = {
            _MODE_ASCII:  "ASCII display — printable chars + escape sequences",
            _MODE_HEX:    "Hex display — two-digit hex per byte",
            _MODE_DEC:    "Decimal display — three-digit decimal per byte",
            _MODE_BIN:    "Binary display — eight-bit representation per byte",
            _MODE_MIXED:  "Mixed — user-defined combination (configure in Settings → Terminal)",
        }
        self._seg_buttons: dict[str, QPushButton] = {}
        for mode in (_MODE_ASCII, _MODE_HEX, _MODE_DEC, _MODE_BIN, _MODE_MIXED):
            btn = QPushButton(mode)
            btn.setObjectName("segBtn")
            btn.setProperty("active", mode == self._mode)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(_MODE_TIPS.get(mode, mode))
            btn.clicked.connect(lambda _checked=False, m=mode: self._on_mode_clicked(m))
            self._seg_buttons[mode] = btn
            toolbar.addWidget(btn)

        toolbar.addSpacing(8)

        ts_label = QLabel("TS:")
        ts_label.setStyleSheet("color: #7d8590; font-size: 10px;")
        toolbar.addWidget(ts_label)
        self._ts_combo = QComboBox()
        self._ts_combo.addItems(["Wall", "Delta", "Elapsed", "None"])
        self._ts_combo.setFixedWidth(78)
        self._ts_combo.setToolTip("Timestamp display format")
        self._ts_combo.currentTextChanged.connect(self._on_ts_format_changed)
        toolbar.addWidget(self._ts_combo)

        toolbar.addStretch()

        self._pause_btn = QPushButton("⏸ Pause")
        self._pause_btn.setObjectName("pauseBtn")
        self._pause_btn.setCheckable(True)
        self._pause_btn.setToolTip("Freeze the live view (buffer new data)")
        self._pause_btn.setFixedWidth(82)
        toolbar.addWidget(self._pause_btn)

        self._log_btn = QPushButton("Log: Off")
        self._log_btn.setObjectName("logBtn")
        self._log_btn.setCheckable(True)
        self._log_btn.setToolTip(
            "Log: Off — click to start saving received/sent data to a file.\n"
            "The log file is created automatically in your home folder."
        )
        self._log_btn.setFixedWidth(82)
        toolbar.addWidget(self._log_btn)

        self._filter_box = QLineEdit()
        self._filter_box.setObjectName("filterBox")
        self._filter_box.setPlaceholderText("Filter (direction:rx, hex:02 07…)")
        self._filter_box.setToolTip(
            "Filter rows — examples:\n"
            "  direction:rx  (or dir:rx / dir:tx)\n"
            "  hex:02 07  (exact byte sequence)\n"
            "  kind:data  (data / info / error)\n"
            "  plain text  (case-insensitive substring match)"
        )
        self._filter_box.setClearButtonEnabled(True)
        self._filter_box.setFixedWidth(200)
        toolbar.addWidget(self._filter_box)

        self._scroll_btn = QPushButton("⤓")  # downward arrow to bar
        self._scroll_btn.setObjectName("scrollBtn")
        self._scroll_btn.setCheckable(True)
        self._scroll_btn.setChecked(True)
        self._scroll_btn.setToolTip("Auto-scroll to newest")
        toolbar.addWidget(self._scroll_btn)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setObjectName("termClearBtn")
        self._clear_btn.setToolTip("Clear terminal display (Ctrl+L)")
        toolbar.addWidget(self._clear_btn)

        self._export_btn = QPushButton("Export")
        self._export_btn.setObjectName("exportBtn")
        self._export_btn.setToolTip("Export terminal contents to a file")
        toolbar.addWidget(self._export_btn)

        self._msg_count = QLabel("0 msgs")
        self._msg_count.setObjectName("msgCount")
        toolbar.addWidget(self._msg_count)

        root.addLayout(toolbar)

        # --- Find bar (hidden until Ctrl+F) ---
        self._find_bar = QFrame()
        self._find_bar.setObjectName("findBar")
        self._find_bar.setFrameShape(QFrame.Shape.StyledPanel)
        find_row = QHBoxLayout(self._find_bar)
        find_row.setContentsMargins(6, 3, 6, 3)
        find_row.setSpacing(4)

        close_find_btn = QPushButton("✕")
        close_find_btn.setFixedSize(20, 20)
        close_find_btn.setToolTip("Close find bar (Esc)")
        close_find_btn.clicked.connect(self._hide_find_bar)
        find_row.addWidget(close_find_btn)

        find_row.addWidget(QLabel("Find:"))

        self._find_input = QLineEdit()
        self._find_input.setPlaceholderText("Search text or hex…")
        self._find_input.setClearButtonEnabled(True)
        find_row.addWidget(self._find_input, stretch=1)

        self._find_fmt_combo = QComboBox()
        self._find_fmt_combo.addItems(["Text", "Hex"])
        self._find_fmt_combo.setFixedWidth(68)
        find_row.addWidget(self._find_fmt_combo)

        self._find_prev_btn = QPushButton("▲")
        self._find_prev_btn.setFixedWidth(28)
        self._find_prev_btn.setToolTip("Previous match")
        find_row.addWidget(self._find_prev_btn)

        self._find_next_btn = QPushButton("▼")
        self._find_next_btn.setFixedWidth(28)
        self._find_next_btn.setToolTip("Next match")
        find_row.addWidget(self._find_next_btn)

        self._find_count_lbl = QLabel("")
        self._find_count_lbl.setStyleSheet("color: #7d8590; font-size: 10px; min-width: 50px;")
        find_row.addWidget(self._find_count_lbl)

        self._find_bar.hide()
        root.addWidget(self._find_bar)

        # --- Table ---
        self._table = QTableWidget(0, 8)
        self._table.setObjectName("terminalTable")
        self._table.setHorizontalHeaderLabels(
            ["#", "Time", "Dir", "HEX", "ASCII", "DEC", "BIN", "Ch"]
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(True)
        # Custom delegate so trigger highlights survive the QSS alternating-row fill.
        self._table.setItemDelegate(_HighlightDelegate(self._table))
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setWordWrap(False)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        hh = self._table.horizontalHeader()
        hh.setStretchLastSection(False)
        for col in range(self._table.columnCount()):
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        self._table.setColumnHidden(self.COL_CHANNEL, True)   # shown only in tap mode
        self._table.verticalHeader().setDefaultSectionSize(22)
        # Horizontal scrollbar so wide content (many bytes, BIN mode, MIXED) is reachable.
        self._table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        # Initial column visibility for the default mode (MIXED shows both).
        self._apply_mode_columns()

        root.addWidget(self._table, stretch=1)

        # --- Send bar ---
        send_row = QHBoxLayout()
        send_row.setSpacing(6)

        self._send_input = QLineEdit()
        self._send_input.setObjectName("sendInput")
        self._send_input.setPlaceholderText("Type data to send…")
        self._send_input.setToolTip(
            "Enter data to send. Press Enter or click Send.\n"
            "In Hex mode: space-separated bytes, e.g.  01 02 0A"
        )
        self._send_input.setClearButtonEnabled(True)
        send_row.addWidget(self._send_input, stretch=1)

        self._format_combo = QComboBox()
        self._format_combo.addItems(["ASCII", "Hex"])
        self._format_combo.setFixedWidth(76)
        self._format_combo.setToolTip("Input encoding")
        send_row.addWidget(self._format_combo)

        self._term_combo = QComboBox()
        self._term_combo.addItems(["None", "CR", "LF", "CR+LF"])
        self._term_combo.setCurrentIndex(3)
        self._term_combo.setFixedWidth(84)
        self._term_combo.setToolTip("Line terminator")
        send_row.addWidget(self._term_combo)

        self._break_btn = QPushButton("Break")
        self._break_btn.setObjectName("breakBtn")
        self._break_btn.setToolTip("Send serial BREAK condition")
        self._break_btn.setFixedWidth(58)
        send_row.addWidget(self._break_btn)

        self._send_btn = QPushButton("Send ⚡")
        self._send_btn.setObjectName("sendBtn")
        send_row.addWidget(self._send_btn)

        root.addLayout(send_row)

    def _connect_signals(self) -> None:
        self._filter_box.textChanged.connect(self._on_filter_changed)
        self._clear_btn.clicked.connect(self.clear)
        self._export_btn.clicked.connect(self._on_export)
        self._scroll_btn.toggled.connect(self._on_scroll_toggled)
        self._send_btn.clicked.connect(self._on_send)
        self._send_input.returnPressed.connect(self._on_send)
        # Pause, Log + Break buttons
        self._pause_btn.toggled.connect(self._on_pause_toggled)
        self._log_btn.toggled.connect(self._on_log_toggled)
        self._break_btn.clicked.connect(self.send_break_requested)
        # Find bar
        self._find_input.textChanged.connect(self._on_find_text_changed)
        self._find_input.returnPressed.connect(self._find_next)
        self._find_fmt_combo.currentIndexChanged.connect(self._on_find_text_changed)
        self._find_next_btn.clicked.connect(self._find_next)
        self._find_prev_btn.clicked.connect(self._find_prev)
        # Context menu
        self._table.customContextMenuRequested.connect(self._on_context_menu)
        # Double-click column divider to auto-fit that column
        self._table.horizontalHeader().sectionDoubleClicked.connect(
            self._table.resizeColumnToContents
        )
        # Shortcuts
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self._show_find_bar)
        QShortcut(QKeySequence("Escape"), self._find_bar).activated.connect(self._hide_find_bar)
        # Ctrl+C → copy selection as TSV (pastes directly into Excel / Sheets)
        QShortcut(QKeySequence("Ctrl+C"), self._table).activated.connect(self._copy_selection_tsv)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        try:
            self._redistribute_columns()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Public API (called by main_window)
    # ------------------------------------------------------------------

    def append_rx(self, data: bytes, timestamp: float = 0.0) -> None:
        if not data:
            return
        self._add_record("RX", data, timestamp, kind="data")

    def append_tx(self, data: bytes) -> None:
        if not data:
            return
        self._add_record("TX", data, time.perf_counter(), kind="data")

    def append_info(self, msg: str) -> None:
        self._add_record("--", msg.encode("utf-8", "replace"), time.perf_counter(),
                          kind="info", text=msg)

    def append_error(self, msg: str) -> None:
        self._add_record("!!", msg.encode("utf-8", "replace"), time.perf_counter(),
                          kind="error", text=msg)

    # ------------------------------------------------------------------
    # Tap / Monitor mode
    # ------------------------------------------------------------------

    def enable_tap_mode(self) -> None:
        """Switch the terminal into tap mode — shows the Channel column."""
        self._tap_mode = True
        self._apply_mode_columns()
        # Hide send bar controls that don't apply to a tap session
        self._send_btn.setEnabled(False)
        self._break_btn.setEnabled(False)
        self._send_btn.setToolTip("Send is disabled in tap/monitor mode")

    def append_tap_rx(self, data: bytes, ts: float, channel: str) -> None:
        """Append an RX record tagged with ``channel`` (``"A"`` or ``"B"``)."""
        if not data:
            return
        self._add_record("RX", data, ts, kind="data", channel=channel)

    def append_tap_info(self, msg: str, channel: str = "") -> None:
        """Info message shown in the tap terminal, optionally tagged with a channel."""
        self._add_record("--", msg.encode("utf-8", "replace"), time.perf_counter(),
                         kind="info", text=msg, channel=channel)

    def append_tap_error(self, msg: str, channel: str = "") -> None:
        """Error message shown in the tap terminal, optionally tagged with a channel."""
        self._add_record("!!", msg.encode("utf-8", "replace"), time.perf_counter(),
                         kind="error", text=msg, channel=channel)

    def _apply_highlight(
        self,
        row: int,
        rec: dict,
        trigger_name: str,
        trigger_color: str,
    ) -> None:
        """Tint every cell of ``row`` via the custom highlight role + tooltip."""
        color = self._soft_bg(trigger_color)
        tip = f"★ Trigger '{trigger_name}' matched this packet"
        for col in range(self._table.columnCount()):
            item = self._table.item(row, col)
            if item is None:
                continue
            item.setData(_HIGHLIGHT_ROLE, color)
            item.setToolTip(tip)
        rec["trigger_color"] = trigger_color
        rec["trigger_name"] = trigger_name

    def highlight_last_rx(self, trigger_name: str, trigger_color: str) -> None:
        """Tint the most-recent RX row to mark a live trigger match."""
        for i in range(len(self._records) - 1, -1, -1):
            rec = self._records[i]
            if rec["direction"] == "RX" and rec["kind"] == "data":
                if i < self._table.rowCount():
                    self._apply_highlight(i, rec, trigger_name, trigger_color)
                return

    def highlight_all_matching(
        self,
        pattern: bytes,
        trigger_name: str,
        trigger_color: str,
    ) -> int:
        """Retroactively tint every RX row whose data contains ``pattern``.

        Returns the number of rows tinted.  Called when a trigger is added or
        re-enabled so the user gets immediate feedback on already-captured data.
        """
        if not pattern:
            return 0
        count = 0
        row_count = self._table.rowCount()
        for row, rec in enumerate(self._records):
            if row >= row_count:
                break
            if rec["direction"] != "RX" or rec["kind"] != "data":
                continue
            if pattern not in rec["data"]:
                continue
            self._apply_highlight(row, rec, trigger_name, trigger_color)
            count += 1
        return count

    def clear_trigger_highlights(self, trigger_name: str) -> None:
        """Remove all highlight marks set by *trigger_name* from every row.

        Called when a trigger is stopped so its tint is removed immediately.
        Rows matched by a different (still-active) trigger are not touched;
        main_window re-applies the still-active triggers after calling this.
        """
        row_count = self._table.rowCount()
        for row, rec in enumerate(self._records):
            if row >= row_count:
                break
            if rec.get("trigger_name") != trigger_name:
                continue
            # Clear the highlight role and tooltip on every cell of this row.
            for col in range(self._table.columnCount()):
                item = self._table.item(row, col)
                if item is None:
                    continue
                item.setData(_HIGHLIGHT_ROLE, None)
                item.setToolTip("")
            rec.pop("trigger_color", None)
            rec.pop("trigger_name", None)

    # ------------------------------------------------------------------
    # Sequence running highlights
    # ------------------------------------------------------------------

    def set_mixed_layers(self, layers: list[str]) -> None:
        """Update the columns shown in MIXED mode.

        Because every row's data is always pre-rendered in all four columns,
        this is instant — only column visibility changes, no re-render needed.
        """
        valid = [l for l in layers if l in ("hex", "ascii", "dec", "bin")]
        self._mixed_layers = valid if valid else ["hex", "ascii"]
        if self._mode == _MODE_MIXED:
            self._apply_mode_columns()

    def add_sequence_highlight(self, seq_id: str, pattern: bytes, color: str) -> None:
        """Highlight every RX row whose data matches *pattern* while the
        sequence is running.  New rows are highlighted as they arrive.
        """
        if not pattern:
            return
        self._seq_highlights[seq_id] = (pattern, color)
        # Retroactively tint rows already in the table
        row_count = self._table.rowCount()
        for row, rec in enumerate(self._records):
            if row >= row_count:
                break
            if rec["direction"] == "RX" and rec["kind"] == "data":
                if pattern in rec["data"]:
                    self._apply_seq_highlight(row, color)

    def remove_sequence_highlight(self, seq_id: str) -> None:
        """Remove a sequence's highlight rule and clear its tints from the table."""
        if seq_id not in self._seq_highlights:
            return
        del self._seq_highlights[seq_id]
        # Re-render so the removed tint disappears (trigger tints stay intact).
        self._rerender_all()

    def _apply_seq_highlight(self, row: int, color: str) -> None:
        soft = self._soft_bg(color)
        for col in range(self._table.columnCount()):
            item = self._table.item(row, col)
            if item is not None:
                item.setData(_SEQ_ROLE, soft)

    def _soft_bg(self, accent_hex: str) -> QColor:
        """Blend ``accent_hex`` toward the panel background.

        Mix ratios are chosen so the tint is clearly visible but the existing
        monochrome text (green RX / blue TX) stays readable on both themes.
        Falls back to the style's trigger-highlight color if accent is empty.
        """
        if not accent_hex:
            accent_hex = self._resolved_style().trigger_highlight_color or "#f9e2af"
        try:
            accent = QColor(accent_hex)
        except Exception:
            accent = QColor("#f9e2af")
        if self._is_dark:
            base = QColor("#1e1e2e")
            mix = 0.50
        else:
            base = QColor("#ffffff")
            mix = 0.65
        r = int(base.red() * (1 - mix) + accent.red() * mix)
        g = int(base.green() * (1 - mix) + accent.green() * mix)
        b = int(base.blue() * (1 - mix) + accent.blue() * mix)
        return QColor(r, g, b)

    def clear(self) -> None:
        self._records.clear()
        self._buffer.clear()
        self._pending.clear()
        self._table.setRowCount(0)
        self._total_appended = 0
        self._next_index = 1
        self._start_mono = time.perf_counter()
        self._find_rows = []
        self._find_idx = -1
        self._find_count_lbl.setText("")
        self._update_count()

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        resolved = self._style.resolve(is_dark)
        self._apply_bg_style(resolved.bg_color)
        self._rerender_all()

    def set_paused(self, paused: bool) -> None:
        """Pause/resume the live feed.

        On resume we don't dump every buffered chunk synchronously — that
        used to freeze the UI for several seconds when thousands of chunks
        accumulated during a long pause. Instead we splice the buffered
        chunks onto the front of the pending queue and let the regular
        16 ms drain handle them in batches, exactly the same path the
        live feed uses.
        """
        was_paused = self._paused
        self._paused = paused
        if was_paused and not paused and self._buffer:
            buffered = self._buffer
            self._buffer = []
            # Prepend buffered chunks (oldest first) ahead of any live chunks
            # that may already be queued for the next drain.
            self._pending = buffered + self._pending
            if not self._drain_scheduled:
                self._drain_scheduled = True
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(0, self._drain_pending)
            self._maybe_scroll()

    # ------------------------------------------------------------------
    # Record handling
    # ------------------------------------------------------------------

    def _add_record(self, direction: str, data: bytes, ts: float, kind: str,
                    text: str = "", channel: str = "") -> None:
        """Build a record and queue it for the next batched drain (~60 FPS).

        Coalescing rationale — calling ``QTableWidget.insertRow`` once per
        incoming chunk on the UI thread melts down under multi-port load:
        in multiline mode every insert forces a re-measure of every visible
        row, so 5 ports each emitting 50 chunks/sec used to drop the UI to
        single-digit FPS. We now buffer chunks for one 16 ms tick and apply
        all the inserts in one ``setUpdatesEnabled(False)`` batch.
        """
        try:
            now = datetime.now()
            wall = now.strftime("%H:%M:%S.") + f"{now.microsecond // 1000:03d}"
            # ``data`` is already an immutable bytes from the protocol layer
            # (pyserial.read, QTcpSocket.readAll, QLocalSocket.readAll all
            # return fresh bytes). Calling ``bytes(data)`` again was a
            # wasted copy that added up at high RX rates.
            rec = {
                "idx": self._next_index,
                "ts": ts,
                "t_mono": time.perf_counter(),
                "wall": wall,
                "direction": direction,
                "data": data if isinstance(data, bytes) else bytes(data),
                "kind": kind,
                "text": text,
                "channel": channel,
            }
            self._next_index += 1
            self._total_appended += 1

            if self._paused:
                self._buffer.append(rec)
                self._update_count()
                return

            self._pending.append(rec)
            if not self._drain_scheduled:
                self._drain_scheduled = True
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(16, self._drain_pending)
        except Exception as exc:  # never let a formatting error crash the UI
            self._safe_error(f"Terminal render error: {exc}")

    # Maximum number of records to insert per UI frame. Tuned so a frame stays
    # comfortably under 16 ms even with multi-line cells; larger backlogs are
    # processed across multiple frames so the UI never hangs.
    _DRAIN_CHUNK = 500

    def _drain_pending(self) -> None:
        """Insert pending records into the table — at most ``_DRAIN_CHUNK`` per tick.

        If more records are queued than fit in one chunk (e.g. after a long
        pause), the rest are processed by re-scheduling the drain for the
        next event-loop tick. This keeps the UI responsive even when 50 000
        chunks need to land.
        """
        self._drain_scheduled = False
        if not self._pending:
            return

        # Slice out at most _DRAIN_CHUNK records for this frame; leave the
        # remainder in self._pending so the next tick picks them up.
        if len(self._pending) > self._DRAIN_CHUNK:
            batch = self._pending[:self._DRAIN_CHUNK]
            self._pending = self._pending[self._DRAIN_CHUNK:]
            more_to_drain = True
        else:
            batch = self._pending
            self._pending = []
            more_to_drain = False

        # One repaint at the end of the batch instead of one per insert.
        first_new_row = self._table.rowCount()
        self._table.setUpdatesEnabled(False)
        try:
            for rec in batch:
                self._records.append(rec)
                self._insert_row(rec)
                # Apply any active sequence highlights to the new row
                if (
                    rec["direction"] == "RX"
                    and rec["kind"] == "data"
                    and self._seq_highlights
                ):
                    row = self._table.rowCount() - 1
                    for _sid, (pattern, hl_color) in self._seq_highlights.items():
                        if pattern in rec["data"]:
                            self._apply_seq_highlight(row, hl_color)
                            break
            # Single cap-enforcement per batch (was O(N²) when called per row).
            self._enforce_cap()
        except Exception as exc:
            self._safe_error(f"Terminal batch render error: {exc}")
        finally:
            self._table.setUpdatesEnabled(True)

        # Incremental filter — only re-check the rows we just added (or
        # adjusted indices for after _enforce_cap removed old rows).
        new_count = self._table.rowCount()
        if first_new_row < new_count and self._filter_text:
            # After cap-enforcement the new rows may have shifted up.
            start = max(0, new_count - len(batch))
            self._apply_filter(only_rows=range(start, new_count))
        self._update_count()
        self._maybe_scroll()

        # If more chunks remain (large backlog from resume), schedule another
        # drain so the UI gets a chance to repaint between batches.
        if more_to_drain and not self._drain_scheduled:
            self._drain_scheduled = True
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, self._drain_pending)

    def _safe_error(self, msg: str) -> None:
        try:
            now = datetime.now()
            wall = now.strftime("%H:%M:%S.000")
            rec = {
                "idx": self._next_index,
                "ts": 0.0,
                "t_mono": time.perf_counter(),
                "wall": wall,
                "direction": "!!",
                "data": msg.encode("utf-8", "replace"),
                "kind": "error",
                "text": msg,
                "channel": "",
            }
            self._next_index += 1
            self._records.append(rec)
            self._insert_row(rec)
        except Exception:
            pass

    def _enforce_cap(self) -> None:
        overflow = len(self._records) - _MAX_ROWS
        if overflow > 0:
            del self._records[:overflow]
            for _ in range(overflow):
                if self._table.rowCount() > 0:
                    self._table.removeRow(0)

    # ------------------------------------------------------------------
    # Style API
    # ------------------------------------------------------------------

    def apply_style(self, style: TerminalStyle) -> None:
        """Apply a new TerminalStyle and re-render all rows."""
        self._style = style
        resolved = style.resolve(self._is_dark)
        # Font
        self._mono = QFont(resolved.font_family or "Cascadia Code")
        self._mono.setStyleHint(QFont.StyleHint.Monospace)
        self._mono.setPointSize(max(7, resolved.font_size))
        # Invalidate the per-row height cache; recomputed lazily on next insert.
        self._cached_line_h = 0
        # Timestamp format
        fmt = resolved.timestamp_format or "wall"
        self._ts_format = fmt
        idx = self._ts_combo.findText(fmt.capitalize())
        if idx >= 0:
            self._ts_combo.blockSignals(True)
            self._ts_combo.setCurrentIndex(idx)
            self._ts_combo.blockSignals(False)
        self._table.setColumnHidden(self.COL_TIME, fmt == "none")
        # ASCII rendering mode — "multiline" (default, Docklight-style),
        # "ctrl" (visible <CR>/<LF> tags), or "escape" (legacy \r\n literals).
        self._show_ctrl_chars = getattr(resolved, "show_ctrl_chars", False)
        self._ascii_render = getattr(resolved, "ascii_render", "multiline")
        if self._ascii_render not in ("multiline", "ctrl", "escape"):
            self._ascii_render = "multiline"
        # Word-wrap is enabled for both single-line escape mode and multi-line.
        # We always keep the vertical header in *Fixed* mode and set each row's
        # height MANUALLY in ``_populate_row`` — Qt's ``ResizeToContents``
        # mode re-measures every visible row on every insert, which is O(N)
        # per insert and freezes the UI under flood load.
        is_multiline = self._ascii_render == "multiline"
        self._table.setWordWrap(is_multiline)
        vh = self._table.verticalHeader()
        vh.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        vh.setDefaultSectionSize(22)
        # Background color override via inline stylesheet (beats QSS file)
        self._apply_bg_style(resolved.bg_color)
        self._rerender_all()

    def _apply_bg_style(self, bg_color: str) -> None:
        """Push background color onto the table via an inline stylesheet."""
        defaults = theme_defaults(self._is_dark)
        bg = bg_color or defaults["bg_color"]
        alt = defaults["alt_bg_color"]
        self._table.setStyleSheet(
            f"QTableWidget {{ background-color: {bg}; "
            f"alternate-background-color: {alt}; }}"
        )

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _resolved_style(self) -> TerminalStyle:
        return self._style.resolve(self._is_dark)

    def _data_color(self, role: str) -> QColor:
        rs = self._resolved_style()
        theme = theme_defaults(self._is_dark)
        if role == "RX":
            return QColor(rs.rx_color or theme["rx_color"])
        if role == "TX":
            return QColor(rs.tx_color or theme["tx_color"])
        suffix = "dark" if self._is_dark else "light"
        if role == "info":
            return QColor(_INFO_COLOR[suffix])
        if role == "error":
            return QColor(_ERROR_COLOR[suffix])
        return QColor("#888888")

    def _badge_color(self, direction: str) -> QColor:
        theme = theme_defaults(self._is_dark)
        key = "rx_badge_color" if direction == "RX" else "tx_badge_color"
        return QColor(theme.get(key, "#888888"))

    def _muted_color(self) -> QColor:
        return QColor("#8b949e" if self._is_dark else "#656d76")

    def _insert_row(self, rec: dict) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._populate_row(row, rec)

    # Cached per-line pixel height for the current font — recomputed only
    # when ``apply_style`` runs. Avoids a QFontMetrics call per insert.
    def _line_height_px(self) -> int:
        from PyQt6.QtGui import QFontMetrics
        cached = getattr(self, "_cached_line_h", 0)
        if cached:
            return cached
        h = max(16, QFontMetrics(self._mono).lineSpacing() + 2)
        self._cached_line_h = h
        return h

    def _size_row_to_content(self, row: int, data: bytes) -> None:
        """Set row height based on number of line-breaks in the ASCII view.

        Cheap O(1) per row — counts byte 0x0A in the raw chunk. CR/LF pairs
        collapse to one line because :func:`_ascii_multiline` does the same.
        """
        # Count NL bytes; CRLF was already collapsed by the renderer.
        # Bytes are scanned in C, so this is fast even for 8 KB chunks.
        lines = data.count(b"\n") + max(1, data.count(b"\r") - data.count(b"\r\n"))
        if lines < 1:
            lines = 1
        # Clamp to a reasonable max so a single huge chunk can't make one
        # gigantic row that scrolls past the viewport edge.
        lines = min(lines, 50)
        self._table.setRowHeight(row, lines * self._line_height_px() + 4)

    def _populate_row(self, row: int, rec: dict) -> None:
        """Fill the visible columns of ``row`` with the formatted bytes.

        Mode-aware parsing — only the data columns currently *visible* for
        the active display mode are formatted. The hidden columns get
        cheap empty placeholders so column-index based highlighting still
        addresses every cell. This avoids wasting CPU on hex/dec/bin
        rendering when the user is viewing ASCII (and vice versa); on a
        high-baud port the savings are substantial.
        """
        kind = rec["kind"]
        direction = rec["direction"]
        data = rec["data"]

        # Column 0: index
        idx_item = QTableWidgetItem(f"#{rec['idx']}")
        idx_item.setForeground(QBrush(self._muted_color()))
        self._table.setItem(row, self.COL_INDEX, idx_item)

        # Column 1: timestamp
        time_item = QTableWidgetItem(self._format_time(rec, row))
        time_item.setFont(self._mono)
        time_item.setForeground(QBrush(self._muted_color()))
        self._table.setItem(row, self.COL_TIME, time_item)

        if kind in ("info", "error"):
            dir_item = QTableWidgetItem("")
            self._table.setItem(row, self.COL_DIR, dir_item)
            role = "info" if kind == "info" else "error"
            msg = rec.get("text") or _ascii_escaped(data)
            fg_brush = QBrush(self._data_color(role))
            # Status / connection / error messages need to be readable in
            # EVERY display mode (the user reported them being invisible in
            # ASCII / DEC / BIN). Put the same message string into every
            # data column so whichever one is visible shows it.
            for col in (self.COL_HEX, self.COL_ASCII, self.COL_DEC, self.COL_BIN):
                item = QTableWidgetItem(msg)
                item.setFont(self._mono)
                item.setForeground(fg_brush)
                self._table.setItem(row, col, item)
            return

        # Direction badge
        dir_item = QTableWidgetItem(direction)
        dir_font = QFont(self._mono)
        dir_font.setBold(True)
        dir_item.setFont(dir_font)
        dir_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        dir_item.setForeground(QBrush(self._data_color(direction)))
        self._table.setItem(row, self.COL_DIR, dir_item)

        fg = QBrush(self._data_color(direction))

        # Decide which columns are actually visible right now. Hidden columns
        # get an empty QTableWidgetItem so highlight/copy still has cells to
        # address, but we skip the expensive string formatting for them.
        visible = set(self._visible_data_cols) if self._visible_data_cols else {
            self.COL_HEX, self.COL_ASCII, self.COL_DEC, self.COL_BIN,
        }

        if self.COL_HEX in visible:
            it = QTableWidgetItem(_hex_str(data))
            it.setFont(self._mono); it.setForeground(fg)
            self._table.setItem(row, self.COL_HEX, it)
        else:
            self._table.setItem(row, self.COL_HEX, QTableWidgetItem(""))

        if self.COL_ASCII in visible:
            if self._ascii_render == "multiline":
                ascii_text = _ascii_multiline(data)
            elif self._ascii_render == "ctrl" or self._show_ctrl_chars:
                ascii_text = _ascii_with_ctrl(data)
            else:
                ascii_text = _ascii_escaped(data)
            it = QTableWidgetItem(ascii_text)
            it.setFont(self._mono); it.setForeground(fg)
            self._table.setItem(row, self.COL_ASCII, it)
        else:
            self._table.setItem(row, self.COL_ASCII, QTableWidgetItem(""))

        if self.COL_DEC in visible:
            it = QTableWidgetItem(_dec_str(data))
            it.setFont(self._mono); it.setForeground(fg)
            self._table.setItem(row, self.COL_DEC, it)
        else:
            self._table.setItem(row, self.COL_DEC, QTableWidgetItem(""))

        if self.COL_BIN in visible:
            it = QTableWidgetItem(_bin_str(data))
            it.setFont(self._mono); it.setForeground(fg)
            self._table.setItem(row, self.COL_BIN, it)
        else:
            self._table.setItem(row, self.COL_BIN, QTableWidgetItem(""))

        # Manual per-row height in multiline mode — O(1) per insert vs O(N)
        # for Qt's ResizeToContents. We count newlines in whichever data
        # column is visible (almost always ASCII) and pick the tallest.
        if self._ascii_render == "multiline":
            self._size_row_to_content(row, data)

        # Channel column (tap mode only — shows "A" or "B" and tints the row)
        ch = rec.get("channel", "")
        ch_item = QTableWidgetItem(ch)
        ch_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if ch:
            ch_item.setFont(dir_font)
            ch_item.setForeground(QBrush(QColor("#ffffff")))
            ch_color = (
                QColor("#1d6fa4") if ch == "A" else QColor("#1a8a4a")
            )
            ch_item.setBackground(QBrush(ch_color))
        self._table.setItem(row, self.COL_CHANNEL, ch_item)

        # Apply channel tint to all cells of the row (lowest-priority background)
        if ch:
            if ch == "A":
                tint = _CHANNEL_A_DARK if self._is_dark else _CHANNEL_A_LIGHT
            else:
                tint = _CHANNEL_B_DARK if self._is_dark else _CHANNEL_B_LIGHT
            for col in range(self._table.columnCount()):
                item = self._table.item(row, col)
                if item is not None:
                    item.setData(_CHANNEL_ROLE, tint)

    def _rerender_all(self) -> None:
        self._table.setRowCount(0)
        for rec in self._records:
            self._insert_row(rec)
            row = self._table.rowCount() - 1
            # Re-apply trigger tint (color is recomputed for the new theme).
            color = rec.get("trigger_color")
            if color:
                self._apply_highlight(row, rec, rec.get("trigger_name", ""), color)
            # Re-apply sequence highlight (lower priority — trigger wins if both match).
            if rec["direction"] == "RX" and rec["kind"] == "data" and self._seq_highlights:
                for _sid, (pattern, hl_color) in self._seq_highlights.items():
                    if pattern in rec["data"]:
                        self._apply_seq_highlight(row, hl_color)
                        break
        self._apply_filter()
        self._maybe_scroll()

    # ------------------------------------------------------------------
    # Filtering / scrolling / count
    # ------------------------------------------------------------------

    def _row_matches(self, rec: dict) -> bool:
        """Delegate to the shared DSL helper so the log writer behaves identically."""
        from kcom.core.filter import matches_filter
        return matches_filter(
            rec["data"], rec["direction"], self._filter_text,
            kind=rec["kind"], text=rec.get("text") or "",
        )

    def _apply_filter(self, only_rows: range | None = None) -> None:
        """Apply the current filter to every row, or only to a slice.

        Performance — when no filter is set this is a tight no-op (all rows
        are visible by default, so nothing to hide). When a filter IS set
        and we know which rows are new, we can pass ``only_rows`` to skip
        re-evaluating thousands of already-classified rows.
        """
        if not self._filter_text:
            return
        rows = only_rows if only_rows is not None else range(len(self._records))
        for row in rows:
            if 0 <= row < len(self._records):
                rec = self._records[row]
                self._table.setRowHidden(row, not self._row_matches(rec))

    def _on_filter_changed(self, text: str) -> None:
        new_filter = text.strip()
        had_filter = bool(self._filter_text)
        self._filter_text = new_filter
        # When filter is cleared, un-hide every row in one pass; otherwise
        # apply the new filter to every row.
        if not new_filter and had_filter:
            for row in range(len(self._records)):
                self._table.setRowHidden(row, False)
        else:
            self._apply_filter()
        # Notify listeners (the active LogManager mirrors the filter so the
        # logged data matches what's on screen).
        self.filter_changed.emit(new_filter)

    def filter_text(self) -> str:
        """Return the currently-active filter DSL (empty string = no filter)."""
        return self._filter_text

    def _on_scroll_toggled(self, checked: bool) -> None:
        self._auto_scroll = checked
        if checked:
            self._table.scrollToBottom()

    def _maybe_scroll(self) -> None:
        if self._auto_scroll:
            self._table.scrollToBottom()

    def _update_count(self) -> None:
        self._msg_count.setText(f"{self._total_appended} msgs")

    # ------------------------------------------------------------------
    # Per-session logging
    # ------------------------------------------------------------------

    def _on_pause_toggled(self, checked: bool) -> None:
        self.set_paused(checked)
        if checked:
            self._pause_btn.setText("▶ Resume")
            self._pause_btn.setToolTip(
                f"Paused — {len(self._buffer)} messages buffered. Click to resume."
            )
        else:
            count = len(self._buffer)
            self._pause_btn.setText("⏸ Pause")
            self._pause_btn.setToolTip("Freeze the live view (buffer new data)")
            if count:
                self.append_info(f"Resumed — flushed {count} buffered messages")

    def _on_log_toggled(self, checked: bool) -> None:
        if checked:
            self.log_start_requested.emit()
        else:
            self.log_stop_requested.emit()

    def set_log_active(self, path: str) -> None:
        self._is_logging = True
        self._log_btn.blockSignals(True)
        self._log_btn.setChecked(True)
        self._log_btn.blockSignals(False)
        self._log_btn.setText("Log: ON")
        self._log_btn.setToolTip(
            f"Logging active\nFile: {os.path.basename(path)}\nClick to stop logging."
        )
        self._log_btn.setStyleSheet(
            "QPushButton { background: #1f883d; color: #ffffff; border-radius: 4px; }"
        )

    def set_log_stopped(self) -> None:
        self._is_logging = False
        self._log_btn.blockSignals(True)
        self._log_btn.setChecked(False)
        self._log_btn.blockSignals(False)
        self._log_btn.setText("Log: Off")
        self._log_btn.setToolTip(
            "Log: Off — click to start saving received/sent data to a file.\n"
            "The log file is created automatically in your home folder."
        )
        self._log_btn.setStyleSheet("")

    # ------------------------------------------------------------------
    # Snapshot capture
    # ------------------------------------------------------------------

    def save_snapshot(self, window_lines: int = 50) -> None:
        """Save the last *window_lines* terminal records to a text file."""
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        default = f"kcom-snapshot-{ts}.txt"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Snapshot", default, "Text files (*.txt);;All files (*)"
        )
        if not path:
            return
        records = self._records[-window_lines:]
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(f"# KCom Snapshot — {datetime.now().isoformat(timespec='seconds')}\n")
                fh.write(f"# Last {len(records)} records\n\n")
                for rec in records:
                    if rec["kind"] in ("info", "error"):
                        tag = "INFO" if rec["kind"] == "info" else "ERROR"
                        msg = rec.get("text") or _ascii_escaped(rec["data"])
                        fh.write(f"#{rec['idx']}  {rec['wall']}  {tag}  {msg}\n")
                    else:
                        data = rec["data"]
                        fh.write(
                            f"#{rec['idx']}  {rec['wall']}  {rec['direction']}  "
                            f"{_hex_str(data)}  |{_ascii_sidebar(data)}|\n"
                        )
            self.append_info(f"Snapshot saved → {path}")
        except OSError as exc:
            self.append_error(f"Snapshot failed: {exc}")

    # ------------------------------------------------------------------
    # Timestamp formatting
    # ------------------------------------------------------------------

    def _format_time(self, rec: dict, row_idx: int) -> str:
        fmt = self._ts_format
        if fmt == "none":
            return ""
        if fmt == "wall":
            return rec["wall"]
        t = rec["t_mono"]
        if fmt == "elapsed":
            ms = (t - self._start_mono) * 1000
            return f"{ms:,.0f} ms"
        if fmt == "delta":
            if row_idx == 0 or not self._records:
                return "0 ms"
            prev_t = self._records[row_idx - 1]["t_mono"] if row_idx < len(self._records) else t
            delta_ms = (t - prev_t) * 1000
            return f"+{delta_ms:.0f} ms"
        return rec["wall"]

    def _on_ts_format_changed(self, text: str) -> None:
        self._ts_format = text.lower()
        self._table.setColumnHidden(self.COL_TIME, self._ts_format == "none")
        self._rerender_all()

    # ------------------------------------------------------------------
    # Find bar
    # ------------------------------------------------------------------

    def _show_find_bar(self) -> None:
        self._find_bar.show()
        self._find_input.setFocus()
        self._find_input.selectAll()

    def _hide_find_bar(self) -> None:
        self._clear_find_highlights()
        self._find_bar.hide()
        self._table.clearSelection()

    def _on_find_text_changed(self, _: object = None) -> None:
        self._run_find()

    def _run_find(self) -> None:
        self._clear_find_highlights()
        text = self._find_input.text().strip()
        if not text:
            self._find_count_lbl.setText("")
            return

        is_hex = self._find_fmt_combo.currentText() == "Hex"
        try:
            if is_hex:
                needle = bytes.fromhex(text.replace(" ", ""))
            else:
                needle = text.lower().encode("utf-8", "replace")
        except ValueError:
            self._find_count_lbl.setText("bad hex")
            return

        amber = self._find_amber()
        self._find_rows = []
        row_count = self._table.rowCount()
        for row, rec in enumerate(self._records):
            if row >= row_count:
                break
            haystack = rec["data"] if is_hex else rec["data"].lower()
            if needle in haystack:
                self._find_rows.append(row)
                for col in range(self._table.columnCount()):
                    item = self._table.item(row, col)
                    if item:
                        item.setData(_FIND_ROLE, amber)

        total = len(self._find_rows)
        if total == 0:
            self._find_count_lbl.setText("no matches")
            self._find_idx = -1
        else:
            self._find_idx = 0
            self._scroll_to_find(self._find_idx)
            self._find_count_lbl.setText(f"1/{total}")

    def _find_next(self) -> None:
        if not self._find_rows:
            self._run_find()
            return
        self._find_idx = (self._find_idx + 1) % len(self._find_rows)
        self._scroll_to_find(self._find_idx)
        self._find_count_lbl.setText(f"{self._find_idx + 1}/{len(self._find_rows)}")

    def _find_prev(self) -> None:
        if not self._find_rows:
            self._run_find()
            return
        self._find_idx = (self._find_idx - 1) % len(self._find_rows)
        self._scroll_to_find(self._find_idx)
        self._find_count_lbl.setText(f"{self._find_idx + 1}/{len(self._find_rows)}")

    def _scroll_to_find(self, idx: int) -> None:
        row = self._find_rows[idx]
        self._table.selectRow(row)
        self._table.scrollTo(
            self._table.model().index(row, 0),
            QAbstractItemView.ScrollHint.PositionAtCenter,
        )

    def _clear_find_highlights(self) -> None:
        for row in self._find_rows:
            row_count = self._table.rowCount()
            if row >= row_count:
                continue
            for col in range(self._table.columnCount()):
                item = self._table.item(row, col)
                if item:
                    item.setData(_FIND_ROLE, None)
        self._find_rows = []
        self._find_idx = -1

    def _find_amber(self) -> QColor:
        if self._is_dark:
            return QColor("#4a3800")
        return QColor("#fff3cd")

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Excel / CSV copy
    # ------------------------------------------------------------------

    def _copy_selection_tsv(self) -> None:
        """Copy selected cells as tab-separated values — pastes into Excel / Sheets."""
        self._copy_selection(separator="\t", include_headers=False)

    def _copy_selection_csv(self) -> None:
        """Copy selected cells as RFC-4180 CSV."""
        self._copy_selection(separator=",", include_headers=False)

    def _copy_selection_tsv_headers(self) -> None:
        self._copy_selection(separator="\t", include_headers=True)

    def _copy_selection(self, separator: str = "\t", include_headers: bool = False) -> None:
        indexes = self._table.selectedIndexes()
        if not indexes:
            return

        # Build row→{col→text} map, skipping hidden columns
        from collections import defaultdict
        cell_map: dict[int, dict[int, str]] = defaultdict(dict)
        for idx in indexes:
            col = idx.column()
            if self._table.isColumnHidden(col):
                continue
            cell_map[idx.row()][col] = idx.data() or ""

        if not cell_map:
            return

        # Determine the ordered list of visible columns actually selected
        all_cols = sorted({c for row in cell_map.values() for c in row})

        def _cell(text: str) -> str:
            if separator == ",":
                if any(ch in text for ch in (',', '"', '\n', '\r')):
                    return '"' + text.replace('"', '""') + '"'
            return text

        lines: list[str] = []

        if include_headers:
            headers = [
                self._table.horizontalHeaderItem(c).text() if self._table.horizontalHeaderItem(c) else ""
                for c in all_cols
            ]
            lines.append(separator.join(_cell(h) for h in headers))

        for row in sorted(cell_map):
            row_data = cell_map[row]
            lines.append(separator.join(_cell(row_data.get(c, "")) for c in all_cols))

        QApplication.clipboard().setText("\n".join(lines))

    def _on_context_menu(self, pos) -> None:
        indexes = self._table.selectedIndexes()
        rows = sorted({idx.row() for idx in indexes})
        has_selection = bool(indexes)
        menu = QMenu(self)

        # --- Table / spreadsheet copy ---
        copy_tsv     = menu.addAction("Copy as Table  (Ctrl+C — paste into Excel / Sheets)")
        copy_csv     = menu.addAction("Copy as CSV")
        copy_tsv_hdr = menu.addAction("Copy as Table with Headers")
        copy_tsv.setEnabled(has_selection)
        copy_csv.setEnabled(has_selection)
        copy_tsv_hdr.setEnabled(has_selection)
        menu.addSeparator()

        # --- Raw byte copy ---
        copy_hex   = menu.addAction("Copy Raw — Hex")
        copy_ascii = menu.addAction("Copy Raw — ASCII")
        copy_bytes = menu.addAction("Copy Raw — Compact Hex")
        menu.addSeparator()

        # --- Create actions (single data row only) ---
        create_trigger  = menu.addAction("Create RX Trigger from pattern…")
        create_sequence = menu.addAction("Create TX Sequence from data…")
        menu.addSeparator()

        # --- Log helpers ---
        annotate_act = menu.addAction("Insert Annotation…")
        snapshot_act = menu.addAction("Save Snapshot (last 50 rows)…")
        annotate_act.setEnabled(self._is_logging)

        single_data_row = (
            len(rows) == 1
            and rows[0] < len(self._records)
            and self._records[rows[0]]["kind"] == "data"
        )
        create_trigger.setEnabled(single_data_row)
        create_sequence.setEnabled(single_data_row)

        action = menu.exec(self._table.viewport().mapToGlobal(pos))
        if action is None:
            return

        if action == copy_tsv:
            self._copy_selection_tsv()
            return
        if action == copy_csv:
            self._copy_selection_csv()
            return
        if action == copy_tsv_hdr:
            self._copy_selection_tsv_headers()
            return

        selected_data = b"".join(
            self._records[r]["data"]
            for r in rows
            if r < len(self._records) and self._records[r]["kind"] == "data"
        )

        if action == copy_hex:
            QApplication.clipboard().setText(_hex_str(selected_data))
        elif action == copy_ascii:
            QApplication.clipboard().setText(_ascii_escaped(selected_data))
        elif action == copy_bytes:
            QApplication.clipboard().setText(selected_data.hex())
        elif action == create_trigger:
            self.create_trigger_requested.emit(self._records[rows[0]]["data"])
        elif action == create_sequence:
            self.create_sequence_requested.emit(self._records[rows[0]]["data"])
        elif action == annotate_act:
            text, ok = QInputDialog.getText(self, "Insert Annotation", "Annotation text:")
            if ok and text.strip():
                self.annotation_requested.emit(text.strip())
        elif action == snapshot_act:
            self.save_snapshot()

    # ------------------------------------------------------------------
    # Mode segmented control
    # ------------------------------------------------------------------

    def _on_mode_clicked(self, mode: str) -> None:
        if mode == self._mode:
            return
        self._mode = mode
        for m, btn in self._seg_buttons.items():
            btn.setProperty("active", m == mode)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._apply_mode_columns()
        self._rerender_all()
        # Notify listeners (LogManager subscribes so log columns match the screen)
        self.display_mode_changed.emit(self._mode)

    def display_mode(self) -> str:
        """Return the current display mode (``ASCII`` / ``HEX`` / ``DEC`` / ``BIN`` / ``MIXED``)."""
        return self._mode

    def _apply_mode_columns(self) -> None:
        """Show the appropriate data columns for the current mode.

        Non-MIXED: exactly one data column is visible (the one matching the mode).
        MIXED:     the user-selected layer columns are all visible side-by-side.
        The last visible data column always stretches; others use Interactive width.
        """
        _LAYER_TO_COL = {
            "hex":   self.COL_HEX,
            "ascii": self.COL_ASCII,
            "dec":   self.COL_DEC,
            "bin":   self.COL_BIN,
        }
        _ALL_DATA_COLS = [self.COL_HEX, self.COL_ASCII, self.COL_DEC, self.COL_BIN]

        if self._mode == _MODE_MIXED:
            visible = [_LAYER_TO_COL[l] for l in self._mixed_layers if l in _LAYER_TO_COL]
            if not visible:
                visible = [self.COL_HEX]
        elif self._mode == _MODE_ASCII:
            visible = [self.COL_ASCII]
        elif self._mode == _MODE_DEC:
            visible = [self.COL_DEC]
        elif self._mode == _MODE_BIN:
            visible = [self.COL_BIN]
        else:  # HEX
            visible = [self.COL_HEX]

        header = self._table.horizontalHeader()
        for col in _ALL_DATA_COLS:
            hidden = col not in visible
            self._table.setColumnHidden(col, hidden)
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        self._table.setColumnHidden(self.COL_CHANNEL, not self._tap_mode)
        self._visible_data_cols = visible

        # Auto-size fixed columns to content, then distribute data columns equally.
        # Deferred so the viewport has its final size after layout completes.
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self._init_column_widths)

    # Default widths (px) for the fixed metadata columns. Sized to comfortably
    # fit the column header text PLUS a few rows of representative content so
    # the user sees "#", "Time", and "Dir" clearly on an empty terminal.
    _DEFAULT_WIDTHS = {
        # COL_INDEX  — 6-digit message number with header "#"
        0: 50,
        # COL_TIME   — "HH:MM:SS.mmm" with a little padding
        1: 150,
        # COL_DIR    — "RX" / "TX"
        2: 30,
        # COL_CHANNEL — "A" / "B"
        7: 36,
    }

    def _init_column_widths(self) -> None:
        """Apply sensible default widths to fixed columns, then distribute data columns.

        Earlier versions called ``resizeColumnToContents`` on an empty table,
        which left ``#`` and ``Time`` collapsed to header-only width. Users
        reported these were unreadable. We now apply a hard-coded sensible
        default once (then the user can drag to taste — those drags are
        preserved by :meth:`_redistribute_columns`).
        """
        for col, width in self._DEFAULT_WIDTHS.items():
            if not self._table.isColumnHidden(col):
                # Only set the default if the user hasn't already widened it.
                if self._table.columnWidth(col) < width:
                    self._table.setColumnWidth(col, width)
        self._redistribute_columns()

    def _redistribute_columns(self) -> None:
        """Distribute visible data columns equally across the available viewport width."""
        visible = self._visible_data_cols
        if not visible:
            return
        _FIXED_COLS = [self.COL_INDEX, self.COL_TIME, self.COL_DIR, self.COL_CHANNEL]
        # Read current fixed-column widths without resizing them (preserves user adjustments)
        fixed_total = sum(
            self._table.columnWidth(c)
            for c in _FIXED_COLS
            if not self._table.isColumnHidden(c)
        )
        vp_width = self._table.viewport().width()
        available = vp_width - fixed_total
        if available <= 0:
            return
        per_col = max(60, available // len(visible))
        for col in visible:
            self._table.setColumnWidth(col, per_col)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _on_export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Terminal", "kcom-terminal.txt",
            "Text files (*.txt);;All files (*)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                for rec in self._records:
                    if rec["kind"] in ("info", "error"):
                        tag = "INFO" if rec["kind"] == "info" else "ERROR"
                        msg = rec.get("text") or _ascii_escaped(rec["data"])
                        fh.write(f"#{rec['idx']}  {rec['wall']}  {tag}  {msg}\n")
                    else:
                        data = rec["data"]
                        fh.write(
                            f"#{rec['idx']}  {rec['wall']}  {rec['direction']}  "
                            f"{_hex_str(data)}  |{_ascii_sidebar(data)}|\n"
                        )
            self.append_info(f"Exported to {path}")
        except OSError as exc:
            self.append_error(f"Export failed: {exc}")

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

    def _on_send(self) -> None:
        raw = self._send_input.text().strip()
        if not raw:
            return
        fmt = self._format_combo.currentText()
        try:
            if fmt == "Hex":
                data = hex_str_to_bytes(raw)
            else:
                data = raw.encode("utf-8", errors="replace")
        except ValueError as exc:
            self.append_error(f"Bad hex input: {exc}")
            return

        term_map = {"None": "none", "CR": "cr", "LF": "lf", "CR+LF": "crlf"}
        terminator = term_map.get(self._term_combo.currentText(), "none")
        data = apply_terminator(data, terminator)

        self.send_requested.emit(data)
        self._send_input.clear()
