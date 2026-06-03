"""Tests for kcom/utils/platform_utils.py."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from kcom.utils.platform_utils import (
    PortInfo, get_platform, is_windows, is_linux, is_macos,
    _classify_port, _port_sort_key, get_available_ports,
)


class TestPortInfo:
    def test_display_label_with_description(self):
        p = PortInfo(device="/dev/ttyUSB0", description="FTDI USB Serial",
                     port_type="usb")
        label = p.display_label()
        assert "/dev/ttyUSB0" in label
        assert "FTDI USB Serial" in label

    def test_display_label_same_desc_as_device(self):
        p = PortInfo(device="/dev/ttyUSB0", description="/dev/ttyUSB0",
                     port_type="usb")
        assert p.display_label() == "/dev/ttyUSB0"

    def test_type_badge_hardware(self):
        p = PortInfo(device="COM1", description="", port_type="hardware")
        assert p.type_badge() == "[HW]"

    def test_type_badge_usb(self):
        p = PortInfo(device="COM3", description="", port_type="usb")
        assert p.type_badge() == "[USB]"

    def test_type_badge_virtual(self):
        p = PortInfo(device="/dev/tnt0", description="", port_type="virtual")
        assert p.type_badge() == "[VIRT]"

    def test_type_badge_bluetooth(self):
        p = PortInfo(device="COM5", description="", port_type="bluetooth")
        assert p.type_badge() == "[BT]"

    def test_type_badge_unknown(self):
        p = PortInfo(device="X", description="", port_type="unknown")
        assert p.type_badge() == ""

    def test_accessible_default_true(self):
        p = PortInfo(device="X", description="", port_type="unknown")
        assert p.accessible is True


class TestClassifyPort:
    def test_usb_in_hwid(self):
        assert _classify_port("/dev/ttyUSB0", "USB VID:PID=1234:ABCD") == "usb"

    def test_bluetooth(self):
        assert _classify_port("rfcomm0", "") == "bluetooth"

    def test_virtual_tnt(self):
        assert _classify_port("/dev/tnt0", "") == "virtual"

    def test_virtual_pts(self):
        assert _classify_port("/dev/pts/1", "") == "virtual"

    def test_hardware_fallback(self):
        result = _classify_port("/dev/ttyS0", "")
        assert result in ("hardware", "unknown")


class TestPortSortKey:
    def test_numeric_part_extracted(self):
        key1 = _port_sort_key("COM1")
        key10 = _port_sort_key("COM10")
        key2 = _port_sort_key("COM2")
        assert key1 < key2 < key10

    def test_linux_tty(self):
        k0 = _port_sort_key("/dev/ttyS0")
        k2 = _port_sort_key("/dev/ttyS2")
        k10 = _port_sort_key("/dev/ttyS10")
        assert k0 < k2 < k10

    def test_no_digits(self):
        key = _port_sort_key("nodigits")
        assert isinstance(key, tuple)


class TestPlatformDetect:
    def test_get_platform_returns_known(self):
        assert get_platform() in ("windows", "macos", "linux")

    def test_exactly_one_true(self):
        flags = [is_windows(), is_linux(), is_macos()]
        assert sum(flags) == 1


class TestGetAvailablePorts:
    def test_returns_list(self):
        ports = get_available_ports()
        assert isinstance(ports, list)

    def test_all_portinfo_instances(self):
        ports = get_available_ports()
        for p in ports:
            assert isinstance(p, PortInfo)

    def test_virtual_false_excludes_virtual(self):
        """With include_virtual=False, no virtual type ports should appear."""
        with patch("serial.tools.list_ports.comports", return_value=[]):
            ports = get_available_ports(include_virtual=False)
        virtual_ports = [p for p in ports if p.port_type == "virtual"]
        assert virtual_ports == []

    def test_device_strings_nonempty(self):
        ports = get_available_ports()
        for p in ports:
            assert p.device  # non-empty device string
