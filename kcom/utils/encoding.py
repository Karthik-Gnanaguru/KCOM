"""Byte encoding and formatting utilities."""

from __future__ import annotations

from enum import Enum, auto


class DisplayMode(Enum):
    ASCII = auto()
    HEX = auto()
    DECIMAL = auto()
    BINARY = auto()
    MIXED = auto()


def bytes_to_hex(data: bytes, width: int = 16) -> str:
    """Format bytes as a Wireshark-style hex dump with offset column and ASCII sidebar."""
    if not data:
        return ""

    lines = []
    for i in range(0, len(data), width):
        chunk = data[i : i + width]
        offset = f"{i:08x}"
        hex_part = " ".join(f"{b:02X}" for b in chunk)
        # Pad hex part to consistent width
        hex_part = hex_part.ljust(width * 3 - 1)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{offset}  {hex_part}  |{ascii_part}|")
    return "\n".join(lines)


def bytes_to_hex_inline(data: bytes) -> str:
    """Format bytes as a single space-separated uppercase hex line: '02 03 05'."""
    return " ".join(f"{b:02X}" for b in data)


def bytes_to_ascii(data: bytes) -> str:
    """Convert bytes to ASCII string, escaping non-printable characters."""
    result = []
    for b in data:
        if 32 <= b < 127:
            result.append(chr(b))
        elif b == 0x0D:
            result.append("\\r")
        elif b == 0x0A:
            result.append("\\n")
        elif b == 0x09:
            result.append("\\t")
        else:
            result.append(f"\\x{b:02x}")
    return "".join(result)


def bytes_to_decimal(data: bytes) -> str:
    """Convert bytes to space-separated decimal values."""
    return " ".join(str(b) for b in data)


def bytes_to_binary(data: bytes) -> str:
    """Convert bytes to space-separated 8-bit binary strings."""
    return " ".join(f"{b:08b}" for b in data)


def bytes_to_mixed(data: bytes) -> str:
    """Printable ASCII chars as-is, non-printable as hex escapes."""
    result = []
    for b in data:
        if 32 <= b < 127:
            result.append(chr(b))
        else:
            result.append(f"[{b:02X}]")
    return "".join(result)


# Valid layer identifiers for bytes_to_mixed_custom.
MIXED_LAYER_NAMES: tuple[str, ...] = ("hex", "ascii", "dec", "bin")


def bytes_to_mixed_custom(data: bytes, layers: list[str]) -> str:
    """Format each byte as a combination of the selected sub-formats.

    *layers* is an ordered list, e.g. ``["hex", "ascii"]``.  Each byte is
    rendered as ``part1·part2·…`` (middle dot separator).  Bytes are separated
    by a single space.

    Layer keys:
      ``"hex"``   → ``41``
      ``"ascii"`` → ``A`` (printable), ``·`` (non-printable)
      ``"dec"``   → ``65``
      ``"bin"``   → ``01000001``

    Falls back to plain hex when *layers* is empty.
    """
    if not layers:
        return bytes_to_hex_inline(data)

    parts: list[str] = []
    for b in data:
        byte_parts: list[str] = []
        for layer in layers:
            if layer == "hex":
                byte_parts.append(f"{b:02X}")
            elif layer == "ascii":
                byte_parts.append(chr(b) if 32 <= b < 127 else "·")
            elif layer == "dec":
                byte_parts.append(str(b))
            elif layer == "bin":
                byte_parts.append(f"{b:08b}")
        parts.append("·".join(byte_parts))
    return " ".join(parts)


def hex_str_to_bytes(s: str) -> bytes:
    """Parse hex string like '41 42 43' or '414243' to bytes.

    Raises ValueError on invalid input.
    """
    s = s.strip()
    if not s:
        return b""

    # Remove common separators: spaces, colons, dashes
    cleaned = s.replace(" ", "").replace(":", "").replace("-", "")

    if len(cleaned) % 2 != 0:
        raise ValueError(f"Hex string has odd number of characters: {s!r}")

    try:
        return bytes.fromhex(cleaned)
    except ValueError as e:
        raise ValueError(f"Invalid hex string {s!r}: {e}") from e


def format_bytes(data: bytes, mode: DisplayMode) -> str:
    """Dispatch byte formatting based on DisplayMode."""
    if mode == DisplayMode.ASCII:
        return bytes_to_ascii(data)
    elif mode == DisplayMode.HEX:
        return bytes_to_hex(data)
    elif mode == DisplayMode.DECIMAL:
        return bytes_to_decimal(data)
    elif mode == DisplayMode.BINARY:
        return bytes_to_binary(data)
    elif mode == DisplayMode.MIXED:
        return bytes_to_mixed(data)
    else:
        return bytes_to_ascii(data)


def format_line(data: bytes, mode: DisplayMode) -> str:
    """Single-line representation of a data chunk (no offsets/sidebar).

    Unlike :func:`format_bytes`, HEX mode here is a simple inline string
    ('02 03 05') suitable for one-packet-per-line terminal display.
    """
    if mode == DisplayMode.ASCII:
        return bytes_to_ascii(data)
    elif mode == DisplayMode.HEX:
        return bytes_to_hex_inline(data)
    elif mode == DisplayMode.DECIMAL:
        return bytes_to_decimal(data)
    elif mode == DisplayMode.BINARY:
        return bytes_to_binary(data)
    elif mode == DisplayMode.MIXED:
        return bytes_to_mixed(data)
    return bytes_to_ascii(data)


def apply_terminator(data: bytes, terminator: str) -> bytes:
    """Append CR/LF/CRLF based on terminator string."""
    if terminator == "cr":
        return data + b"\r"
    elif terminator == "lf":
        return data + b"\n"
    elif terminator == "crlf":
        return data + b"\r\n"
    return data
