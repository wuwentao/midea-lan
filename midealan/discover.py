"""Midea lan discover."""

import contextlib
import logging
import re
import select
import socket
import time
from collections.abc import Callable
from importlib import util as importlib_util
from ipaddress import IPv4Network
from typing import Any, NamedTuple

import ifaddr
from defusedxml import ElementTree

from .const import DeviceType, ProtocolVersion
from .exceptions import ElementMissing, MideaLanError
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
PORT_START, PORT_END = 4, 8
SN_START, SN_END = 8, 40
MODEL_START, MODEL_END = 17, 25
# A valid SSID is shaped like ``net_<type>_<id>`` so the parser can read the
# hex device-type from its second underscore-delimited field.
SSID_MIN_PARTS = 2
# A device reports it is connected to the Midea cloud when this byte equals 1.
CONNECTED_FLAG = 1
# A device is the master gateway when exactly these bits are set.
MASTER_GATEWAY_MASK = 0x81
# Discovery protocol v4 replies use a bare 5a5a datagram even though their TCP
# connection still requires the token-authenticated 8370 transport.
SECURE_UDP_VERSION = 4
# Datagram read size. The official app reads 1024-byte datagrams; keep parity so
# a larger reply (e.g. a long SSID plus the identity tail) is never truncated.
DISCOVERY_RECV_BUFFER = 1024
# Ports the scan probe is broadcast to. 6445 is the current port; 20086 is a
# legacy port kept for older devices that still listen there.
SEND_BROADCAST_PORTS = (6445, 20086)
# Fixed ports some devices announce / reply to instead of our ephemeral send
# socket. The official app binds both in addition to its send socket
# (DeviceBroadcastManager: RECEIVE_BROADCAST_PORT=7083,
# RECEIVE_BROADCAST_NEW_PORT=15000); without binding them those devices are
# never received and silently fail discovery.
RECEIVE_BROADCAST_PORTS = (7083, 15000)
# Overall time budget for one discover() scan.
DISCOVERY_TIMEOUT = 5.0

# Support-verdict values attached to every discovered device so callers (CLI,
# HA) can surface a device even when midealan cannot control it yet, together
# with a human-readable reason, instead of silently dropping it. This answers
# the recurring "my device isn't found" reports: an unsupported device now
# appears with an explanation rather than vanishing.
SUPPORT_SUPPORTED = "supported"
SUPPORT_EXPERIMENTAL = "experimental"
SUPPORT_UNSUPPORTED = "unsupported"


def _device_package_exists(device_type: int) -> bool:
    """Return whether a ``devices/<hextype>`` package exists for this type.

    Mirrors the naming rule in :func:`midealan.devices.device_selector`: types
    below ``0xA0`` are prefixed with ``x`` (e.g. ``x13``). Uses
    ``importlib.util.find_spec`` so no device module is imported as a side
    effect of discovery.
    """
    suffix = (
        f"x{device_type:02x}" if device_type < DeviceType.A0 else f"{device_type:02x}"
    )
    try:
        return importlib_util.find_spec(f"midealan.devices.{suffix}") is not None
    except ModuleNotFoundError:
        # A parent package is missing; treat as "no package" rather than raising.
        return False


def _support_verdict(device_type: int, udp_version: int) -> tuple[str, str]:
    """Classify a discovered device into a support verdict plus a reason.

    - ``supported``: a device package exists and the classic LAN transport
      applies (``udp_version < 4``).
    - ``experimental``: a ``udp_version >= 4`` ("TLS") device. These need the
      certificate/ECDH handshake transport whose control path is still being
      verified against real hardware, so flag them rather than claiming full
      support.
    - ``unsupported``: no ``devices/<hextype>`` package implements this type.

    The reason is a short English string suitable for logging or a diagnostic
    entity; it is empty only for the plain ``supported`` case.
    """
    if not _device_package_exists(device_type):
        return (
            SUPPORT_UNSUPPORTED,
            f"no device package for type 0x{device_type:02x}",
        )
    if udp_version >= SECURE_UDP_VERSION:
        return (
            SUPPORT_EXPERIMENTAL,
            (
                f"type 0x{device_type:02x} uses the udp_version>={SECURE_UDP_VERSION} "
                "TLS transport; LAN control is still being verified"
            ),
        )
    return (SUPPORT_SUPPORTED, "")


def _ext_le_int(raw: bytes | bytearray) -> int:
    """Decode a little-endian unsigned integer (official Util.bytesToInt)."""
    return int.from_bytes(raw, "little")


def _ext_first_byte(raw: bytes | bytearray) -> int:
    """Decode a single unsigned byte."""
    return raw[0]


def _ext_is_master_gateway(raw: bytes | bytearray) -> bool:
    """Decode the master-gateway flag byte."""
    return (raw[0] & MASTER_GATEWAY_MASK) == MASTER_GATEWAY_MASK


def _ext_is_connected(raw: bytes | bytearray) -> bool:
    """Decode the cloud-connected flag byte."""
    return raw[0] == CONNECTED_FLAG


def _ext_hex(raw: bytes | bytearray) -> str:
    """Decode a byte range as a lowercase hex string (BCD / random code)."""
    return raw.hex()


class _ExtendedField(NamedTuple):
    """One best-effort field in the tail of a v2/v3 discover reply.

    ``start``/``end`` are byte offsets relative to the end of the SSID
    (``DISCOVERY_MIN_REPLY_LENGTH + ssid_len``); ``min_len`` is how many bytes
    must follow the SSID before the field is safe to read, matching the
    official MSDeviceScanResult.parseDataBytes length guards.
    """

    key: str
    start: int
    end: int
    min_len: int
    decode: Callable[[bytes | bytearray], Any]


# Field layout of the reply tail, ordered by ascending min_len so parsing can
# stop at the first field the reply is too short to contain (the official
# parser returns early at the same points). Offsets are relative to the end of
# the SSID. Capability/provisioning flag bytes (identification, extra-low/high)
# are intentionally not exposed -- they only matter during device setup.
_EXTENDED_FIELDS: tuple[_ExtendedField, ...] = (
    _ExtendedField("udp_version", 4, 8, 8, _ext_le_int),
    _ExtendedField("protocol_code", 8, 9, 9, _ext_first_byte),
    _ExtendedField("is_master_gateway", 11, 12, 12, _ext_is_master_gateway),
    _ExtendedField("manufacturer_code", 12, 14, 14, _ext_le_int),
    _ExtendedField("device_subtype", 16, 18, 22, _ext_le_int),
    _ExtendedField("protocol_version", 28, 34, 34, _ext_hex),
    _ExtendedField("server_connected", 34, 35, 35, _ext_is_connected),
    _ExtendedField("max_tcp_count", 35, 36, 37, _ext_first_byte),
    _ExtendedField("current_tcp_count", 36, 37, 37, _ext_first_byte),
    _ExtendedField("random_code", 37, 53, 53, _ext_hex),
)


def _parse_extended_fields(
    reply: bytes | bytearray,
    ssid_len: int,
) -> dict[str, Any]:
    """Decode the optional device-identity fields after the SSID.

    Mirrors MSDeviceScanResult.parseDataBytes: every field is length-guarded,
    so a short reply simply yields fewer keys instead of raising. Only the
    fields actually present are returned; callers use ``.get()``.

    Note: when ``udp_version`` >= 4 the device uses TLS and its serial/tid are
    PBKDF2-encrypted with the app's private key (unavailable here), so those
    stay as decoded by the caller rather than being re-decrypted.
    """
    base = DISCOVERY_MIN_REPLY_LENGTH + ssid_len
    length = len(reply)
    fields: dict[str, Any] = {}
    for spec in _EXTENDED_FIELDS:
        if length < base + spec.min_len:
            break
        fields[spec.key] = spec.decode(reply[base + spec.start : base + spec.end])
    return fields


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

    A valid reply carries an SSID-length byte at ``SSID_LENGTH_OFFSET``, enough
    trailing bytes to hold that SSID, and an SSID shaped like ``net_<type>_...``
    where ``<type>`` is the hex device-type the parser later reads. Validating
    the SSID here matters because AES decryption of an unrelated block-aligned
    plaintext body can yield bytes with valid padding and a plausible length;
    rejecting them lets ``_decrypt_or_plaintext_reply`` fall back to the raw
    plaintext body instead of letting the parser raise on ``split("_")[1]``.
    """
    if len(reply) <= DISCOVERY_MIN_REPLY_LENGTH:
        return False
    ssid_len = reply[SSID_LENGTH_OFFSET]
    if ssid_len + DISCOVERY_MIN_REPLY_LENGTH > len(reply):
        return False
    raw_ssid = reply[DISCOVERY_MIN_REPLY_LENGTH : DISCOVERY_MIN_REPLY_LENGTH + ssid_len]
    try:
        parts = raw_ssid.decode("ascii").split("_")
    except UnicodeDecodeError:
        return False
    if len(parts) < SSID_MIN_PARTS:
        return False
    try:
        int(parts[1], 16)
    except ValueError:
        return False
    return True


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
    data, addr = sock.recvfrom(DISCOVERY_RECV_BUFFER)
    ip = addr[0]
    _LOGGER.debug("Received response from %s: %s", addr, data.hex())
    if len(data) >= DISCOVERY_MIN_RESPONSE_LENGTH and (
        data[:2].hex() == "5a5a"
        or data[:2].hex() == "8370"
        or data[8:10].hex() == "5a5a"
    ):
        if data[:2].hex() == "5a5a":
            protocol = ProtocolVersion.V2
        elif data[:2].hex() == "8370":
            protocol = ProtocolVersion.V3
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
            # G2: a 5a5a/8370-framed reply from a real Midea device, but its
            # body neither decrypts nor is a valid plaintext reply. Log at info
            # (not warning) so an undecodable but genuine device leaves a trace
            # for the user without alarming them, then skip it.
            _LOGGER.info(
                "Discovered device %s (id %s) but its reply could not be "
                "decoded (body: %s); skipping. This device is reachable but "
                "midealan cannot parse its discovery reply.",
                ip,
                device_id,
                encrypt_data.hex(),
            )
            return 0, None
        _LOGGER.debug("Declassified reply: %s", reply.hex())
        ssid_len = reply[SSID_LENGTH_OFFSET]
        ssid = reply[
            DISCOVERY_MIN_REPLY_LENGTH : DISCOVERY_MIN_REPLY_LENGTH + ssid_len
        ].decode("ascii")
        device_type = ssid.split("_")[1]
        port = bytes2port(reply[PORT_START:PORT_END])
        model = _decode_ascii_or_hex(reply[MODEL_START:MODEL_END])
        sn = _decode_ascii_or_hex(reply[SN_START:SN_END])
        mac = _extract_mac(reply, ssid_len, sn)
        extended = _parse_extended_fields(reply, ssid_len)
        if extended.get("udp_version", 0) >= SECURE_UDP_VERSION:
            # UDP discovery v4+ (TLS) devices broadcast a bare 5a5a datagram
            # but still require the token-authenticated 8370 transport for TCP
            # control, so drive them over V3 (mirrors the official app's
            # MSDeviceScanResult.getConnectWiFiVersion() returning 3 when
            # isTLS()). Their serial/model bytes are PBKDF2-encrypted and
            # cannot be decoded without the app's AP private key, so drop the
            # undecryptable identity and let callers use the cloud serial.
            protocol = ProtocolVersion.V3
            sn = ""
            model = ""
            # Signal callers (CLI, HA) that an empty serial here is expected,
            # not a decode failure: the real serial must come from the cloud.
            extended["sn_encrypted"] = True
    elif data[:6].hex() == "3c3f786d6c20":
        protocol = ProtocolVersion.V1
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
        extended = {}
    else:
        # G1: a datagram arrived from this address but its leading bytes match
        # no known discovery frame (not 5a5a/8370 v2/v3, not a v1 XML header).
        # This can be ordinary non-Midea LAN traffic on the shared fixed ports
        # (7083/15000), so log at debug -- enough to trace a genuinely missed
        # device when debugging, without spamming warnings on a busy network.
        _LOGGER.debug(
            "Ignoring an unrecognized discovery datagram from %s "
            "(%d bytes, header %s); not a known Midea discovery frame.",
            ip,
            len(data),
            data[:8].hex(),
        )
        return 0, None
    type_int = int(device_type, 16)
    support, support_reason = _support_verdict(
        type_int,
        extended.get("udp_version", 0),
    )
    return device_id, {
        "device_id": device_id,
        "type": type_int,
        "ip_address": ip,
        "port": port,
        "model": model,
        "sn": sn,
        "protocol": protocol,
        "mac": mac,
        "support": support,
        "support_reason": support_reason,
        **extended,
    }


def _open_broadcast_send_socket(stack: contextlib.ExitStack) -> socket.socket:
    """Open the ephemeral socket used to send the scan probe and read replies."""
    sock = stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    return sock


def _open_receive_socket(
    stack: contextlib.ExitStack,
    port: int,
) -> socket.socket | None:
    """Bind a UDP socket to a fixed receive port, or None if it can't be bound.

    The official app binds 7083 and 15000 alongside its send socket to catch
    devices that announce there. Binding may fail (port already in use, or no
    permission); that is non-fatal -- discovery continues on the sockets that
    did open -- so a bind error is logged and None is returned.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("", port))
    except OSError as e:
        _LOGGER.warning("Can't bind discovery receive port %s: %s", port, repr(e))
        sock.close()
        return None
    return stack.enter_context(sock)


def discover(
    discover_type: list | None = None,
    ip_address: list | None = None,
) -> dict[int, dict[str, Any]]:
    """Discover devices.

    Sends the scan probe to the broadcast ports and listens for replies on the
    ephemeral send socket plus the fixed broadcast-receive ports (7083/15000),
    mirroring the official app so devices that announce on those fixed ports are
    discovered too.
    """
    if discover_type is None:
        discover_type = []

    found_devices: dict[int, dict[str, Any]] = {}
    addrs = enum_all_broadcast() if ip_address is None else [ip_address]

    _LOGGER.debug("All addresses for broadcast: %s", addrs)
    with contextlib.ExitStack() as stack:
        send_sock = _open_broadcast_send_socket(stack)
        # Bind the fixed receive ports too; keep only the ones that bound.
        recv_socks = [
            sock
            for port in RECEIVE_BROADCAST_PORTS
            if (sock := _open_receive_socket(stack, port)) is not None
        ]
        read_socks = [send_sock, *recv_socks]
        for addr in addrs:
            for port in SEND_BROADCAST_PORTS:
                try:
                    send_sock.sendto(BROADCAST_MSG, (addr, port))
                except OSError as e:
                    _LOGGER.warning("Can't access network %s: %s", addrs, repr(e))
        _discover_receive_loop(read_socks, discover_type, found_devices)
    return found_devices


def _discover_receive_loop(
    read_socks: list[socket.socket],
    discover_type: list,
    found_devices: dict[int, dict[str, Any]],
) -> None:
    """Read replies from every open socket until the time budget elapses.

    select() multiplexes the send socket and the fixed receive ports so a slow
    device on one port never starves another. The overall DISCOVERY_TIMEOUT is
    the same budget the single-socket loop used.
    """
    deadline = time.monotonic() + DISCOVERY_TIMEOUT
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            readable, _, _ = select.select(read_socks, [], [], remaining)
        except OSError:
            _LOGGER.exception("Socket error")
            break
        if not readable:
            break
        for sock in readable:
            try:
                device_id, device = _parse_discover_response(sock, found_devices)
                if device is None:
                    continue
                if len(discover_type) != 0 and device.get("type") not in discover_type:
                    # The caller restricted the scan to specific device types
                    # and this one isn't on the list, so it is filtered out by
                    # request -- not a support problem.
                    _LOGGER.debug(
                        "Skipping device (type 0x%02x) not in the requested "
                        "discover_type filter: %s",
                        device.get("type", 0),
                        device,
                    )
                    continue
                found_devices[device_id] = device
                support = device.get("support", SUPPORT_SUPPORTED)
                if support == SUPPORT_SUPPORTED:
                    _LOGGER.debug("Found a supported device: %s", device)
                else:
                    # Surface the device anyway, but make the reason explicit so
                    # a user whose device "isn't found" can see why midealan
                    # can't fully drive it yet.
                    _LOGGER.info(
                        "Found a %s device (type 0x%02x) at %s: %s",
                        support,
                        device.get("type", 0),
                        device.get("ip_address"),
                        device.get("support_reason") or "see protocol notes",
                    )
            except OSError:
                _LOGGER.exception("Socket error")
            except (MideaLanError, ValueError, IndexError, KeyError):
                # A single malformed or unknown reply must not abort the whole
                # scan: skip just this packet so the remaining devices on the
                # LAN are still discovered. Mirrors the official app, which
                # wraps per-packet parsing in a catch-all and keeps scanning.
                _LOGGER.warning(
                    "Skipping an unparsable discovery response",
                    exc_info=True,
                )


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
