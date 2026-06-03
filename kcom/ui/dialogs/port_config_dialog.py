"""Port configuration dialog — Serial and Network settings."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QProcess, QThread, pyqtSignal as Signal
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from kcom.models.port_config import (
    ConnectionType,
    FlowControl,
    HIDConfig,
    NamedPipeConfig,
    NetworkConfig,
    Parity,
    PortConfig,
    SerialConfig,
)
from kcom.utils.platform_utils import PortInfo, get_available_ports


_BAUD_RATES = [
    110, 300, 600, 1200, 2400, 4800, 9600, 14400, 19200,
    38400, 57600, 115200, 230400, 460800, 921600, 1000000, 2000000,
]

# Tag colours shown next to each port type in the dropdown
_TYPE_COLORS = {
    "hardware":  "#89b4fa",   # blue
    "usb":       "#a6e3a1",   # green
    "virtual":   "#f9e2af",   # yellow
    "bluetooth": "#cba6f7",   # purple
    "unknown":   "#6c7086",   # grey
}

_TYPE_LABELS = {
    "hardware":  "HW",
    "usb":       "USB",
    "virtual":   "VIRT",
    "bluetooth": "BT",
    "unknown":   "?",
}


class _PortScanThread(QThread):
    """Scans for ports in a background thread to avoid blocking the UI."""
    finished = Signal(list)   # list[PortInfo]

    def __init__(self, include_virtual: bool) -> None:
        super().__init__()
        self._include_virtual = include_virtual

    def run(self) -> None:
        ports = get_available_ports(include_virtual=self._include_virtual)
        self.finished.emit(ports)


from kcom.ui.dialogs.base_dialog import CenteredDialog


class PortConfigDialog(CenteredDialog):
    """Modal dialog for configuring a new or existing port connection."""

    def __init__(
        self,
        config: PortConfig | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Connection Configuration")
        self.setMinimumWidth(540)
        self.setModal(True)

        self._scan_thread: _PortScanThread | None = None
        self._all_ports: list[PortInfo] = []

        self._build_ui()
        self._connect_signals()

        if config is not None:
            self.set_config(config)
        else:
            self._start_port_scan()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)

        self._tabs = QTabWidget()
        main_layout.addWidget(self._tabs)

        self._tabs.addTab(self._build_serial_tab(),     "Serial")
        self._tabs.addTab(self._build_network_tab(),    "Network")
        self._tabs.addTab(self._build_named_pipe_tab(), "Named Pipe")
        self._tabs.addTab(self._build_hid_tab(),        "USB HID")

        # Connection name
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name (optional):"))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Leave blank to use port name")
        name_row.addWidget(self._name_edit, stretch=1)
        main_layout.addLayout(name_row)

        # Auto-reconnect option
        reconnect_row = QHBoxLayout()
        self._auto_reconnect_check = QCheckBox("Auto-reconnect on unexpected disconnect")
        self._auto_reconnect_check.setChecked(True)
        self._auto_reconnect_check.setToolTip(
            "If the connection drops unexpectedly, automatically retry after 3 seconds"
        )
        reconnect_row.addWidget(self._auto_reconnect_check)
        reconnect_row.addStretch()
        main_layout.addLayout(reconnect_row)

        # Save-as-preset row
        preset_row = QHBoxLayout()
        self._preset_check = QCheckBox("Save this configuration as a preset")
        preset_row.addWidget(self._preset_check)
        self._preset_name_edit = QLineEdit()
        self._preset_name_edit.setPlaceholderText("Preset name")
        self._preset_name_edit.setEnabled(False)
        self._preset_check.toggled.connect(self._preset_name_edit.setEnabled)
        preset_row.addWidget(self._preset_name_edit, stretch=1)
        main_layout.addLayout(preset_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

    def _build_serial_tab(self) -> QWidget:
        widget = QWidget()
        outer = QVBoxLayout(widget)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        # ── Port selector group ───────────────────────────────────────
        port_group = QGroupBox("Port")
        port_group_layout = QVBoxLayout(port_group)
        port_group_layout.setSpacing(6)

        # Dropdown row
        combo_row = QHBoxLayout()
        self._port_combo = QComboBox()
        self._port_combo.setEditable(True)
        self._port_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._port_combo.setPlaceholderText("Select or type a port…")
        self._port_combo.setMinimumWidth(200)
        combo_row.addWidget(self._port_combo, stretch=1)

        self._refresh_btn = QPushButton("⟳ Refresh")
        self._refresh_btn.setFixedWidth(84)
        self._refresh_btn.setToolTip("Re-scan all serial and virtual ports")
        combo_row.addWidget(self._refresh_btn)
        port_group_layout.addLayout(combo_row)

        # Virtual port checkbox
        virt_row = QHBoxLayout()
        self._virt_check = QCheckBox("Include virtual / pseudo-terminal ports")
        self._virt_check.setChecked(True)
        self._virt_check.setToolTip(
            "Scan /dev/pts/*, /dev/tnt* (socat, tty0tty) and other virtual ports"
        )
        virt_row.addWidget(self._virt_check)
        virt_row.addStretch()
        port_group_layout.addLayout(virt_row)

        # Status line: "Found N ports (M virtual)"
        self._port_status_label = QLabel("Scanning…")
        self._port_status_label.setObjectName("infoLabel")
        self._port_status_label.setStyleSheet("font-size: 11px; color: #6c7086;")
        port_group_layout.addWidget(self._port_status_label)

        outer.addWidget(port_group)

        # ── Serial parameters group ───────────────────────────────────
        params_group = QGroupBox("Parameters")
        params_layout = QFormLayout(params_group)
        params_layout.setSpacing(8)
        params_layout.setContentsMargins(10, 12, 10, 10)

        self._baud_combo = QComboBox()
        self._baud_combo.setEditable(True)
        for br in _BAUD_RATES:
            self._baud_combo.addItem(str(br))
        self._baud_combo.setCurrentText("115200")
        params_layout.addRow("Baud rate:", self._baud_combo)

        self._data_bits_combo = QComboBox()
        for db in [5, 6, 7, 8]:
            self._data_bits_combo.addItem(str(db))
        self._data_bits_combo.setCurrentText("8")
        params_layout.addRow("Data bits:", self._data_bits_combo)

        self._parity_combo = QComboBox()
        self._parity_combo.addItems(["None", "Odd", "Even", "Mark", "Space"])
        params_layout.addRow("Parity:", self._parity_combo)

        self._stop_bits_combo = QComboBox()
        self._stop_bits_combo.addItems(["1", "1.5", "2"])
        params_layout.addRow("Stop bits:", self._stop_bits_combo)

        self._flow_combo = QComboBox()
        self._flow_combo.addItems(["None", "RTS/CTS", "XON/XOFF", "DTR/DSR"])
        params_layout.addRow("Flow control:", self._flow_combo)

        self._timeout_spin = QSpinBox()
        self._timeout_spin.setRange(0, 60000)
        self._timeout_spin.setSuffix(" ms")
        self._timeout_spin.setSpecialValueText("Non-blocking (0)")
        self._timeout_spin.setValue(0)
        params_layout.addRow("Timeout:", self._timeout_spin)

        outer.addWidget(params_group)
        outer.addStretch()

        return widget

    def _build_network_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        box = QGroupBox("Network")
        form = QFormLayout(box)
        form.setSpacing(8)
        form.setContentsMargins(10, 12, 10, 10)

        self._net_type_combo = QComboBox()
        self._net_type_combo.addItems(["TCP Client", "TCP Server", "UDP"])
        form.addRow("Type:", self._net_type_combo)

        self._host_label = QLabel("Remote Host:")
        self._host_edit = QLineEdit("localhost")
        self._host_edit.setPlaceholderText("hostname or IP address")
        form.addRow(self._host_label, self._host_edit)

        self._net_port_label = QLabel("Remote Port:")
        self._net_port_spin = QSpinBox()
        self._net_port_spin.setRange(1, 65535)
        self._net_port_spin.setValue(9000)
        form.addRow(self._net_port_label, self._net_port_spin)

        self._local_port_label = QLabel("Local Port (receive):")
        self._local_port_spin = QSpinBox()
        self._local_port_spin.setRange(0, 65535)
        self._local_port_spin.setSpecialValueText("Auto (0)")
        self._local_port_spin.setValue(0)
        self._local_port_spin.setToolTip("Local UDP bind port; 0 lets the OS assign one")
        form.addRow(self._local_port_label, self._local_port_spin)

        layout.addWidget(box)
        layout.addStretch()

        self._net_type_combo.currentIndexChanged.connect(self._update_net_form)
        self._update_net_form(0)

        return widget

    def _build_named_pipe_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        hint = QLabel(
            "Windows: use a Win32 pipe name such as <b>\\\\\\\\.\\\\pipe\\\\kcom</b>.<br>"
            "Linux / macOS: use a filesystem path such as <b>/tmp/kcom.sock</b>."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #7d8590; font-size: 10px;")
        layout.addWidget(hint)

        box = QGroupBox("Named Pipe / Unix Socket")
        form = QFormLayout(box)
        form.setSpacing(8)

        self._pipe_role_combo = QComboBox()
        self._pipe_role_combo.addItems(["Client", "Server"])
        self._pipe_role_combo.setToolTip(
            "Client connects to an existing pipe; Server creates and listens on the pipe."
        )
        form.addRow("Role:", self._pipe_role_combo)

        self._pipe_path_edit = QLineEdit()
        self._pipe_path_edit.setPlaceholderText(r"e.g. /tmp/kcom.sock  or  \\.\pipe\kcom")
        form.addRow("Pipe path / name:", self._pipe_path_edit)

        layout.addWidget(box)
        layout.addStretch()
        return widget

    def _build_hid_tab(self) -> QWidget:
        import sys as _sys
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Availability banner — checked fresh every time the dialog opens
        from kcom.protocols.usb_hid import check_hid_availability, list_hid_devices
        self._hid_proc: QProcess | None = None

        hid_ok, hid_err = check_hid_availability()

        # Always create the banner widget; hide it when HID is available
        banner = QWidget()
        banner.setObjectName("hidBanner")
        banner.setStyleSheet("#hidBanner { background: #2a1a1a; border-radius: 4px; }")
        banner_row = QHBoxLayout(banner)
        banner_row.setContentsMargins(10, 8, 10, 8)
        banner_row.setSpacing(10)

        self._hid_banner_lbl = QLabel()
        self._hid_banner_lbl.setWordWrap(True)
        banner_row.addWidget(self._hid_banner_lbl, stretch=1)

        self._hid_install_btn = QPushButton("Install hidapi")
        self._hid_install_btn.setFixedWidth(110)
        self._hid_install_btn.setToolTip("Run: pip install hidapi")
        self._hid_install_btn.clicked.connect(self._install_hidapi)
        banner_row.addWidget(self._hid_install_btn)

        layout.addWidget(banner)

        self._hid_banner = banner
        self._update_hid_banner(hid_ok, hid_err)

        box = QGroupBox("USB HID Device")
        form = QFormLayout(box)
        form.setSpacing(8)

        # Device picker (populated from scan)
        scan_row = QHBoxLayout()
        self._hid_device_combo = QComboBox()
        self._hid_device_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._hid_device_combo.setToolTip("Select a detected HID device or enter VID:PID manually")
        scan_row.addWidget(self._hid_device_combo, stretch=1)
        self._hid_scan_btn = QPushButton("⟳ Scan")
        self._hid_scan_btn.setFixedWidth(70)
        self._hid_scan_btn.clicked.connect(self._scan_hid_devices)
        scan_row.addWidget(self._hid_scan_btn)
        form.addRow("Device:", scan_row)

        self._hid_vid_spin = QSpinBox()
        self._hid_vid_spin.setRange(0, 0xFFFF)
        self._hid_vid_spin.setDisplayIntegerBase(16)
        self._hid_vid_spin.setPrefix("0x")
        self._hid_vid_spin.setToolTip("Vendor ID (hex). 0 = any vendor.")
        form.addRow("Vendor ID:", self._hid_vid_spin)

        self._hid_pid_spin = QSpinBox()
        self._hid_pid_spin.setRange(0, 0xFFFF)
        self._hid_pid_spin.setDisplayIntegerBase(16)
        self._hid_pid_spin.setPrefix("0x")
        self._hid_pid_spin.setToolTip("Product ID (hex). 0 = any product.")
        form.addRow("Product ID:", self._hid_pid_spin)

        self._hid_report_spin = QSpinBox()
        self._hid_report_spin.setRange(1, 255)
        self._hid_report_spin.setValue(64)
        self._hid_report_spin.setSuffix(" bytes")
        self._hid_report_spin.setToolTip("Report payload size (excluding the leading report-ID byte).")
        form.addRow("Report size:", self._hid_report_spin)

        self._hid_iface_spin = QSpinBox()
        self._hid_iface_spin.setRange(-1, 31)
        self._hid_iface_spin.setSpecialValueText("Auto (-1)")
        self._hid_iface_spin.setValue(-1)
        form.addRow("Interface:", self._hid_iface_spin)

        layout.addWidget(box)
        layout.addStretch()

        # Connect device combo → auto-fill VID/PID
        self._hid_device_combo.currentIndexChanged.connect(self._on_hid_device_selected)
        self._scan_hid_devices()
        return widget

    def _update_hid_banner(self, hid_ok: bool, error: str = "") -> None:
        """Refresh the HID banner to reflect the current availability state."""
        if hid_ok:
            self._hid_banner.hide()
            return
        self._hid_banner.show()
        # Distinguish: Python package missing vs native C library missing
        if "Native library" in error or "native library" in error.lower() or "libhidapi" in error.lower():
            self._hid_banner_lbl.setText(
                "<b style='color:#f9e2af'>USB HID — native library missing.</b><br>"
                f"<span style='color:#cdd6f4'>{error.split(chr(10))[0]}</span><br>"
                "<span style='color:#a6e3a1'>Linux: <tt>sudo apt install libhidapi-hidraw0</tt></span>"
            )
            self._hid_install_btn.setText("Install hidapi")
        else:
            self._hid_banner_lbl.setText(
                "<b style='color:#f38ba8'>USB HID — Python package not found.</b><br>"
                "<span style='color:#cba6f7'>Click Install to set it up automatically.</span>"
            )
            self._hid_install_btn.setText("Install hidapi")
        self._hid_install_btn.show()
        self._hid_install_btn.setEnabled(True)

    def _install_hidapi(self) -> None:
        """Run ``pip install hidapi`` via QProcess (non-blocking)."""
        import sys
        self._hid_install_btn.setEnabled(False)
        self._hid_install_btn.setText("Installing…")
        self._hid_banner_lbl.setText(
            "<span style='color:#f9e2af'>Running: pip install hidapi — please wait…</span>"
        )
        self._hid_proc = QProcess(self)
        self._hid_proc.finished.connect(self._on_hidapi_install_finished)
        self._hid_proc.start(sys.executable, ["-m", "pip", "install", "hidapi"])

    def _on_hidapi_install_finished(self, exit_code: int, _status) -> None:
        from kcom.protocols.usb_hid import check_hid_availability
        if exit_code == 0:
            # Re-attempt import now that pip has installed the package
            hid_ok, hid_err = check_hid_availability()
            if hid_ok:
                self._hid_banner.hide()
                self._scan_hid_devices()
                return
            # Installed but native library still missing
            self._update_hid_banner(False, hid_err)
        else:
            stderr = ""
            if self._hid_proc:
                stderr = bytes(self._hid_proc.readAllStandardError()).decode("utf-8", errors="replace").strip()
            self._hid_banner_lbl.setText(
                "<b style='color:#f38ba8'>✗ pip install failed.</b><br>"
                f"<span style='color:#f38ba8'>{stderr[:140] or 'Check your internet connection.'}</span>"
            )
            self._hid_install_btn.setEnabled(True)
            self._hid_install_btn.setText("Retry")

    def _scan_hid_devices(self) -> None:
        from kcom.protocols.usb_hid import list_hid_devices
        self._hid_device_combo.blockSignals(True)
        self._hid_device_combo.clear()
        self._hid_device_combo.addItem("(manual entry)", userData=None)
        for d in list_hid_devices():
            label = (
                f"{d['vendor_id']:04X}:{d['product_id']:04X}  "
                f"{d.get('manufacturer', '')} {d.get('product', '')}".strip()
            )
            self._hid_device_combo.addItem(label, userData=d)
        self._hid_device_combo.blockSignals(False)

    def _on_hid_device_selected(self, _idx: int) -> None:
        d = self._hid_device_combo.currentData()
        if isinstance(d, dict):
            self._hid_vid_spin.setValue(d.get("vendor_id", 0))
            self._hid_pid_spin.setValue(d.get("product_id", 0))
            if d.get("interface_number", -1) >= 0:
                self._hid_iface_spin.setValue(d["interface_number"])

    def _update_net_form(self, _index: int = 0) -> None:
        """Show/hide fields depending on network type selection."""
        net_type = self._net_type_combo.currentText()
        is_server = net_type == "TCP Server"
        is_udp    = net_type == "UDP"

        # TCP Server listens on a port — no remote host
        self._host_label.setVisible(not is_server)
        self._host_edit.setVisible(not is_server)

        # Port label changes meaning
        if is_server:
            self._net_port_label.setText("Listen Port:")
        elif is_udp:
            self._net_port_label.setText("Remote Port:")
        else:
            self._net_port_label.setText("Remote Port:")

        # Local port spinner only needed for UDP
        self._local_port_label.setVisible(is_udp)
        self._local_port_spin.setVisible(is_udp)

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self._refresh_btn.clicked.connect(self._start_port_scan)
        self._virt_check.stateChanged.connect(self._start_port_scan)
        # _net_type_combo signal is already wired inside _build_network_tab

    # ------------------------------------------------------------------
    # Port scanning
    # ------------------------------------------------------------------

    def _start_port_scan(self) -> None:
        """Kick off background scan and show 'Scanning…' state."""
        self._port_combo.setEnabled(False)
        self._refresh_btn.setEnabled(False)
        self._port_status_label.setText("Scanning…")

        if self._scan_thread and self._scan_thread.isRunning():
            self._scan_thread.quit()
            self._scan_thread.wait(500)

        include_virt = self._virt_check.isChecked()
        self._scan_thread = _PortScanThread(include_virtual=include_virt)
        self._scan_thread.finished.connect(self._on_scan_finished)
        self._scan_thread.start()

    def _on_scan_finished(self, ports: list) -> None:
        """Populate the combo box from scan results."""
        self._all_ports = ports
        previous = self._get_port_device()

        self._port_combo.blockSignals(True)
        self._port_combo.clear()

        hw_count = 0
        virt_count = 0

        for info in ports:
            label = self._format_port_label(info)
            self._port_combo.addItem(label, userData=info.device)

            if info.port_type in ("hardware", "usb"):
                hw_count += 1
            else:
                virt_count += 1

        # Restore previous selection
        if previous:
            for i in range(self._port_combo.count()):
                if self._port_combo.itemData(i) == previous:
                    self._port_combo.setCurrentIndex(i)
                    break
            else:
                self._port_combo.setCurrentText(previous)
        elif self._port_combo.count() > 0:
            self._port_combo.setCurrentIndex(0)

        self._port_combo.blockSignals(False)
        self._port_combo.setEnabled(True)
        self._refresh_btn.setEnabled(True)

        # Update status label
        total = len(ports)
        if total == 0:
            self._port_status_label.setText(
                "No ports found — type a path manually or create a virtual port"
            )
            self._port_status_label.setStyleSheet("font-size: 11px; color: #f38ba8;")
        else:
            parts = []
            if hw_count:
                parts.append(f"{hw_count} hardware/USB")
            if virt_count:
                parts.append(f"{virt_count} virtual")
            self._port_status_label.setText(
                f"Found {total} port{'s' if total != 1 else ''}"
                + (f"  ({',  '.join(parts)})" if parts else "")
            )
            self._port_status_label.setStyleSheet("font-size: 11px; color: #6c7086;")

    def _format_port_label(self, info: PortInfo) -> str:
        """Build a display string: '/dev/ttyUSB0  —  USB serial  [USB]'"""
        badge = _TYPE_LABELS.get(info.port_type, "")
        inaccessible = "  ⚠ no access" if not info.accessible else ""
        if info.description and info.description != info.device:
            return f"{info.device}  —  {info.description}  [{badge}]{inaccessible}"
        return f"{info.device}  [{badge}]{inaccessible}"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_config(self) -> PortConfig:
        """Build and return a PortConfig from the current dialog state."""
        tab = self._tabs.currentIndex()
        if tab == 2:  # Named Pipe
            is_server = self._pipe_role_combo.currentText() == "Server"
            ct = ConnectionType.NAMED_PIPE_SERVER if is_server else ConnectionType.NAMED_PIPE_CLIENT
            return PortConfig(
                connection_type=ct,
                named_pipe=NamedPipeConfig(path=self._pipe_path_edit.text().strip()),
                name=self._name_edit.text().strip(),
                auto_reconnect=self._auto_reconnect_check.isChecked(),
            )
        if tab == 3:  # USB HID
            return PortConfig(
                connection_type=ConnectionType.USB_HID,
                hid=HIDConfig(
                    vendor_id=self._hid_vid_spin.value(),
                    product_id=self._hid_pid_spin.value(),
                    interface_number=self._hid_iface_spin.value(),
                    report_size=self._hid_report_spin.value(),
                ),
                name=self._name_edit.text().strip(),
                auto_reconnect=self._auto_reconnect_check.isChecked(),
            )
        if tab == 0:
            parity_map = {
                "None": Parity.NONE, "Odd": Parity.ODD, "Even": Parity.EVEN,
                "Mark": Parity.MARK, "Space": Parity.SPACE,
            }
            flow_map = {
                "None": FlowControl.NONE, "RTS/CTS": FlowControl.RTS_CTS,
                "XON/XOFF": FlowControl.XON_XOFF, "DTR/DSR": FlowControl.DTR_DSR,
            }
            stop_map = {"1": 1.0, "1.5": 1.5, "2": 2.0}

            try:
                baud = int(self._baud_combo.currentText())
            except ValueError:
                baud = 115200

            serial_cfg = SerialConfig(
                port=self._get_port_device(),
                baud_rate=baud,
                data_bits=int(self._data_bits_combo.currentText()),
                parity=parity_map.get(self._parity_combo.currentText(), Parity.NONE),
                stop_bits=stop_map.get(self._stop_bits_combo.currentText(), 1.0),
                flow_control=flow_map.get(self._flow_combo.currentText(), FlowControl.NONE),
                timeout=self._timeout_spin.value() / 1000.0,
            )
            return PortConfig(
                connection_type=ConnectionType.SERIAL,
                serial=serial_cfg,
                name=self._name_edit.text().strip(),
                auto_reconnect=self._auto_reconnect_check.isChecked(),
            )
        else:
            type_map = {
                "TCP Client": ConnectionType.TCP_CLIENT,
                "TCP Server": ConnectionType.TCP_SERVER,
                "UDP": ConnectionType.UDP,
            }
            net_type = self._net_type_combo.currentText()
            is_server = net_type == "TCP Server"
            net_cfg = NetworkConfig(
                host="" if is_server else self._host_edit.text().strip(),
                port=self._net_port_spin.value(),
                local_port=self._local_port_spin.value(),
            )
            return PortConfig(
                connection_type=type_map.get(net_type, ConnectionType.TCP_CLIENT),
                network=net_cfg,
                name=self._name_edit.text().strip(),
                auto_reconnect=self._auto_reconnect_check.isChecked(),
            )

    def preset_name(self) -> str:
        """Return the preset name to save under, or "" if none requested."""
        if self._preset_check.isChecked():
            return self._preset_name_edit.text().strip()
        return ""

    def set_config(self, config: PortConfig) -> None:
        """Populate the dialog from an existing PortConfig."""
        self._name_edit.setText(config.name)
        self._auto_reconnect_check.setChecked(config.auto_reconnect)

        if config.connection_type == ConnectionType.SERIAL:
            self._tabs.setCurrentIndex(0)
            sc = config.serial

            # Scan then select the saved port
            self._start_port_scan()
            # Port will be restored in _on_scan_finished via previous-device logic.
            # Also store it so the restore works before the scan completes.
            self._port_combo.setCurrentText(sc.port)

            self._baud_combo.setCurrentText(str(sc.baud_rate))
            self._data_bits_combo.setCurrentText(str(sc.data_bits))

            parity_rev = {
                Parity.NONE: "None", Parity.ODD: "Odd", Parity.EVEN: "Even",
                Parity.MARK: "Mark", Parity.SPACE: "Space",
            }
            self._parity_combo.setCurrentText(parity_rev.get(sc.parity, "None"))

            stop_rev = {1.0: "1", 1.5: "1.5", 2.0: "2"}
            self._stop_bits_combo.setCurrentText(stop_rev.get(sc.stop_bits, "1"))

            flow_rev = {
                FlowControl.NONE: "None", FlowControl.RTS_CTS: "RTS/CTS",
                FlowControl.XON_XOFF: "XON/XOFF", FlowControl.DTR_DSR: "DTR/DSR",
            }
            self._flow_combo.setCurrentText(flow_rev.get(sc.flow_control, "None"))
            self._timeout_spin.setValue(int(sc.timeout * 1000))
        elif config.connection_type in (
            ConnectionType.NAMED_PIPE_CLIENT, ConnectionType.NAMED_PIPE_SERVER
        ):
            self._tabs.setCurrentIndex(2)
            role = "Server" if config.connection_type == ConnectionType.NAMED_PIPE_SERVER else "Client"
            self._pipe_role_combo.setCurrentText(role)
            self._pipe_path_edit.setText(config.named_pipe.path)
        elif config.connection_type == ConnectionType.USB_HID:
            self._tabs.setCurrentIndex(3)
            self._hid_vid_spin.setValue(config.hid.vendor_id)
            self._hid_pid_spin.setValue(config.hid.product_id)
            self._hid_iface_spin.setValue(config.hid.interface_number)
            self._hid_report_spin.setValue(config.hid.report_size)
        else:
            self._tabs.setCurrentIndex(1)
            type_rev = {
                ConnectionType.TCP_CLIENT: "TCP Client",
                ConnectionType.TCP_SERVER: "TCP Server",
                ConnectionType.UDP: "UDP",
            }
            idx = self._net_type_combo.findText(
                type_rev.get(config.connection_type, "TCP Client")
            )
            if idx >= 0:
                self._net_type_combo.setCurrentIndex(idx)
            net = config.network
            self._host_edit.setText(net.host)
            self._net_port_spin.setValue(net.port)
            self._local_port_spin.setValue(net.local_port)
            self._update_net_form()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_port_device(self) -> str:
        """Return the raw device path from the combo (strips display label)."""
        data = self._port_combo.currentData()
        if data:
            return str(data)
        text = self._port_combo.currentText().strip()
        # Strip the label suffix added by _format_port_label
        return text.split("  —  ")[0].split("  [")[0].strip()
