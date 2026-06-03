"""Serial port protocol handler with dedicated reader thread."""

from __future__ import annotations

import errno
import sys
import time
from typing import TYPE_CHECKING

import serial

from PyQt6.QtCore import QThread, QTimer, pyqtSignal as Signal

from kcom.models.port_config import FlowControl, Parity, PortConfig
from kcom.protocols.base_protocol import BaseProtocol

if TYPE_CHECKING:
    pass


def friendly_serial_error(exc: Exception, port: str) -> str:
    """Turn a raw serial/OS exception into an actionable message."""
    text = str(exc)
    err_no = getattr(exc, "errno", None)
    low = text.lower()

    is_permission = err_no == errno.EACCES or "permission denied" in low or "access is denied" in low
    is_busy = err_no == errno.EBUSY or "resource busy" in low or "in use" in low
    is_missing = err_no == errno.ENOENT or "no such file" in low or "could not open port" in low and "permission" not in low

    if is_permission:
        if sys.platform.startswith("linux"):
            return (
                f"Permission denied opening {port}.\n"
                f"  • Real hardware: add yourself to the 'dialout' group:\n"
                f"      sudo usermod -aG dialout $USER   (then log out/in)\n"
                f"  • Virtual port (socat/tty0tty): it was likely created by root.\n"
                f"    Recreate it without sudo, or give it open permissions, e.g.:\n"
                f"      socat -d -d pty,raw,echo=0,perm=0666,link={port} pty,raw,echo=0,perm=0666,link=...\n"
                f"  • Quick check:  ls -lL {port}"
            )
        if sys.platform == "darwin":
            return f"Permission denied opening {port}. Check the device owner with: ls -lL {port}"
        return (
            f"Access denied opening {port}. Another program may have it open, "
            f"or you may need Administrator rights."
        )
    if is_busy:
        return (
            f"{port} is busy — another program (or another KCom tab) already has it open. "
            f"Close the other connection and try again."
        )
    if is_missing:
        return (
            f"{port} was not found. It may have been unplugged or the virtual-port "
            f"helper (socat/com0com) is no longer running. Click Refresh in the port dialog."
        )
    return text


class SerialReaderThread(QThread):
    """Dedicated QThread that polls the serial port and emits received data.

    Must be created in the main thread but runs its loop in a worker thread.
    """

    data_received: Signal = Signal(bytes, float)
    error_occurred: Signal = Signal(str, str)  # (code, message)

    def __init__(self, port: serial.Serial) -> None:
        super().__init__()
        self._port = port
        self._running = False

    def run(self) -> None:
        """Main read loop — runs in worker thread."""
        self._running = True
        while self._running:
            try:
                if self._port.is_open:
                    waiting = self._port.in_waiting
                    if waiting > 0:
                        data = self._port.read(waiting)
                        if data:
                            ts = time.perf_counter()
                            self.data_received.emit(data, ts)
                    else:
                        # Small sleep to avoid 100% CPU when idle
                        self.msleep(1)
                else:
                    break
            except serial.SerialException as e:
                self.error_occurred.emit("READ_ERROR", str(e))
                break
            except OSError as e:
                self.error_occurred.emit("READ_ERROR", str(e))
                break

    def stop(self) -> None:
        """Signal the loop to stop and wait for the thread to finish."""
        self._running = False
        self.wait(3000)  # Wait up to 3 seconds


_RECONNECT_DELAY_MS = 3000


class SerialProtocol(BaseProtocol):
    """Serial port communication handler backed by pyserial."""

    def __init__(self, config: PortConfig) -> None:
        super().__init__()
        self._config = config
        self._serial: serial.Serial | None = None
        self._reader_thread: SerialReaderThread | None = None
        self._user_disconnected = False

        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._do_connect)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def connect(self) -> None:  # type: ignore[override]
        """Open the serial port and start the reader thread."""
        self._user_disconnected = False
        self._do_connect()

    def _do_connect(self) -> None:
        """Internal connect — also called by the reconnect timer."""
        sc = self._config.serial

        # Map enums to pyserial constants
        parity_map = {
            Parity.NONE: serial.PARITY_NONE,
            Parity.ODD: serial.PARITY_ODD,
            Parity.EVEN: serial.PARITY_EVEN,
            Parity.MARK: serial.PARITY_MARK,
            Parity.SPACE: serial.PARITY_SPACE,
        }
        stopbits_map = {
            1.0: serial.STOPBITS_ONE,
            1.5: serial.STOPBITS_ONE_POINT_FIVE,
            2.0: serial.STOPBITS_TWO,
        }
        flow_rtscts = sc.flow_control == FlowControl.RTS_CTS
        flow_xonxoff = sc.flow_control == FlowControl.XON_XOFF
        flow_dsrdtr = sc.flow_control == FlowControl.DTR_DSR

        try:
            self._serial = serial.Serial(
                port=sc.port,
                baudrate=sc.baud_rate,
                bytesize=sc.data_bits,
                parity=parity_map.get(sc.parity, serial.PARITY_NONE),
                stopbits=stopbits_map.get(sc.stop_bits, serial.STOPBITS_ONE),
                rtscts=flow_rtscts,
                xonxoff=flow_xonxoff,
                dsrdtr=flow_dsrdtr,
                timeout=sc.timeout if sc.timeout > 0 else None,
                write_timeout=None,
            )
        except serial.SerialException as e:
            msg = friendly_serial_error(e, sc.port)
            low = str(e).lower()
            if "permission" in low or "access" in low:
                code = "PERMISSION_DENIED"
            elif "busy" in low or "in use" in low:
                code = "PORT_BUSY"
            elif "not found" in low or "no such" in low or "could not open" in low:
                code = "PORT_NOT_FOUND"
            else:
                code = "CONNECT_ERROR"
            self.error_occurred.emit(code, msg)
            return
        except ValueError as e:
            self.error_occurred.emit("CONFIG_ERROR", f"Invalid port configuration: {e}")
            return

        self._reader_thread = SerialReaderThread(self._serial)
        self._reader_thread.data_received.connect(self.data_received)
        self._reader_thread.error_occurred.connect(self._on_reader_error)
        self._reader_thread.start()
        self.connected.emit()

    def disconnect(self) -> None:  # type: ignore[override]
        """Stop the reader thread and close the serial port."""
        self._user_disconnected = True
        self._reconnect_timer.stop()
        if self._reader_thread is not None:
            self._reader_thread.stop()
            self._reader_thread = None

        if self._serial is not None and self._serial.is_open:
            try:
                self._serial.close()
            except serial.SerialException:
                pass
            self._serial = None

        self.disconnected.emit()

    def send(self, data: bytes) -> None:
        """Write bytes to the serial port."""
        if self._serial is None or not self._serial.is_open:
            self.error_occurred.emit("NOT_CONNECTED", "Port is not open")
            return
        try:
            self._serial.write(data)
        except serial.SerialException as e:
            self.error_occurred.emit("WRITE_ERROR", f"Write error: {e}")
        except OSError as e:
            self.error_occurred.emit("WRITE_ERROR", f"Write OS error: {e}")

    def is_connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def send_break(self) -> None:
        """Assert a BREAK condition on the serial line for the default duration."""
        if self._serial is None or not self._serial.is_open:
            self.error_occurred.emit("NOT_CONNECTED", "Cannot send BREAK: port is not open")
            return
        try:
            self._serial.send_break()
        except serial.SerialException as e:
            self.error_occurred.emit("BREAK_ERROR", f"Break error: {e}")

    def get_port_signals(self) -> dict:
        """Return current hardware signal states."""
        if self._serial is None or not self._serial.is_open:
            return {"RTS": False, "DTR": False, "CTS": False, "DSR": False, "DCD": False, "RI": False}
        try:
            return {
                "RTS": bool(self._serial.rts),
                "DTR": bool(self._serial.dtr),
                "CTS": bool(self._serial.cts),
                "DSR": bool(self._serial.dsr),
                "DCD": bool(self._serial.cd),
                "RI": bool(self._serial.ri),
            }
        except Exception:
            return {"RTS": False, "DTR": False, "CTS": False, "DSR": False, "DCD": False, "RI": False}

    # ------------------------------------------------------------------
    # Private slots
    # ------------------------------------------------------------------

    def _on_reader_error(self, code: str, msg: str) -> None:
        """Handle errors from the reader thread — clean up and optionally reconnect."""
        self.error_occurred.emit(code, msg)
        if self._serial is not None and self._serial.is_open:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None
        self._reader_thread = None
        self.disconnected.emit()
        if not self._user_disconnected and self._config.auto_reconnect:
            self._reconnect_timer.start(_RECONNECT_DELAY_MS)
