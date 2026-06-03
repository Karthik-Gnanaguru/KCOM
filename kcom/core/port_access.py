"""Serial-port permission helpers.

On Linux/macOS a serial device (or a socat/tty0tty virtual PTY created by root)
may not be readable/writable by the current user. This module detects those
ports and can request elevated permission to open them up, using ``pkexec``
(graphical PolicyKit prompt) or ``sudo`` as a fallback.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from kcom.utils.platform_utils import get_available_ports


def is_unix() -> bool:
    return not sys.platform.startswith("win")


def real_device(path: str) -> str:
    """Resolve symlinks (e.g. /dev/ttyVirt0 -> /dev/pts/10)."""
    try:
        return os.path.realpath(path)
    except OSError:
        return path


def is_accessible(path: str) -> bool:
    """True if the current user can both read and write the device."""
    try:
        return os.access(path, os.R_OK | os.W_OK)
    except OSError:
        return False


def is_serial_device(path: str) -> bool:
    """True only for genuine serial device names we may safely chmod.

    Excludes bare pseudo-terminals (``/dev/pts/*``, ``ptmx``) which are login
    shells, not serial ports — touching their permissions would be unsafe. The
    named virtual-serial links (``/dev/ttyVirt*`` etc.) are kept; they resolve
    to their own PTY which is the correct chmod target.
    """
    if path.startswith("/dev/pts/") or path.endswith("/ptmx"):
        return False
    base = os.path.basename(path)
    prefixes = (
        "ttyS", "ttyUSB", "ttyACM", "ttyAMA", "ttyVirt", "ttyV", "ttyRFC",
        "rfcomm", "tnt", "cu.", "tty.usb", "tty.Bluetooth", "cu.Bluetooth",
    )
    return base.startswith(prefixes)


def inaccessible_ports() -> list[str]:
    """Return paths of genuine serial ports the current user cannot open.

    Windows COM ports do not use POSIX permissions, so this is empty there.
    """
    if not is_unix():
        return []
    blocked: list[str] = []
    for info in get_available_ports(include_virtual=True):
        dev = info.device
        if not dev or not is_serial_device(dev):
            continue
        if os.path.exists(dev) and not is_accessible(dev):
            blocked.append(dev)
    return blocked


def _privilege_cmd() -> list[str] | None:
    """Return the privilege-escalation command prefix, or None if unavailable."""
    if shutil.which("pkexec"):
        return ["pkexec"]
    if shutil.which("sudo"):
        # -n: never prompt on a TTY-less GUI; if it needs a password this fails
        # cleanly and we report that pkexec is preferred.
        return ["sudo", "-A"]
    return None


def make_accessible(devices: list[str], timeout: float = 120.0) -> tuple[bool, str]:
    """Grant read/write access to the given serial devices.

    Resolves each path to its real device node and runs a single privileged
    ``chmod a+rw`` over all of them. Returns (success, message).
    """
    if not is_unix():
        return True, "No permission changes needed on this platform."

    reals = sorted({real_device(d) for d in devices})
    reals = [d for d in reals if os.path.exists(d)]
    if not reals:
        return True, "No ports needed changes."

    # Anything already writable can be skipped.
    targets = [d for d in reals if not is_accessible(d)]
    if not targets:
        return True, "All ports are already accessible."

    cmd = _privilege_cmd()
    if cmd is None:
        return False, (
            "Cannot escalate privileges: neither 'pkexec' nor 'sudo' was found.\n"
            "Install policykit-1 (pkexec) or run the chmod manually."
        )

    full = cmd + ["chmod", "a+rw", *targets]
    try:
        result = subprocess.run(
            full, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return False, "Permission request timed out."
    except OSError as e:
        return False, f"Failed to run privilege helper: {e}"

    if result.returncode == 0:
        still_blocked = [d for d in targets if not is_accessible(d)]
        if still_blocked:
            return False, "Permission command ran but ports are still blocked."
        return True, f"Granted access to {len(targets)} port(s)."

    err = (result.stderr or "").strip()
    # pkexec returns 126/127 when the auth dialog is dismissed/unavailable.
    if result.returncode in (126, 127):
        return False, "Permission request was cancelled or unavailable."
    return False, err or f"Permission command failed (exit {result.returncode})."
