"""Tests for kcom/models/port_config.py."""
from __future__ import annotations

import pytest
from kcom.models.port_config import (
    ConnectionType, Parity, FlowControl,
    SerialConfig, NetworkConfig, HIDConfig, NamedPipeConfig,
    PortConfig, TapConfig,
)


class TestSerialConfig:
    def test_defaults(self):
        c = SerialConfig()
        assert c.port == ""
        assert c.baud_rate == 115200
        assert c.data_bits == 8
        assert c.parity == Parity.NONE
        assert c.stop_bits == 1.0
        assert c.flow_control == FlowControl.NONE

    def test_to_dict_enum_values(self):
        c = SerialConfig(parity=Parity.EVEN, flow_control=FlowControl.RTS_CTS)
        d = c.to_dict()
        assert d["parity"] == "E"
        assert d["flow_control"] == "rtscts"

    def test_round_trip(self):
        c = SerialConfig(port="COM3", baud_rate=9600, parity=Parity.ODD, stop_bits=2.0)
        assert SerialConfig.from_dict(c.to_dict()) == c

    def test_from_dict_defaults(self):
        c = SerialConfig.from_dict({})
        assert c.baud_rate == 115200
        assert c.parity == Parity.NONE

    def test_all_parities(self):
        for p in Parity:
            c = SerialConfig.from_dict({"parity": p.value})
            assert c.parity == p

    def test_all_flow_controls(self):
        for fc in FlowControl:
            c = SerialConfig.from_dict({"flow_control": fc.value})
            assert c.flow_control == fc


class TestNetworkConfig:
    def test_defaults(self):
        c = NetworkConfig()
        assert c.host == "localhost"
        assert c.port == 502
        assert c.local_port == 0

    def test_round_trip(self):
        c = NetworkConfig(host="192.168.1.1", port=8080, local_port=5000)
        assert NetworkConfig.from_dict(c.to_dict()) == c

    def test_local_port_zero_omitted(self):
        c = NetworkConfig(local_port=0)
        assert "local_port" not in c.to_dict()

    def test_local_port_nonzero_included(self):
        c = NetworkConfig(local_port=5000)
        assert c.to_dict()["local_port"] == 5000

    def test_from_dict_defaults(self):
        c = NetworkConfig.from_dict({})
        assert c.host == "localhost"
        assert c.port == 502


class TestHIDConfig:
    def test_defaults(self):
        h = HIDConfig()
        assert h.vendor_id == 0
        assert h.product_id == 0
        assert h.interface_number == -1
        assert h.report_size == 64

    def test_round_trip(self):
        h = HIDConfig(vendor_id=0x046D, product_id=0xC52B, report_size=32)
        assert HIDConfig.from_dict(h.to_dict()) == h

    def test_from_dict_defaults(self):
        h = HIDConfig.from_dict({})
        assert h.report_size == 64
        assert h.interface_number == -1


class TestNamedPipeConfig:
    def test_defaults(self):
        n = NamedPipeConfig()
        assert n.path == ""

    def test_round_trip(self):
        n = NamedPipeConfig(path="/tmp/kcom.sock")
        assert NamedPipeConfig.from_dict(n.to_dict()) == n

    def test_from_dict_defaults(self):
        n = NamedPipeConfig.from_dict({})
        assert n.path == ""


class TestPortConfig:
    def test_defaults(self):
        p = PortConfig()
        assert p.connection_type == ConnectionType.SERIAL
        assert p.auto_reconnect is True

    def test_display_name_serial_port(self):
        p = PortConfig(serial=SerialConfig(port="/dev/ttyUSB0"))
        assert p.display_name() == "/dev/ttyUSB0"

    def test_display_name_serial_no_port(self):
        p = PortConfig()
        assert p.display_name() == "Serial"

    def test_display_name_custom_name_overrides(self):
        p = PortConfig(name="My Device")
        assert p.display_name() == "My Device"

    def test_display_name_tcp_server(self):
        p = PortConfig(
            connection_type=ConnectionType.TCP_SERVER,
            network=NetworkConfig(port=4321)
        )
        assert p.display_name() == "TCP Server :4321"

    def test_display_name_udp(self):
        p = PortConfig(
            connection_type=ConnectionType.UDP,
            network=NetworkConfig(host="10.0.0.1", port=1234)
        )
        assert p.display_name() == "UDP 10.0.0.1:1234"

    def test_display_name_usb_hid_with_vid_pid(self):
        p = PortConfig(
            connection_type=ConnectionType.USB_HID,
            hid=HIDConfig(vendor_id=0x046D, product_id=0xC52B)
        )
        assert p.display_name() == "HID 046D:C52B"

    def test_display_name_usb_hid_no_vid(self):
        p = PortConfig(connection_type=ConnectionType.USB_HID)
        assert p.display_name() == "USB HID"

    def test_display_name_named_pipe_client(self):
        p = PortConfig(
            connection_type=ConnectionType.NAMED_PIPE_CLIENT,
            named_pipe=NamedPipeConfig(path="/tmp/kcom.sock")
        )
        assert "Client" in p.display_name()
        assert "kcom.sock" in p.display_name()

    def test_display_name_named_pipe_server(self):
        p = PortConfig(
            connection_type=ConnectionType.NAMED_PIPE_SERVER,
            named_pipe=NamedPipeConfig(path="/tmp/kcom.sock")
        )
        assert "Server" in p.display_name()

    def test_display_name_tcp_client(self):
        p = PortConfig(
            connection_type=ConnectionType.TCP_CLIENT,
            network=NetworkConfig(host="192.168.1.1", port=8080)
        )
        assert p.display_name() == "192.168.1.1:8080"

    def test_round_trip_serial(self):
        p = PortConfig(
            connection_type=ConnectionType.SERIAL,
            serial=SerialConfig(port="COM1", baud_rate=9600),
            auto_reconnect=False,
        )
        assert PortConfig.from_dict(p.to_dict()) == p

    def test_round_trip_network(self):
        p = PortConfig(
            connection_type=ConnectionType.TCP_CLIENT,
            network=NetworkConfig(host="10.0.0.1", port=5000),
        )
        assert PortConfig.from_dict(p.to_dict()) == p

    def test_round_trip_hid(self):
        p = PortConfig(
            connection_type=ConnectionType.USB_HID,
            hid=HIDConfig(vendor_id=0x1234, product_id=0xABCD),
        )
        assert PortConfig.from_dict(p.to_dict()) == p

    def test_from_dict_defaults(self):
        p = PortConfig.from_dict({})
        assert p.connection_type == ConnectionType.SERIAL
        assert p.auto_reconnect is True


class TestTapConfig:
    def test_defaults(self):
        t = TapConfig()
        assert t.forward_mode == "off"
        assert t.name == ""

    def test_display_name_custom(self):
        t = TapConfig(name="Bridge")
        assert t.display_name() == "Bridge"

    def test_display_name_auto(self):
        t = TapConfig(
            port_a=PortConfig(serial=SerialConfig(port="/dev/ttyS0")),
            port_b=PortConfig(serial=SerialConfig(port="/dev/ttyS1")),
        )
        name = t.display_name()
        assert "/dev/ttyS0" in name
        assert "/dev/ttyS1" in name
        assert "↔" in name

    def test_round_trip(self):
        t = TapConfig(
            port_a=PortConfig(serial=SerialConfig(port="COM1")),
            port_b=PortConfig(connection_type=ConnectionType.TCP_CLIENT),
            forward_mode="both",
            name="Test",
        )
        t2 = TapConfig.from_dict(t.to_dict())
        assert t2.forward_mode == "both"
        assert t2.name == "Test"
        assert t2.port_a.serial.port == "COM1"

    def test_from_dict_defaults(self):
        t = TapConfig.from_dict({})
        assert t.forward_mode == "off"
