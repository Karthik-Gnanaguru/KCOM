"""HTTP/JSON API server running FastAPI+uvicorn in a dedicated QThread.

Requires optional dependencies::

    pip install fastapi uvicorn[standard]

When those packages are not installed the server fails gracefully and emits
``error_signal`` with an installation hint.

Architecture
------------
The server runs a ``asyncio`` event loop inside a QThread.  Data arrives from
the Qt main thread via :meth:`push_data`, which schedules a coroutine into the
server's asyncio loop using ``asyncio.run_coroutine_threadsafe``.

All WebSocket clients subscribed to a session receive every incoming data
frame; the frame is a JSON object::

    {"session_id": "...", "direction": "rx", "data_hex": "0102...", "ts": 1.234}
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING

from PyQt6.QtCore import QThread, pyqtSignal as Signal

if TYPE_CHECKING:
    pass

try:
    import fastapi as _fastapi
    import uvicorn as _uvicorn
    _API_AVAILABLE = True
except ImportError:
    _fastapi = None  # type: ignore[assignment]
    _uvicorn = None  # type: ignore[assignment]
    _API_AVAILABLE = False


class APIServer(QThread):
    """FastAPI+uvicorn server running in a background QThread.

    Signals
    -------
    started_signal(port):
        Emitted when the server is ready to accept connections.
    stopped_signal():
        Emitted when the server has shut down.
    error_signal(message):
        Emitted on startup failure.
    """

    started_signal: Signal = Signal(int)   # port number
    stopped_signal: Signal = Signal()
    error_signal: Signal = Signal(str)

    def __init__(self, port: int, session_manager, parent=None) -> None:
        super().__init__(parent)
        self._port = port
        self._session_manager = session_manager
        self._loop: asyncio.AbstractEventLoop | None = None
        self._server: object | None = None  # uvicorn.Server
        # session_id → set of asyncio.Queue for connected WebSocket clients
        self._ws_queues: dict[str, set] = {}

    # ------------------------------------------------------------------
    # QThread entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        if not _API_AVAILABLE:
            self.error_signal.emit(
                "HTTP API requires fastapi and uvicorn.\n"
                "Install them with:  pip install fastapi 'uvicorn[standard]'"
            )
            return

        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        app = self._build_app()
        config = _uvicorn.Config(
            app,
            host="127.0.0.1",
            port=self._port,
            loop="none",           # we manage the loop ourselves
            log_level="warning",
            lifespan="off",
        )
        self._server = _uvicorn.Server(config)

        # Patch uvicorn's startup notification
        original_startup = self._server.startup

        async def _patched_startup(sockets=None):
            await original_startup(sockets=sockets)
            self.started_signal.emit(self._port)

        self._server.startup = _patched_startup

        try:
            self._loop.run_until_complete(self._server.serve())
        except Exception as exc:
            self.error_signal.emit(f"API server error: {exc}")
        finally:
            self._loop.close()
            self._loop = None
            self.stopped_signal.emit()

    def stop(self) -> None:
        """Request the server to shut down gracefully."""
        if self._server is not None and self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._server.should_exit.__setattr__, "should_exit", True)
            # Simpler: set the flag directly
            try:
                self._server.should_exit = True  # type: ignore[attr-defined]
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Data bridge (called from Qt main thread)
    # ------------------------------------------------------------------

    def push_data(self, session_id: str, data: bytes, direction: str) -> None:
        """Forward a data frame to all WebSocket subscribers for *session_id*.

        Safe to call from any thread.
        """
        if self._loop is None or not self._loop.is_running():
            return
        frame = json.dumps({
            "session_id": session_id,
            "direction": direction,
            "data_hex": data.hex(),
            "ts": time.perf_counter(),
        })
        asyncio.run_coroutine_threadsafe(
            self._broadcast(session_id, frame),
            self._loop,
        )

    async def _broadcast(self, session_id: str, frame: str) -> None:
        queues = self._ws_queues.get(session_id, set())
        dead = set()
        for q in list(queues):
            try:
                q.put_nowait(frame)
            except asyncio.QueueFull:
                dead.add(q)
        queues -= dead

    # ------------------------------------------------------------------
    # FastAPI app builder
    # ------------------------------------------------------------------

    def _build_app(self):
        app = _fastapi.FastAPI(title="KCom API", version="1.0")

        session_manager = self._session_manager
        ws_queues = self._ws_queues

        @app.get("/sessions")
        def list_sessions():
            """Return a list of active sessions."""
            result = []
            for sid, session in session_manager.sessions.items():
                result.append({
                    "session_id": sid,
                    "name": session.config.display_name(),
                    "connection_type": session.config.connection_type.value,
                    "status": session.status.value,
                    "bytes_rx": session.stats.bytes_rx,
                    "bytes_tx": session.stats.bytes_tx,
                })
            return result

        @app.get("/sessions/{session_id}")
        def get_session(session_id: str):
            session = session_manager.get_session(session_id)
            if session is None:
                raise _fastapi.HTTPException(status_code=404, detail="Session not found")
            return {
                "session_id": session_id,
                "name": session.config.display_name(),
                "connection_type": session.config.connection_type.value,
                "status": session.status.value,
                "bytes_rx": session.stats.bytes_rx,
                "bytes_tx": session.stats.bytes_tx,
                "peer_info": session.peer_info(),
            }

        @app.post("/sessions/{session_id}/send")
        def send_to_session(session_id: str, body: dict):
            """Send data to a session. Body: ``{"hex": "0102..."}`` or ``{"text": "hello"}``."""
            session = session_manager.get_session(session_id)
            if session is None:
                raise _fastapi.HTTPException(status_code=404, detail="Session not found")
            if "hex" in body:
                try:
                    data = bytes.fromhex(body["hex"])
                except ValueError:
                    raise _fastapi.HTTPException(status_code=400, detail="Invalid hex data")
            elif "text" in body:
                data = str(body["text"]).encode("utf-8", "replace")
            else:
                raise _fastapi.HTTPException(status_code=400, detail="Provide 'hex' or 'text'")
            session.send(data)
            return {"sent": len(data)}

        @app.websocket("/sessions/{session_id}/stream")
        async def ws_stream(websocket, session_id: str):
            session = session_manager.get_session(session_id)
            if session is None:
                await websocket.close(code=1008)
                return

            await websocket.accept()
            q: asyncio.Queue = asyncio.Queue(maxsize=500)
            ws_queues.setdefault(session_id, set()).add(q)
            try:
                while True:
                    frame = await asyncio.wait_for(q.get(), timeout=30.0)
                    await websocket.send_text(frame)
            except (asyncio.TimeoutError, Exception):
                pass
            finally:
                ws_queues.get(session_id, set()).discard(q)
                try:
                    await websocket.close()
                except Exception:
                    pass

        return app
