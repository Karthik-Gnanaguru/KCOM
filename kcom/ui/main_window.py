"""Main application window."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal as Signal
from PyQt6.QtGui import QAction, QCloseEvent, QFont, QIcon, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QDialogButtonBox,
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QSpacerItem,
    QSplitter,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from kcom.ui.dialogs.base_dialog import CenteredDialog

from kcom.core.log_manager import LogManager, SessionLogger
from kcom.core.port_session import ConnectionStatus
from kcom.core.sequence_runner import SequenceRunner
from kcom.core.session_manager import SessionManager
from kcom.core.tap_session import TapSession
from kcom.ui.log_panel import LogPanel
from kcom.ui.port_panel import PortPanel
from kcom.ui.script_panel import ScriptPanel
from kcom.ui.sequence_panel import SequencePanel
from kcom.ui.trigger_panel import TriggerPanel
from kcom.ui.terminal_table import TerminalTable
from kcom.ui.doc_panel import DocPanel
from kcom.core.settings_store import SettingsStore
from kcom.scripting.runtime import ScriptRuntime
from kcom.utils.resources import logo_path


class _ExitConfirmDialog(CenteredDialog):
    """Confirmation dialog shown when closing KCom with active connections."""

    def __init__(self, n: int, names: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Exit KCom")
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(24, 20, 24, 16)

        conn_word = "connection" if n == 1 else "connections"
        heading = QLabel(
            f"There {'is' if n == 1 else 'are'} <b>{n}</b> active {conn_word}:"
        )
        heading.setWordWrap(True)
        layout.addWidget(heading)

        names_lbl = QLabel(names)
        names_lbl.setWordWrap(True)
        names_lbl.setStyleSheet("color: #7d8590; padding-left: 8px; font-size: 11px;")
        layout.addWidget(names_lbl)

        question = QLabel("Disconnect all and exit KCom?")
        question.setWordWrap(True)
        layout.addWidget(question)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No
        )
        buttons.button(QDialogButtonBox.StandardButton.No).setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class WelcomeWidget(QWidget):
    """Welcome tab shown on startup — quick-start guide + example project links."""

    new_connection_requested: Signal = Signal()
    open_example_requested: Signal = Signal(str)   # absolute file path

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("WelcomeWidget")
        self._build_ui()

    def _build_ui(self) -> None:
        import os
        from PyQt6.QtWidgets import (
            QHBoxLayout, QPushButton, QScrollArea, QVBoxLayout,
        )
        from PyQt6.QtCore import Qt

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(20)

        # ── Title ─────────────────────────────────────────────────────
        title = QLabel("Welcome to KCom")
        title.setStyleSheet(
            "font-size: 26px; font-weight: bold; color: #8250df; background: transparent;"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Professional Serial & Network Communication Studio  ·  v1.0")
        subtitle.setStyleSheet("font-size: 13px; color: #7d8590; background: transparent;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        # ── Quick-start ───────────────────────────────────────────────
        qs = QLabel(
            "<b>Quick start</b><br>"
            "1. Click <b>+ New Connection</b> (Ctrl+N)<br>"
            "2. Pick your port / baud rate and click OK<br>"
            "3. Incoming data appears colour-coded in the terminal<br><br>"
            "<b>Tips</b><br>"
            "• Display mode: ASCII / Hex / Mixed / DEC / BIN — button bar in the terminal<br>"
            "• Terminator: append CR, LF, or CR+LF from the send-bar combo<br>"
            "• Press <b>F1</b> anywhere for context-sensitive help<br>"
            "• Ctrl+Shift+/ → Keyboard Shortcuts reference"
        )
        qs.setWordWrap(True)
        qs.setStyleSheet(
            "font-size: 12px; padding: 16px;"
            "border: 1px solid #7d859033; border-radius: 6px;"
        )
        layout.addWidget(qs)

        # ── Action buttons ────────────────────────────────────────────
        btn_row = QHBoxLayout()
        connect_btn = QPushButton("  + New Connection")
        connect_btn.setToolTip("Open a new serial or network connection (Ctrl+N)")
        connect_btn.setStyleSheet(
            "font-size: 13px; padding: 8px 20px; font-weight: bold;"
            "background: #8250df; color: #ffffff; border-radius: 8px; border: none;"
        )
        connect_btn.clicked.connect(self.new_connection_requested)
        btn_row.addWidget(connect_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # ── Example projects ──────────────────────────────────────────
        examples_label = QLabel("<b>Example Projects</b>")
        examples_label.setStyleSheet("font-size: 13px; margin-top: 6px;")
        layout.addWidget(examples_label)

        _EXAMPLES = [
            (
                "loopback_test.kcom",
                "Loopback Test",
                "Serial loopback with Ping sequence and wildcard counter. "
                "PONG trigger included.",
                "#89b4fa",
            ),
            (
                "tcp_echo_client.kcom",
                "TCP Echo Client",
                "Connect to a TCP echo server (port 7). "
                "Includes Hello World and 10 Hz flood sequences.",
                "#a6e3a1",
            ),
            (
                "modbus_rtu_master.kcom",
                "Modbus RTU Master",
                "FC01 / FC03 / FC06 sequences with CRC-16 Modbus auto-appended. "
                "Exception trigger included.",
                "#f9e2af",
            ),
        ]

        _examples_dir = os.path.normpath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "examples")
        )

        examples_grid = QHBoxLayout()
        examples_grid.setSpacing(12)
        for fname, ex_title, ex_desc, colour in _EXAMPLES:
            path = os.path.join(_examples_dir, fname)
            tile = QWidget()
            tile.setToolTip(f"Load example: {fname}")
            tile.setStyleSheet(
                f"QWidget {{ background: {colour}18; border: 1px solid {colour}66; "
                f"border-radius: 8px; }}"
                f"QWidget:hover {{ background: {colour}30; }}"
            )
            tile.setCursor(Qt.CursorShape.PointingHandCursor)
            tile_layout = QVBoxLayout(tile)
            tile_layout.setContentsMargins(12, 10, 12, 10)
            tile_layout.setSpacing(4)
            name_lbl = QLabel(f"<b style='color:{colour};'>{ex_title}</b>")
            name_lbl.setWordWrap(True)
            tile_layout.addWidget(name_lbl)
            desc_lbl = QLabel(ex_desc)
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet("font-size: 10px; color: #7d8590;")
            tile_layout.addWidget(desc_lbl)
            open_btn = QPushButton("Open →")
            open_btn.setStyleSheet(
                f"QPushButton {{ font-size: 10px; padding: 3px 8px; "
                f"background: {colour}40; border: 1px solid {colour}88; "
                f"border-radius: 4px; color: #cdd6f4; }}"
                f"QPushButton:hover {{ background: {colour}70; }}"
            )
            _path_capture = path
            open_btn.clicked.connect(
                lambda _chk=False, p=_path_capture: self.open_example_requested.emit(p)
            )
            open_btn.setToolTip(f"Load {fname}")
            tile_layout.addWidget(open_btn)
            examples_grid.addWidget(tile, stretch=1)

        layout.addLayout(examples_grid)
        layout.addStretch()

        scroll.setWidget(inner)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)


class PortTab(QWidget):
    """A tab holding one connection's own structured terminal."""

    def __init__(self, session_id: str, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session_id = session_id

        from PyQt6.QtWidgets import QVBoxLayout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.terminal = TerminalTable()
        layout.addWidget(self.terminal)


class TapTab(QWidget):
    """A tab holding a combined tap/monitor terminal (two-port session)."""

    def __init__(self, tap_session_id: str, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tap_session_id = tap_session_id

        from PyQt6.QtWidgets import QVBoxLayout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.terminal = TerminalTable()
        self.terminal.enable_tap_mode()
        layout.addWidget(self.terminal)


class MainWindow(QMainWindow):
    """KCom main application window.

    Owns the tab widget, docks, menus, toolbar, and status bar.
    Delegates all connection logic to SessionManager.
    """

    def __init__(
        self,
        session_manager: SessionManager,
        theme_manager,
        settings: SettingsStore | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._session_manager = session_manager
        self._theme_manager = theme_manager
        self._settings = settings or SettingsStore()
        # session_id → PortTab
        self._port_tabs: dict[str, PortTab] = {}
        # tap_session_id → TapTab
        self._tap_tabs: dict[str, TapTab] = {}
        # All connections log to one ~/kcom-session.txt, overwritten each run.
        self._session_logger = SessionLogger(self._settings.get_log_path())
        self._session_logger.start_session("KCom")
        self._sequences: list = []     # shared TxSequence list

        # Python scripting runtime
        self._script_runtime = ScriptRuntime(self)

        # Per-sequence periodic senders. Multiple sequences can run at once;
        # each entry holds the runner plus the (session, data, name) it targets.
        self._runners: dict[str, dict] = {}

        # Load persisted terminal style (user color/font overrides).
        self._terminal_style = self._settings.get_terminal_style()

        self.setWindowTitle("KCom — Serial & Network Communication Studio")
        self.setWindowIcon(QIcon(logo_path()))
        self.resize(1280, 800)

        self._build_central_widget()
        self._build_menus()
        self._build_toolbar()
        self._build_status_bar()
        self._build_docks()
        self._connect_session_manager()

        # Show welcome tab
        self._add_welcome_tab()

        # Restore previous window geometry if available
        geom = self._settings.get_window_geometry()
        if geom:
            self.restoreGeometry(geom)

        # Once the window is visible, make serial ports accessible to the app.
        QTimer.singleShot(300, lambda: self._check_port_permissions(prompt=True))

        # Start HTTP API server if enabled in settings
        self._api_server: object | None = None
        if self._settings.get_api_enabled():
            QTimer.singleShot(500, self._start_api_server)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_central_widget(self) -> None:
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.setMovable(True)
        self._tabs.tabCloseRequested.connect(self._on_tab_close_requested)
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self._tabs)

    def _build_menus(self) -> None:
        mb = self.menuBar()

        # --- File ---
        file_menu = mb.addMenu("&File")

        new_conn_action = QAction("&New Connection…", self)
        new_conn_action.setShortcut(QKeySequence("Ctrl+N"))
        new_conn_action.setStatusTip("Open a new port connection")
        new_conn_action.triggered.connect(self._on_new_connection)
        file_menu.addAction(new_conn_action)
        self._new_conn_action = new_conn_action

        file_menu.addSeparator()

        open_project_action = QAction("&Open Project…", self)
        open_project_action.setShortcut(QKeySequence("Ctrl+O"))
        open_project_action.triggered.connect(self._on_open_project)
        file_menu.addAction(open_project_action)

        save_project_action = QAction("&Save Project…", self)
        save_project_action.setShortcut(QKeySequence("Ctrl+S"))
        save_project_action.triggered.connect(self._on_save_project)
        file_menu.addAction(save_project_action)

        file_menu.addSeparator()

        export_session_action = QAction("&Export Session Data…", self)
        export_session_action.setShortcut(QKeySequence("Ctrl+E"))
        export_session_action.setStatusTip(
            "Export the captured session log to a file of your choice"
        )
        export_session_action.triggered.connect(self._on_export_session)
        file_menu.addAction(export_session_action)

        file_menu.addSeparator()

        self._recent_menu = file_menu.addMenu("Recent Projects")
        self._update_recent_menu()

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # --- View ---
        view_menu = mb.addMenu("&View")

        self._toggle_theme_action = QAction("Toggle Theme (Dark/Light)", self)
        self._toggle_theme_action.setShortcut(QKeySequence("Ctrl+T"))
        self._toggle_theme_action.triggered.connect(self._on_toggle_theme)
        view_menu.addAction(self._toggle_theme_action)

        fs_action = QAction("Full Screen", self)
        fs_action.setShortcut(QKeySequence("F11"))
        fs_action.setCheckable(True)
        fs_action.triggered.connect(self._on_toggle_fullscreen)
        view_menu.addAction(fs_action)
        self._fs_action = fs_action

        view_menu.addSeparator()

        self._toggle_port_panel_action = QAction("Port Panel", self)
        self._toggle_port_panel_action.setToolTip("Show/hide the port connections panel")
        self._toggle_port_panel_action.setCheckable(True)
        self._toggle_port_panel_action.setChecked(True)
        view_menu.addAction(self._toggle_port_panel_action)

        self._toggle_seq_panel_action = QAction("Sequences && Triggers Panel", self)
        self._toggle_seq_panel_action.setCheckable(True)
        self._toggle_seq_panel_action.setChecked(True)
        self._toggle_seq_panel_action.setToolTip("Show/hide TX Sequences and RX Triggers panel")
        view_menu.addAction(self._toggle_seq_panel_action)

        self._toggle_doc_panel_action = QAction("Documentation Panel", self)
        self._toggle_doc_panel_action.setCheckable(True)
        self._toggle_doc_panel_action.setChecked(True)
        self._toggle_doc_panel_action.setToolTip("Show/hide the documentation / notes panel")
        view_menu.addAction(self._toggle_doc_panel_action)

        self._toggle_log_panel_action = QAction("Log Panel", self)
        self._toggle_log_panel_action.setCheckable(True)
        self._toggle_log_panel_action.setChecked(True)
        self._toggle_log_panel_action.setToolTip("Show/hide the global session log panel")
        view_menu.addAction(self._toggle_log_panel_action)

        self._toggle_script_panel_action = QAction("Script Panel", self)
        self._toggle_script_panel_action.setCheckable(True)
        self._toggle_script_panel_action.setChecked(False)
        self._toggle_script_panel_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self._toggle_script_panel_action.setToolTip("Show/hide the Python script editor (Ctrl+Shift+S)")
        view_menu.addAction(self._toggle_script_panel_action)

        # --- Ports ---
        ports_menu = mb.addMenu("&Ports")

        ports_menu.addAction(new_conn_action)

        tap_conn_action = QAction("New &Tap Connection…", self)
        tap_conn_action.setShortcut(QKeySequence("Ctrl+Shift+T"))
        tap_conn_action.setStatusTip("Open a two-port tap / monitor session")
        tap_conn_action.triggered.connect(self._on_new_tap_connection)
        ports_menu.addAction(tap_conn_action)
        self._tap_conn_action = tap_conn_action

        self._connections_menu = ports_menu.addMenu("Saved Connections")
        self._refresh_connections_menu()

        close_conn_action = QAction("&Close Connection", self)
        close_conn_action.setShortcut(QKeySequence("Ctrl+W"))
        close_conn_action.setToolTip("Close the currently active connection tab (Ctrl+W)")
        close_conn_action.triggered.connect(self._on_close_current_connection)
        ports_menu.addAction(close_conn_action)

        ports_menu.addSeparator()

        clear_term_action = QAction("Clear Terminal", self)
        clear_term_action.setShortcut(QKeySequence("Ctrl+L"))
        clear_term_action.triggered.connect(self._on_clear_terminal)
        ports_menu.addAction(clear_term_action)

        # --- Tools ---
        tools_menu = mb.addMenu("&Tools")

        fix_perms_action = QAction("&Fix Port Permissions…", self)
        fix_perms_action.setStatusTip(
            "Grant this app read/write access to serial ports (asks for admin password)"
        )
        fix_perms_action.triggered.connect(lambda: self._check_port_permissions(prompt=True, manual=True))
        tools_menu.addAction(fix_perms_action)

        settings_action = QAction("&Settings…", self)
        settings_action.setShortcut(QKeySequence("Ctrl+,"))
        settings_action.triggered.connect(self._on_settings)
        tools_menu.addAction(settings_action)

        diagnostics_action = QAction("&Diagnostics…", self)
        diagnostics_action.setStatusTip(
            "Live snapshot of sessions, thread count, memory and queue depths"
        )
        diagnostics_action.triggered.connect(self._on_diagnostics)
        tools_menu.addAction(diagnostics_action)

        # --- Help ---
        help_menu = mb.addMenu("&Help")

        help_action = QAction("&Help…", self)
        help_action.setShortcut(QKeySequence("F1"))
        help_action.setToolTip("Open context-sensitive help (F1)")
        help_action.triggered.connect(self._on_show_help)
        help_menu.addAction(help_action)

        hotkeys_action = QAction("&Keyboard Shortcuts…", self)
        hotkeys_action.setShortcut(QKeySequence("Ctrl+Shift+/"))
        hotkeys_action.setToolTip("Show all keyboard shortcuts")
        hotkeys_action.triggered.connect(self._on_show_hotkeys)
        help_menu.addAction(hotkeys_action)

        help_menu.addSeparator()

        about_action = QAction("&About KCom", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main Toolbar")
        tb.setObjectName("mainToolbar")
        tb.setMovable(False)
        tb.setIconSize(QSize(18, 18))
        self.addToolBar(tb)

        # New connection
        new_act = QAction("＋ New", self)
        new_act.setToolTip("New connection (Ctrl+N)")
        new_act.triggered.connect(self._on_new_connection)
        tb.addAction(new_act)

        tb.addSeparator()

        # Connect/Disconnect toggle
        self._connect_action = QAction("Connect", self)
        self._connect_action.setToolTip("Connect/Disconnect current port")
        self._connect_action.setCheckable(False)
        self._connect_action.triggered.connect(self._on_toggle_connection)
        tb.addAction(self._connect_action)

        tb.addSeparator()

        # Clear terminal
        clear_act = QAction("Clear", self)
        clear_act.setToolTip("Clear terminal (Ctrl+L)")
        clear_act.triggered.connect(self._on_clear_terminal)
        tb.addAction(clear_act)

        tb.addSeparator()

        # Log start/stop
        self._log_action = QAction("Log: Off", self)
        self._log_action.setToolTip(
            "Log: Off — click to start recording all received/sent data to a file.\n"
            "The file is saved automatically in your home folder.\n"
            "Click again to stop logging."
        )
        self._log_action.setCheckable(True)
        self._log_action.triggered.connect(self._on_toggle_log)
        tb.addAction(self._log_action)

        tb.addSeparator()

        # Theme toggle
        theme_act = QAction("Theme", self)
        theme_act.setToolTip("Toggle Dark/Light theme (Ctrl+T)")
        theme_act.triggered.connect(self._on_toggle_theme)
        tb.addAction(theme_act)

    def _build_status_bar(self) -> None:
        sb = self.statusBar()

        self._status_port_label = QLabel("No connection")
        self._status_port_label.setMinimumWidth(160)
        sb.addWidget(self._status_port_label)

        self._status_sep1 = QLabel("|")
        self._status_sep1.setStyleSheet("color: #7d8590; background: transparent;")
        sb.addWidget(self._status_sep1)

        self._status_rx_label = QLabel("RX: 0 B")
        self._status_rx_label.setMinimumWidth(80)
        sb.addWidget(self._status_rx_label)

        self._status_tx_label = QLabel("TX: 0 B")
        self._status_tx_label.setMinimumWidth(80)
        sb.addWidget(self._status_tx_label)

        sb.addPermanentWidget(QLabel(f"KCom v1.0.0  |  Theme: {self._theme_manager.current}"))

    # Docks are movable and closable (minimize), but NOT floatable (no detach).
    _DOCK_FEATURES = (
        QDockWidget.DockWidgetFeature.DockWidgetMovable
        | QDockWidget.DockWidgetFeature.DockWidgetClosable
    )

    def _build_docks(self) -> None:
        # --- Port list panel (left dock) ---
        self._port_panel = PortPanel(self._session_manager)
        port_dock = QDockWidget("Ports", self)
        port_dock.setObjectName("portDock")
        port_dock.setWidget(self._port_panel)
        port_dock.setFeatures(self._DOCK_FEATURES)
        port_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        port_dock.setMinimumWidth(180)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, port_dock)
        self._port_dock = port_dock

        # Connect port panel signals
        self._port_panel.new_connection_requested.connect(self._on_new_connection)
        self._port_panel.port_selected.connect(self._on_port_panel_selection)
        self._port_panel.close_port_requested.connect(self._on_close_session)

        # --- Left dock: SequencePanel (top) + TriggerPanel (bottom) ---
        left_splitter = QSplitter(Qt.Orientation.Vertical)

        self._sequence_panel = SequencePanel()
        self._sequence_panel.send_requested.connect(self._on_send_sequence)
        self._sequence_panel.stop_requested.connect(self._on_stop_sequence)
        self._sequence_panel.sequences_changed.connect(self._on_sequences_changed)
        left_splitter.addWidget(self._sequence_panel)

        self._trigger_panel = TriggerPanel()
        self._trigger_panel.triggers_changed.connect(self._on_triggers_changed)
        self._trigger_panel.set_theme(self._theme_manager.current == "dark")
        left_splitter.addWidget(self._trigger_panel)
        left_splitter.setSizes([300, 200])

        seq_dock = QDockWidget("Sequences && Triggers", self)
        seq_dock.setObjectName("leftDock")
        seq_dock.setWidget(left_splitter)
        seq_dock.setFeatures(self._DOCK_FEATURES)
        seq_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        seq_dock.setMinimumWidth(200)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, seq_dock)
        self._seq_dock = seq_dock

        # --- Documentation panel (right dock, below sequences) ---
        self._doc_panel = DocPanel()
        doc_dock = QDockWidget("Documentation", self)
        doc_dock.setObjectName("docDock")
        doc_dock.setWidget(self._doc_panel)
        doc_dock.setFeatures(self._DOCK_FEATURES)
        doc_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, doc_dock)
        self._doc_dock = doc_dock

        # --- Log panel (bottom dock) ---
        self._log_panel = LogPanel()
        log_dock = QDockWidget("Log", self)
        log_dock.setObjectName("logDock")
        log_dock.setWidget(self._log_panel)
        log_dock.setFeatures(self._DOCK_FEATURES)
        log_dock.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.TopDockWidgetArea
        )
        log_dock.setMaximumHeight(160)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, log_dock)
        self._log_dock = log_dock

        # Connect log panel signals
        self._log_panel.log_start_requested.connect(self._on_log_start)
        self._log_panel.log_stop_requested.connect(self._on_log_stop)

        # --- Script panel (bottom dock, hidden by default) ---
        self._script_panel = ScriptPanel()
        script_dock = QDockWidget("Script", self)
        script_dock.setObjectName("scriptDock")
        script_dock.setWidget(self._script_panel)
        script_dock.setFeatures(self._DOCK_FEATURES)
        script_dock.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea
            | Qt.DockWidgetArea.TopDockWidgetArea
            | Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
        )
        script_dock.setMinimumHeight(200)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, script_dock)
        script_dock.hide()
        self._script_dock = script_dock

        # Wire ScriptPanel ↔ ScriptRuntime
        self._script_panel.run_requested.connect(
            lambda code, fname: self._script_runtime.run_script(code, fname)
        )
        self._script_panel.stop_requested.connect(self._script_runtime.stop)
        self._script_runtime.log_output.connect(self._script_panel.append_output)
        self._script_runtime.script_started.connect(self._script_panel.on_script_started)
        self._script_runtime.script_finished.connect(self._script_panel.on_script_finished)
        self._script_runtime.script_error.connect(self._script_panel.on_script_error)

        # Wire ScriptRuntime API signals → application effects
        self._script_runtime.api.send_requested.connect(self._on_script_send)
        self._script_runtime.api.logging_start_requested.connect(
            self._on_script_logging_start
        )
        self._script_runtime.api.logging_stop_requested.connect(
            self._on_script_logging_stop
        )
        self._script_runtime.api.exit_requested.connect(QApplication.quit)

        # --- Help browser dock (right side, hidden by default) ---
        from kcom.ui.help_browser import HelpBrowser
        self._help_browser = HelpBrowser(self)
        self._help_browser.setFeatures(self._DOCK_FEATURES)
        self._help_browser.setMinimumWidth(260)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._help_browser)
        self._help_browser.hide()

        # Wire dock visibility to View menu actions (minimize + restore)
        for action, dock in (
            (self._toggle_port_panel_action, port_dock),
            (self._toggle_seq_panel_action, seq_dock),
            (self._toggle_doc_panel_action, doc_dock),
            (self._toggle_log_panel_action, log_dock),
            (self._toggle_script_panel_action, script_dock),
        ):
            action.toggled.connect(dock.setVisible)
            dock.visibilityChanged.connect(action.setChecked)

    def _connect_session_manager(self) -> None:
        self._session_manager.session_opened.connect(self._on_session_opened)
        self._session_manager.session_closed.connect(self._on_session_closed)
        self._session_manager.session_error.connect(self._on_session_error)
        self._session_manager.session_status_changed.connect(self._on_session_status_changed)

    def _add_welcome_tab(self) -> None:
        welcome = WelcomeWidget()
        welcome.new_connection_requested.connect(self._on_new_connection)
        welcome.open_example_requested.connect(self._load_project)
        self._tabs.addTab(welcome, "Welcome")
        self._tabs.setTabsClosable(False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_port_tab(self, session) -> None:
        """Create a PortTab for the given session and add it to the tab widget."""
        if session.session_id in self._port_tabs:
            return

        title = session.config.display_name()
        tab = PortTab(session.session_id, title)
        is_dark = self._theme_manager.current == "dark"
        tab.terminal.set_theme(is_dark)
        tab.terminal.apply_style(self._terminal_style)
        tab.terminal.set_mixed_layers(self._settings.get_mixed_layers())
        self._port_tabs[session.session_id] = tab

        # Each connection keeps its own terminal; received bytes go only to it.
        session.data_received.connect(
            lambda data, ts, t=tab: t.terminal.append_rx(data, ts)
        )

        # Forward RX data to the script runtime (on_receive callbacks)
        session.data_received.connect(
            lambda data, ts: self._script_runtime.dispatch_receive(data, ts)
        )

        # Session logger: capture every RX byte
        session.data_received.connect(
            lambda data, ts, name=session.config.display_name(): self._session_logger.feed(name, data, "RX")
        )

        # Wire terminal send to session
        tab.terminal.send_requested.connect(
            lambda data, sid=session.session_id: self._on_terminal_send(sid, data)
        )

        # Wire session status and errors
        session.status_changed.connect(
            lambda sid, status, t=tab: self._on_session_tab_status(t, sid, status)
        )
        session.error_occurred.connect(
            lambda sid, msg, t=tab: t.terminal.append_error(msg)
        )
        session.stats_updated.connect(
            lambda sid: self._update_status_bar_stats(sid)
        )
        session.overflow_warning.connect(
            lambda sid, dropped, name=session.config.display_name():
                self._on_rx_overflow(name, dropped)
        )

        # Forward RX/TX data to the API server for WebSocket streaming
        session.data_received.connect(
            lambda data, ts, sid=session.session_id:
                self._api_push(sid, data, "rx")
        )

        # Context menu → "Create RX Trigger" / "Create TX Sequence"
        tab.terminal.create_trigger_requested.connect(
            self._on_create_trigger_from_bytes
        )
        tab.terminal.create_sequence_requested.connect(
            self._on_create_sequence_from_bytes
        )

        # Per-session logging
        tab.terminal.log_start_requested.connect(
            lambda sid=session.session_id: self._on_tab_log_start(sid)
        )
        tab.terminal.log_stop_requested.connect(
            lambda sid=session.session_id: self._on_tab_log_stop(sid)
        )
        # Keep the log-format columns in sync with the terminal display mode
        # (ASCII / HEX / DEC / BIN / MIXED) — so the log only writes what's on screen.
        tab.terminal.display_mode_changed.connect(
            lambda mode, lm=session.log_manager: lm.set_display_mode(mode)
        )
        # Seed the current mode so logging started later picks up the active mode.
        session.log_manager.set_display_mode(tab.terminal.display_mode())

        # Keep the LogManager's filter in lock-step with the terminal's filter
        # DSL — the user's "log only what's visible" requirement.
        tab.terminal.filter_changed.connect(
            lambda needle, lm=session.log_manager: lm.set_filter(needle)
        )
        session.log_manager.set_filter(tab.terminal.filter_text())
        session.log_manager.logging_started.connect(
            lambda path, t=tab: t.terminal.set_log_active(path)
        )
        session.log_manager.logging_stopped.connect(
            lambda _path, t=tab: t.terminal.set_log_stopped()
        )
        session.log_manager.error_occurred.connect(
            lambda msg, t=tab: (t.terminal.set_log_stopped(),
                                t.terminal.append_info(f"Log error: {msg}"))
        )

        # Annotation
        tab.terminal.annotation_requested.connect(
            lambda text, sid=session.session_id: self._on_annotation(sid, text)
        )

        # Break signal
        tab.terminal.send_break_requested.connect(
            lambda sid=session.session_id: self._on_send_break(sid)
        )

        # Push the current trigger list into this session and listen for fires
        session.trigger_engine.set_triggers(self._trigger_panel.get_triggers())
        session.trigger_engine.trigger_fired.connect(
            lambda trig, matched, sid=session.session_id:
                self._on_trigger_fired(sid, trig, matched)
        )

        idx = self._tabs.addTab(tab, title)
        self._tabs.setTabsClosable(True)
        self._tabs.setCurrentIndex(idx)

        # Add to port panel
        self._port_panel.add_session(session)

    def remove_port_tab(self, session_id: str) -> None:
        """Remove the tab for a session."""
        tab = self._port_tabs.pop(session_id, None)
        if tab is None:
            return
        idx = self._tabs.indexOf(tab)
        if idx >= 0:
            self._tabs.removeTab(idx)

        self._port_panel.remove_session(session_id)

        # If no more port tabs, disable close on welcome
        if not self._port_tabs and not self._tap_tabs:
            self._tabs.setTabsClosable(False)

    # ------------------------------------------------------------------
    # Tap session management
    # ------------------------------------------------------------------

    def add_tap_tab(self, tap: TapSession) -> None:
        """Create a TapTab for a TapSession and wire all its signals."""
        if tap.session_id in self._tap_tabs:
            return

        title = tap.config.display_name()
        tab = TapTab(tap.session_id, title)
        is_dark = self._theme_manager.current == "dark"
        tab.terminal.set_theme(is_dark)
        tab.terminal.apply_style(self._terminal_style)
        tab.terminal.set_mixed_layers(self._settings.get_mixed_layers())
        self._tap_tabs[tap.session_id] = tab

        # Data from either channel goes to the tap terminal
        tap.data_received.connect(
            lambda data, ts, ch, t=tab: t.terminal.append_tap_rx(data, ts, ch)
        )

        # Status changes update the tab title
        tap.status_changed.connect(
            lambda _sid, status, t=tab: self._on_tap_status(t, tap, status)
        )

        # Errors shown in the tap terminal
        tap.error_occurred.connect(
            lambda _sid, msg, t=tab: t.terminal.append_tap_error(msg)
        )

        idx = self._tabs.addTab(tab, f"⌥ {title}")
        self._tabs.setTabsClosable(True)
        self._tabs.setCurrentIndex(idx)
        tab.terminal.append_tap_info(
            f"Tap session: {tap.config.port_a.display_name()} ↔ "
            f"{tap.config.port_b.display_name()}  "
            f"[forward: {tap.config.forward_mode}]"
        )

    def remove_tap_tab(self, tap_session_id: str) -> None:
        """Remove the TapTab for a tap session."""
        tab = self._tap_tabs.pop(tap_session_id, None)
        if tab is None:
            return
        idx = self._tabs.indexOf(tab)
        if idx >= 0:
            self._tabs.removeTab(idx)
        if not self._port_tabs and not self._tap_tabs:
            self._tabs.setTabsClosable(False)

    def _on_tap_status(self, tab: TapTab, tap: TapSession, status: str) -> None:
        """Update the TapTab title to reflect the combined connection status."""
        idx = self._tabs.indexOf(tab)
        if idx < 0:
            return
        # status is prefixed "A:connected" or "B:disconnected" etc.
        base = tap.config.display_name()
        self._tabs.setTabText(idx, f"⌥ {base}  [{status}]")

    # ------------------------------------------------------------------
    # Session manager slots
    # ------------------------------------------------------------------

    def _on_session_opened(self, session_id: str) -> None:
        session = self._session_manager.get_session(session_id)
        if session is not None:
            self.add_port_tab(session)
            self._status_port_label.setText(f"Connecting: {session.config.display_name()}")

    def _on_session_closed(self, session_id: str) -> None:
        self.remove_port_tab(session_id)
        if not self._port_tabs:
            self._status_port_label.setText("No connection")
            self._status_rx_label.setText("RX: 0 B")
            self._status_tx_label.setText("TX: 0 B")

    def _on_session_error(self, session_id: str, msg: str) -> None:
        # The terminal message is already written by the per-session
        # error_occurred connection (see add_port_tab); here we only flag the
        # tab title so the same error isn't printed twice.
        tab = self._port_tabs.get(session_id)
        if tab:
            idx = self._tabs.indexOf(tab)
            if idx >= 0:
                current_title = self._tabs.tabText(idx)
                if not current_title.startswith("⚠"):
                    self._tabs.setTabText(idx, f"⚠ {current_title}")

        # Offer to fix permission problems right where they happen.
        if "permission denied" in msg.lower() or "access is denied" in msg.lower():
            QTimer.singleShot(0, lambda: self._check_port_permissions(prompt=True))

    def _on_session_status_changed(self, session_id: str, status: str) -> None:
        self._port_panel.update_session_status(session_id, status)
        tab = self._port_tabs.get(session_id)
        if tab:
            self._on_session_tab_status(tab, session_id, status)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _on_session_tab_status(self, tab: PortTab, session_id: str, status: str) -> None:
        session = self._session_manager.get_session(session_id)
        if session is None:
            return

        # If this session's tab is the active one, the Connect/Disconnect
        # button must mirror the new status.
        if self._tabs.currentWidget() is tab:
            self._update_connect_action_label()

        idx = self._tabs.indexOf(tab)
        if idx >= 0:
            name = session.config.display_name()
            status_icons = {
                ConnectionStatus.CONNECTED.value: "●",
                ConnectionStatus.CONNECTING.value: "◌",
                ConnectionStatus.DISCONNECTED.value: "○",
                ConnectionStatus.ERROR.value: "⚠",
            }
            icon = status_icons.get(status, "")
            self._tabs.setTabText(idx, f"{icon} {name}")

        # Update status bar if this is the current tab
        current_tab = self._tabs.currentWidget()
        if current_tab is tab:
            self._update_status_bar_for_session(session_id)
            if status == ConnectionStatus.CONNECTED.value:
                tab.terminal.append_info(f"Connected to {session.config.display_name()}")
                self._session_logger.log_event(session.config.display_name(), "CONNECTED")
            elif status == ConnectionStatus.DISCONNECTED.value:
                tab.terminal.append_info("Disconnected")
                self._session_logger.log_event(session.config.display_name(), "DISCONNECTED")
            elif status == ConnectionStatus.ERROR.value:
                pass  # error message already shown by error signal

    def _update_status_bar_for_session(self, session_id: str) -> None:
        session = self._session_manager.get_session(session_id)
        if session is None:
            return
        name = session.config.display_name()
        status_text = f"{session.status.value.upper()}: {name}"
        peer = session.peer_info()
        if peer:
            status_text += f"  ↔  {peer}"
        self._status_port_label.setText(status_text)
        self._update_status_bar_stats(session_id)

    def _update_status_bar_stats(self, session_id: str) -> None:
        # Only update if this session's tab is active
        current = self._tabs.currentWidget()
        if not isinstance(current, PortTab) or current.session_id != session_id:
            return
        session = self._session_manager.get_session(session_id)
        if session is None:
            return

        def fmt_bytes(n: int) -> str:
            if n < 1024:
                return f"{n} B"
            elif n < 1024 * 1024:
                return f"{n / 1024:.1f} KB"
            else:
                return f"{n / 1024 / 1024:.2f} MB"

        self._status_rx_label.setText(f"RX: {fmt_bytes(session.stats.bytes_rx)}")
        self._status_tx_label.setText(f"TX: {fmt_bytes(session.stats.bytes_tx)}")

    def _on_tab_changed(self, index: int) -> None:
        widget = self._tabs.widget(index)
        if isinstance(widget, PortTab):
            self._update_status_bar_for_session(widget.session_id)
        else:
            self._status_port_label.setText("No connection")
            self._status_rx_label.setText("")
            self._status_tx_label.setText("")
        self._update_connect_action_label()

    def _update_connect_action_label(self) -> None:
        """Sync the toolbar action's label to the current tab's session state."""
        widget = self._tabs.currentWidget()
        if not isinstance(widget, PortTab):
            self._connect_action.setText("Connect")
            self._connect_action.setToolTip("Open a new connection")
            return
        session = self._session_manager.get_session(widget.session_id)
        if session is not None and session.is_connected():
            self._connect_action.setText("Disconnect")
            self._connect_action.setToolTip(
                f"Disconnect {session.config.display_name()}"
            )
        else:
            self._connect_action.setText("Connect")
            self._connect_action.setToolTip(
                "Reconnect this port" if session is not None else "Open a new connection"
            )

    def _on_tab_close_requested(self, index: int) -> None:
        widget = self._tabs.widget(index)
        if isinstance(widget, PortTab):
            self._on_close_session(widget.session_id)
        elif isinstance(widget, TapTab):
            tap_id = widget.tap_session_id
            # Find and disconnect/cleanup the TapSession
            tab = self._tap_tabs.get(tap_id)
            if tab is not None:
                # Find the TapSession — it's parented to self
                for child in self.children():
                    if isinstance(child, TapSession) and child.session_id == tap_id:
                        child.disconnect()
                        child.setParent(None)
                        break
            self.remove_tap_tab(tap_id)

    def _on_send_sequence(self, seq) -> None:
        """Send one sequence — once, or periodically if repeat != 1.

        Multiple sequences can run concurrently; each gets its own runner.
        If the sequence is already running, the call is ignored (the row's
        Stop button is what cancels it).
        """
        if seq.id in self._runners:
            return  # already running — Stop button cancels it

        tab = self._current_port_tab()
        if tab is None:
            QMessageBox.information(
                self, "No connection", "Open and connect a port first."
            )
            return
        session = self._session_manager.get_session(tab.session_id)
        if session is None or not session.is_connected():
            QMessageBox.information(
                self, "Not connected", "The current port is not connected."
            )
            return
        try:
            data = seq.get_bytes()
        except Exception as e:
            tab.terminal.append_error(f"Sequence parse error: {e}")
            return

        repeat = seq.repeat_count
        interval = seq.repeat_interval_ms

        byte_delay = getattr(seq, "byte_delay_ms", 0)

        # One-shot: a single send with no repeat configured.
        if repeat == 1:
            self._transmit(session.session_id, data, byte_delay_ms=byte_delay)
            return

        # Periodic: each running sequence gets its own runner.
        runner = SequenceRunner(self)
        runner.tick.connect(lambda sid=seq.id: self._on_runner_tick(sid))
        runner.finished.connect(lambda sid=seq.id: self._on_runner_finished(sid))
        runner.progress.connect(self._on_runner_progress)
        self._runners[seq.id] = {
            "runner": runner,
            "session_id": session.session_id,
            "data": data,
            "name": seq.name,
            "byte_delay_ms": byte_delay,
            "color": getattr(seq, "color", "#89b4fa"),
        }
        self._sequence_panel.set_row_running(seq.id, True)
        # Highlight matching bytes in this session's terminal while the
        # sequence is running — removed automatically when it finishes.
        tab = self._port_tabs.get(session.session_id)
        if tab is not None:
            tab.terminal.add_sequence_highlight(
                seq.id, data, getattr(seq, "color", "#89b4fa")
            )
        runner.start(repeat, interval)

    def _transmit(self, session_id: str, data: bytes, byte_delay_ms: int = 0) -> bool:
        """Send bytes to a session and echo them as TX in its terminal.

        When *byte_delay_ms* > 0, bytes are drip-fed one per timer tick.
        """
        session = self._session_manager.get_session(session_id)
        if session is None or not session.is_connected():
            return False
        if byte_delay_ms > 0 and len(data) > 1:
            self._transmit_with_delay(session_id, data, byte_delay_ms)
        else:
            session.send(data)
            tab = self._port_tabs.get(session_id)
            if tab is not None:
                tab.terminal.append_tx(data)
            self._session_logger.feed(session.config.display_name(), data, "TX")
        return True

    def _transmit_with_delay(self, session_id: str, data: bytes, delay_ms: int) -> None:
        """Send *data* byte-by-byte with *delay_ms* between each byte."""
        from PyQt6.QtCore import QTimer as _QTimer

        remaining = list(data)

        def _send_next() -> None:
            if not remaining:
                return
            b = bytes([remaining.pop(0)])
            session = self._session_manager.get_session(session_id)
            if session and session.is_connected():
                session.send(b)
                tab = self._port_tabs.get(session_id)
                if tab is not None:
                    tab.terminal.append_tx(b)
                self._session_logger.feed(session.config.display_name(), b, "TX")
            if remaining:
                _QTimer.singleShot(delay_ms, _send_next)

        _send_next()

    def _on_runner_tick(self, seq_id: str) -> None:
        info = self._runners.get(seq_id)
        if info is None:
            return
        if not self._transmit(
            info["session_id"],
            info["data"],
            byte_delay_ms=info.get("byte_delay_ms", 0),
        ):
            # Target port went away — kill this runner.
            info["runner"].stop()

    def _on_runner_progress(self, sent: int, total: int) -> None:
        if total > 0:
            self.statusBar().showMessage(f"Sending sequence: {sent}/{total}", 2000)
        else:
            self.statusBar().showMessage(
                f"Sending sequence: {sent} (repeating — press Stop)", 2000
            )

    def _on_runner_finished(self, seq_id: str) -> None:
        info = self._runners.pop(seq_id, None)
        self._sequence_panel.set_row_running(seq_id, False)
        if info:
            # Remove this sequence's byte highlight from the terminal.
            tab = self._port_tabs.get(info["session_id"])
            if tab is not None:
                tab.terminal.remove_sequence_highlight(seq_id)
            self.statusBar().showMessage(
                f"Sequence '{info['name']}' finished", 3000
            )

    def _on_stop_sequence(self, seq_id: str) -> None:
        info = self._runners.get(seq_id)
        if info is None:
            return
        info["runner"].stop()
        # _on_runner_finished cleans up self._runners and updates the button.

    def _on_sequences_changed(self, sequences: list) -> None:
        self._sequences = sequences
        # Trigger panel needs the new list so its action labels and editor
        # dropdown resolve sequence names correctly.
        self._trigger_panel.set_sequences(sequences)

    # ------------------------------------------------------------------
    # Receive Triggers
    # ------------------------------------------------------------------

    def _on_triggers_changed(self, triggers: list) -> None:
        """Push the updated trigger list into every active session's engine.

        On Start: retroactively highlight every existing RX row that matches
        the newly-enabled trigger, so the user gets immediate visual feedback.
        On Stop: remove that trigger's tint from every row it highlighted.
        Multiple triggers are handled independently — stopping one never
        removes highlights set by a still-active trigger on the same row.
        """
        for session in self._session_manager.all_sessions():
            session.trigger_engine.set_triggers(triggers)

        # Step 1 — clear highlights for every disabled trigger.
        for trig in triggers:
            if not trig.enabled:
                for tab in self._port_tabs.values():
                    tab.terminal.clear_trigger_highlights(trig.name)

        # Step 2 — re-apply highlights for every enabled trigger.
        # Running this after the clear ensures that rows matched by multiple
        # triggers are re-highlighted by whichever triggers are still active.
        for trig in triggers:
            if not trig.enabled:
                continue
            try:
                pat = trig.get_pattern_bytes()
            except Exception:
                continue
            if not pat:
                continue
            for tab in self._port_tabs.values():
                tab.terminal.highlight_all_matching(pat, trig.name, trig.color)

    def _on_trigger_fired(self, session_id: str, trig, matched: bytes) -> None:
        """Dispatch the trigger's action and give the user visible feedback."""
        tab = self._port_tabs.get(session_id)
        if tab is not None:
            tab.terminal.highlight_last_rx(trig.name, trig.color)
        self.statusBar().showMessage(f"★ Trigger '{trig.name}' matched", 3000)

        action = trig.action
        if action == "log":
            label = trig.action_data.strip() or trig.name
            self._session_logger.log_event(
                self._session_manager.get_session(session_id).config.display_name()
                if self._session_manager.get_session(session_id) else "session",
                f"TRIGGER {label}",
            )
        elif action == "notify":
            msg = trig.action_data.strip() or f"Trigger '{trig.name}' fired"
            self.statusBar().showMessage(msg, 4000)
        elif action == "stop":
            session = self._session_manager.get_session(session_id)
            if session is not None and session.is_connected():
                session.disconnect()  # type: ignore[call-arg]
        elif action == "send_sequence":
            seq = next((s for s in self._sequences if s.id == trig.action_data), None)
            if seq is None:
                if tab is not None:
                    tab.terminal.append_error(
                        f"Trigger '{trig.name}': configured sequence not found"
                    )
                return
            try:
                data = seq.get_bytes()
            except Exception as e:
                if tab is not None:
                    tab.terminal.append_error(
                        f"Trigger '{trig.name}': sequence parse error: {e}"
                    )
                return
            # Fire the reply on the session that matched — not the active tab.
            self._transmit(session_id, data)

    def _on_create_trigger_from_bytes(self, data: bytes) -> None:
        """Open trigger editor pre-filled with *data* as a hex pattern."""
        self._trigger_panel.add_trigger_preset(data)

    def _on_create_sequence_from_bytes(self, data: bytes) -> None:
        """Open sequence editor pre-filled with *data* as a hex string."""
        self._sequence_panel.add_sequence_preset(data)

    # ------------------------------------------------------------------
    # HTTP/JSON API server
    # ------------------------------------------------------------------

    def _start_api_server(self) -> None:
        from kcom.api.server import APIServer, _API_AVAILABLE
        if not _API_AVAILABLE:
            self.statusBar().showMessage(
                "HTTP API unavailable — install: pip install fastapi 'uvicorn[standard]'",
                8000,
            )
            return
        port = self._settings.get_api_port()
        server = APIServer(port=port, session_manager=self._session_manager, parent=self)
        server.started_signal.connect(
            lambda p: self.statusBar().showMessage(f"HTTP API listening on 127.0.0.1:{p}", 5000)
        )
        server.error_signal.connect(
            lambda msg: self.statusBar().showMessage(f"API error: {msg}", 8000)
        )
        server.start()
        self._api_server = server

    def _stop_api_server(self) -> None:
        from kcom.api.server import APIServer
        if isinstance(self._api_server, APIServer):
            self._api_server.stop()
            self._api_server.wait(3000)
            self._api_server = None

    def _api_push(self, session_id: str, data: bytes, direction: str) -> None:
        # Defensive: an API-server hiccup must never propagate up the Qt
        # signal chain and freeze the data-receive path for the active tab.
        try:
            from kcom.api.server import APIServer
            if isinstance(self._api_server, APIServer):
                self._api_server.push_data(session_id, data, direction)
        except Exception:
            pass

    def _on_rx_overflow(self, session_name: str, dropped: int) -> None:
        """Show a status-bar warning when the RX ring buffer is near-full or full."""
        if dropped == 0:
            msg = f"⚠ RX buffer high-water mark reached for {session_name}"
        else:
            msg = f"⚠ RX buffer overflow for {session_name} — {dropped} chunk(s) dropped"
        self.statusBar().showMessage(msg, 5000)

    def _on_tab_log_start(self, session_id: str) -> None:
        """Start per-session logging using an auto-generated path from settings."""
        import os as _os
        from datetime import datetime as _dt
        session = self._session_manager.get_session(session_id)
        if session is None:
            return
        log_path = self._settings.get_log_path()
        folder = _os.path.dirname(log_path) or _os.path.expanduser("~")
        ts = _dt.now().strftime("%Y%m%d-%H%M%S")
        name = session.config.display_name().replace("/", "-").replace(":", "-")
        path = _os.path.join(folder, f"kcom-{name}-{ts}.txt")
        tab = self._port_tabs.get(session_id)
        dm = tab.terminal.display_mode() if tab else None
        session.log_manager.start_logging(path, "text", display_mode=dm)

    def _on_tab_log_stop(self, session_id: str) -> None:
        session = self._session_manager.get_session(session_id)
        if session is not None:
            session.log_manager.stop_logging()

    def _on_annotation(self, session_id: str, text: str) -> None:
        session = self._session_manager.get_session(session_id)
        if session is not None:
            session.annotate(text)

    def _on_script_send(self, data: bytes) -> None:
        """Route kcom.send() to the currently-active port tab."""
        tab = self._current_port_tab()
        if tab is None:
            self._script_panel.append_output("[script] kcom.send: no active session")
            return
        self._transmit(tab.session_id, data)

    def _on_script_logging_start(self, path: str) -> None:
        """kcom.start_logging(path) — start per-session logging for current tab."""
        import os as _os
        from datetime import datetime as _dt
        tab = self._current_port_tab()
        if tab is None:
            return
        session = self._session_manager.get_session(tab.session_id)
        if session is None:
            return
        if not path:
            log_path = self._settings.get_log_path()
            folder = _os.path.dirname(log_path) or _os.path.expanduser("~")
            ts = _dt.now().strftime("%Y%m%d-%H%M%S")
            name = session.config.display_name().replace("/", "-").replace(":", "-")
            path = _os.path.join(folder, f"kcom-{name}-{ts}.txt")
        dm = tab.terminal.display_mode() if tab else None
        session.log_manager.start_logging(path, "text", display_mode=dm)

    def _on_script_logging_stop(self) -> None:
        """kcom.stop_logging() — stop per-session logging for current tab."""
        tab = self._current_port_tab()
        if tab is None:
            return
        session = self._session_manager.get_session(tab.session_id)
        if session is not None:
            session.log_manager.stop_logging()

    def _on_send_break(self, session_id: str) -> None:
        session = self._session_manager.get_session(session_id)
        if session is None:
            return
        session.send_break()
        tab = self._port_tabs.get(session_id)
        if tab:
            tab.terminal.append_info("BREAK signal sent")

    def _current_port_tab(self):
        widget = self._tabs.currentWidget()
        if isinstance(widget, PortTab):
            return widget
        return None

    def _on_terminal_send(self, session_id: str, data: bytes) -> None:
        session = self._session_manager.get_session(session_id)
        if session is None:
            return
        session.send(data)
        tab = self._port_tabs.get(session_id)
        if tab:
            tab.terminal.append_tx(data)
        self._session_logger.feed(session.config.display_name(), data, "TX")

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    def _on_new_tap_connection(self) -> None:
        from kcom.ui.dialogs.tap_config_dialog import TapConfigDialog

        dlg = TapConfigDialog(parent=self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        tap_config = dlg.get_config()
        tap = TapSession(tap_config, parent=self)
        self.add_tap_tab(tap)
        tap.connect()

    def _on_new_connection(self) -> None:
        from kcom.ui.dialogs.port_config_dialog import PortConfigDialog

        dlg = PortConfigDialog(parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            config = dlg.get_config()
            self._settings.set_last_config(config.to_dict())
            preset = dlg.preset_name()
            if preset:
                self._settings.save_connection_preset(preset, config.to_dict())
                self._refresh_connections_menu()
            self._session_manager.open_session(config)

    def _refresh_connections_menu(self) -> None:
        """Rebuild the Ports → Saved Connections submenu from settings."""
        if not hasattr(self, "_connections_menu"):
            return
        self._connections_menu.clear()
        presets = self._settings.get_connection_presets()
        if not presets:
            empty = QAction("(no saved connections)", self)
            empty.setEnabled(False)
            self._connections_menu.addAction(empty)
            return
        for preset in presets:
            name = preset.get("preset_name", "unnamed")
            action = QAction(name, self)
            action.triggered.connect(
                lambda _checked=False, p=preset: self._apply_preset(p)
            )
            self._connections_menu.addAction(action)

    def _apply_preset(self, preset: dict) -> None:
        """Open a connection from a saved preset (applies all its settings)."""
        from kcom.models.port_config import PortConfig

        data = {k: v for k, v in preset.items() if k != "preset_name"}
        try:
            config = PortConfig.from_dict(data)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Invalid saved connection: {e}")
            return
        self._settings.set_last_config(config.to_dict())
        self._session_manager.open_session(config)

    def _check_port_permissions(self, prompt: bool = True, manual: bool = False) -> None:
        """Detect serial ports the app can't open and offer to grant access.

        Runs at startup and from Tools → Fix Port Permissions. Uses pkexec/sudo
        (which shows its own password prompt) to chmod the devices.
        """
        from kcom.core import port_access

        if not port_access.is_unix():
            if manual:
                QMessageBox.information(
                    self, "Port Permissions",
                    "Serial ports on this platform do not need permission changes.",
                )
            return

        blocked = port_access.inaccessible_ports()
        if not blocked:
            if manual:
                QMessageBox.information(
                    self, "Port Permissions", "All detected serial ports are already accessible."
                )
            return

        if prompt:
            listing = "\n".join(f"  • {d}" for d in blocked)
            reply = QMessageBox.question(
                self,
                "Grant Serial Port Access",
                f"{len(blocked)} serial port(s) are not accessible to KCom:\n\n{listing}\n\n"
                "Grant read/write access now? You'll be asked for your password.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        ok, message = port_access.make_accessible(blocked)
        if ok:
            self.statusBar().showMessage(message, 5000)
            if manual:
                QMessageBox.information(self, "Port Permissions", message)
        else:
            QMessageBox.warning(
                self, "Port Permissions",
                f"Could not grant access automatically:\n\n{message}\n\n"
                "You can run this manually, e.g.:\n"
                f"  sudo chmod a+rw {' '.join(blocked)}",
            )

    def _on_close_current_connection(self) -> None:
        current = self._tabs.currentWidget()
        if isinstance(current, PortTab):
            self._on_close_session(current.session_id)

    def _on_close_session(self, session_id: str) -> None:
        # Stop any periodic sends targeting the session being closed.
        for seq_id, info in list(self._runners.items()):
            if info["session_id"] == session_id:
                info["runner"].stop()
        session = self._session_manager.get_session(session_id)
        if session and session.is_connected():
            reply = QMessageBox.question(
                self,
                "Close Connection",
                f"Close connection to {session.config.display_name()}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self._session_manager.close_session(session_id)

    def _on_clear_terminal(self) -> None:
        current = self._tabs.currentWidget()
        if isinstance(current, PortTab):
            current.terminal.clear()

    def _on_toggle_connection(self) -> None:
        """Connect or disconnect the current tab's session."""
        current = self._tabs.currentWidget()
        if not isinstance(current, PortTab):
            self._on_new_connection()
            return
        session = self._session_manager.get_session(current.session_id)
        if session is None:
            return
        if session.is_connected():
            session.disconnect()  # type: ignore[call-arg]
        else:
            session.connect()  # type: ignore[call-arg]

    def _on_toggle_theme(self) -> None:
        new_theme = self._theme_manager.toggle()
        is_dark = new_theme == "dark"
        for tab in self._port_tabs.values():
            tab.terminal.set_theme(is_dark)
            tab.terminal.apply_style(self._terminal_style)
        self._trigger_panel.set_theme(is_dark)

    def _on_toggle_fullscreen(self, checked: bool) -> None:
        if checked:
            self.showFullScreen()
        else:
            self.showNormal()

    def _on_port_panel_selection(self, session_id: str) -> None:
        tab = self._port_tabs.get(session_id)
        if tab:
            self._tabs.setCurrentWidget(tab)

    def _on_log_start(self, path: str, mode: str) -> None:
        current = self._tabs.currentWidget()
        if not isinstance(current, PortTab):
            return
        session = self._session_manager.get_session(current.session_id)
        if session is None:
            return
        log_mgr = session.log_manager
        log_mgr.start_logging(path, mode, display_mode=current.terminal.display_mode())
        if log_mgr.is_logging:
            self._log_panel.set_logging_active(path)
            self._log_action.setText("Log: ON")
            self._log_action.setChecked(True)

    def _on_log_stop(self) -> None:
        current = self._tabs.currentWidget()
        if not isinstance(current, PortTab):
            return
        session = self._session_manager.get_session(current.session_id)
        if session is None:
            return
        session.log_manager.stop_logging()
        self._log_panel.set_logging_stopped()
        self._log_action.setText("Log: Off")
        self._log_action.setChecked(False)

    def _on_toggle_log(self, checked: bool) -> None:
        if checked:
            current = self._tabs.currentWidget()
            if not isinstance(current, PortTab):
                self._log_action.setChecked(False)
                self.statusBar().showMessage("Open a connection first, then start logging.", 3000)
                return
            self._on_tab_log_start(current.session_id)
            session = self._session_manager.get_session(current.session_id)
            if session is not None and session.log_manager.is_logging:
                self._log_action.setText("Log: ON")
                self._log_dock.show()   # reveal panel so user can see the active file path
            else:
                self._log_action.setChecked(False)
        else:
            self._on_log_stop()

    _PROJECT_FILTER = (
        "KCom Project (*.kcom);;"
        "Docklight Project (*.ptp);;"
        "Legacy KCom (*.kcp *.kproj);;"
        "All files (*)"
    )
    _NATIVE_EXT = ".kcom"

    def _on_open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Project", "", self._PROJECT_FILTER
        )
        if not path:
            return
        self._load_project(path)

    def _on_save_project(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Project", "project.kcom", self._PROJECT_FILTER
        )
        if not path:
            return
        # Append native extension when the user typed no extension.
        if not any(path.lower().endswith(ext)
                   for ext in (".kcom", ".ptp", ".kcp", ".kproj")):
            path += self._NATIVE_EXT

        from kcom.core.project_manager import ProjectManager
        from kcom.models.project import ProjectData

        pm = ProjectManager(parent=self)
        sessions = self._session_manager.all_sessions()
        tap_configs = [
            child.config
            for child in self.children()
            if isinstance(child, TapSession)
        ]
        project = ProjectData(
            name="KCom Project",
            notes=self._doc_panel.text(),
            port_configs=[s.config for s in sessions],
            tap_configs=tap_configs,
            sequences=self._sequence_panel.get_sequences(),
            triggers=self._trigger_panel.get_triggers(),
        )
        if not pm.save(path, project):
            QMessageBox.critical(self, "Error", "Failed to save project file.")
        else:
            self._update_recent_menu()
            self.statusBar().showMessage(f"Project saved: {path}", 4000)

    def _load_project(self, path: str) -> None:
        """Load a project file and restore sessions, sequences, and triggers."""
        from kcom.core.project_manager import ProjectManager

        pm = ProjectManager(parent=self)
        project = pm.load(path)
        if project is None:
            QMessageBox.critical(self, "Error", f"Failed to load:\n{path}")
            return

        # Restore send sequences, receive triggers, and documentation notes.
        # Order matters: trigger panel needs the sequence list first so its
        # "→ send «name»" labels resolve correctly.
        self._sequences = list(project.sequences)
        self._sequence_panel.set_sequences(project.sequences)
        self._trigger_panel.set_sequences(project.sequences)
        self._trigger_panel.set_triggers(project.triggers)
        self._doc_panel.set_text(project.notes)

        # Open sessions for each saved port config
        for cfg in project.port_configs:
            self._session_manager.open_session(cfg)

        # Restore tap sessions
        for tap_cfg in project.tap_configs:
            tap = TapSession(tap_cfg, parent=self)
            self.add_tap_tab(tap)
            tap.connect()

        self._update_recent_menu()
        self.statusBar().showMessage(f"Project loaded: {path}", 4000)

    def _on_export_session(self) -> None:
        """Export the always-on session log to a user-chosen path."""
        import os

        default_name = os.path.basename(self._session_logger.path)
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Session Data",
            default_name,
            "Text files (*.txt);;Log files (*.log);;All files (*)",
        )
        if not path:
            return
        if self._session_logger.export(path):
            self.statusBar().showMessage(f"Session data exported: {path}", 4000)
        else:
            QMessageBox.critical(
                self, "Export Failed", f"Could not export session data to:\n{path}"
            )

    def _on_diagnostics(self) -> None:
        """Open the live Diagnostics dialog (Tools menu)."""
        from kcom.ui.dialogs.diagnostics_dialog import DiagnosticsDialog
        dlg = DiagnosticsDialog(self, parent=self)
        dlg.exec()

    def _on_settings(self) -> None:
        from kcom.ui.dialogs.settings_dialog import SettingsDialog
        prev_api_enabled = self._settings.get_api_enabled()
        prev_api_port = self._settings.get_api_port()
        dlg = SettingsDialog(parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            theme = dlg.selected_theme()
            if theme in ("dark", "light"):
                self._theme_manager.apply(theme)
            # Pick up & broadcast new terminal style to all open tabs.
            self._terminal_style = dlg.terminal_style()
            self._settings.set_terminal_style(self._terminal_style)
            is_dark = self._theme_manager.current == "dark"
            mixed_layers = self._settings.get_mixed_layers()
            for tab in self._port_tabs.values():
                tab.terminal.set_theme(is_dark)
                tab.terminal.apply_style(self._terminal_style)
                tab.terminal.set_mixed_layers(mixed_layers)
            # Restart API server if its settings changed
            new_api_enabled = self._settings.get_api_enabled()
            new_api_port = self._settings.get_api_port()
            if (new_api_enabled != prev_api_enabled) or (new_api_enabled and new_api_port != prev_api_port):
                self._stop_api_server()
                if new_api_enabled:
                    self._start_api_server()

    def _on_show_help(self) -> None:
        focused = self.focusWidget()
        self._help_browser.show_context_help(focused)

    def _on_show_hotkeys(self) -> None:
        from kcom.ui.dialogs.hotkeys_dialog import HotkeysDialog
        HotkeysDialog(parent=self).exec()

    def _on_about(self) -> None:
        from PyQt6.QtGui import QPixmap

        box = QMessageBox(self)
        box.setWindowTitle("About KCom")
        box.setIconPixmap(
            QPixmap(logo_path()).scaled(
                96, 96,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        box.setText(
            "<h2>KCom v1.0.0</h2>"
            "<p>Professional Serial &amp; Network Communication Studio</p>"
            "<p>Built with Python 3.11+, PyQt6, pyserial</p>"
            "<br>"
            "<p><b>Features:</b></p>"
            "<ul>"
            "<li>Serial port connection with configurable parameters</li>"
            "<li>ASCII / Hex / Decimal / Binary / Mixed display modes</li>"
            "<li>Send Sequences with checksums (XOR, CRC-8/16/32, Sum)</li>"
            "<li>Receive Triggers &amp; auto-response</li>"
            "<li>Always-on session capture to ~/kcom-session.txt</li>"
            "<li>Docklight-style <code>.ptp</code> project save/load</li>"
            "<li>Dark (Catppuccin Mocha) and Light themes</li>"
            "</ul>"
        )
        box.exec()

    def _update_recent_menu(self) -> None:
        from kcom.core.project_manager import ProjectManager
        pm = ProjectManager()
        self._recent_menu.clear()
        for path in pm.recent_projects:
            action = QAction(path, self)
            action.triggered.connect(
                lambda checked, p=path: self._open_recent_project(p)
            )
            self._recent_menu.addAction(action)
        if not pm.recent_projects:
            empty_action = QAction("(no recent projects)", self)
            empty_action.setEnabled(False)
            self._recent_menu.addAction(empty_action)

    def _open_recent_project(self, path: str) -> None:
        self._load_project(path)

    # ------------------------------------------------------------------
    # Window events
    # ------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        sessions = self._session_manager.all_sessions()
        if sessions:
            n = len(sessions)
            names = ", ".join(s.config.display_name() for s in sessions[:3])
            if n > 3:
                names += f" … (+{n - 3} more)"

            dlg = _ExitConfirmDialog(n, names, parent=self)
            if not dlg.exec():
                event.ignore()
                return
        self._settings.set_window_geometry(bytes(self.saveGeometry()))
        for info in list(self._runners.values()):
            info["runner"].stop()
        self._runners.clear()
        # Disconnect all tap sessions
        for child in list(self.children()):
            if isinstance(child, TapSession):
                child.disconnect()
        self._session_manager.close_all()
        self._session_logger.close()
        self._stop_api_server()
        event.accept()
