"""Bundled inline help content for the KCom help browser.

Each entry in ``TOPICS`` is a ``(title, html_body)`` pair.
``CONTEXT_MAP`` maps widget class names / object names to a topic title so the
F1 key can jump to the relevant section.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Topic content (HTML)
# ---------------------------------------------------------------------------

_STYLE = """
<style>
  body  { font-family: sans-serif; font-size: 12px; margin: 12px; }
  h2    { color: #8250df; border-bottom: 1px solid #7d859044; padding-bottom: 4px; }
  h3    { color: #89b4fa; margin-top: 14px; }
  code  { background: #2a2a3a; color: #a6e3a1; padding: 1px 4px; border-radius: 3px; }
  table { border-collapse: collapse; width: 100%; margin-top: 8px; }
  th    { background: #2a2a3a; color: #cba6f7; padding: 4px 8px; text-align: left; }
  td    { padding: 4px 8px; border-bottom: 1px solid #7d859022; }
  tr:nth-child(even) td { background: #ffffff0a; }
  .tip  { background: #1a2a1a; border-left: 3px solid #a6e3a1;
          padding: 6px 10px; margin: 8px 0; border-radius: 0 4px 4px 0; }
  .warn { background: #2a1a1a; border-left: 3px solid #f38ba8;
          padding: 6px 10px; margin: 8px 0; border-radius: 0 4px 4px 0; }
</style>
"""

TOPICS: list[tuple[str, str]] = [

    ("Overview", _STYLE + """
<h2>KCom — Quick Overview</h2>
<p>KCom is a professional serial &amp; network communication studio.
It lets you open multiple connections simultaneously and displays
incoming/outgoing data in colour-coded terminal tabs.</p>

<h3>Key Concepts</h3>
<table>
<tr><th>Concept</th><th>Description</th></tr>
<tr><td><b>Session</b></td><td>One active connection (serial port, TCP, UDP, pipe, HID)</td></tr>
<tr><td><b>Terminal</b></td><td>The scrolling data viewer for a session's RX/TX traffic</td></tr>
<tr><td><b>Sequence</b></td><td>A pre-defined byte string you can send on demand or on a timer</td></tr>
<tr><td><b>Trigger</b></td><td>A pattern that fires an auto-response when seen in RX data</td></tr>
<tr><td><b>Tap</b></td><td>Two-port monitor that shows traffic from both sides in one terminal</td></tr>
<tr><td><b>Script</b></td><td>Python script with access to all sessions via the <code>kcom</code> API</td></tr>
</table>

<div class="tip">
Press <b>F1</b> while focused on any panel to jump straight to its help page.
</div>
"""),

    ("Terminal", _STYLE + """
<h2>Terminal</h2>
<p>The terminal displays RX data (colour-coded) and echoes TX data in a separate colour.
Each tab is independent.</p>

<h3>Display Modes</h3>
<table>
<tr><th>Mode</th><th>Example</th></tr>
<tr><td>ASCII</td><td>Hello\\r\\n</td></tr>
<tr><td>HEX</td><td>48 65 6C 6C 6F 0D 0A</td></tr>
<tr><td>Mixed</td><td>48 65 6C 6C 6F <i>(H e l l o)</i></td></tr>
<tr><td>DEC</td><td>072 101 108 108 111</td></tr>
<tr><td>BIN</td><td>01001000 01100101 …</td></tr>
</table>

<h3>Keyboard Shortcuts</h3>
<table>
<tr><th>Key</th><th>Action</th></tr>
<tr><td><code>Ctrl+F</code></td><td>Open find bar</td></tr>
<tr><td><code>F3</code> / <code>Enter</code></td><td>Find next</td></tr>
<tr><td><code>Shift+F3</code></td><td>Find previous</td></tr>
<tr><td><code>Esc</code></td><td>Close find bar</td></tr>
<tr><td><code>Ctrl+C</code></td><td>Copy selected rows</td></tr>
</table>

<h3>Context Menu</h3>
<p>Right-click on any row to: Copy Hex / ASCII / Bytes, create an RX Trigger
from the selection, create a TX Sequence, insert an annotation, or save a snapshot.</p>

<h3>Pause Mode</h3>
<p>Click ⏸ to freeze the display without losing incoming data.
The buffer count is shown in the tooltip while paused.
Click ▶ to flush and resume.</p>
"""),

    ("Connections", _STYLE + """
<h2>Connections</h2>
<p>Open a connection via <b>Ports → New Connection…</b> (Ctrl+N).</p>

<h3>Supported Types</h3>
<table>
<tr><th>Type</th><th>Notes</th></tr>
<tr><td>Serial</td><td>COM port / tty — configure baud, parity, flow control</td></tr>
<tr><td>TCP Client</td><td>Connects to a remote host:port; auto-reconnects on drop</td></tr>
<tr><td>TCP Server</td><td>Listens on a local port; accepts one client at a time</td></tr>
<tr><td>UDP</td><td>Bind a local port, send/receive datagrams to a remote endpoint</td></tr>
<tr><td>Named Pipe</td><td>Win32 pipe or Unix domain socket (client or server)</td></tr>
<tr><td>USB HID</td><td>Requires <code>pip install hidapi</code>; select device by VID:PID</td></tr>
</table>

<h3>Auto-Reconnect</h3>
<p>Tick <b>Auto-reconnect on unexpected disconnect</b> in the port config dialog.
The protocol retries after 3 s on a drop that was not user-initiated.</p>

<div class="tip">
Serial port permissions on Linux: run
<code>sudo usermod -aG dialout $USER</code> then log out/in.
</div>
"""),

    ("Sequences & Triggers", _STYLE + """
<h2>TX Sequences &amp; RX Triggers</h2>

<h3>TX Sequences</h3>
<p>A sequence is a byte string you send on demand or repeatedly on a timer.</p>
<ul>
<li>Encoding: <b>Hex</b> / ASCII / Decimal / Binary</li>
<li>Terminator: None, CR, LF, CR+LF</li>
<li>Checksum: XOR, Sum8, CRC-8, CRC-16 Modbus, CRC-32</li>
<li>Repeat count + interval — 0 repeats = loop forever until Stop</li>
<li>Per-byte delay: drip-feeds bytes one at a time</li>
</ul>

<h3>Hex Wildcards</h3>
<table>
<tr><th>Token</th><th>Meaning</th></tr>
<tr><td><code>?</code></td><td>Random byte 0x00–0xFF</td></tr>
<tr><td><code>#</code></td><td>Auto-incrementing counter (wraps at 256)</td></tr>
<tr><td><code>^XY</code></td><td>Random byte masked by 0xXY</td></tr>
<tr><td><code>&lt;Name&gt;</code></td><td>Named value lookup (int or bytes)</td></tr>
</table>

<h3>RX Triggers</h3>
<p>A trigger matches incoming bytes and fires one or more actions:</p>
<ul>
<li>Log to file</li>
<li>Send a TX Sequence</li>
<li>Run a Python expression</li>
<li>Play a sound / show a notification</li>
</ul>
<p>Patterns can be <b>Hex</b> (exact byte match), <b>ASCII</b> (text search),
or <b>Regex</b> (on the decoded string).</p>
"""),

    ("Logging", _STYLE + """
<h2>Logging</h2>

<h3>Global Session Log</h3>
<p>KCom writes every RX/TX byte to <code>~/kcom-session.txt</code> automatically.
Change the path in <b>Settings → Serial</b>.</p>

<h3>Per-Session Logging</h3>
<p>Click the <b>Log</b> toggle button in a terminal tab toolbar.
A timestamped file is created in the same folder as the global log.</p>

<h3>Log Formats</h3>
<table>
<tr><th>Format</th><th>File</th><th>Notes</th></tr>
<tr><td>Plain Text</td><td>.txt</td><td>Human-readable with timestamps</td></tr>
<tr><td>Hex Dump</td><td>.txt</td><td>Classic hex+ASCII columns</td></tr>
<tr><td>HTML</td><td>.html</td><td>Dark-themed, colour-coded, open in any browser</td></tr>
<tr><td>CSV</td><td>.csv</td><td>Timestamp, direction, hex, ASCII per row</td></tr>
</table>

<h3>Annotations &amp; Snapshots</h3>
<p>Right-click the terminal → <b>Insert Annotation…</b> to add a text marker to the log.
<b>Save Snapshot…</b> exports the last 50 records to a timestamped .txt file.</p>
"""),

    ("Python Scripting", _STYLE + """
<h2>Python Scripting</h2>
<p>Open the script panel with <b>View → Script Panel</b> (Ctrl+Shift+S).</p>

<h3>kcom API</h3>
<table>
<tr><th>Call</th><th>Description</th></tr>
<tr><td><code>kcom.send(session, hex_str)</code></td><td>Send hex bytes to a session</td></tr>
<tr><td><code>kcom.send_text(session, text)</code></td><td>Send UTF-8 text</td></tr>
<tr><td><code>kcom.on_receive(callback)</code></td><td>Register a receive callback</td></tr>
<tr><td><code>kcom.start_logging(path)</code></td><td>Start logging to file</td></tr>
<tr><td><code>kcom.stop_logging()</code></td><td>Stop logging</td></tr>
<tr><td><code>kcom.log(message)</code></td><td>Print to script output console</td></tr>
<tr><td><code>kcom.sleep(seconds)</code></td><td>Non-blocking delay</td></tr>
<tr><td><code>kcom.file_input(path)</code></td><td>Read bytes from file</td></tr>
<tr><td><code>kcom.file_output(path)</code></td><td>Write bytes to file</td></tr>
<tr><td><code>kcom.exit()</code></td><td>Stop the script</td></tr>
</table>

<h3>CLI Usage</h3>
<pre><code>python main.py --run script.py --minimize project.kcom</code></pre>
<p><code>--invisible</code> runs completely headless (no window).</p>

<div class="warn">
Scripts run in a daemon thread. Long-running tight loops should call
<code>kcom.sleep()</code> to yield CPU.
</div>
"""),

    ("Tap / Monitor", _STYLE + """
<h2>Tap / Monitor Mode</h2>
<p>A Tap session listens on <b>two</b> ports simultaneously and shows traffic
from both in a single terminal with colour-coded channel columns.</p>

<ul>
<li><b>Channel A</b> — blue tint</li>
<li><b>Channel B</b> — green tint</li>
</ul>

<h3>Forwarding Modes</h3>
<table>
<tr><th>Mode</th><th>Behaviour</th></tr>
<tr><td>Off (monitor only)</td><td>Passively observe both sides</td></tr>
<tr><td>A → B</td><td>Forward all bytes received on A to B</td></tr>
<tr><td>B → A</td><td>Forward all bytes received on B to A</td></tr>
<tr><td>Bidirectional (bridge)</td><td>Full transparent bridge</td></tr>
</table>

<p>Open via <b>Ports → New Tap Connection…</b> (Ctrl+Shift+T).</p>
"""),

    ("HTTP API", _STYLE + """
<h2>HTTP / JSON API</h2>
<p>KCom exposes a REST + WebSocket API for external tool integration.
Enable it in <b>Settings → Advanced → HTTP / JSON API</b>.</p>

<p>Requires: <code>pip install fastapi "uvicorn[standard]"</code></p>

<h3>Endpoints</h3>
<table>
<tr><th>Method</th><th>Path</th><th>Description</th></tr>
<tr><td>GET</td><td>/sessions</td><td>List all active sessions</td></tr>
<tr><td>GET</td><td>/sessions/{id}</td><td>Get session details &amp; stats</td></tr>
<tr><td>POST</td><td>/sessions/{id}/send</td><td>Send data (hex or text body)</td></tr>
<tr><td>WS</td><td>/sessions/{id}/stream</td><td>Stream RX data as JSON frames</td></tr>
</table>

<h3>Send Example</h3>
<pre><code>curl -X POST http://127.0.0.1:8765/sessions/&lt;id&gt;/send \\
     -H 'Content-Type: application/json' \\
     -d '{"hex": "0102030A"}'</code></pre>
"""),

    ("Settings", _STYLE + """
<h2>Settings</h2>
<p>Open with <b>Tools → Settings…</b> (Ctrl+,).</p>

<h3>Tabs</h3>
<table>
<tr><th>Tab</th><th>Controls</th></tr>
<tr><td>Appearance</td><td>Theme, terminal font family &amp; size, timestamp format, control-char labels</td></tr>
<tr><td>Terminal</td><td>RX/TX/background/highlight colour overrides (per-theme defaults)</td></tr>
<tr><td>Serial</td><td>Default baud rate</td></tr>
<tr><td>Advanced</td><td>Process priority, render-throttle threshold, RX ring-buffer cap,
                        HTTP API enable &amp; port</td></tr>
</table>

<h3>Timestamp Formats</h3>
<table>
<tr><th>Format</th><th>Example</th></tr>
<tr><td>Wall</td><td>14:32:07.412</td></tr>
<tr><td>Delta</td><td>+0.023 s</td></tr>
<tr><td>Elapsed</td><td>00:01:42.300</td></tr>
<tr><td>None</td><td>(hidden)</td></tr>
</table>
"""),

]

# ---------------------------------------------------------------------------
# Context map: widget objectName or class name → topic title
# ---------------------------------------------------------------------------

CONTEXT_MAP: dict[str, str] = {
    # Terminal / PortTab
    "TerminalTable":    "Terminal",
    "PortTab":          "Terminal",
    # Panels
    "SequencePanel":    "Sequences & Triggers",
    "TriggerPanel":     "Sequences & Triggers",
    "LogPanel":         "Logging",
    "ScriptPanel":      "Python Scripting",
    "PortPanel":        "Connections",
    # Dialogs
    "PortConfigDialog": "Connections",
    "TapConfigDialog":  "Tap / Monitor",
    # Default
    "MainWindow":       "Overview",
    "WelcomeWidget":    "Overview",
}

# Topic titles as a sorted list for the browser sidebar
TOPIC_TITLES: list[str] = [t for t, _ in TOPICS]
TOPIC_HTML: dict[str, str] = dict(TOPICS)
