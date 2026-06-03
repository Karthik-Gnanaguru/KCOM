"""USB HID protocol handler.

Requires the ``hidapi`` Python package::

    pip install hidapi

If the package is not installed, ``connect()`` emits ``error_occurred`` with a
clear installation hint rather than crashing.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from PyQt6.QtCore import QThread, pyqtSignal as Signal

from kcom.models.port_config import PortConfig
from kcom.protocols.base_protocol import BaseProtocol

_HID_AVAILABLE = False
_HID_ERROR: str = ""
_hid = None

try:
    import hid as _hid  # type: ignore[assignment]
    # Guard: the ctypes 'hid' package (pip install hid) also imports as 'hid'
    # but exposes hid.Device (capital D) instead of hid.device (lowercase d).
    # Having both packages installed causes this conflict.  Detect it early.
    if not hasattr(_hid, "device"):
        raise ImportError(
            "Wrong 'hid' package loaded — the ctypes 'hid' package is installed "
            "alongside 'hidapi' and is shadowing it.\n"
            "Fix:  pip uninstall hid  (keep only hidapi)"
        )
    _HID_AVAILABLE = True
except ImportError as _e:
    _e_str = str(_e)
    # The 'hid' / 'hidapi' package raises ImportError when the native C library
    # (libhidapi-hidraw.so) is missing.  Distinguish that from "not installed".
    if any(k in _e_str for k in ("libhidapi", "Unable to load", "cannot open shared object",
                                  "No such file", "Wrong 'hid' package")):
        _HID_ERROR = (
            f"{_e_str}\n"
            "On Linux:  sudo apt install libhidapi-hidraw0 libhidapi-libusb0\n"
            "On macOS:  brew install hidapi\n"
            "On Windows: see https://github.com/libusb/hidapi/releases"
        )
    else:
        _HID_ERROR = (
            "Python package 'hidapi' not found.\n"
            "Install:  pip install hidapi\n"
            "Linux also needs:  sudo apt install libhidapi-hidraw0"
        )
except Exception as _e:
    _HID_ERROR = (
        f"Native HID library not found: {_e}\n"
        "On Linux:  sudo apt install libhidapi-hidraw0 libhidapi-libusb0\n"
        "On macOS:  brew install hidapi"
    )


def check_hid_availability() -> tuple[bool, str]:
    """Re-attempt the ``hid`` import and refresh the module-level globals.

    Called each time the USB HID tab is shown so that a package installed
    *after* KCom started is picked up without a restart.

    Returns ``(available, error_message)``.
    """
    global _HID_AVAILABLE, _hid, _HID_ERROR
    if _HID_AVAILABLE:
        return True, ""
    import importlib, sys
    # Remove stale cached failure so importlib tries fresh
    for key in list(sys.modules.keys()):
        if key == "hid" or key.startswith("hid."):
            del sys.modules[key]
    try:
        mod = importlib.import_module("hid")
        if not hasattr(mod, "device"):
            raise ImportError(
                "Wrong 'hid' package loaded — ctypes 'hid' shadows 'hidapi'.\n"
                "Fix:  pip uninstall hid  (keep only hidapi)"
            )
        _hid = mod
        _HID_AVAILABLE = True
        _HID_ERROR = ""
        return True, ""
    except ImportError as exc:
        exc_str = str(exc)
        if any(k in exc_str for k in ("libhidapi", "Unable to load", "cannot open shared object",
                                       "No such file", "Wrong 'hid' package")):
            _HID_ERROR = (
                f"{exc_str}\n"
                "On Linux:  sudo apt install libhidapi-hidraw0 libhidapi-libusb0\n"
                "On macOS:  brew install hidapi"
            )
        else:
            _HID_ERROR = (
                "Python package 'hidapi' not found.\n"
                "Install:  pip install hidapi\n"
                "Linux also needs:  sudo apt install libhidapi-hidraw0"
            )
        return False, _HID_ERROR
    except Exception as exc:
        _HID_ERROR = (
            f"Native HID library not found: {exc}\n"
            "On Linux:  sudo apt install libhidapi-hidraw0 libhidapi-libusb0\n"
            "On macOS:  brew install hidapi"
        )
        return False, _HID_ERROR


_POLL_INTERVAL_MS = 5   # read poll frequency when idle


class _HIDReaderThread(QThread):
    """Polls the HID device for incoming reports in a worker thread."""

    data_received: Signal = Signal(bytes, float)
    error_occurred: Signal = Signal(str, str)  # (code, message)

    def __init__(self, device: object, report_size: int) -> None:
        super().__init__()
        self._device = device
        self._report_size = report_size
        self._running = False

    def run(self) -> None:
        self._running = True
        while self._running:
            try:
                # Non-blocking read: timeout=0 returns immediately if no data
                data = bytes(self._device.read(self._report_size + 1, timeout_ms=10))
                if data:
                    # Strip leading report-id byte (often 0x00 for single-report devices)
                    payload = data[1:] if data[0] == 0x00 else data
                    self.data_received.emit(payload, time.perf_counter())
                else:
                    self.msleep(_POLL_INTERVAL_MS)
            except Exception as exc:
                self.error_occurred.emit("READ_ERROR", str(exc))
                break

    def stop(self) -> None:
        self._running = False
        self.wait(3000)


class HIDProtocol(BaseProtocol):
    """USB HID communication handler backed by ``hidapi``.

    Reports are sent/received as raw bytes with the report-id byte prepended
    on write (0x00 for single-report devices).
    """

    def __init__(self, config: PortConfig) -> None:
        super().__init__()
        self._config = config
        self._device: object | None = None
        self._reader: _HIDReaderThread | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def connect(self) -> None:  # type: ignore[override]
        if not _HID_AVAILABLE:
            self.error_occurred.emit("MISSING_DEPENDENCY", _HID_ERROR)
            return

        hid_cfg = self._config.hid
        try:
            dev = _hid.device()
            dev.open(hid_cfg.vendor_id, hid_cfg.product_id)
            dev.set_nonblocking(True)
            self._device = dev
        except OSError as exc:
            low = str(exc).lower()
            if "permission" in low or "access" in low:
                code = "PERMISSION_DENIED"
            elif "not found" in low or "no such" in low:
                code = "DEVICE_NOT_FOUND"
            else:
                code = "CONNECT_ERROR"
            self.error_occurred.emit(code, f"HID open failed: {exc}")
            return
        except Exception as exc:
            self.error_occurred.emit("CONNECT_ERROR", f"HID open failed: {exc}")
            return

        self._reader = _HIDReaderThread(self._device, hid_cfg.report_size)
        self._reader.data_received.connect(self.data_received)
        self._reader.error_occurred.connect(self._on_reader_error)
        self._reader.start()
        self.connected.emit()

    def disconnect(self) -> None:  # type: ignore[override]
        if self._reader is not None:
            self._reader.stop()
            self._reader = None
        if self._device is not None:
            try:
                self._device.close()  # type: ignore[attr-defined]
            except Exception:
                pass
            self._device = None
        self.disconnected.emit()

    def send(self, data: bytes) -> None:
        if self._device is None:
            self.error_occurred.emit("NOT_CONNECTED", "HID device is not open")
            return
        try:
            # Prepend 0x00 report-id for single-report devices
            self._device.write(b"\x00" + data)  # type: ignore[attr-defined]
        except Exception as exc:
            self.error_occurred.emit("WRITE_ERROR", f"HID write error: {exc}")

    def is_connected(self) -> bool:
        return self._device is not None

    def peer_info(self) -> str:
        if not self.is_connected():
            return ""
        hid_cfg = self._config.hid
        return f"HID {hid_cfg.vendor_id:04X}:{hid_cfg.product_id:04X}"

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _on_reader_error(self, code: str, msg: str) -> None:
        self.error_occurred.emit(code, msg)
        self.disconnect()


def list_hid_devices() -> list[dict]:
    """Return a list of connected HID devices as dicts with vid/pid/name keys.

    Returns an empty list when ``hidapi`` is not installed.
    """
    if not _HID_AVAILABLE:
        return []
    try:
        return [
            {
                "vendor_id": d["vendor_id"],
                "product_id": d["product_id"],
                "manufacturer": d.get("manufacturer_string", ""),
                "product": d.get("product_string", ""),
                "usage_page": d.get("usage_page", 0),
                "interface_number": d.get("interface_number", -1),
            }
            for d in _hid.enumerate()
        ]
    except Exception:
        return []
