"""Settings dialog — application preferences (Appearance / Terminal / Serial)."""
from __future__ import annotations

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)

from kcom.models.terminal_style import TerminalStyle, theme_defaults
from kcom.ui.dialogs.base_dialog import CenteredDialog

_GUIDE_BODY = r"""
<body>

<h1>KCom — Quick Start Guide</h1>

<h2>Step 1 — Open a Connection (Ctrl+N)</h2>
<p>The <b>Connection Configuration</b> dialog has four tabs:</p>

<h3>Serial</h3>
<p>Select a port from the dropdown (click <b>⟳ Refresh</b> to re-scan).
Set Baud Rate, Data Bits, Parity, Stop Bits to match your device.
Most devices: <b>115200, 8N1, no flow control</b>.</p>

<h3>Network</h3>
<table>
<tr><th>Type</th><th>When to use</th><th>Key fields</th></tr>
<tr><td>TCP Client</td><td>Your device is a TCP server</td><td>Host IP, Remote Port</td></tr>
<tr><td>TCP Server</td><td>Your device connects to KCom</td><td>Listen Port only</td></tr>
<tr><td>UDP</td><td>Connectionless datagram protocol</td><td>Remote Host/Port + Local Port</td></tr>
</table>

<h3>Named Pipe / Unix Socket</h3>
<p>For inter-process communication on the same machine.<br>
Windows: <code>\\.\pipe\mydevice</code> &nbsp;|&nbsp; Linux/macOS: <code>/tmp/mydevice.sock</code><br>
Choose <b>Client</b> if another app owns the pipe; <b>Server</b> if KCom should create it.</p>

<h3>USB HID</h3>
<p>Communicates directly with HID-class USB devices (custom embedded boards, game controllers, etc.).<br>
Click <b>⟳ Scan</b> to list connected devices. Select one — VID/PID fill automatically.
Adjust <b>Report Size</b> to match your device firmware (default 64 bytes).</p>
<div class="warn">Requires <code>pip install hidapi</code>. Use the <b>Install hidapi</b> button on the
USB HID tab if it is not installed, then restart KCom.</div>
<p><b>Linux udev rule</b> (run once, no sudo needed after):</p>
<p><code>echo 'SUBSYSTEM=="hidraw", ATTRS{idVendor}=="XXXX", ATTRS{idProduct}=="YYYY",
MODE="0666"' | sudo tee /etc/udev/rules.d/99-kcom-hid.rules</code><br>
Then: <code>sudo udevadm control --reload-rules &amp;&amp; sudo udevadm trigger</code></p>

<h2>Step 2 — Use the Terminal</h2>
<p>Each connection opens in its own tab. The terminal shows every received (green) and sent (blue) packet.</p>

<h3>Display Modes</h3>
<table>
<tr><th>Button</th><th>Shows</th><th>Best for</th></tr>
<tr><td>ASCII</td><td>Text + escape codes (\r \n \xNN)</td><td>AT commands, NMEA, text protocols</td></tr>
<tr><td>HEX</td><td>41 0D FF …</td><td>Binary protocols, debugging</td></tr>
<tr><td>DEC</td><td>65 13 255 …</td><td>Sensor values, numeric data</td></tr>
<tr><td>BIN</td><td>01000001 …</td><td>Bit-level inspection</td></tr>
<tr><td>MIXED</td><td>Separate columns per format</td><td>Full byte analysis</td></tr>
</table>
<p>Configure MIXED columns: <b>Settings → Terminal → Mixed Console Display</b>.</p>
<p>All columns auto-size to content. Use the <b>horizontal scrollbar</b> at the bottom
to pan when packets are wide.</p>

<h3>Timestamp (TS: dropdown)</h3>
<table>
<tr><th>Mode</th><th>Shows</th></tr>
<tr><td>Wall</td><td>14:23:05.123 — clock time</td></tr>
<tr><td>Delta</td><td>+17 ms — time since previous row</td></tr>
<tr><td>Elapsed</td><td>1 203 ms — time since clear</td></tr>
<tr><td>None</td><td>Column hidden</td></tr>
</table>

<h3>Send Bar</h3>
<p>Type data → select format (<b>ASCII</b> or <b>Hex</b>) → choose terminator → press <b>Enter</b> or <b>Send ⚡</b>.<br>
Hex example: <code>01 03 00 00 00 0A</code> — spaces are optional.</p>
<table>
<tr><th>Terminator</th><th>Bytes added</th></tr>
<tr><td>None</td><td>(nothing)</td></tr>
<tr><td>CR</td><td>0x0D</td></tr>
<tr><td>LF</td><td>0x0A</td></tr>
<tr><td>CR+LF</td><td>0x0D 0x0A — most common for AT commands</td></tr>
</table>

<h1>TX Sequences</h1>
<p>Saved, optionally repeating byte packets. Click <b>+ Add</b> in the Sequences panel.</p>
<table>
<tr><th>Field</th><th>Description</th></tr>
<tr><td>Encoding</td><td>hex / ascii / dec / bin</td></tr>
<tr><td>Data</td><td>Payload bytes in chosen encoding</td></tr>
<tr><td>Checksum</td><td>None / XOR / Sum8 / CRC-8 / CRC-16 Modbus / CRC-32 — auto-appended</td></tr>
<tr><td>Repeat Count</td><td>0 = infinite, N = send N times</td></tr>
<tr><td>Repeat Interval</td><td>ms between sends</td></tr>
<tr><td>Byte Delay</td><td>ms between individual bytes (0 = burst)</td></tr>
</table>

<h3>Hex Wildcards (hex encoding only)</h3>
<table>
<tr><th>Token</th><th>Meaning</th></tr>
<tr><td><code>?</code></td><td>Random byte 0x00–0xFF each send</td></tr>
<tr><td><code>#</code></td><td>Auto-increment counter (wraps 0–255)</td></tr>
<tr><td><code>^XY</code></td><td>Random byte masked by 0xXY</td></tr>
<tr><td><code>&lt;Name&gt;</code></td><td>Named value from the sequence's value table</td></tr>
</table>

<p>Click <b>▶ Send</b> to send once or start repeating. Click <b>■ Stop</b> to stop.
Running sequences highlight matching RX rows in the terminal in the sequence's color.
Use <b>⧉ Dup</b> to duplicate a sequence for variations.</p>

<h1>RX Triggers</h1>
<p>Watch incoming data and fire an action when a pattern matches. Click <b>+ Add</b> in the Triggers panel.</p>
<table>
<tr><th>Match Type</th><th>Meaning</th></tr>
<tr><td>contains</td><td>Pattern anywhere in the RX chunk</td></tr>
<tr><td>starts_with</td><td>Chunk starts with pattern</td></tr>
<tr><td>ends_with</td><td>Chunk ends with pattern</td></tr>
<tr><td>exact</td><td>Chunk is exactly the pattern</td></tr>
<tr><td>regex</td><td>Regular expression (Latin-1 bytes)</td></tr>
</table>
<table>
<tr><th>Action</th><th>Result</th></tr>
<tr><td>log</td><td>Writes a tagged line to the session log</td></tr>
<tr><td>notify</td><td>Status-bar message for 4 s</td></tr>
<tr><td>stop</td><td>Disconnects the port</td></tr>
<tr><td>send_sequence</td><td>Fires a TX sequence automatically (auto-reply)</td></tr>
</table>
<p>Enable: click <b>▶ Start</b> (turns to ■ Stop when active). Enabled triggers
retroactively highlight all matching existing rows.</p>

<h1>Logging</h1>
<p>Use the <b>Log Panel</b> (bottom). Select a folder and format, then click Start.</p>
<table>
<tr><th>Format</th><th>Contents</th></tr>
<tr><td>Text</td><td>Timestamp, direction, hex + ASCII sidebar</td></tr>
<tr><td>CSV</td><td>Timestamp, direction, hex, ASCII (Excel-ready)</td></tr>
<tr><td>HTML</td><td>Color-coded web page</td></tr>
<tr><td>Hex Dump</td><td>Wireshark-style 16-byte rows with offset column</td></tr>
</table>

<h1>Tap / Monitor Mode (Ctrl+Shift+T)</h1>
<p>Sniff traffic between two devices. Configure Port A, Port B, and a Forward Mode:</p>
<table>
<tr><th>Forward Mode</th><th>Behaviour</th></tr>
<tr><td>Off (Monitor)</td><td>Read-only — no forwarding</td></tr>
<tr><td>A → B</td><td>Data from A is forwarded to B</td></tr>
<tr><td>B → A</td><td>Data from B is forwarded to A</td></tr>
<tr><td>Bridge</td><td>Full bidirectional transparent bridge</td></tr>
</table>

<h1>Find &amp; Filter</h1>
<p><b>Filter box</b> (toolbar) — hides non-matching rows in real time:</p>
<ul>
<li><code>dir:rx</code> — show only RX rows</li>
<li><code>hex:02 07</code> — rows containing byte sequence</li>
<li><code>kind:data</code> — data rows only (hide info/errors)</li>
<li><code>hello</code> — plain text substring match</li>
</ul>
<p><b>Find bar (Ctrl+F)</b> — highlights and jumps between matching rows. Press Esc to close.</p>

<h1>Keyboard Shortcuts</h1>
<table>
<tr><th>Shortcut</th><th>Action</th></tr>
<tr><td>Ctrl+N</td><td>New Connection</td></tr>
<tr><td>Ctrl+Shift+T</td><td>New Tap Connection</td></tr>
<tr><td>Ctrl+O</td><td>Open Project</td></tr>
<tr><td>Ctrl+S</td><td>Save Project</td></tr>
<tr><td>Ctrl+W</td><td>Close Current Tab</td></tr>
<tr><td>Ctrl+L</td><td>Clear Terminal</td></tr>
<tr><td>Ctrl+T</td><td>Toggle Dark / Light Theme</td></tr>
<tr><td>Ctrl+,</td><td>Settings</td></tr>
<tr><td>Ctrl+F</td><td>Find in Terminal</td></tr>
<tr><td>Ctrl+Shift+S</td><td>Toggle Script Panel</td></tr>
<tr><td>F1</td><td>Help Browser</td></tr>
<tr><td>F11</td><td>Full Screen</td></tr>
<tr><td>Enter</td><td>Send (in terminal input)</td></tr>
</table>

<h1>Python Scripting</h1>
<p>Open the Script Panel (<b>Ctrl+Shift+S</b>) or run headless:</p>
<p><code>python main.py --run script.py --invisible project.kcom</code></p>
<p>Available in scripts: <code>kcom.send(data)</code> · <code>kcom.start_logging(path)</code>
· <code>kcom.stop_logging()</code> · <code>on_receive(data, ts)</code> callback.</p>

<h1>Troubleshooting</h1>
<table>
<tr><th>Problem</th><th>Fix</th></tr>
<tr><td>Serial port not listed</td><td><code>sudo usermod -aG dialout $USER</code> then re-login, or Tools → Fix Port Permissions</td></tr>
<tr><td>Connected but no data</td><td>Check baud rate / parity — switch to HEX to see raw bytes</td></tr>
<tr><td>USB HID access denied</td><td>Add udev rule (see USB HID section above)</td></tr>
<tr><td>TCP connection refused</td><td>Verify server is running: <code>nc -vz host port</code></td></tr>
<tr><td>Trigger never fires</td><td>Check pattern encoding (hex vs ascii) and click ▶ Start</td></tr>
<tr><td>High CPU usage</td><td>Settings → Advanced → set Render Throttle (e.g. 200000)</td></tr>
</table>

</body>
</html>
"""


def _guide_html(is_dark: bool) -> str:
    if is_dark:
        css = """
        body { color: #cdd6f4; background: #1e1e2e; font-family: sans-serif;
               font-size: 13px; margin: 16px; line-height: 1.5; }
        h1   { color: #cba6f7; border-bottom: 1px solid #45475a; padding-bottom: 4px; }
        h2   { color: #89b4fa; margin-top: 20px; }
        h3   { color: #a6e3a1; margin-top: 14px; }
        code { background: #313244; color: #f38ba8; padding: 1px 4px;
               border-radius: 3px; font-family: monospace; }
        table{ border-collapse: collapse; width: 100%; margin: 8px 0; }
        th   { background: #313244; color: #cdd6f4; text-align: left;
               padding: 5px 8px; border: 1px solid #45475a; }
        td   { padding: 4px 8px; border: 1px solid #45475a; }
        tr:nth-child(even) td { background: #181825; }
        ul   { margin: 6px 0 6px 20px; }
        .note{ background: #1c2b1c; border-left: 3px solid #a6e3a1;
               padding: 6px 10px; margin: 8px 0; border-radius: 3px; }
        .warn{ background: #2b1c1c; border-left: 3px solid #f38ba8;
               padding: 6px 10px; margin: 8px 0; border-radius: 3px; }
        """
    else:
        css = """
        body { color: #24292f; background: #ffffff; font-family: sans-serif;
               font-size: 13px; margin: 16px; line-height: 1.5; }
        h1   { color: #8250df; border-bottom: 1px solid #d0d7de; padding-bottom: 4px; }
        h2   { color: #0969da; margin-top: 20px; }
        h3   { color: #1a7f37; margin-top: 14px; }
        code { background: #f6f8fa; color: #cf222e; padding: 1px 4px;
               border-radius: 3px; font-family: monospace; border: 1px solid #d0d7de; }
        table{ border-collapse: collapse; width: 100%; margin: 8px 0; }
        th   { background: #f6f8fa; color: #24292f; text-align: left;
               padding: 5px 8px; border: 1px solid #d0d7de; }
        td   { padding: 4px 8px; border: 1px solid #d0d7de; }
        tr:nth-child(even) td { background: #f6f8fa; }
        ul   { margin: 6px 0 6px 20px; }
        .note{ background: #dafbe1; border-left: 3px solid #1a7f37;
               padding: 6px 10px; margin: 8px 0; border-radius: 3px; }
        .warn{ background: #fff8c5; border-left: 3px solid #9a6700;
               padding: 6px 10px; margin: 8px 0; border-radius: 3px; }
        """
    return f"<html><head><style>{css}</style></head>" + _GUIDE_BODY


class _ColorButton(QWidget):
    """A push-button that shows a color swatch and opens QColorDialog on click.

    ``value`` is the hex color string (e.g. ``"#3fb950"``).
    Empty string means "use theme default"; the swatch shows the resolved color.
    """

    def __init__(
        self,
        default_hex: str = "#000000",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._value: str = ""          # "" = user hasn't overridden
        self._default_hex = default_hex

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)

        self._btn = QPushButton()
        self._btn.setFixedSize(80, 26)
        self._btn.setToolTip("Click to pick a color")
        self._btn.clicked.connect(self._pick)
        row.addWidget(self._btn)

        self._reset_btn = QPushButton("Reset")
        self._reset_btn.setFixedSize(54, 26)
        self._reset_btn.setToolTip("Restore theme default")
        self._reset_btn.clicked.connect(self._reset)
        row.addWidget(self._reset_btn)

        row.addStretch()
        self._refresh_swatch()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def value(self) -> str:
        """The user-chosen hex string, or ``""`` if using theme default."""
        return self._value

    @value.setter
    def value(self, v: str) -> None:
        self._value = v or ""
        self._refresh_swatch()

    def set_default(self, hex_color: str) -> None:
        """Update the fallback color shown when value is empty."""
        self._default_hex = hex_color
        self._refresh_swatch()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _effective_hex(self) -> str:
        return self._value if self._value else self._default_hex

    def _refresh_swatch(self) -> None:
        hex_color = self._effective_hex()
        c = QColor(hex_color)
        # Choose label text color for legibility
        luminance = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
        text_color = "#000000" if luminance > 128 else "#ffffff"
        label = self._value if self._value else "(default)"
        self._btn.setStyleSheet(
            f"QPushButton {{ background: {hex_color}; color: {text_color}; "
            f"border: 1px solid #7d8590; border-radius: 4px; "
            f"font-size: 9px; }}"
        )
        self._btn.setText(label)

    def _pick(self) -> None:
        initial = QColor(self._effective_hex())
        color = QColorDialog.getColor(
            initial, self, "Pick Color",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if color.isValid():
            self._value = color.name()
            self._refresh_swatch()

    def _reset(self) -> None:
        self._value = ""
        self._refresh_swatch()


class SettingsDialog(CenteredDialog):
    """Application settings — three tabs: Appearance, Terminal, Serial."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(520)
        self.setModal(True)

        self._settings = QSettings("KCom", "KCom")
        self._build_ui()
        self._load_settings()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(10)

        tabs = QTabWidget()
        root.addWidget(tabs)

        tabs.addTab(self._build_appearance_tab(), "Appearance")
        tabs.addTab(self._build_terminal_tab(),   "Terminal")
        tabs.addTab(self._build_serial_tab(),     "Serial")
        tabs.addTab(self._build_advanced_tab(),   "Advanced")
        tabs.addTab(self._build_guide_tab(),      "Guide")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save_settings)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _build_appearance_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 12, 12, 12)

        box = QGroupBox("Appearance")
        form = QFormLayout(box)
        form.setSpacing(8)

        self._theme_combo = QComboBox()
        self._theme_combo.addItems(["Dark", "Light"])
        form.addRow("Theme:", self._theme_combo)

        self._font_family_combo = QComboBox()
        for fam in ["Cascadia Code", "Consolas", "Courier New", "Fira Code",
                     "JetBrains Mono", "Monospace", "Source Code Pro"]:
            self._font_family_combo.addItem(fam)
        form.addRow("Terminal font:", self._font_family_combo)

        self._font_size_spin = QSpinBox()
        self._font_size_spin.setRange(7, 24)
        self._font_size_spin.setSuffix(" pt")
        self._font_size_spin.setValue(10)
        form.addRow("Font size:", self._font_size_spin)

        self._ts_format_combo = QComboBox()
        self._ts_format_combo.addItems(["Wall", "Delta", "Elapsed", "None"])
        self._ts_format_combo.setToolTip(
            "Wall = HH:MM:SS.mmm · Delta = time since previous message · "
            "Elapsed = ms since session start · None = hide timestamps"
        )
        form.addRow("Timestamp:", self._ts_format_combo)

        # ASCII column rendering — replaces the legacy show_ctrl_chars checkbox
        self._ascii_render_combo = QComboBox()
        self._ascii_render_combo.addItems([
            "Multi-line  (Docklight-style — \\r\\n become real line breaks)",
            "Control labels  (<CR><LF><NUL> etc.)",
            "Escape sequences  (legacy \\r\\n literals)",
        ])
        self._ascii_render_combo.setToolTip(
            "How the ASCII column renders carriage returns, line feeds and "
            "other control bytes.\n\n"
            "• Multi-line   — best for terminal-style log output (ESP32, AT commands).\n"
            "• Control labels — keep everything on one row but show <CR>/<LF> tags.\n"
            "• Escape sequences — original behaviour, shows literal \\r\\n."
        )
        form.addRow("ASCII rendering:", self._ascii_render_combo)
        # Kept as a hidden attribute so the rest of the dialog logic
        # (load / save) still has something to read for the legacy field.
        self._ctrl_chars_check = QCheckBox()
        self._ctrl_chars_check.setVisible(False)

        layout.addWidget(box)
        layout.addStretch()
        return w

    def _build_terminal_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 12, 12, 12)

        hint = QLabel(
            "Override terminal colors. Click a swatch to pick; "
            "\"Reset\" restores the active theme's default."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #7d8590; font-size: 10px;")
        layout.addWidget(hint)

        box = QGroupBox("Colors")
        form = QFormLayout(box)
        form.setSpacing(8)

        self._rx_color_btn  = _ColorButton()
        self._tx_color_btn  = _ColorButton()
        self._bg_color_btn  = _ColorButton()
        self._hl_color_btn  = _ColorButton()

        form.addRow("RX data color:",       self._rx_color_btn)
        form.addRow("TX data color:",       self._tx_color_btn)
        form.addRow("Background color:",    self._bg_color_btn)
        form.addRow("Trigger highlight:",   self._hl_color_btn)

        layout.addWidget(box)

        # ── Mixed console display ────────────────────────────────────────
        mixed_box = QGroupBox("Mixed Console Display")
        mixed_vbox = QVBoxLayout(mixed_box)
        mixed_vbox.setSpacing(6)

        mixed_desc = QLabel(
            "When the terminal is set to <b>Mixed</b> mode, each byte is shown "
            "as the selected formats combined with a · separator.<br>"
            "Example with Hex + ASCII: <tt>41·A  0D··  FF··</tt><br>"
            "Select at least one format; order follows the checkboxes top-to-bottom."
        )
        mixed_desc.setWordWrap(True)
        mixed_desc.setStyleSheet("color: #7d8590; font-size: 10px;")
        mixed_vbox.addWidget(mixed_desc)

        self._mix_hex_chk   = QCheckBox("Hex    (41, 0D, FF …)")
        self._mix_ascii_chk = QCheckBox("ASCII  (printable chars, · for non-printable)")
        self._mix_dec_chk   = QCheckBox("Dec    (65, 13, 255 …)")
        self._mix_bin_chk   = QCheckBox("Bin    (01000001, 00001101 …)")

        mixed_vbox.addWidget(self._mix_hex_chk)
        mixed_vbox.addWidget(self._mix_ascii_chk)
        mixed_vbox.addWidget(self._mix_dec_chk)
        mixed_vbox.addWidget(self._mix_bin_chk)

        # Enforce: at least one must stay checked
        for chk in (self._mix_hex_chk, self._mix_ascii_chk,
                    self._mix_dec_chk, self._mix_bin_chk):
            chk.clicked.connect(self._enforce_mixed_minimum)

        layout.addWidget(mixed_box)
        layout.addStretch()

        # Keep swatch defaults in sync when theme combo changes
        self._theme_combo_ref: QComboBox | None = None  # wired after build
        return w

    def _enforce_mixed_minimum(self) -> None:
        """Prevent the user from unchecking the last mixed-mode checkbox."""
        checks = [self._mix_hex_chk, self._mix_ascii_chk,
                  self._mix_dec_chk, self._mix_bin_chk]
        if not any(c.isChecked() for c in checks):
            # Re-enable the one that was just unchecked
            self.sender().setChecked(True)

    def _build_serial_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 12, 12, 12)

        box = QGroupBox("Serial Defaults")
        form = QFormLayout(box)
        form.setSpacing(8)

        self._default_baud_combo = QComboBox()
        for br in [9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600]:
            self._default_baud_combo.addItem(str(br))
        self._default_baud_combo.setCurrentText("115200")
        form.addRow("Default baud rate:", self._default_baud_combo)

        layout.addWidget(box)
        layout.addStretch()
        return w

    def _build_advanced_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 12, 12, 12)

        hint = QLabel(
            "Expert options — changes take effect on next application launch "
            "unless noted otherwise."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #7d8590; font-size: 10px;")
        layout.addWidget(hint)

        box = QGroupBox("Performance")
        form = QFormLayout(box)
        form.setSpacing(8)

        self._priority_combo = QComboBox()
        self._priority_combo.addItems(["Normal", "Above Normal", "High", "Below Normal", "Idle"])
        self._priority_combo.setToolTip(
            "OS process priority for KCom. 'High' may improve latency at fast baud rates "
            "but can starve other apps."
        )
        form.addRow("Process priority:", self._priority_combo)

        self._render_throttle_spin = QSpinBox()
        self._render_throttle_spin.setRange(0, 10_000_000)
        self._render_throttle_spin.setSingleStep(10_000)
        self._render_throttle_spin.setSpecialValueText("No limit (0)")
        self._render_throttle_spin.setSuffix(" bytes/s")
        self._render_throttle_spin.setToolTip(
            "Stop rendering incoming data in the terminal above this rate. "
            "Logging and triggers still run. 0 = always render."
        )
        form.addRow("Disable rendering above:", self._render_throttle_spin)

        self._rx_cap_spin = QSpinBox()
        self._rx_cap_spin.setRange(0, 1_000_000)
        self._rx_cap_spin.setSingleStep(10_000)
        self._rx_cap_spin.setSpecialValueText("Default (100 000)")
        self._rx_cap_spin.setSuffix(" chunks")
        self._rx_cap_spin.setToolTip(
            "Override the RX ring buffer size (number of receive chunks kept in memory). "
            "0 = use the built-in default of 100 000."
        )
        form.addRow("RX ring buffer cap:", self._rx_cap_spin)

        layout.addWidget(box)

        # ── HTTP/JSON API ─────────────────────────────────────────────
        from kcom.api.server import _API_AVAILABLE
        api_box = QGroupBox("HTTP / JSON API")
        api_form = QFormLayout(api_box)
        api_form.setSpacing(8)

        if not _API_AVAILABLE:
            hint_lbl = QLabel(
                "fastapi / uvicorn not found — restart KCom to auto-install."
            )
            hint_lbl.setWordWrap(True)
            hint_lbl.setStyleSheet("color: #8b949e; font-size: 10px;")
            api_form.addRow(hint_lbl)

        self._api_enable_check = QCheckBox("Enable HTTP/JSON API server on startup")
        self._api_enable_check.setEnabled(_API_AVAILABLE)
        api_form.addRow(self._api_enable_check)

        self._api_port_spin = QSpinBox()
        self._api_port_spin.setRange(1024, 65535)
        self._api_port_spin.setValue(8765)
        self._api_port_spin.setEnabled(_API_AVAILABLE)
        self._api_port_spin.setToolTip(
            "TCP port the API server listens on (127.0.0.1 only)."
        )
        api_form.addRow("API port:", self._api_port_spin)

        layout.addWidget(api_box)
        layout.addStretch()
        return w

    def _build_guide_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        is_dark = self._settings.value("theme", "Dark", type=str).lower() == "dark"
        browser = QTextBrowser()
        browser.setOpenExternalLinks(False)
        browser.setMinimumHeight(420)
        browser.setHtml(_guide_html(is_dark))
        layout.addWidget(browser)
        return w

    # ------------------------------------------------------------------
    # Settings persistence
    # ------------------------------------------------------------------

    def _load_settings(self) -> None:
        # Appearance tab
        theme = self._settings.value("theme", "Dark", type=str)
        # findText is case-sensitive; try both capitalised and as-stored.
        idx = self._theme_combo.findText(theme.capitalize())
        if idx < 0:
            idx = self._theme_combo.findText(theme)
        if idx >= 0:
            self._theme_combo.setCurrentIndex(idx)

        font_fam = self._settings.value("terminal_font_family", "Cascadia Code", type=str)
        idx = self._font_family_combo.findText(font_fam)
        if idx >= 0:
            self._font_family_combo.setCurrentIndex(idx)

        font_size = self._settings.value("terminal_font_size", 10, type=int)
        self._font_size_spin.setValue(font_size)

        # Terminal colors — load user overrides, update swatch defaults
        from kcom.core.settings_store import SettingsStore
        store = SettingsStore()
        style = store.get_terminal_style()
        is_dark = theme.lower() == "dark"
        defaults = theme_defaults(is_dark)

        self._rx_color_btn.set_default(defaults["rx_color"])
        self._tx_color_btn.set_default(defaults["tx_color"])
        self._bg_color_btn.set_default(defaults["bg_color"])
        self._hl_color_btn.set_default(defaults["trigger_highlight_color"])

        self._rx_color_btn.value = style.rx_color
        self._tx_color_btn.value = style.tx_color
        self._bg_color_btn.value = style.bg_color
        self._hl_color_btn.value = style.trigger_highlight_color

        ts_fmt = style.timestamp_format or "wall"
        ts_idx = self._ts_format_combo.findText(ts_fmt.capitalize())
        if ts_idx >= 0:
            self._ts_format_combo.setCurrentIndex(ts_idx)

        self._ctrl_chars_check.setChecked(bool(style.show_ctrl_chars))

        # ASCII rendering combo — map model value to combo index.
        _ASCII_ORDER = ["multiline", "ctrl", "escape"]
        ar = (style.ascii_render or "multiline")
        if ar not in _ASCII_ORDER:
            ar = "multiline"
        self._ascii_render_combo.setCurrentIndex(_ASCII_ORDER.index(ar))

        # Serial tab
        baud = self._settings.value("default_baud_rate", "115200", type=str)
        idx = self._default_baud_combo.findText(baud)
        if idx >= 0:
            self._default_baud_combo.setCurrentIndex(idx)

        # Advanced tab
        _priority_labels = {
            "normal": "Normal", "above_normal": "Above Normal", "high": "High",
            "below_normal": "Below Normal", "idle": "Idle",
        }
        priority = store.get_process_priority()
        p_idx = self._priority_combo.findText(_priority_labels.get(priority, "Normal"))
        if p_idx >= 0:
            self._priority_combo.setCurrentIndex(p_idx)

        self._render_throttle_spin.setValue(store.get_render_throttle_bps())
        self._rx_cap_spin.setValue(store.get_rx_buffer_cap())
        self._api_enable_check.setChecked(store.get_api_enabled())
        self._api_port_spin.setValue(store.get_api_port())

        # Mixed terminal layers
        layers = store.get_mixed_layers()
        self._mix_hex_chk.setChecked("hex"   in layers)
        self._mix_ascii_chk.setChecked("ascii" in layers)
        self._mix_dec_chk.setChecked("dec"   in layers)
        self._mix_bin_chk.setChecked("bin"   in layers)

        # Wire theme combo → refresh swatch defaults
        self._theme_combo.currentTextChanged.connect(self._on_theme_preview_changed)

    def _on_theme_preview_changed(self, theme_text: str) -> None:
        """Update swatch default colors when the user previews a different theme."""
        defaults = theme_defaults(theme_text.lower() == "dark")
        self._rx_color_btn.set_default(defaults["rx_color"])
        self._tx_color_btn.set_default(defaults["tx_color"])
        self._bg_color_btn.set_default(defaults["bg_color"])
        self._hl_color_btn.set_default(defaults["trigger_highlight_color"])

    def _save_settings(self) -> None:
        self._settings.setValue("theme", self._theme_combo.currentText())
        self._settings.setValue(
            "terminal_font_family",
            self._font_family_combo.currentText(),
        )
        self._settings.setValue("terminal_font_size", self._font_size_spin.value())
        self._settings.setValue(
            "default_baud_rate",
            self._default_baud_combo.currentText(),
        )

        from kcom.core.settings_store import SettingsStore
        store = SettingsStore()
        style = TerminalStyle(
            rx_color=               self._rx_color_btn.value,
            tx_color=               self._tx_color_btn.value,
            bg_color=               self._bg_color_btn.value,
            trigger_highlight_color= self._hl_color_btn.value,
            font_size=              self._font_size_spin.value(),
            font_family=            self._font_family_combo.currentText(),
            timestamp_format=       self._ts_format_combo.currentText().lower(),
            show_ctrl_chars=        self._ctrl_chars_check.isChecked(),
            ascii_render=           ["multiline", "ctrl", "escape"][
                                        self._ascii_render_combo.currentIndex()
                                    ],
        )
        store.set_terminal_style(style)

        _priority_keys = {
            "Normal": "normal", "Above Normal": "above_normal", "High": "high",
            "Below Normal": "below_normal", "Idle": "idle",
        }
        store.set_process_priority(
            _priority_keys.get(self._priority_combo.currentText(), "normal")
        )
        store.set_render_throttle_bps(self._render_throttle_spin.value())
        store.set_rx_buffer_cap(self._rx_cap_spin.value())
        store.set_api_enabled(self._api_enable_check.isChecked())
        store.set_api_port(self._api_port_spin.value())

        # Mixed layers — preserve order: hex → ascii → dec → bin
        mixed_layers = []
        if self._mix_hex_chk.isChecked():   mixed_layers.append("hex")
        if self._mix_ascii_chk.isChecked(): mixed_layers.append("ascii")
        if self._mix_dec_chk.isChecked():   mixed_layers.append("dec")
        if self._mix_bin_chk.isChecked():   mixed_layers.append("bin")
        store.set_mixed_layers(mixed_layers)

    # ------------------------------------------------------------------
    # Public helpers (called by MainWindow)
    # ------------------------------------------------------------------

    def selected_theme(self) -> str:
        return self._theme_combo.currentText().lower()

    def terminal_font_size(self) -> int:
        return self._font_size_spin.value()

    def terminal_style(self) -> TerminalStyle:
        """Return the TerminalStyle the user has configured."""
        return TerminalStyle(
            rx_color=               self._rx_color_btn.value,
            tx_color=               self._tx_color_btn.value,
            bg_color=               self._bg_color_btn.value,
            trigger_highlight_color= self._hl_color_btn.value,
            font_size=              self._font_size_spin.value(),
            font_family=            self._font_family_combo.currentText(),
            timestamp_format=       self._ts_format_combo.currentText().lower(),
            show_ctrl_chars=        self._ctrl_chars_check.isChecked(),
            ascii_render=           ["multiline", "ctrl", "escape"][
                                        self._ascii_render_combo.currentIndex()
                                    ],
        )


