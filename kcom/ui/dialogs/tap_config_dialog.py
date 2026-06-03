"""Tap / Monitor connection dialog — configure two ports + forwarding mode."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QThread, pyqtSignal as Signal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
    NetworkConfig,
    Parity,
    PortConfig,
    SerialConfig,
    TapConfig,
)
from kcom.utils.platform_utils import PortInfo, get_available_ports


_BAUD_RATES = [
    110, 300, 600, 1200, 2400, 4800, 9600, 14400, 19200,
    38400, 57600, 115200, 230400, 460800, 921600, 1000000,
]


class _ScanThread(QThread):
    finished = Signal(list)

    def __init__(self, include_virtual: bool) -> None:
        super().__init__()
        self._include_virtual = include_virtual

    def run(self) -> None:
        self.finished.emit(get_available_ports(include_virtual=self._include_virtual))


class _PortSelector(QGroupBox):
    """Compact port-configuration widget for one tap channel (A or B)."""

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(label, parent)
        self._scan_thread: _ScanThread | None = None
        self._build_ui()
        self._start_scan()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 12, 8, 8)

        # Connection type tabs
        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_serial_tab(), "Serial")
        self._tabs.addTab(self._build_network_tab(), "Network")
        layout.addWidget(self._tabs)

    def _build_serial_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(6)
        form.setContentsMargins(4, 8, 4, 4)

        row = QHBoxLayout()
        self._port_combo = QComboBox()
        self._port_combo.setEditable(True)
        self._port_combo.setPlaceholderText("Select or type a port…")
        self._port_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row.addWidget(self._port_combo, stretch=1)
        self._refresh_btn = QPushButton("⟳")
        self._refresh_btn.setFixedWidth(28)
        self._refresh_btn.setToolTip("Refresh port list")
        self._refresh_btn.clicked.connect(self._start_scan)
        row.addWidget(self._refresh_btn)
        form.addRow("Port:", row)

        self._baud_combo = QComboBox()
        self._baud_combo.setEditable(True)
        for b in _BAUD_RATES:
            self._baud_combo.addItem(str(b))
        self._baud_combo.setCurrentText("115200")
        form.addRow("Baud:", self._baud_combo)

        self._parity_combo = QComboBox()
        self._parity_combo.addItems(["None", "Odd", "Even"])
        form.addRow("Parity:", self._parity_combo)

        self._stop_combo = QComboBox()
        self._stop_combo.addItems(["1", "1.5", "2"])
        form.addRow("Stop bits:", self._stop_combo)

        return w

    def _build_network_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(6)
        form.setContentsMargins(4, 8, 4, 4)

        self._net_type_combo = QComboBox()
        self._net_type_combo.addItems(["TCP Client", "TCP Server", "UDP"])
        self._net_type_combo.currentIndexChanged.connect(self._update_net_fields)
        form.addRow("Type:", self._net_type_combo)

        self._host_label = QLabel("Host:")
        self._host_edit = QLineEdit("localhost")
        form.addRow(self._host_label, self._host_edit)

        self._port_label = QLabel("Port:")
        self._net_port_spin = QSpinBox()
        self._net_port_spin.setRange(1, 65535)
        self._net_port_spin.setValue(9000)
        form.addRow(self._port_label, self._net_port_spin)

        self._local_port_label = QLabel("Local Port:")
        self._local_port_spin = QSpinBox()
        self._local_port_spin.setRange(0, 65535)
        self._local_port_spin.setSpecialValueText("Auto (0)")
        form.addRow(self._local_port_label, self._local_port_spin)

        self._update_net_fields(0)
        return w

    def _update_net_fields(self, _: int = 0) -> None:
        net_type = self._net_type_combo.currentText()
        is_server = net_type == "TCP Server"
        is_udp    = net_type == "UDP"
        self._host_label.setVisible(not is_server)
        self._host_edit.setVisible(not is_server)
        self._port_label.setText("Listen Port:" if is_server else "Port:")
        self._local_port_label.setVisible(is_udp)
        self._local_port_spin.setVisible(is_udp)

    def _start_scan(self) -> None:
        if self._scan_thread and self._scan_thread.isRunning():
            return
        self._port_combo.setEnabled(False)
        self._refresh_btn.setEnabled(False)
        self._scan_thread = _ScanThread(include_virtual=True)
        self._scan_thread.finished.connect(self._on_scan_done)
        self._scan_thread.start()

    def _on_scan_done(self, ports: list) -> None:
        prev = self._port_combo.currentText()
        self._port_combo.blockSignals(True)
        self._port_combo.clear()
        for info in ports:
            label = info.device
            if info.description and info.description != info.device:
                label += f"  —  {info.description}"
            self._port_combo.addItem(label, userData=info.device)
        if prev:
            for i in range(self._port_combo.count()):
                if self._port_combo.itemData(i) == prev or self._port_combo.itemText(i).startswith(prev):
                    self._port_combo.setCurrentIndex(i)
                    break
            else:
                self._port_combo.setCurrentText(prev)
        self._port_combo.blockSignals(False)
        self._port_combo.setEnabled(True)
        self._refresh_btn.setEnabled(True)

    def _get_serial_port(self) -> str:
        idx = self._port_combo.currentIndex()
        if idx >= 0 and self._port_combo.itemData(idx):
            return self._port_combo.itemData(idx)
        return self._port_combo.currentText().split("  —  ")[0].strip()

    def get_config(self) -> PortConfig:
        if self._tabs.currentIndex() == 0:
            parity_map = {"None": Parity.NONE, "Odd": Parity.ODD, "Even": Parity.EVEN}
            stop_map   = {"1": 1.0, "1.5": 1.5, "2": 2.0}
            try:
                baud = int(self._baud_combo.currentText())
            except ValueError:
                baud = 115200
            return PortConfig(
                connection_type=ConnectionType.SERIAL,
                serial=SerialConfig(
                    port=self._get_serial_port(),
                    baud_rate=baud,
                    parity=parity_map.get(self._parity_combo.currentText(), Parity.NONE),
                    stop_bits=stop_map.get(self._stop_combo.currentText(), 1.0),
                ),
            )
        else:
            type_map = {
                "TCP Client": ConnectionType.TCP_CLIENT,
                "TCP Server": ConnectionType.TCP_SERVER,
                "UDP":        ConnectionType.UDP,
            }
            net_type  = self._net_type_combo.currentText()
            is_server = net_type == "TCP Server"
            return PortConfig(
                connection_type=type_map.get(net_type, ConnectionType.TCP_CLIENT),
                network=NetworkConfig(
                    host="" if is_server else self._host_edit.text().strip(),
                    port=self._net_port_spin.value(),
                    local_port=self._local_port_spin.value(),
                ),
            )

    def set_config(self, config: PortConfig) -> None:
        if config.connection_type == ConnectionType.SERIAL:
            self._tabs.setCurrentIndex(0)
            self._port_combo.setCurrentText(config.serial.port)
            self._baud_combo.setCurrentText(str(config.serial.baud_rate))
        else:
            self._tabs.setCurrentIndex(1)
            type_labels = {
                ConnectionType.TCP_CLIENT: "TCP Client",
                ConnectionType.TCP_SERVER: "TCP Server",
                ConnectionType.UDP: "UDP",
            }
            self._net_type_combo.setCurrentText(type_labels.get(config.connection_type, "TCP Client"))
            self._host_edit.setText(config.network.host)
            self._net_port_spin.setValue(config.network.port)
            self._local_port_spin.setValue(config.network.local_port)


from kcom.ui.dialogs.base_dialog import CenteredDialog


class TapConfigDialog(CenteredDialog):
    """Dialog for configuring a Tap / Monitor session (two ports)."""

    _FORWARD_LABELS = {
        "off":    "Monitor Only (no forwarding)",
        "a_to_b": "Forward A → B",
        "b_to_a": "Forward B → A",
        "both":   "Bidirectional Bridge (A ↔ B)",
    }

    def __init__(
        self,
        config: TapConfig | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tap / Monitor Configuration")
        self.setMinimumWidth(560)
        self.setModal(True)
        self._build_ui()
        if config is not None:
            self._load_config(config)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Name
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name (optional):"))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Leave blank for auto-name")
        name_row.addWidget(self._name_edit, stretch=1)
        layout.addLayout(name_row)

        # Port A
        self._port_a = _PortSelector("Port A", self)
        layout.addWidget(self._port_a)

        # Port B
        self._port_b = _PortSelector("Port B", self)
        layout.addWidget(self._port_b)

        # Forwarding mode
        fwd_group = QGroupBox("Forwarding Mode")
        fwd_form = QFormLayout(fwd_group)
        fwd_form.setSpacing(8)
        fwd_form.setContentsMargins(8, 12, 8, 8)

        self._fwd_combo = QComboBox()
        for key, label in self._FORWARD_LABELS.items():
            self._fwd_combo.addItem(label, userData=key)
        self._fwd_combo.setCurrentIndex(0)
        fwd_form.addRow("Mode:", self._fwd_combo)

        fwd_note = QLabel(
            "Monitor Only: passively capture both ports.\n"
            "Forward: data received on one port is re-sent on the other."
        )
        fwd_note.setStyleSheet("color: #7d8590; font-size: 11px;")
        fwd_form.addRow(fwd_note)
        layout.addWidget(fwd_group)

        # OK / Cancel
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_config(self) -> TapConfig:
        return TapConfig(
            port_a=self._port_a.get_config(),
            port_b=self._port_b.get_config(),
            forward_mode=self._fwd_combo.currentData() or "off",
            name=self._name_edit.text().strip(),
        )

    def _load_config(self, config: TapConfig) -> None:
        self._name_edit.setText(config.name)
        self._port_a.set_config(config.port_a)
        self._port_b.set_config(config.port_b)
        for i in range(self._fwd_combo.count()):
            if self._fwd_combo.itemData(i) == config.forward_mode:
                self._fwd_combo.setCurrentIndex(i)
                break
