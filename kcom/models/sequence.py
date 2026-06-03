"""TX and RX Sequence/Trigger models."""
from __future__ import annotations

import random
import re
import uuid
from dataclasses import dataclass, field
from kcom.utils.checksum import crc16_modbus, crc8, crc32, xor_checksum, sum8


def _parse_data(data_str: str, encoding: str) -> bytes:
    """Parse a data string according to encoding into bytes."""
    s = data_str.strip()
    if not s:
        return b""
    if encoding == "ascii":
        # Unescape \xNN, \r, \n sequences
        return s.encode("latin-1").decode("unicode_escape").encode("latin-1")
    elif encoding == "hex":
        # Accept "41 42 43" or "414243"
        s = s.replace(" ", "").replace(":", "").replace("-", "")
        if len(s) % 2 != 0:
            s = "0" + s
        return bytes.fromhex(s)
    elif encoding == "dec":
        parts = s.split()
        return bytes(int(p) for p in parts if p.isdigit())
    elif encoding == "bin":
        parts = s.split()
        return bytes(int(p, 2) for p in parts if all(c in "01" for c in p))
    return s.encode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Wildcard expansion (hex-mode only)
# ---------------------------------------------------------------------------

# Tokens recognized in hex-mode data strings:
#   FF, 0A       — regular two-nibble hex byte
#   ?            — random byte 0x00–0xFF
#   #            — auto-incrementing counter (wraps at 256)
#   ^XY          — random byte masked by 0xXY  (e.g. ^0F = low nibble only)
#   <Name>       — named value lookup (bytes or 0–255 int) from named_values dict
_WC_TOKEN = re.compile(
    r"<[^>]+>"       # <Name>
    r"|[?#]"         # ? or #
    r"|\^[0-9A-Fa-f]{2}"  # ^XY bitmask
    r"|[0-9A-Fa-f]{1,2}"  # normal hex byte(s)
    r"|\S+"          # catch-all (parse error — skip gracefully)
)


def _has_wildcards(data_str: str) -> bool:
    return bool(re.search(r"[?#<^]", data_str))


def _expand_hex_wildcards(
    data_str: str,
    counter: int,
    named_values: dict,
) -> tuple[bytes, int]:
    """Expand wildcard tokens in a hex-encoded data string.

    Returns ``(expanded_bytes, new_counter)``.
    """
    result = bytearray()
    for token in _WC_TOKEN.findall(data_str):
        if token == "?":
            result.append(random.randint(0, 255))
        elif token == "#":
            result.append(counter & 0xFF)
            counter = (counter + 1) & 0xFF
        elif token.startswith("^") and len(token) == 3:
            try:
                mask = int(token[1:], 16)
                result.append(random.randint(0, 255) & mask)
            except ValueError:
                pass
        elif token.startswith("<") and token.endswith(">"):
            name = token[1:-1]
            val = named_values.get(name)
            if isinstance(val, int):
                result.append(val & 0xFF)
            elif isinstance(val, (bytes, bytearray)):
                result.extend(val)
            else:
                result.append(0x00)   # unknown name → null byte
        else:
            # Regular 1–2 char hex token
            try:
                padded = token if len(token) % 2 == 0 else "0" + token
                result.extend(bytes.fromhex(padded))
            except ValueError:
                pass
    return bytes(result), counter


def _apply_terminator(data: bytes, terminator: str) -> bytes:
    if terminator == "cr":
        return data + b"\r"
    elif terminator == "lf":
        return data + b"\n"
    elif terminator == "crlf":
        return data + b"\r\n"
    return data


def _calc_checksum_bytes(data: bytes, cs_type: str) -> bytes:
    if cs_type == "xor":
        return bytes([xor_checksum(data)])
    elif cs_type == "sum8":
        return bytes([sum8(data)])
    elif cs_type == "crc8":
        return bytes([crc8(data)])
    elif cs_type == "crc16_modbus":
        v = crc16_modbus(data)
        return bytes([v & 0xFF, (v >> 8) & 0xFF])
    elif cs_type == "crc32":
        v = crc32(data)
        return v.to_bytes(4, "little")
    return b""


@dataclass
class TxSequence:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    data_str: str = ""              # User-entered data string
    encoding: str = "hex"           # "hex", "ascii", "dec", "bin"
    terminator: str = "none"        # "none", "cr", "lf", "crlf"
    checksum: str = "none"          # "none", "xor", "sum8", "crc8", "crc16_modbus", "crc32"
    checksum_start: int = 0         # Byte offset to start checksum (0 = all bytes)
    repeat_count: int = 1
    repeat_interval_ms: int = 0
    delay_before_ms: int = 0
    byte_delay_ms: int = 0          # 6.2: inter-byte delay in ms (0 = burst send)
    color: str = "#a6e3a1"
    description: str = ""
    # 6.1 wildcard support: named value lookup dict (<Name> token → bytes or int)
    named_values: dict = field(default_factory=dict, compare=False, repr=False)
    # Per-instance counter for '#' wildcard; not persisted, resets on load
    _counter: int = field(default=0, init=False, compare=False, repr=False)

    def get_bytes(self) -> bytes:
        """Build the final byte sequence: parse (+ expand wildcards) → terminator → checksum."""
        if self.encoding == "hex" and _has_wildcards(self.data_str):
            raw, self._counter = _expand_hex_wildcards(
                self.data_str, self._counter, self.named_values
            )
            raw = _apply_terminator(raw, self.terminator)
        else:
            raw = _parse_data(self.data_str, self.encoding)
            raw = _apply_terminator(raw, self.terminator)
        if self.checksum != "none":
            cs_data = raw[self.checksum_start:]
            raw = raw + _calc_checksum_bytes(cs_data, self.checksum)
        return raw

    def reset_counter(self) -> None:
        """Reset the `#` wildcard counter back to 0."""
        self._counter = 0

    def hex_preview(self, max_bytes: int = 16) -> str:
        """Short hex string preview of the final bytes."""
        try:
            b = self.get_bytes()
        except Exception:
            return "[parse error]"
        chunk = b[:max_bytes]
        s = " ".join(f"{x:02X}" for x in chunk)
        return s + ("…" if len(b) > max_bytes else "")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "data_str": self.data_str,
            "encoding": self.encoding,
            "terminator": self.terminator,
            "checksum": self.checksum,
            "checksum_start": self.checksum_start,
            "repeat_count": self.repeat_count,
            "repeat_interval_ms": self.repeat_interval_ms,
            "delay_before_ms": self.delay_before_ms,
            "byte_delay_ms": self.byte_delay_ms,
            "color": self.color,
            "description": self.description,
            # named_values: only persist string→int/hex entries (skip callable/complex)
            "named_values": {
                k: (v if isinstance(v, int) else v.hex() if isinstance(v, (bytes, bytearray)) else str(v))
                for k, v in self.named_values.items()
            },
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TxSequence":
        # Restore named_values: ints stay ints, hex strings become bytes
        raw_nv = d.get("named_values", {})
        named_values: dict = {}
        for k, v in raw_nv.items():
            if isinstance(v, int):
                named_values[k] = v
            elif isinstance(v, str):
                try:
                    named_values[k] = bytes.fromhex(v)
                except ValueError:
                    named_values[k] = v.encode("utf-8", "replace")
        return cls(
            id=d.get("id", str(uuid.uuid4())),
            name=d.get("name", ""),
            data_str=d.get("data_str", d.get("data", "")),
            encoding=d.get("encoding", "hex"),
            terminator=d.get("terminator", "none"),
            checksum=d.get("checksum", "none"),
            checksum_start=d.get("checksum_start", 0),
            repeat_count=d.get("repeat_count", 1),
            repeat_interval_ms=d.get("repeat_interval_ms", 0),
            delay_before_ms=d.get("delay_before_ms", 0),
            byte_delay_ms=d.get("byte_delay_ms", 0),
            color=d.get("color", "#a6e3a1"),
            description=d.get("description", ""),
            named_values=named_values,
        )
