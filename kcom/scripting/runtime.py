"""KCom scripting runtime — sandboxed Python execution with a kcom.* API."""

from __future__ import annotations

import threading
import time
import traceback
from typing import Callable

from PyQt6.QtCore import QObject, pyqtSignal as Signal


# ---------------------------------------------------------------------------
# KComAPI — the object scripts use as `kcom.*`
# ---------------------------------------------------------------------------

class KComAPI(QObject):
    """Facade exposed to scripts as the ``kcom`` global.

    All methods that cross back into the main thread (send, logging) do so via
    PyQt signals, which Qt routes through the event loop safely from any thread.
    """

    # Signals emitted by the API — MainWindow connects them
    send_requested:           Signal = Signal(bytes)
    logging_start_requested:  Signal = Signal(str)    # path
    logging_stop_requested:   Signal = Signal()
    exit_requested:           Signal = Signal()
    log_output:               Signal = Signal(str)    # printed to script panel

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._receive_callbacks: list[Callable] = []

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

    def send(self, data: bytes) -> None:
        """Send raw bytes to the active session."""
        if isinstance(data, (bytes, bytearray)):
            self.send_requested.emit(bytes(data))

    def send_hex(self, hex_str: str) -> None:
        """Send bytes from a hex string (spaces ignored)."""
        try:
            self.send_requested.emit(bytes.fromhex(hex_str.replace(" ", "")))
        except ValueError as e:
            self.log(f"send_hex error: {e}")

    def send_text(self, text: str, encoding: str = "utf-8") -> None:
        """Send a string encoded as bytes."""
        self.send_requested.emit(text.encode(encoding, errors="replace"))

    # ------------------------------------------------------------------
    # Receive callbacks
    # ------------------------------------------------------------------

    def on_receive(self, callback: Callable[[bytes, float], None]) -> None:
        """Register a callback invoked whenever RX data arrives.

        The callback receives ``(data: bytes, timestamp: float)``.  It is
        called from the main thread via a queued signal, so it is safe to
        update Qt widgets inside callbacks.
        """
        if callable(callback):
            self._receive_callbacks.append(callback)

    def _dispatch_receive(self, data: bytes, ts: float) -> None:
        """Called by ScriptRuntime from the main thread on each RX packet."""
        for cb in list(self._receive_callbacks):
            try:
                cb(data, ts)
            except Exception as exc:
                self.log_output.emit(f"[receive callback error] {exc}")

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def start_logging(self, path: str = "") -> None:
        """Start per-session logging; path auto-generated when empty."""
        self.logging_start_requested.emit(path)

    def stop_logging(self) -> None:
        """Stop per-session logging."""
        self.logging_stop_requested.emit()

    # ------------------------------------------------------------------
    # Output / utilities
    # ------------------------------------------------------------------

    def log(self, *args) -> None:
        """Print a message to the script output panel."""
        self.log_output.emit(" ".join(str(a) for a in args))

    def sleep(self, seconds: float) -> None:
        """Block the script thread for *seconds*."""
        time.sleep(seconds)

    def exit(self) -> None:
        """Request the application to quit."""
        self.exit_requested.emit()

    # ------------------------------------------------------------------
    # File I/O helpers
    # ------------------------------------------------------------------

    def file_input(self, path: str) -> bytes:
        """Read and return the contents of *path* as bytes."""
        with open(path, "rb") as fh:
            return fh.read()

    def file_output(self, path: str, data: bytes | str) -> None:
        """Write *data* to *path*.  Strings are UTF-8 encoded."""
        if isinstance(data, str):
            data = data.encode("utf-8")
        with open(path, "wb") as fh:
            fh.write(data)


# ---------------------------------------------------------------------------
# ScriptThread — Python thread that executes user code
# ---------------------------------------------------------------------------

class ScriptThread(threading.Thread):
    """Runs user script code in a daemon thread.

    *on_finish* and *on_error* are callables invoked on completion or
    exception — they must be thread-safe (e.g. PyQt signals).
    """

    def __init__(
        self,
        code: str,
        filename: str,
        namespace: dict,
        on_finish: Callable,
        on_error: Callable[[str], None],
    ) -> None:
        super().__init__(daemon=True, name="KComScriptThread")
        self._code = code
        self._filename = filename
        self._namespace = namespace
        self._on_finish = on_finish
        self._on_error = on_error
        self._stop_event = threading.Event()

    def stop(self) -> None:
        """Signal the thread to stop (scripts can poll kcom._stop_requested)."""
        self._stop_event.set()

    @property
    def stop_requested(self) -> bool:
        return self._stop_event.is_set()

    def run(self) -> None:
        try:
            compiled = compile(self._code, self._filename, "exec")
            exec(compiled, self._namespace)
            self._on_finish()
        except SystemExit:
            self._on_finish()
        except Exception:
            self._on_error(traceback.format_exc())


# ---------------------------------------------------------------------------
# ScriptRuntime — owns the API + thread lifecycle
# ---------------------------------------------------------------------------

class ScriptRuntime(QObject):
    """Owns one ``KComAPI`` instance and the currently-running script thread.

    Connect ``api.send_requested`` etc. to MainWindow before calling
    :meth:`run_script`.
    """

    log_output:      Signal = Signal(str)   # forwarded from api.log_output
    script_started:  Signal = Signal()
    script_finished: Signal = Signal()
    script_error:    Signal = Signal(str)   # traceback string

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._api = KComAPI(self)
        self._api.log_output.connect(self.log_output)
        self._thread: ScriptThread | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def api(self) -> KComAPI:
        return self._api

    def run_script(self, code: str, filename: str = "<script>") -> None:
        """Execute *code* in a background thread.  Does nothing if already running."""
        if self.is_running():
            return

        self._api._receive_callbacks.clear()

        namespace: dict = {
            "kcom":  self._api,
            # Override print so output goes to the script panel
            "print": lambda *a, **kw: self._api.log_output.emit(
                " ".join(str(x) for x in a)
            ),
        }
        # Expose stop_requested so long-running scripts can poll it
        namespace["kcom"]._stop_event_ref = None  # patched below

        self._thread = ScriptThread(
            code, filename, namespace,
            on_finish=self.script_finished.emit,
            on_error=self.script_error.emit,
        )
        # Allow scripts to call kcom.stop_requested
        self._api.__dict__["_stop_event_ref"] = self._thread._stop_event
        self._thread.start()
        self.script_started.emit()

    def stop(self) -> None:
        """Ask the running script to stop; cannot forcibly kill it."""
        if self._thread:
            self._thread.stop()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def dispatch_receive(self, data: bytes, ts: float) -> None:
        """Forward incoming RX data to registered callbacks (call from main thread)."""
        self._api._dispatch_receive(data, ts)
