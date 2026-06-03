"""Tests for kcom/models/sequence.py — TxSequence, wildcards, checksums."""
from __future__ import annotations

import pytest
from kcom.models.sequence import (
    TxSequence, _parse_data, _has_wildcards, _expand_hex_wildcards,
    _apply_terminator, _calc_checksum_bytes,
)
from kcom.utils.checksum import crc16_modbus, xor_checksum, sum8, crc8, crc32


class TestParseData:
    def test_hex_basic(self):
        assert _parse_data("41 42 43", "hex") == b"ABC"

    def test_hex_no_spaces(self):
        assert _parse_data("414243", "hex") == b"ABC"

    def test_hex_colon_sep(self):
        assert _parse_data("41:42:43", "hex") == b"ABC"

    def test_hex_odd_pads(self):
        assert _parse_data("F", "hex") == b"\x0F"

    def test_ascii_basic(self):
        result = _parse_data("Hello", "ascii")
        assert result == b"Hello"

    def test_dec_basic(self):
        assert _parse_data("65 66 67", "dec") == b"ABC"

    def test_bin_basic(self):
        assert _parse_data("01000001 01000010", "bin") == b"AB"

    def test_empty(self):
        assert _parse_data("", "hex") == b""
        assert _parse_data("   ", "ascii") == b""

    def test_dec_ignores_non_digits(self):
        # Non-digit parts should be skipped
        result = _parse_data("65 notanumber 66", "dec")
        assert result == b"AB"


class TestHasWildcards:
    def test_question_mark(self):
        assert _has_wildcards("FF ? 00")

    def test_hash(self):
        assert _has_wildcards("01 # 03")

    def test_angle_bracket(self):
        assert _has_wildcards("01 <Counter> 03")

    def test_caret(self):
        assert _has_wildcards("^0F")

    def test_no_wildcards(self):
        assert not _has_wildcards("01 02 03")

    def test_empty(self):
        assert not _has_wildcards("")


class TestExpandHexWildcards:
    def test_regular_hex(self):
        result, counter = _expand_hex_wildcards("41 42", 0, {})
        assert result == b"AB"

    def test_random_byte(self):
        # ? produces a single byte in range 0-255
        for _ in range(10):
            result, _ = _expand_hex_wildcards("?", 0, {})
            assert len(result) == 1
            assert 0 <= result[0] <= 255

    def test_counter(self):
        result, new_counter = _expand_hex_wildcards("# #", 5, {})
        assert result[0] == 5
        assert result[1] == 6
        assert new_counter == 7

    def test_counter_wrap(self):
        result, new_counter = _expand_hex_wildcards("#", 255, {})
        assert result[0] == 255
        assert new_counter == 0

    def test_mask_wildcard(self):
        # ^0F = random & 0x0F → low nibble only
        for _ in range(20):
            result, _ = _expand_hex_wildcards("^0F", 0, {})
            assert result[0] & 0xF0 == 0

    def test_named_int(self):
        result, _ = _expand_hex_wildcards("<seq>", 0, {"seq": 0x42})
        assert result == b"\x42"

    def test_named_bytes(self):
        result, _ = _expand_hex_wildcards("<hdr>", 0, {"hdr": b"\x01\x02"})
        assert result == b"\x01\x02"

    def test_named_unknown(self):
        result, _ = _expand_hex_wildcards("<missing>", 0, {})
        assert result == b"\x00"

    def test_odd_hex_padded(self):
        result, _ = _expand_hex_wildcards("F", 0, {})
        assert result == b"\x0F"

    def test_invalid_token_skipped(self):
        result, _ = _expand_hex_wildcards("ZZ", 0, {})
        assert result == b""


class TestApplyTerminator:
    def test_cr(self):
        assert _apply_terminator(b"data", "cr") == b"data\r"

    def test_lf(self):
        assert _apply_terminator(b"data", "lf") == b"data\n"

    def test_crlf(self):
        assert _apply_terminator(b"data", "crlf") == b"data\r\n"

    def test_none(self):
        assert _apply_terminator(b"data", "none") == b"data"


class TestCalcChecksumBytes:
    def test_xor(self):
        data = bytes([0x01, 0x02, 0x04])
        cs = _calc_checksum_bytes(data, "xor")
        assert cs == bytes([xor_checksum(data)])

    def test_sum8(self):
        data = b"\x01\x02\x03"
        assert _calc_checksum_bytes(data, "sum8") == bytes([sum8(data)])

    def test_crc8(self):
        data = b"\x01\x02"
        assert _calc_checksum_bytes(data, "crc8") == bytes([crc8(data)])

    def test_crc16_modbus(self):
        data = bytes([0x01, 0x03, 0x00, 0x00, 0x00, 0x0A])
        expected_crc = crc16_modbus(data)
        cs = _calc_checksum_bytes(data, "crc16_modbus")
        assert cs == bytes([expected_crc & 0xFF, (expected_crc >> 8) & 0xFF])

    def test_crc32(self):
        data = b"hello"
        cs = _calc_checksum_bytes(data, "crc32")
        assert len(cs) == 4
        assert int.from_bytes(cs, "little") == crc32(data)

    def test_none_returns_empty(self):
        assert _calc_checksum_bytes(b"\x01", "none") == b""


class TestTxSequence:
    def test_defaults(self):
        s = TxSequence()
        assert s.encoding == "hex"
        assert s.terminator == "none"
        assert s.checksum == "none"
        assert s.repeat_count == 1

    def test_get_bytes_simple_hex(self):
        s = TxSequence(data_str="41 42 43", encoding="hex")
        assert s.get_bytes() == b"ABC"

    def test_get_bytes_ascii(self):
        s = TxSequence(data_str="Hello", encoding="ascii")
        assert s.get_bytes() == b"Hello"

    def test_get_bytes_dec(self):
        s = TxSequence(data_str="65 66 67", encoding="dec")
        assert s.get_bytes() == b"ABC"

    def test_get_bytes_bin(self):
        s = TxSequence(data_str="01000001", encoding="bin")
        assert s.get_bytes() == b"A"

    def test_terminator_appended_before_checksum(self):
        s = TxSequence(data_str="01", encoding="hex", terminator="lf", checksum="xor")
        raw = s.get_bytes()
        # data=01, term=\n (0x0A), checksum=01^0A=0B
        assert raw == bytes([0x01, 0x0A, 0x01 ^ 0x0A])

    def test_checksum_start_offset(self):
        s = TxSequence(data_str="AA 01 02", encoding="hex",
                       checksum="xor", checksum_start=1)
        raw = s.get_bytes()
        # xor of bytes from index 1: 01^02=03
        assert raw[-1] == 0x03
        assert raw[:3] == bytes([0xAA, 0x01, 0x02])

    def test_counter_increments(self):
        s = TxSequence(data_str="#", encoding="hex")
        b1 = s.get_bytes()
        b2 = s.get_bytes()
        assert b1 == bytes([0])
        assert b2 == bytes([1])

    def test_counter_reset(self):
        s = TxSequence(data_str="#", encoding="hex")
        s.get_bytes()
        s.get_bytes()
        s.reset_counter()
        assert s.get_bytes() == bytes([0])

    def test_hex_preview_truncates(self):
        s = TxSequence(data_str=" ".join(["FF"] * 20), encoding="hex")
        preview = s.hex_preview(max_bytes=4)
        assert "…" in preview

    def test_hex_preview_exact(self):
        s = TxSequence(data_str="01 02 03", encoding="hex")
        preview = s.hex_preview(max_bytes=4)
        assert "…" not in preview

    def test_hex_preview_parse_error(self):
        s = TxSequence(data_str="ZZZZ", encoding="hex")
        # Should not crash
        preview = s.hex_preview()
        assert isinstance(preview, str)

    def test_round_trip_basic(self):
        s = TxSequence(name="Test", data_str="01 02", encoding="hex",
                       terminator="lf", checksum="xor", repeat_count=3)
        s2 = TxSequence.from_dict(s.to_dict())
        assert s2.name == s.name
        assert s2.data_str == s.data_str
        assert s2.terminator == s.terminator
        assert s2.checksum == s.checksum
        assert s2.repeat_count == s.repeat_count

    def test_round_trip_named_values_int(self):
        s = TxSequence(named_values={"addr": 0x42})
        d = s.to_dict()
        s2 = TxSequence.from_dict(d)
        assert s2.named_values["addr"] == 0x42

    def test_round_trip_named_values_bytes(self):
        s = TxSequence(named_values={"hdr": b"\x01\x02"})
        d = s.to_dict()
        s2 = TxSequence.from_dict(d)
        assert s2.named_values["hdr"] == b"\x01\x02"

    def test_counter_not_persisted(self):
        s = TxSequence(data_str="#", encoding="hex")
        s.get_bytes()  # counter → 1
        s2 = TxSequence.from_dict(s.to_dict())
        assert s2.get_bytes() == bytes([0])  # resets to 0

    def test_from_dict_legacy_data_key(self):
        # Legacy projects used "data" instead of "data_str"
        s = TxSequence.from_dict({"data": "01 02", "encoding": "hex"})
        assert s.data_str == "01 02"

    def test_crc16_modbus_checksum(self):
        data = bytes([0x01, 0x03, 0x00, 0x00, 0x00, 0x0A])
        s = TxSequence(
            data_str=" ".join(f"{b:02X}" for b in data),
            encoding="hex",
            checksum="crc16_modbus",
        )
        result = s.get_bytes()
        expected_crc = crc16_modbus(data)
        assert result[-2] == expected_crc & 0xFF
        assert result[-1] == (expected_crc >> 8) & 0xFF
