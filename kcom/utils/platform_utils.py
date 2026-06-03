"""Platform detection and serial port enumeration — including virtual/PTY ports."""

from __future__ import annotations

import glob
import os
import platform
import sys
from dataclasses import dataclass, field


@dataclass
class PortInfo:
    device: str
    description: str
    port_type: str          # "hardware", "usb", "virtual", "bluetooth", "unknown"
    hwid: str = ""
    vid: int | None = None
    pid: int | None = None
    accessible: bool = True

    def display_label(self) -> str:
        """Human-readable label for combo box display."""
        if self.description and self.description != self.device:
            return f"{self.device}  —  {self.description}"
        return self.device

    def type_badge(self) -> str:
        return {
            "hardware":  "[HW]",
            "usb":       "[USB]",
            "virtual":   "[VIRT]",
            "bluetooth": "[BT]",
        }.get(self.port_type, "")


def get_available_ports(include_virtual: bool = True) -> list[PortInfo]:
    """Return all detected serial/COM ports, including virtual ones.

    On Linux this supplements pyserial's /sys scan with a direct /dev scan so
    that pseudo-terminal slaves (/dev/pts/*) and null-modem pairs (/dev/tnt*)
    created by socat / tty0tty / com0com are visible.
    """
    found: dict[str, PortInfo] = {}

    # --- Step 1: pyserial standard scan ---
    try:
        import serial.tools.list_ports
        for p in serial.tools.list_ports.comports():
            ptype = _classify_port(p.device, p.hwid or "")
            found[p.device] = PortInfo(
                device=p.device,
                description=p.description or p.device,
                port_type=ptype,
                hwid=p.hwid or "",
                vid=p.vid,
                pid=p.pid,
            )
    except ImportError:
        pass

    # --- Step 2: platform-specific virtual port scan ---
    if include_virtual:
        _os = get_platform()
        if _os in ("linux", "macos"):
            _scan_unix_virtual_ports(found)
        elif _os == "windows":
            _scan_windows_virtual_ports(found)

    ports = sorted(found.values(), key=lambda p: _port_sort_key(p.device))
    return ports


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _scan_unix_virtual_ports(found: dict[str, PortInfo]) -> None:
    """Scan /dev for virtual/pseudo-terminal ports not found by pyserial."""

    patterns = [
        # Pseudo-terminal slaves (socat, screen, minicom, etc.)
        ("/dev/pts/*",       "virtual",  "PTY slave"),
        # tty0tty null-modem pairs
        ("/dev/tnt*",        "virtual",  "tty0tty virtual"),
        # Some Linux virtual serial drivers
        ("/dev/ttyV*",       "virtual",  "Virtual serial"),
        # RFC 2217 network serial
        ("/dev/ttyRFC*",     "virtual",  "RFC2217 serial"),
        # USB-serial adapters that pyserial sometimes misses
        ("/dev/ttyUSB*",     "usb",      "USB serial"),
        ("/dev/ttyACM*",     "usb",      "USB CDC-ACM"),
        # Bluetooth SPP
        ("/dev/rfcomm*",     "bluetooth","Bluetooth SPP"),
        # macOS USB serial
        ("/dev/tty.usbserial*",  "usb",  "USB serial"),
        ("/dev/tty.usbmodem*",   "usb",  "USB modem"),
        ("/dev/cu.usbserial*",   "usb",  "USB serial"),
        ("/dev/cu.usbmodem*",    "usb",  "USB modem"),
        # macOS Bluetooth
        ("/dev/tty.Bluetooth*",  "bluetooth", "Bluetooth"),
        ("/dev/cu.Bluetooth*",   "bluetooth", "Bluetooth"),
    ]

    for pattern, ptype, desc in patterns:
        for path in sorted(glob.glob(pattern)):
            if path not in found and _is_char_device(path):
                found[path] = PortInfo(
                    device=path,
                    description=desc,
                    port_type=ptype,
                    accessible=_is_accessible(path),
                )


def _scan_windows_virtual_ports(found: dict[str, PortInfo]) -> None:
    """On Windows, try high-numbered COM ports that pyserial may not list."""
    # pyserial on Windows usually finds everything via SetupAPI, but virtual
    # port drivers (com0com, VSPE, HHD) sometimes register COM ports that only
    # appear when opened with the \\.\COM notation for port numbers > 9.
    # We probe COM1-COM256 and include any that open without error.
    import serial
    for n in range(1, 257):
        name = f"COM{n}"
        if name in found:
            continue
        device = f"\\\\.\\{name}"
        try:
            s = serial.Serial(port=device, timeout=0)
            s.close()
            found[name] = PortInfo(
                device=name,
                description="Virtual COM port",
                port_type="virtual",
            )
        except serial.SerialException:
            pass
        except Exception:
            pass


def _classify_port(device: str, hwid: str) -> str:
    d = device.lower()
    h = hwid.lower()
    if "usb" in d or "acm" in d or "usb" in h:
        return "usb"
    if "rfcomm" in d or "bluetooth" in d.lower() or "bluetooth" in h:
        return "bluetooth"
    if "pts" in d or "tnt" in d or "virtual" in h or "com0com" in h:
        return "virtual"
    if "ttys" in d or "com" in d:
        return "hardware"
    return "unknown"


def _is_char_device(path: str) -> bool:
    try:
        return os.path.exists(path) and (os.stat(path).st_mode & 0o170000) == 0o020000
    except OSError:
        return False


def _is_accessible(path: str) -> bool:
    return os.access(path, os.R_OK | os.W_OK)


def _port_sort_key(device: str) -> tuple:
    """Natural sort: /dev/ttyS0 < /dev/ttyS10, COM1 < COM10."""
    import re
    parts = re.split(r"(\d+)", device)
    return tuple(int(p) if p.isdigit() else p.lower() for p in parts)


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

def get_platform() -> str:
    system = platform.system().lower()
    if system == "windows":
        return "windows"
    elif system == "darwin":
        return "macos"
    return "linux"


def is_windows() -> bool:
    return get_platform() == "windows"


def is_linux() -> bool:
    return get_platform() == "linux"


def is_macos() -> bool:
    return get_platform() == "macos"
