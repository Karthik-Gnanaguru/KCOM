"""Checksum and CRC utility functions."""
from __future__ import annotations
import zlib


def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def xor_checksum(data: bytes) -> int:
    result = 0
    for byte in data:
        result ^= byte
    return result


def crc8(data: bytes) -> int:
    crc = 0x00
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = (crc << 1) ^ 0x07
            else:
                crc <<= 1
            crc &= 0xFF
    return crc


def sum8(data: bytes) -> int:
    """8-bit sum of all bytes (modulo 256)."""
    return sum(data) & 0xFF


def sum16(data: bytes) -> int:
    """16-bit sum of all bytes (modulo 65536)."""
    return sum(data) & 0xFFFF
