"""Midea lan discover."""

import logging
import re
import socket
from ipaddress import IPv4Network
from typing import Any

import ifaddr
from defusedxml import ElementTree

from .exceptions import ElementMissing
from .security import LocalSecurity

_LOGGER = logging.getLogger(__name__)

BYTES_2_PORT_LENGTH = 4
BROADCAST_MSG = bytearray(
    [
        0x5A,
        0x5A,
        0x01,
        0x11,
        0x48,
        0x00,
        0x92,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x7F,
        0x75,
        0xBD,
        0x6B,
        0x3E,
        0x4F,
        0x8B,
        0x76,
        0x2E,
        0x84,
        0x9C,
        0x6E,
        0x57,
        0x8D,
        0x65,
        0x90,
        0x03,
        0x6E,
        0x9D,
        0x43,
        0x42,
        0xA5,
        0x0F,
        0x1F,
        0x56,
        0x9E,
        0xB8,
        0xEC,
        0x91,
        0x8E,
        0x92,
        0xE5,
    ],
)

DEVICE_INFO_MSG = bytearray(
    [
        0x5A,
        0x5A,
        0x15,
        0x00,
        0x00,
        0x38,
        0x00,
        0x04,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x27,
        0x33,
        0x05,
        0x13,
        0x06,
        0x14,
        0x14,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x03,
        0xE8,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0xCA,
        0x8D,
        0x9B,
        0xF9,
        0xA0,
        0x30,
        0x1A,
        0xE3,
        0xB7,
        0xE4,
        0x2D,
        0x53,
        0x49,
        0x47,
        0x62,
        0xBE,
    ],
)

DISCOVERY_MIN_RESPONSE_LENGTH = 104
MAX_NETWORK_PREFIX_LENGHT = 32
SERIAL_TYPE1_LENGTH = 32
SERIAL_TYPE2_LENGTH = 22
DISCOVERY_MIN_REPLY_LENGTH = 41
# Offset of the SSID-length byte inside a decrypted/plaintext reply.
SSID_LENGTH_OFFSET = 40
# Byte ranges inside a decrypted/plaintext reply.
SN_START, SN_END = 8, 40
MODEL_START, MODEL_END = 17, 25


def _extract_mac(reply: bytes | bytearray, ssid_len: int, sn: str) -> str | None:
    """Return the MAC address or None if not available.

    Extracts the MAC address from the v3 discover reply and returns it as a
    hexadecimal string without internal separators.
    If the reply does not provide the MAC address, the MAC is extracted from
    the serial number, which also may contain the MAC address.
    Otherwise return None.
    """
    # Based on https://github.com/nbogojevic/midea-beautiful-air/blob/db3622e784891af0a522d70a626fb54e5c3e5e6f/midea_beautiful/lan.py#L264
    mac = None
    mac_start = 63 + ssid_len
    mac_ends = mac_start + 6
    if len(reply) >= mac_ends:
        mac = reply[mac_start:mac_ends].hex()
    elif len(sn) == SERIAL_TYPE1_LENGTH:
        mac = sn[16:28]
    elif len(sn) == SERIAL_TYPE2_LENGTH:
        # MAC address not reported
        mac = None
    else:
        _LOGGER.warning("Unknown serial number format %s", sn)
        mac = None
    if mac and not re.fullmatch(r"[0-9A-Fa-f]{12}", mac):
        _LOGGER.warning("Invalid MAC address %s", mac)
        mac = None
    return mac


def _is_valid_reply(reply: bytes | bytearray) -> bool:
    """Return whether ``reply`` is a well-formed decrypted discover reply.

    A valid reply carries an SSID-length byte at ``SSID_LENGTH_OFFSET`` and
    enough trailing bytes to hold that SSID.
    """
    return len(reply) > DISCOVERY_MIN_REPLY_LENGTH and reply[
        SSID_LENGTH_OFFSET
    ] + DISCOVERY_MIN_REPLY_LENGTH <= len(reply)


def _decrypt_or_plaintext_reply(
    security: LocalSecurity,
    encrypt_data: bytes,
) -> bytearray | None:
    """Return the plaintext discover reply, or None if it cannot be parsed.

    Historically every device encrypted the reply body with AES-ECB. Newer
    appliances (e.g. 2024+ KFR-* ACs, dishwashers, range hoods) broadcast the
    body as plaintext instead -- the official app treats a broadcast as plain
    when its command byte flags it so, and its encrypted-broadcast branch is
    dead code. midealan has no command byte here, so distinguish the two by
    structure rather than by flag.

    Try decryption first (keeps every existing encrypted device working), and
    fall back to treating the body as plaintext when decryption yields nothing
    usable but the raw body is itself a valid reply.
    """
    reply = security.aes_decrypt(encrypt_data)
    if _is_valid_reply(reply):
        return reply
    if _is_valid_reply(encrypt_data):
        return bytearray(encrypt_data)
    return None


def _decode_ascii_or_hex(raw: bytes | bytearray) -> str:
    """Decode ``raw`` as ASCII, falling back to hex for non-ASCII bytes.

    Plaintext broadcasts carry an obfuscated binary serial number where older
    devices sent printable ASCII, so decode defensively instead of raising.
    """
    try:
        return raw.decode("ascii")
    except UnicodeDecodeError:
        return raw.hex()


def _parse_discover_response(
    sock: socket.socket,
    found_devices: dict[int, dict[str, Any]],
) -> tuple[int, dict[str, Any] | None]:
    security = LocalSecurity()
    data, addr = sock.recvfrom(512)
    ip = addr[0]
    _LOGGER.debug("Received response from %s: %s", addr, data.hex())
    if len(data) >= DISCOVERY_MIN_RESPONSE_LENGTH and (
        data[:2].hex() == "5a5a"
        or data[:2].hex() == "8370"
        or data[8:10].hex() == "5a5a"
    ):
        if data[:2].hex() == "5a5a":
            protocol = 2
        elif data[:2].hex() == "8370":
            protocol = 3
            if data[8:10].hex() == "5a5a":
                data = data[8:-16]
            else:
                _LOGGER.error("Unexpected 8370 discovery response: %s", data.hex())
                return 0, None
        else:
            return 0, None
        device_id = int.from_bytes(
            bytearray.fromhex(data[20:26].hex()),
            "little",
        )
        if device_id in found_devices:
            return 0, None
        encrypt_data = data[40:-16]
        reply = _decrypt_or_plaintext_reply(security, encrypt_data)
        if reply is None:
            _LOGGER.warning(
                "Failed to decrypt the encrypt_data: %s from %s. Maybe not support.",
                encrypt_data.hex(),
                ip,
            )
            return 0, None
        _LOGGER.debug("Declassified reply: %s", reply.hex())
        ssid_len = reply[SSID_LENGTH_OFFSET]
        ssid = reply[
            DISCOVERY_MIN_REPLY_LENGTH : DISCOVERY_MIN_REPLY_LENGTH + ssid_len
        ].decode("ascii")
        device_type = ssid.split("_")[1]
        port = bytes2port(reply[4:8])
        model = _decode_ascii_or_hex(reply[MODEL_START:MODEL_END])
        sn = _decode_ascii_or_hex(reply[SN_START:SN_END])
        mac = _extract_mac(reply, ssid_len, sn)
    elif data[:6].hex() == "3c3f786d6c20":
        protocol = 1
        root = ElementTree.fromstring(
            data.decode(encoding="utf-8", errors="replace"),
        )
        child = root.find("body/device")
        if child is None:
            raise ElementMissing
        m = child.attrib
        port, sn, device_type = (
            int(m["port"]),
            m["apc_sn"],
            str(hex(int(m["apc_type"])))[2:],
        )
        response = get_device_info(ip, int(port))
        device_id = get_id_from_response(response)
        if len(sn) == SERIAL_TYPE1_LENGTH:
            model = sn[9:17]
        elif len(sn) == SERIAL_TYPE2_LENGTH:
            model = sn[3:11]
        else:
            model = ""
        mac = _extract_mac(b"", 0, sn)
    else:
        return 0, None
    return device_id, {
        "device_id": device_id,
        "type": int(device_type, 16),
        "ip_address": ip,
        "port": port,
        "model": model,
        "sn": sn,
        "protocol": protocol,
        "mac": mac,
    }


def discover(
    discover_type: list | None = None,
    ip_address: list | None = None,
) -> dict[int, dict[str, Any]]:
    """Discover devices."""
    if discover_type is None:
        discover_type = []

    found_devices: dict[int, dict[str, Any]] = {}
    addrs = enum_all_broadcast() if ip_address is None else [ip_address]

    _LOGGER.debug("All addresses for broadcast: %s", addrs)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(5)
        for addr in addrs:
            try:
                sock.sendto(BROADCAST_MSG, (addr, 6445))
                sock.sendto(BROADCAST_MSG, (addr, 20086))
            except OSError as e:
                _LOGGER.warning("Can't access network %s: %s", addrs, repr(e))
        while True:
            try:
                device_id, device = _parse_discover_response(sock, found_devices)
                if device is None:
                    continue
                if len(discover_type) == 0 or device.get("type") in discover_type:
                    found_devices[device_id] = device
                    _LOGGER.debug("Found a supported device: %s", device)
                else:
                    _LOGGER.debug("Found a unsupported device: %s", device)
            except TimeoutError:
                break
            except OSError:
                _LOGGER.exception("Socket error")
    return found_devices


def get_id_from_response(response: bytearray) -> int:
    """Get ID from response."""
    if response[64:-16][:6].hex() == "3c3f786d6c20":
        xml = response[64:-16]
        root = ElementTree.fromstring(xml.decode(encoding="utf-8", errors="replace"))
        child = root.find("smartDevice")
        if child is None:
            raise ElementMissing
        m = child.attrib
        return int.from_bytes(bytearray.fromhex(m["devId"]), "little")
    return 0


def bytes2port(value_bytes: bytes | bytearray | None) -> int:
    """Bytes to port."""
    if value_bytes is None:
        return 0
    b, i = 0, 0
    while b < BYTES_2_PORT_LENGTH:
        b1 = value_bytes[b] & 0xFF if b < len(value_bytes) else 0
        i |= b1 << b * 8
        b += 1
    return i


def get_device_info(device_ip: str, device_port: int) -> bytearray:
    """Get device info."""
    response = bytearray(0)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(8)
            device_address = (device_ip, device_port)
            sock.connect(device_address)
            _LOGGER.debug(
                "Sending to %s:%s %s",
                device_ip,
                device_port,
                DEVICE_INFO_MSG.hex(),
            )
            sock.sendall(DEVICE_INFO_MSG)
            response = bytearray(sock.recv(512))
    except TimeoutError:
        _LOGGER.warning(
            "Connect the device %s:%s timed out for 8s."
            "Don't care about a small amount of this. if many maybe not support.",
            device_ip,
            device_port,
        )
    except OSError:
        _LOGGER.warning("Can't connect to Device %s:%s", device_ip, device_port)
    return response


def enum_all_broadcast() -> list:
    """Enum all broadcast addresses."""
    nets = []
    adapters = ifaddr.get_adapters()
    for adapter in adapters:
        for ip in adapter.ips:
            if ip.is_IPv4 and ip.network_prefix < MAX_NETWORK_PREFIX_LENGHT:
                local_network = IPv4Network(
                    f"{ip.ip}/{ip.network_prefix}",
                    strict=False,
                )
                if (
                    local_network.is_private
                    and not local_network.is_loopback
                    and not local_network.is_link_local
                ):
                    addr = str(local_network.broadcast_address)
                    if addr not in nets:
                        nets.append(addr)
    return nets
