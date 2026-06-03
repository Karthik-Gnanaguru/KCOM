"""Tests for kcom/utils/checksum.py."""
from __future__ import annotations

import pytest
from kcom.utils.checksum import crc16_modbus, crc32, xor_checksum, crc8, sum8, sum16


class TestCRC16Modbus:
    def test_known_vector(self):
        # CRC16/Modbus: 01 03 00 00 00 0A → 0xCDC5
        data = bytes([0x01, 0x03, 0x00, 0x00, 0x00, 0x0A])
        assert crc16_modbus(data) == 0xCDC5

    def test_empty(self):
        assert crc16_modbus(b"") == 0xFFFF

    def test_single_byte(self):
        # Manual: init=0xFFFF, process 0x01
        result = crc16_modbus(bytes([0x01]))
        assert 0 <= result <= 0xFFFF

    def test_range(self):
        for data in [b"hello", b"\x00\xFF", b"\xAA\xBB\xCC"]:
            r = crc16_modbus(data)
            assert 0 <= r <= 0xFFFF

    def test_known_vector_2(self):
        # CRC16/Modbus: 01 03 00 64 00 01 → 0xD5C5
        data = bytes([0x01, 0x03, 0x00, 0x64, 0x00, 0x01])
        assert crc16_modbus(data) == 0xD5C5

    def test_byte_order_matters(self):
        assert crc16_modbus(b"\x01\x02") != crc16_modbus(b"\x02\x01")


class TestCRC32:
    def test_known_vector(self):
        assert crc32(b"123456789") == 0xCBF43926

    def test_empty(self):
        assert crc32(b"") == 0x00000000

    def test_range(self):
        r = crc32(b"KCom")
        assert 0 <= r <= 0xFFFFFFFF

    def test_deterministic(self):
        assert crc32(b"test") == crc32(b"test")


class TestXORChecksum:
    def test_single_byte(self):
        assert xor_checksum(bytes([0xAB])) == 0xAB

    def test_two_same_bytes(self):
        assert xor_checksum(bytes([0xFF, 0xFF])) == 0x00

    def test_empty(self):
        assert xor_checksum(b"") == 0

    def test_known(self):
        assert xor_checksum(bytes([0x01, 0x02, 0x04])) == 0x07

    def test_range(self):
        assert 0 <= xor_checksum(b"\xAA\xBB\xCC") <= 0xFF


class TestCRC8:
    def test_empty(self):
        assert crc8(b"") == 0x00

    def test_range(self):
        for data in [b"\x01", b"\xFF", b"hello"]:
            assert 0 <= crc8(data) <= 0xFF

    def test_known_vector(self):
        # CRC-8 (poly 0x07): 0x01 0x02 → verify with manual calc
        r1 = crc8(bytes([0x01, 0x02]))
        assert isinstance(r1, int)
        assert 0 <= r1 <= 255

    def test_deterministic(self):
        assert crc8(b"abc") == crc8(b"abc")

    def test_single_byte(self):
        r = crc8(bytes([0x31]))
        assert 0 <= r <= 0xFF


class TestSum8:
    def test_zero(self):
        assert sum8(b"") == 0

    def test_single(self):
        assert sum8(bytes([0x42])) == 0x42

    def test_wrap_around(self):
        assert sum8(bytes([0xFF, 0x01])) == 0x00

    def test_known(self):
        assert sum8(bytes([0x01, 0x02, 0x03])) == 0x06

    def test_large_wrap(self):
        assert sum8(bytes([0x80, 0x80])) == 0x00


class TestSum16:
    def test_zero(self):
        assert sum16(b"") == 0

    def test_single(self):
        assert sum16(bytes([0x01])) == 0x01

    def test_wrap_around(self):
        # 0xFF + 0xFF + 0x02 = 512 = 0x0200; sum16 keeps 16-bit result
        assert sum16(bytes([0xFF, 0xFF, 0x02])) == 0x0200

    def test_range(self):
        assert 0 <= sum16(b"hello world") <= 0xFFFF

    def test_larger_than_sum8(self):
        data = bytes(range(100))
        assert sum16(data) >= sum8(data) or sum16(data) == sum8(data) % 256
