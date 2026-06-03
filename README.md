<div align="center">

<img src="kcom/resources/icons/kcom_logo.png" alt="KCom Logo" width="160" height="160" />

# KCom

### Professional Serial & Network Communication Studio

*Talk to any port. See every byte. Automate the rest.*

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![PyQt6](https://img.shields.io/badge/PyQt6-6.6%2B-41CD52?style=for-the-badge&logo=qt&logoColor=white)](https://www.riverbankcomputing.com/software/pyqt/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20Windows-blue?style=for-the-badge)](#build--install--run)
[![Release](https://img.shields.io/badge/Release-v1.0.0-success?style=for-the-badge)](https://github.com/Karthik-Gnanaguru/KCOM/tags)

**[Features](#-features)** · **[Build](#-build--install--run)** · **[Walkthrough](#-first-use-walkthrough)** · **[Scripting](#-python-scripting-api)** · **[REST API](#-rest--websocket-api)**

</div>

---

KCom is a cross-platform desktop studio for communicating with hardware and network endpoints. Built with **Python 3.11+** and **PyQt6**, it combines a power-user terminal, scriptable automation, trigger/response logic, and a REST + WebSocket bridge — all in one window.

---

## ✨ Features

### 🔌 Universal Transports

| Transport | Direction | Notes |
|---|---|---|
| **Serial / UART** | RX + TX | RS-232, RS-485, USB-UART, hardware/software flow control |
| **TCP Client** | RX + TX | Connects to any TCP server |
| **TCP Server** | RX + TX | Listens for incoming clients; multi-client capable |
| **UDP** | RX + TX | Unicast send and receive |
| **USB HID** | RX + TX | Generic and vendor HID via `hidapi`, report-size aware |
| **Named Pipe** | RX + TX | Cross-platform IPC (`/tmp/...` on POSIX, `\\.\pipe\...` on Windows) |

Auto-reconnect is supported for Serial, TCP Client, and Named Pipe sessions.

---

### 🎯 Sequences (TX Automation)

- Encoding: HEX / ASCII / DEC / BIN
- Auto-checksum: **CRC-16 Modbus, CRC-32, CRC-8, XOR, SUM-8** — appended automatically with a configurable start offset
- Wildcard bytes: `?` random, `#` 8-bit counter, `^FF` masked-random, `<Name>` named value
- Terminator: none / CR / LF / CRLF
- Per-sequence **repeat count + interval**, **delay-before-send**, **inter-byte delay**
- Send Once or Start/Stop continuous transmission

---

### 🛎 Triggers (RX Automation)

- Match mode: **contains**
- Matched rows highlighted in the trigger's assigned color
- Pattern in HEX or ASCII
- Additional modes and actions are accessible through the `.kcom` JSON file

---

### 🔁 Tap / Bridge

- Forward bytes between two open sessions
- 4 modes: **Monitor Only · A → B · B → A · Bidirectional**
- Both endpoints share a single terminal with a per-row **Channel** column

---

### 🖥️ Structured Terminal

- 5 display modes: **ASCII · HEX · DEC · BIN · MIXED** — switch live without losing data
- 4 timestamp formats: **Wall · Delta · Elapsed · None**
- **Pause / Resume** with RX buffering — review one section while data keeps arriving
- **Filter bar DSL** — `dir:rx`, `dir:tx`, `hex:02 07`, `kind:data|info|error` + plain substring
- Direction-colored rows (RX green / TX blue); trigger-matched rows highlighted in the trigger's color

---

### 📝 Logging & Export

- Per-connection start/stop logging from the toolbar **Log** button
- Formats: **Text (.txt)** and **CSV (.csv)**
- Columns match the active display mode; switching modes mid-session is honored live
- Filter follows the screen — active filter DSL applies to the log file; clear the filter to resume full logging
- Background **writer thread** with bounded queue + drop-oldest — file I/O never blocks the UI
- Direction markers + ISO timestamps; inline **Annotation** markers via right-click menu
- A separate **`~/kcom-session.txt`** captures the complete unfiltered session activity across all open ports — every byte, every CONNECT/DISCONNECT event, every error
- Export terminal contents to a text file (`Ctrl+E`)
- **Copy as Table** / **Copy as CSV** via right-click menu

---

### 🐍 Python Scripting

- In-app **script editor** dock with Run / Stop (`F5`)
- `kcom.*` runtime API: `send`, `send_hex`, `send_text`, `on_receive`, `start_logging`, `stop_logging`, `log`, `sleep`, `file_input`, `file_output`, `exit`
- Run headlessly: `python main.py --invisible --run script.py`

---

### 🌐 REST + WebSocket API

- Optional **FastAPI + uvicorn** server (default port `8765`)
- Endpoints: `GET /sessions`, `GET /sessions/{id}`, `POST /sessions/{id}/send`
- Stream RX bytes via **WebSocket**: `/sessions/{id}/stream`
- Enable in **Settings → Advanced → HTTP/JSON API**

---

### 🎨 Themes & UX

- **Dark** and **Light** Qt stylesheets, live toggle (`Ctrl+T`)
- Welcome tab with one-click example projects
- **Help browser dock** with context-sensitive help (`F1`)
- Process priority setting (Idle … High) applied at startup
- Full keyboard navigation; shortcuts dialog at `Ctrl+Shift+/`
- **Tools → Diagnostics…** — live snapshot of sessions, threads, memory, queue depths + Force GC button

---

### 💾 Project Files

- Save and load everything as `.kcom` — plain JSON
- Open with `python main.py myproject.kcom` or **File → Open Project**

---

## ⚡ Performance & Robustness

KCom stays responsive under sustained high-throughput RX without losing a single byte. Three layered defenses keep the UI thread free:

| Layer | Mechanism | Result |
|---|---|---|
| **Protocol read** | All transports drain their socket/port in one `readAll()` call per `readyRead`; UDP merges every pending datagram into one emission | One signal per kernel-buffer cycle |
| **PortSession RX coalescer** | Bursts within an **8 ms / 8 KB** window are concatenated and fan out once through log / terminal / triggers / scripts / API | Verified **82× reduction** on small-packet floods (30k pkts × 100 B) |
| **UI render coalescer** | Terminal table batches inserts at ~60 FPS with `setUpdatesEnabled(False)`; row heights set per-row O(1) instead of Qt's `ResizeToContents` O(N) | 30k chunks render in **578 ms**, zero data loss |
| **Threaded log writer** | `LogManager` and `SessionLogger` push formatted lines to a bounded queue drained by a background thread; lazy 250 ms flush + drop-oldest if disk stalls | UI never blocks on disk I/O |

**Stress test results:**

| Test | Result |
|---|---|
| 5,000 multi-line ASCII chunks → terminal | Drains in 252 ms (~20k chunks/sec) |
| 30,000 × 100 B serial flood | 3 MB through PortSession in 13 ms; all bytes preserved |
| 5,000 × 256 B TCP burst (1.28 MB) | Received in 51 ms, 70× emit-coalescing |
| Pause ~30 s during flood, then resume | Drains in chunked batches; `set_paused(False)` returns in **0 ms** |

> **Live triage:** **Tools → Diagnostics…** shows per-session RX/TX byte counters, ring-buffer fill, dropped chunks, log writer queue drops, live process memory, and a **Force GC** button.

---

## 📦 Requirements

To build the executable you need:

- **Python 3.11+** with `pip`
- **OS:** Linux, macOS, or Windows (build natively per target — PyInstaller does not cross-compile)
- ~300 MB free disk for the build; ~62 MB for the final executable

All dependencies — PyQt6, pyserial, FastAPI, hidapi, themes, icons, and example projects — are bundled into the executable. End-users do **not** need Python installed.

---

## 🛠 Build → Install → Run

### Step 1 — Clone the source

```bash
git clone https://github.com/Karthik-Gnanaguru/KCOM.git
cd KCOM
```

### Step 2 — Build for your platform

** Linux**

```bash
chmod +x build/build_linux.sh
./build/build_linux.sh

```

Produces: `dist/KCom/KCom` *(folder bundle)* or `dist/KCom-linux-x86_64.AppImage` *(if `appimagetool` is on PATH)*

---

** macOS**

```bash
chmod +x build/build_macos.sh
./build/build_macos.sh
```

Produces: `dist/KCom.app` *(double-click to launch)* or `dist/KCom-macos.dmg` *(if `create-dmg` is installed via Homebrew)*

---

** Windows**

```bat
build\build_windows.bat
```

Produces: `dist\KCom\KCom.exe`

---

> Each build script: detects a usable Python, runs `pip install -r requirements.txt` + `pip install pyinstaller`, invokes PyInstaller against [`build/kcom.spec`](build/kcom.spec), then strips unused Qt6 modules via [`build/post_clean.py`](build/post_clean.py).
>
> First build: ~2–5 minutes. Rebuilds are fast.

### Step 3 — Run the executable

| OS | Command |
|---|---|
| ** Linux** | `./dist/KCom/KCom` or double-click `KCom-linux-x86_64.AppImage` |
| ** macOS** | `open dist/KCom.app` or double-click in Finder |
| ** Windows** | Double-click `dist\KCom\KCom.exe` or run from `cmd` |

### Step 4 — Install system-wide *(optional)*

**Linux**

```bash
sudo cp -r dist/KCom /opt/KCom
sudo ln -s /opt/KCom/KCom /usr/local/bin/kcom
```

Or for the AppImage:

```bash
chmod +x dist/KCom-linux-x86_64.AppImage
mv dist/KCom-linux-x86_64.AppImage ~/Applications/
```

**macOS**

```bash
cp -R dist/KCom.app /Applications/
```

Or mount the DMG and drag into Applications.

** Windows**

Copy `dist\KCom\` into `C:\Program Files\KCom\`, then create a Start menu or Desktop shortcut pointing to `KCom.exe`.

---

### Platform Notes

** Linux — serial port permissions**

```bash
sudo usermod -aG dialout $USER
```

Log out and back in after running this. Alternatively, use **Tools → Fix Port Permissions…** for a GUI wizard.

- **Wayland:** KCom forces the `xcb` backend automatically; no action needed.
- **USB HID** *(optional)*: `sudo apt install libhidapi-hidraw0`

---

** macOS — Gatekeeper (first launch)**

The build is not notarised. Right-click `KCom.app` → **Open**, then confirm in the dialog.

- **USB HID** *(optional)*: `brew install hidapi`

---

** Windows — SmartScreen**

The first launch may show "Windows protected your PC". Click **More info → Run anyway**. USB HID and serial ports work out of the box.

---

## ▶ Run from Source *(developer mode)*

```bash
git clone https://github.com/Karthik-Gnanaguru/KCOM.git
cd KCOM
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python main.py                   # auto-installs missing deps on first run
```

KCom detects missing packages (`PyQt6`, `pyserial`, `fastapi`, `uvicorn`) and runs `pip install -r requirements.txt` automatically on first launch.

---

## 🚀 First-Use Walkthrough

1. Click **`＋ New`** in the **Ports** panel (or `Ctrl+N`), pick a transport, fill in the settings, click **OK**.
2. Click **Connect** in the toolbar — the structured terminal tab opens.
3. Type bytes in the send bar (HEX or ASCII), press `Enter` or click **Send**.
4. Add a **Sequence** in the Sequences panel and click **Send Now** (or **Start** for repeated transmission).
5. Add an **RX Trigger** — matching rows are highlighted in the trigger's color and the configured action fires.
6. **File → Save Project** to write a `.kcom` file you can reload on any machine.

> **Pro tip:** Right-click any terminal row to *Create RX Trigger* or *Create TX Sequence* pre-filled with the selected bytes.

---

## 🖥️ Terminal Display Modes

| Mode | Sample Output |
|---|---|
| **ASCII** | `Hello\r\n` |
| **HEX** | `48 65 6C 6C 6F 0D 0A` |
| **DEC** | `72 101 108 108 111 13 10` |
| **BIN** | `01001000 01100101 01101100 01101100 01101111 00001101 00001010` |
| **MIXED** | `48 65 6C 6C 6F  ‖  Hello` *(HEX + ASCII side-by-side; configurable in Settings → Terminal)* |

Switch live without losing data using the mode buttons in the terminal toolbar. Double-click any column divider to auto-fit; drag to resize.

---

## 🔎 Filter & Find

**Find bar** (`Ctrl+F`) — search HEX or ASCII; `Enter` jumps to the next match; `▲ ▼` step through results; `Esc` closes.

**Filter bar DSL** — hides non-matching rows live:

| Token | Effect |
|---|---|
| `dir:rx` / `dir:tx` | Show only incoming / outgoing rows |
| `hex:02 07 A5` | Show rows whose payload contains this hex pattern |
| `kind:data` / `kind:info` / `kind:error` | Filter by row type |
| *(anything else)* | Plain substring match against the row's text |

---

## 🎯 Sequences & Triggers

```jsonc
// Sequence — Modbus FC03 with auto-CRC16
{
  "name": "Read HR 1-4",
  "data_str": "01 03 00 00 00 04",
  "encoding": "hex",
  "checksum": "crc16_modbus",   // appended automatically
  "repeat_count": 0,            // 0 = forever
  "repeat_interval_ms": 1000
}

// Trigger — fire on a Modbus exception (0x83)
{
  "name": "Modbus Exception",
  "match_type": "contains",
  "pattern": "01 83",
  "pattern_encoding": "hex",
  "action": "log",
  "color": "#f38ba8"
}
```

**Wildcard transmit bytes** (HEX encoding):

| Token | Meaning |
|---|---|
| `?` | Random byte (0x00–0xFF) per send |
| `#` | Incrementing 8-bit counter (wraps at 256) |
| `^FF` | Random byte ANDed with `0xFF` mask |
| `<Name>` | Named value, configurable per sequence in the editor |

---

## 🐍 Python Scripting API

```python
kcom.log("Starting test sequence")

# Send raw bytes / hex / text
kcom.send(b"\x01\x03\x00\x00\x00\x04")
kcom.send_hex("01 03 00 00 00 04")
kcom.send_text("AT+CSQ\r\n")

# React to incoming bytes
def on_rx(data: bytes, ts: float):
    kcom.log("got", data.hex())
kcom.on_receive(on_rx)

# Logging
kcom.start_logging("/tmp/capture.log")
kcom.sleep(5)
kcom.stop_logging()

# File helpers
data = kcom.file_input("/tmp/payload.bin")
kcom.file_output("/tmp/echo.bin", data)

kcom.log("Done")
kcom.exit()
```

Run inside the GUI (script panel, `F5`) **or** completely headless:

```bash
python main.py --invisible --run automation.py
```

---

## 🌐 REST + WebSocket API

Enable in **Settings → Advanced → HTTP/JSON API server** and restart KCom.

```bash
# List active sessions
curl http://localhost:8765/sessions

# Inspect one session
curl http://localhost:8765/sessions/SESSION_ID

# Send bytes (hex)
curl -X POST http://localhost:8765/sessions/SESSION_ID/send \
     -H "Content-Type: application/json" \
     -d '{"hex": "48656c6c6f"}'

# Send bytes (text)
curl -X POST http://localhost:8765/sessions/SESSION_ID/send \
     -H "Content-Type: application/json" \
     -d '{"text": "AT+CSQ\r\n"}'

# Stream RX bytes over WebSocket
# Frames: { session_id, direction, data_hex, ts }
wscat -c ws://localhost:8765/sessions/SESSION_ID/stream
```

---

## 📂 Example Projects

Open via **File → Open Example…** or from the Welcome tab.

| Project | File | Description |
|---|---|---|
| 🔁 **Loopback Test** | [`examples/loopback_test.kcom`](examples/loopback_test.kcom) | Serial loopback — PING sequence + PONG trigger, plus a wildcard counter frame with XOR checksum |
| 🌐 **TCP Echo Client** | [`examples/tcp_echo_client.kcom`](examples/tcp_echo_client.kcom) | Echo to `127.0.0.1:5000` (start `ncat -l 5000 -k -e /bin/cat` first) |
| ⚙️ **Modbus RTU Master** | [`examples/modbus_rtu_master.kcom`](examples/modbus_rtu_master.kcom) | FC01 / FC03 / FC06 with CRC-16 auto-append + exception trigger |

---

## 💾 Project File Format

`.kcom` files are plain JSON:

```jsonc
{
  "version": "1.1",
  "name": "My Project",
  "notes": "free-form notes...",
  "port_configs": [
    {
      "connection_type": "serial",
      "serial": { "port": "/dev/ttyUSB0", "baud_rate": 9600 },
      "name": "Modbus",
      "auto_reconnect": true
    }
  ],
  "sequences": [
    {
      "id": "seq-1",
      "name": "Hello",
      "data_str": "48 65 6C 6C 6F",
      "encoding": "hex",
      "terminator": "crlf",
      "checksum": "none",
      "repeat_count": 1,
      "repeat_interval_ms": 0
    }
  ],
  "triggers": [
    {
      "id": "trig-1",
      "name": "ACK",
      "match_type": "contains",
      "pattern": "OK",
      "pattern_encoding": "ascii",
      "action": "log",
      "color": "#f9e2af"
    }
  ],
  "tap_configs": []
}
```

---

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+N` | New connection |
| `Ctrl+O` | Open project |
| `Ctrl+S` | Save project |
| `Ctrl+E` | Export terminal contents |
| `Ctrl+W` | Close current connection / tab |
| `Ctrl+Q` | Exit KCom |
| `Ctrl+T` | Toggle light / dark theme |
| `Ctrl+L` | Clear terminal |
| `Ctrl+F` | Find in terminal |
| `F5` | Run current script |
| `F1` | Open context-sensitive help |
| `Ctrl+,` | Open Settings |

The full list is also available in **Help → Keyboard Shortcuts** (`Ctrl+Shift+/`).

---

## 📦 Python Dependencies

| Package | Min Version | Purpose |
|---|---|---|
| PyQt6 | 6.6.0 | UI framework |
| pyserial | 3.5 | Serial port access |
| hidapi | 0.14.0 | USB HID transport |
| fastapi | 0.110.0 | REST / WebSocket API server |
| uvicorn[standard] | 0.29.0 | ASGI runtime for the API server |

---

## 🧪 Running Tests

```bash
pip install ".[dev]" pytest-cov pytest-html

pytest                            # full suite
pytest tests/test_checksum.py     # single module
pytest -x                         # stop on first failure
```

Coverage focuses on the **core** layer and **models** — checksum, data pipeline, encoding, project manager, sequence runner, settings store, trigger engine, port/sequence/trigger models, and platform utils.

- HTML report: `tests/report.html`
- Coverage: `tests/coverage_html/index.html`

---

## 🧰 Troubleshooting

<details>
<summary><b>Serial port not listed</b></summary>

Check `ls /dev/ttyUSB*` or `ls /dev/ttyACM*` on Linux. Ensure your user is in the `dialout` group:

```bash
sudo usermod -aG dialout $USER
```

Log out and back in after running this. The **Tools → Fix Port Permissions…** wizard provides a GUI alternative.
</details>

<details>
<summary><b>USB HID: "native library not found"</b></summary>

Install the native hidapi library:

```bash
# Linux
sudo apt install libhidapi-hidraw0

# macOS
brew install hidapi
```

On Windows, the library is bundled automatically.
</details>

<details>
<summary><b>App exits immediately on Linux (Wayland)</b></summary>

KCom forces `QT_QPA_PLATFORM=xcb` automatically. If issues persist, launch with:

```bash
QT_QPA_PLATFORM=xcb python main.py
```
</details>

<details>
<summary><b>REST API unreachable on port 8765</b></summary>

Verify it is enabled in **Settings → Advanced → HTTP/JSON API server**, then restart KCom — the server only starts at boot. The port is configurable in the same dialog.
</details>

<details>
<summary><b>Build fails on Windows with "Python not found"</b></summary>

Install Python 3.11+ from [python.org](https://www.python.org/downloads/windows/) or:

```bat
winget install -e --id Python.Python.3.12
```

Tick **"Add python.exe to PATH"** during install, open a **new** terminal, and re-run `build\build_windows.bat`. The build script detects the Microsoft Store stub and rejects it with a helpful message.
</details>

---

## 🤝 Contributing

Issues and pull requests are welcome at [github.com/Karthik-Gnanaguru/KCOM](https://github.com/Karthik-Gnanaguru/KCOM).

1. Fork the repo and create a feature branch
2. `pip install ".[dev]"` and run `pytest` before opening a PR
3. Match existing code style — `black .` and `ruff check .`

---

## 📄 License

Released under the **MIT License** — see [`LICENSE`](LICENSE) for the full text.

---

<div align="center">

 Linux ·  macOS ·  Windows · Python 3.11+

</div>
