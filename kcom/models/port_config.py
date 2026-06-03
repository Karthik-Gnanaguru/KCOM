"""Port and connection configuration dataclasses."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum


class ConnectionType(Enum):
    SERIAL = "serial"
    TCP_CLIENT = "tcp_client"
    TCP_SERVER = "tcp_server"
    UDP = "udp"
    USB_HID = "usb_hid"
    NAMED_PIPE_CLIENT = "named_pipe_client"
    NAMED_PIPE_SERVER = "named_pipe_server"
    BLUETOOTH = "bluetooth"


class Parity(Enum):
    NONE = "N"
    ODD = "O"
    EVEN = "E"
    MARK = "M"
    SPACE = "S"


class FlowControl(Enum):
    NONE = "none"
    RTS_CTS = "rtscts"
    XON_XOFF = "xonxoff"
    DTR_DSR = "dtrdsr"


@dataclass
class SerialConfig:
    port: str = ""
    baud_rate: int = 115200
    data_bits: int = 8
    parity: Parity = Parity.NONE
    stop_bits: float = 1.0
    flow_control: FlowControl = FlowControl.NONE
    timeout: float = 0.0  # non-blocking

    def to_dict(self) -> dict:
        return {
            "port": self.port,
            "baud_rate": self.baud_rate,
            "data_bits": self.data_bits,
            "parity": self.parity.value,
            "stop_bits": self.stop_bits,
            "flow_control": self.flow_control.value,
            "timeout": self.timeout,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SerialConfig":
        return cls(
            port=d.get("port", ""),
            baud_rate=d.get("baud_rate", 115200),
            data_bits=d.get("data_bits", 8),
            parity=Parity(d.get("parity", "N")),
            stop_bits=d.get("stop_bits", 1.0),
            flow_control=FlowControl(d.get("flow_control", "none")),
            timeout=d.get("timeout", 0.0),
        )


@dataclass
class NetworkConfig:
    host: str = "localhost"
    port: int = 502
    local_port: int = 0   # UDP: local bind port (0 = OS-assigned)

    def to_dict(self) -> dict:
        d: dict = {"host": self.host, "port": self.port}
        if self.local_port:
            d["local_port"] = self.local_port
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "NetworkConfig":
        return cls(
            host=d.get("host", "localhost"),
            port=d.get("port", 502),
            local_port=d.get("local_port", 0),
        )


@dataclass
class HIDConfig:
    """USB HID device selector (requires ``hidapi`` package)."""
    vendor_id: int = 0       # 0 = any
    product_id: int = 0      # 0 = any
    usage_page: int = 0      # 0 = any (HID usage page filter)
    interface_number: int = -1  # -1 = first available
    report_size: int = 64    # bytes per report (excluding report-id byte)
    # Non-zero VID/PID address a specific device; the config dialog pre-fills
    # these from the device list scan.

    def to_dict(self) -> dict:
        return {
            "vendor_id": self.vendor_id,
            "product_id": self.product_id,
            "usage_page": self.usage_page,
            "interface_number": self.interface_number,
            "report_size": self.report_size,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HIDConfig":
        return cls(
            vendor_id=d.get("vendor_id", 0),
            product_id=d.get("product_id", 0),
            usage_page=d.get("usage_page", 0),
            interface_number=d.get("interface_number", -1),
            report_size=d.get("report_size", 64),
        )


@dataclass
class NamedPipeConfig:
    """Named pipe / Unix domain socket configuration."""
    path: str = ""   # Win32: r"\\.\pipe\name" · Unix: /tmp/kcom.sock

    def to_dict(self) -> dict:
        return {"path": self.path}

    @classmethod
    def from_dict(cls, d: dict) -> "NamedPipeConfig":
        return cls(path=d.get("path", ""))


@dataclass
class PortConfig:
    connection_type: ConnectionType = ConnectionType.SERIAL
    serial: SerialConfig = field(default_factory=SerialConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    hid: HIDConfig = field(default_factory=HIDConfig)
    named_pipe: NamedPipeConfig = field(default_factory=NamedPipeConfig)
    name: str = ""  # user-defined name, defaults to port device name
    auto_reconnect: bool = True  # reconnect automatically after unexpected disconnect

    def display_name(self) -> str:
        if self.name:
            return self.name
        ct = self.connection_type
        if ct == ConnectionType.SERIAL:
            return self.serial.port or "Serial"
        if ct == ConnectionType.TCP_SERVER:
            return f"TCP Server :{self.network.port}"
        if ct == ConnectionType.UDP:
            return f"UDP {self.network.host}:{self.network.port}"
        if ct == ConnectionType.USB_HID:
            vid, pid = self.hid.vendor_id, self.hid.product_id
            if vid and pid:
                return f"HID {vid:04X}:{pid:04X}"
            return "USB HID"
        if ct in (ConnectionType.NAMED_PIPE_CLIENT, ConnectionType.NAMED_PIPE_SERVER):
            tail = self.named_pipe.path.split("/")[-1].split("\\")[-1] or "pipe"
            role = "Server" if ct == ConnectionType.NAMED_PIPE_SERVER else "Client"
            return f"Pipe {role} {tail}"
        return f"{self.network.host}:{self.network.port}"

    def to_dict(self) -> dict:
        return {
            "connection_type": self.connection_type.value,
            "serial": self.serial.to_dict(),
            "network": self.network.to_dict(),
            "hid": self.hid.to_dict(),
            "named_pipe": self.named_pipe.to_dict(),
            "name": self.name,
            "auto_reconnect": self.auto_reconnect,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PortConfig":
        return cls(
            connection_type=ConnectionType(d.get("connection_type", "serial")),
            serial=SerialConfig.from_dict(d.get("serial", {})),
            network=NetworkConfig.from_dict(d.get("network", {})),
            hid=HIDConfig.from_dict(d.get("hid", {})),
            named_pipe=NamedPipeConfig.from_dict(d.get("named_pipe", {})),
            name=d.get("name", ""),
            auto_reconnect=d.get("auto_reconnect", True),
        )


@dataclass
class TapConfig:
    """Configuration for a Tap / Monitor session using two physical ports."""

    port_a: PortConfig = field(default_factory=PortConfig)
    port_b: PortConfig = field(default_factory=PortConfig)
    # "off" = monitor only  "a_to_b" = forward A→B  "b_to_a" = forward B→A  "both" = bridge
    forward_mode: str = "off"
    name: str = ""

    def display_name(self) -> str:
        if self.name:
            return self.name
        return f"Tap: {self.port_a.display_name()} ↔ {self.port_b.display_name()}"

    def to_dict(self) -> dict:
        return {
            "port_a": self.port_a.to_dict(),
            "port_b": self.port_b.to_dict(),
            "forward_mode": self.forward_mode,
            "name": self.name,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TapConfig":
        return cls(
            port_a=PortConfig.from_dict(d.get("port_a", {})),
            port_b=PortConfig.from_dict(d.get("port_b", {})),
            forward_mode=d.get("forward_mode", "off"),
            name=d.get("name", ""),
        )
