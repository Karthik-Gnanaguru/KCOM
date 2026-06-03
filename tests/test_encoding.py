"""Tests for kcom/utils/encoding.py."""
from __future__ import annotations

import pytest
from kcom.utils.encoding import (
    DisplayMode,
    bytes_to_ascii,
    bytes_to_binary,
    bytes_to_decimal,
    bytes_to_hex,
    bytes_to_hex_inline,
    bytes_to_mixed,
    hex_str_to_bytes,
    format_bytes,
    format_line,
    apply_terminator,
)


class TestBytesToAscii:
    def test_printable(self):
        assert bytes_to_ascii(b"Hello") == "Hello"

    def test_cr_escape(self):
        assert bytes_to_ascii(b"\r") == "\\r"

    def test_lf_escape(self):
        assert bytes_to_ascii(b"\n") == "\\n"

    def test_tab_escape(self):
        assert bytes_to_ascii(b"\t") == "\\t"

    def test_non_printable_hex_escape(self):
        assert bytes_to_ascii(bytes([0x01])) == "\\x01"
        assert bytes_to_ascii(bytes([0xFF])) == "\\xff"

    def test_mixed(self):
        result = bytes_to_ascii(b"A\x00B")
        assert result == "A\\x00B"

    def test_empty(self):
        assert bytes_to_ascii(b"") == ""

    def test_space_is_printable(self):
        assert bytes_to_ascii(b" ") == " "

    def test_tilde_is_printable(self):
        assert bytes_to_ascii(b"~") == "~"

    def test_del_is_escaped(self):
        # 0x7F = DEL — not in printable range 32..126
        assert bytes_to_ascii(bytes([0x7F])) == "\\x7f"


class TestBytesToHexInline:
    def test_basic(self):
        assert bytes_to_hex_inline(b"\x01\x02\x03") == "01 02 03"

    def test_uppercase(self):
        assert bytes_to_hex_inline(b"\xAB\xCD") == "AB CD"

    def test_empty(self):
        assert bytes_to_hex_inline(b"") == ""

    def test_single(self):
        assert bytes_to_hex_inline(b"\xFF") == "FF"


class TestBytesToHex:
    def test_offset_present(self):
        result = bytes_to_hex(b"\x41\x42\x43")
        assert "00000000" in result

    def test_ascii_sidebar(self):
        result = bytes_to_hex(b"ABC")
        assert "ABC" in result

    def test_non_printable_dot(self):
        result = bytes_to_hex(bytes([0x01, 0x41]))
        assert "." in result

    def test_empty(self):
        assert bytes_to_hex(b"") == ""

    def test_multiline(self):
        data = bytes(range(32))
        lines = bytes_to_hex(data).splitlines()
        assert len(lines) == 2  # 16 bytes per line → 2 lines

    def test_padding_consistent(self):
        # Short chunk should still be padded to full width
        result = bytes_to_hex(b"\x01", width=16)
        assert "  |" in result


class TestBytesToDecimal:
    def test_basic(self):
        assert bytes_to_decimal(b"\x01\x02\x03") == "1 2 3"

    def test_empty(self):
        assert bytes_to_decimal(b"") == ""

    def test_zero(self):
        assert bytes_to_decimal(b"\x00") == "0"

    def test_max(self):
        assert bytes_to_decimal(b"\xFF") == "255"


class TestBytesToBinary:
    def test_basic(self):
        assert bytes_to_binary(b"\x01") == "00000001"

    def test_empty(self):
        assert bytes_to_binary(b"") == ""

    def test_two_bytes(self):
        assert bytes_to_binary(b"\x00\xFF") == "00000000 11111111"

    def test_leading_zeros(self):
        assert bytes_to_binary(b"\x04") == "00000100"


class TestBytesToMixed:
    def test_printable_passthrough(self):
        assert bytes_to_mixed(b"Hi") == "Hi"

    def test_non_printable_hex(self):
        assert bytes_to_mixed(bytes([0x01])) == "[01]"

    def test_mixed(self):
        result = bytes_to_mixed(b"A\x01B")
        assert result == "A[01]B"

    def test_empty(self):
        assert bytes_to_mixed(b"") == ""

    def test_space_printable(self):
        assert bytes_to_mixed(b" ") == " "


class TestHexStrToBytes:
    def test_spaced(self):
        assert hex_str_to_bytes("41 42 43") == b"ABC"

    def test_no_sep(self):
        assert hex_str_to_bytes("414243") == b"ABC"

    def test_colon_sep(self):
        assert hex_str_to_bytes("41:42:43") == b"ABC"

    def test_dash_sep(self):
        assert hex_str_to_bytes("41-42-43") == b"ABC"

    def test_empty(self):
        assert hex_str_to_bytes("") == b""

    def test_whitespace_only(self):
        assert hex_str_to_bytes("   ") == b""

    def test_odd_length_raises(self):
        with pytest.raises(ValueError):
            hex_str_to_bytes("414")

    def test_invalid_hex_raises(self):
        with pytest.raises(ValueError):
            hex_str_to_bytes("GG")

    def test_uppercase(self):
        assert hex_str_to_bytes("FF") == b"\xFF"

    def test_lowercase(self):
        assert hex_str_to_bytes("ff") == b"\xFF"


class TestFormatBytes:
    def test_ascii_mode(self):
        assert format_bytes(b"Hi", DisplayMode.ASCII) == "Hi"

    def test_hex_mode_contains_offset(self):
        result = format_bytes(b"ABC", DisplayMode.HEX)
        assert "00000000" in result

    def test_decimal_mode(self):
        assert format_bytes(b"\x01", DisplayMode.DECIMAL) == "1"

    def test_binary_mode(self):
        assert format_bytes(b"\xFF", DisplayMode.BINARY) == "11111111"

    def test_mixed_mode(self):
        assert format_bytes(b"\x01A", DisplayMode.MIXED) == "[01]A"


class TestFormatLine:
    def test_hex_inline(self):
        result = format_line(b"\x01\x02", DisplayMode.HEX)
        assert result == "01 02"
        assert "\n" not in result

    def test_ascii(self):
        assert format_line(b"Hi", DisplayMode.ASCII) == "Hi"

    def test_decimal(self):
        assert format_line(b"\x05", DisplayMode.DECIMAL) == "5"

    def test_binary(self):
        assert format_line(b"\x01", DisplayMode.BINARY) == "00000001"

    def test_mixed(self):
        assert format_line(b"\x00A", DisplayMode.MIXED) == "[00]A"


class TestApplyTerminator:
    def test_cr(self):
        assert apply_terminator(b"hello", "cr") == b"hello\r"

    def test_lf(self):
        assert apply_terminator(b"hello", "lf") == b"hello\n"

    def test_crlf(self):
        assert apply_terminator(b"hello", "crlf") == b"hello\r\n"

    def test_none(self):
        assert apply_terminator(b"hello", "none") == b"hello"

    def test_unknown(self):
        assert apply_terminator(b"hello", "unknown") == b"hello"

    def test_empty_data(self):
        assert apply_terminator(b"", "lf") == b"\n"
