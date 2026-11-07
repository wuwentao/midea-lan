"""Midea LAN "TLS" transport for ``udp_version >= 4`` appliances.

Despite the name used by the Midea apps, this is NOT SSL/TLS. It is a plain TCP
channel (the same 5a5a framing used elsewhere) whose per-device ``token``/``key``
8370 handshake is replaced by an application-level certificate + ECDH key
agreement, after which control frames are protected with AES-128-CCM under the
negotiated session key.

The flow mirrors the ``com.midea.iot.msmart`` SDK:

1. Provision an app certificate from the Midea cloud (see
   :mod:`midealan.cloud`): generate a local EC (secp256r1) key pair, build a
   PKCS#10 CSR whose subject carries ``CN = sha256(keyId)[:32]``, and POST it to
   ``applyCertByP10`` to obtain ``{cert, superiorCert:[root, center]}``.
2. Open a TCP socket and run the ``0x75`` handshake (:class:`TLSSession`):
   send the center + app certificates and a 16-byte nonce ``N1``; the device
   replies with its module certificate chain, a nonce ``N2`` and an HMAC tag.
   The session key is ``sha256(ecdh_shared || N1 || N2)[:16]``.
3. Wrap each appliance frame as an :class:`MSDatagram` with
   ``encrypt_type = 2`` (AES-128-CCM) and a 16-byte MD5 signature keyed by the
   account ``ap_private_key``.

All multi-byte integers are little-endian, matching the existing 5a5a reader.
"""

from __future__ import annotations

import base64
import hmac
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import md5, sha256

from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from Crypto.Protocol.DH import key_agreement
from Crypto.PublicKey import ECC
from Crypto.Random import get_random_bytes
from Crypto.Signature import DSS

from .exceptions import (
    CannotAuthenticate,
    DataSignDoesntMatch,
    DataUnexpectedLength,
    MessageWrongFormat,
)

# ---------------------------------------------------------------------------
# MSWifiDatagram framing constants
# ---------------------------------------------------------------------------
FRAME_MAGIC = b"\x5a\x5a"
HEADER_LENGTH = 40
SIGNATURE_LENGTH = 16
# A CCM body carries a 13-byte nonce prefix and a 16-byte authentication tag in
# addition to the ciphertext, plus the trailing frame signature.
CCM_NONCE_LENGTH = 13
CCM_TAG_LENGTH = 16
CCM_OVERHEAD = CCM_NONCE_LENGTH + CCM_TAG_LENGTH + SIGNATURE_LENGTH  # == 45
PLAIN_OVERHEAD = HEADER_LENGTH + SIGNATURE_LENGTH  # == 56
# A frame is at minimum the 40-byte header plus the 16-byte trailing signature.
MIN_FRAME_LENGTH = HEADER_LENGTH + SIGNATURE_LENGTH  # == 56
# Session counter carried as a 2-byte little-endian prefix for version >= 3.
CNT_LENGTH = 2
CNT_MAX = 0xFFFF
TLS_VERSION = 3

# encrypt_type values (low nibble of header byte 3).
ENCRYPT_TYPE_NONE = 0
ENCRYPT_TYPE_AES128 = 1
ENCRYPT_TYPE_CCM = 2
# sign_type values (high nibble of header byte 3).
SIGN_TYPE_NONE = 0
SIGN_TYPE_MD5 = 1

# MSCommand.WifiCommand message types (little-endian 16-bit on the wire).
MSG_TYPE_CERT_REQUEST = 0x0075
MSG_TYPE_CERT_RESPONSE = 0x8075
MSG_TYPE_DATA_TRANSMIT = 0x0020
MSG_TYPE_DATA_TRANSMIT_RESPONSE = 0x8020
MSG_TYPE_HEARTBEAT = 0x007B
MSG_TYPE_HEARTBEAT_RESPONSE = 0x807B

# Handshake body markers.
_CERT_STEP_HELLO = 1
_CERT_STEP_FINISH = 2
_CERT_STATUS_OK = 0
_NONCE_N1_LENGTH = 16
_NONCE_N2_EXPECTED = 16
_SESSION_KEY_LENGTH = 16
_HMAC_LENGTH = 32
_ZERO_DEVICE_ID = "000000000000"
# Minimum handshake body lengths: the hello reply needs step/pad/status, the
# finished reply needs step/pad plus a 2-byte inner length.
_MIN_HELLO_BODY = 3
_MIN_FINISH_BODY = 4

# ---------------------------------------------------------------------------
# Minimal DER encoder (only what a PKCS#10 CSR needs)
# ---------------------------------------------------------------------------
_TAG_BOOLEAN = 0x01
_TAG_INTEGER = 0x02
_TAG_BIT_STRING = 0x03
_TAG_OCTET_STRING = 0x04
_TAG_OID = 0x06
_TAG_UTF8_STRING = 0x0C
_TAG_PRINTABLE_STRING = 0x13
_TAG_SEQUENCE = 0x30
_TAG_SET = 0x31
_TAG_CONTEXT_0 = 0xA0
_DER_SHORT_LEN_MAX = 0x80

# X.500 / PKCS attribute object identifiers.
_OID_CN = "2.5.4.3"
_OID_OU = "2.5.4.11"
_OID_O = "2.5.4.10"
_OID_L = "2.5.4.7"
_OID_ST = "2.5.4.8"
_OID_C = "2.5.4.6"
_OID_BASIC_CONSTRAINTS = "2.5.29.19"
_OID_EXTENSION_REQUEST = "1.2.840.113549.1.9.14"
_OID_ECDSA_WITH_SHA256 = "1.2.840.10045.4.3.2"

# CSR subject constants (match the app's MSmartCertKeyVerify).
_CSR_OU = "MideaCAOperation"
_CSR_O = "MideaCA"
_CSR_L = "foshan"
_CSR_ST = "guangdong"
_CSR_C = "CN"
_CSR_CN_LENGTH = 32


def _der_length(size: int) -> bytes:
    """Encode an ASN.1 DER length."""
    # DER short form covers lengths below 0x80; larger lengths use long form.
    if size < _DER_SHORT_LEN_MAX:
        return bytes([size])
    encoded = size.to_bytes((size.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(encoded)]) + encoded


def _der(tag: int, body: bytes) -> bytes:
    """Wrap ``body`` in a DER tag-length-value triple."""
    return bytes([tag]) + _der_length(len(body)) + body


def _der_oid(oid: str) -> bytes:
    """Encode a dotted object identifier as DER."""
    parts = [int(part) for part in oid.split(".")]
    first = 40 * parts[0] + parts[1]

    def _base128(value: int) -> bytes:
        chunk = [value & 0x7F]
        value >>= 7
        while value:
            chunk.insert(0, (value & 0x7F) | 0x80)
            value >>= 7
        return bytes(chunk)

    encoded = _base128(first)
    for part in parts[2:]:
        encoded += _base128(part)
    return _der(_TAG_OID, encoded)


def _der_rdn(oid: str, value: str, tag: int) -> bytes:
    """Encode a single relative distinguished name (SET OF ATV)."""
    atv = _der(_TAG_SEQUENCE, _der_oid(oid) + _der(tag, value.encode("utf-8")))
    return _der(_TAG_SET, atv)


def build_csr(ec_key: ECC.EccKey, key_id: str) -> str:
    """Build a PKCS#10 CSR for ``ec_key`` and return it base64-encoded.

    The subject mirrors the Midea app:
    ``CN=sha256(key_id)[:32], OU=MideaCAOperation, O=MideaCA, L=foshan,
    ST=guangdong, C=CN`` and a critical ``BasicConstraints(cA=TRUE)`` is carried
    in an extensionRequest attribute, signed with SHA256withECDSA.
    """
    common_name = sha256(key_id.encode("utf-8")).hexdigest()[:_CSR_CN_LENGTH]
    subject = _der(
        _TAG_SEQUENCE,
        _der_rdn(_OID_CN, common_name, _TAG_UTF8_STRING)
        + _der_rdn(_OID_OU, _CSR_OU, _TAG_UTF8_STRING)
        + _der_rdn(_OID_O, _CSR_O, _TAG_UTF8_STRING)
        + _der_rdn(_OID_L, _CSR_L, _TAG_UTF8_STRING)
        + _der_rdn(_OID_ST, _CSR_ST, _TAG_UTF8_STRING)
        + _der_rdn(_OID_C, _CSR_C, _TAG_PRINTABLE_STRING),
    )
    # SubjectPublicKeyInfo: PyCryptodome exports a complete SPKI structure.
    spki = ec_key.public_key().export_key(format="DER")

    # BasicConstraints ::= SEQUENCE { cA BOOLEAN }
    basic_constraints = _der(_TAG_SEQUENCE, bytes([_TAG_BOOLEAN, 0x01, 0xFF]))
    extension = _der(
        _TAG_SEQUENCE,
        _der_oid(_OID_BASIC_CONSTRAINTS)
        + bytes([_TAG_BOOLEAN, 0x01, 0xFF])  # critical = TRUE
        + _der(_TAG_OCTET_STRING, basic_constraints),
    )
    extension_request = _der(
        _TAG_SEQUENCE,
        _der_oid(_OID_EXTENSION_REQUEST)
        + _der(_TAG_SET, _der(_TAG_SEQUENCE, extension)),
    )
    attributes = _der(_TAG_CONTEXT_0, extension_request)

    cert_request_info = _der(
        _TAG_SEQUENCE,
        _der(_TAG_INTEGER, b"\x00") + subject + spki + attributes,
    )
    digest = SHA256.new(cert_request_info)
    signature = DSS.new(ec_key, "fips-186-3", encoding="der").sign(digest)
    signature_algorithm = _der(_TAG_SEQUENCE, _der_oid(_OID_ECDSA_WITH_SHA256))
    csr = _der(
        _TAG_SEQUENCE,
        cert_request_info
        + signature_algorithm
        + _der(_TAG_BIT_STRING, b"\x00" + signature),
    )
    return base64.b64encode(csr).decode("ascii")


def generate_ec_keypair() -> ECC.EccKey:
    """Generate a fresh secp256r1 (P-256) key pair for the app certificate."""
    return ECC.generate(curve="p256")


# ---------------------------------------------------------------------------
# AES-128-CCM helpers
# ---------------------------------------------------------------------------
def ccm_encrypt(key: bytes, nonce: bytes, plaintext: bytes, aad: bytes) -> bytes:
    """Encrypt with AES-128-CCM and return ``ciphertext || tag``."""
    cipher = AES.new(key, AES.MODE_CCM, nonce=nonce, mac_len=CCM_TAG_LENGTH)
    if aad:
        cipher.update(aad)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext)
    return ciphertext + tag


def ccm_decrypt(key: bytes, nonce: bytes, data: bytes, aad: bytes) -> bytes:
    """Decrypt ``ciphertext || tag`` produced by AES-128-CCM."""
    if len(data) < CCM_TAG_LENGTH:
        raise DataUnexpectedLength
    ciphertext, tag = data[:-CCM_TAG_LENGTH], data[-CCM_TAG_LENGTH:]
    cipher = AES.new(key, AES.MODE_CCM, nonce=nonce, mac_len=CCM_TAG_LENGTH)
    if aad:
        cipher.update(aad)
    return cipher.decrypt_and_verify(ciphertext, tag)


def ecdh_shared_secret(private_key: ECC.EccKey, peer_public: ECC.EccKey) -> bytes:
    """Return the raw ECDH shared secret (the X coordinate), as Java does."""
    return bytes(
        key_agreement(
            static_priv=private_key,
            static_pub=peer_public,
            kdf=lambda value: value,
        ),
    )


def _timestamp() -> bytes:
    """Build the 8-byte MSWifiDatagram timestamp (month is 0-based)."""
    now = datetime.now(tz=UTC)
    year = now.year
    return bytes(
        [
            (now.microsecond // 1000) & 0xFF,
            now.second,
            now.minute,
            now.hour,
            now.day,
            (now.month - 1) & 0xFF,
            year % 100,
            year // 100,
        ],
    )


@dataclass
class ParsedDatagram:
    """A decoded :class:`MSDatagram`."""

    msg_type: int
    version: int
    encrypt_type: int
    body: bytes


class MSDatagram:
    """Build and parse ``5a5a`` MSWifiDatagram frames for the TLS transport.

    ``ap_private_key`` keys the trailing MD5 signature; ``session_key`` (once the
    handshake completes) keys AES-128-CCM control frames. A per-session send
    counter is prefixed to every ``version >= 3`` payload.
    """

    def __init__(
        self,
        device_id: int,
        ap_private_key: str | None = None,
        session_key: bytes | None = None,
    ) -> None:
        """Initialize the datagram codec."""
        self._device_id = device_id
        self._ap_private_key = ap_private_key
        self._session_key = session_key
        self._send_cnt = 1
        self._msg_id = 1

    def set_session_key(self, session_key: bytes) -> None:
        """Record the negotiated AES-128-CCM session key."""
        self._session_key = session_key

    def _next_cnt(self) -> int:
        cnt = self._send_cnt
        self._send_cnt += 1
        if self._send_cnt > CNT_MAX:
            self._send_cnt = 1
        return cnt

    def _next_msg_id(self) -> int:
        msg_id = self._msg_id
        self._msg_id += 1
        return msg_id

    def _sign(self, frame: bytearray) -> bytes:
        """MD5(frame[:-16] || ap_private_key) truncated to 16 bytes."""
        key = (self._ap_private_key or "").encode("utf-8")
        body = bytes(frame[: len(frame) - SIGNATURE_LENGTH])
        # MD5 here is a protocol-defined integrity tag, not a security hash.
        return md5(
            body + key,
            usedforsecurity=False,
        ).digest()[:SIGNATURE_LENGTH]

    def _header(self, length: int, msg_type: int, encrypt_type: int) -> bytearray:
        """Build the fixed 40-byte MSWifiDatagram header."""
        header = bytearray(HEADER_LENGTH)
        header[0:2] = FRAME_MAGIC
        header[2] = TLS_VERSION
        header[3] = (encrypt_type & 0x0F) | (SIGN_TYPE_MD5 << 4)
        header[4:6] = length.to_bytes(2, "little")
        header[6:8] = msg_type.to_bytes(2, "little")
        header[8:12] = self._next_msg_id().to_bytes(4, "little")
        header[12:20] = _timestamp()
        header[20:26] = self._device_id.to_bytes(8, "little")[:6]
        return header

    def encode(
        self,
        payload: bytes,
        msg_type: int,
        encrypt_type: int = ENCRYPT_TYPE_CCM,
        device_id: int | None = None,
    ) -> bytes:
        """Serialize ``payload`` into a signed MSWifiDatagram frame.

        For ``version >= 3`` the payload is prefixed with a 2-byte session
        counter before any encryption. ``device_id`` overrides the frame device
        id (the handshake uses an all-zero id).
        """
        cnt_payload = self._next_cnt().to_bytes(2, "little") + payload

        if encrypt_type == ENCRYPT_TYPE_CCM:
            if self._session_key is None:
                raise CannotAuthenticate
            nonce = get_random_bytes(CCM_NONCE_LENGTH)
            length = len(cnt_payload) + CCM_OVERHEAD + HEADER_LENGTH
            header = self._header(length, msg_type, encrypt_type)
            if device_id is not None:
                header[20:26] = device_id.to_bytes(8, "little")[:6]
            ciphertext = ccm_encrypt(
                self._session_key,
                nonce,
                cnt_payload,
                bytes(header),
            )
            frame = bytearray(header + nonce + ciphertext + bytes(SIGNATURE_LENGTH))
        else:
            length = len(cnt_payload) + PLAIN_OVERHEAD
            header = self._header(length, msg_type, encrypt_type)
            if device_id is not None:
                header[20:26] = device_id.to_bytes(8, "little")[:6]
            frame = bytearray(header + cnt_payload + bytes(SIGNATURE_LENGTH))

        frame[length - SIGNATURE_LENGTH : length] = self._sign(frame)
        return bytes(frame)

    def decode(self, frame: bytes) -> ParsedDatagram:
        """Parse a single MSWifiDatagram frame.

        Returns the decrypted, counter-stripped body. Raises
        :class:`MessageWrongFormat` for a malformed frame and
        :class:`DataUnexpectedLength` for a truncated one.
        """
        if len(frame) < MIN_FRAME_LENGTH or frame[0:2] != FRAME_MAGIC:
            raise MessageWrongFormat("not a 5a5a datagram")
        version = frame[2]
        encrypt_type = frame[3] & 0x0F
        length = int.from_bytes(frame[4:6], "little")
        msg_type = int.from_bytes(frame[6:8], "little")
        if length > len(frame) or length < MIN_FRAME_LENGTH:
            raise DataUnexpectedLength
        raw_body = frame[HEADER_LENGTH : length - SIGNATURE_LENGTH]

        if encrypt_type == ENCRYPT_TYPE_CCM:
            if self._session_key is None:
                raise CannotAuthenticate
            if len(raw_body) < CCM_NONCE_LENGTH:
                raise DataUnexpectedLength
            nonce = raw_body[:CCM_NONCE_LENGTH]
            aad = frame[:HEADER_LENGTH]
            body = ccm_decrypt(
                self._session_key,
                nonce,
                raw_body[CCM_NONCE_LENGTH:],
                aad,
            )
        else:
            body = raw_body

        if version >= TLS_VERSION and len(body) >= CNT_LENGTH:
            body = body[CNT_LENGTH:]
        return ParsedDatagram(
            msg_type=msg_type,
            version=version,
            encrypt_type=encrypt_type,
            body=body,
        )


def _u16_le(data: bytes) -> int:
    """Read a little-endian 16-bit integer."""
    return int.from_bytes(data[:2], "little")


def _hmac_sha256(message: bytes, key: bytes) -> bytes:
    """HMAC-SHA256 over ``message`` with ``key``."""
    return hmac.new(key, message, sha256).digest()


@dataclass
class CertBundle:
    """Provisioned material needed to run the TLS handshake.

    ``cert_private_key`` is the locally generated EC key (used for ECDH);
    ``app_cert`` / ``center_cert`` / ``root_cert`` are DER certificates from the
    cloud; ``ap_private_key`` keys the frame MD5 signature; ``key_id`` is kept
    for reference / re-provisioning.
    """

    cert_private_key: ECC.EccKey
    app_cert: bytes
    center_cert: bytes
    root_cert: bytes
    ap_private_key: str
    key_id: str


class TLSSession:
    """Drive the ``0x75`` certificate + ECDH handshake and derive the key.

    The caller owns the socket; this class only produces request bytes and
    consumes response frames so it stays fully unit-testable:

    ``build_cert_request()`` -> send -> ``process_cert_response(reply)`` ->
    ``build_finish()`` -> send -> ``process_finish(reply)`` -> ``session_key``.
    """

    def __init__(self, bundle: CertBundle, device_id: int) -> None:
        """Initialize the handshake with a provisioned :class:`CertBundle`."""
        self._bundle = bundle
        self._codec = MSDatagram(device_id, ap_private_key=bundle.ap_private_key)
        self._n1 = b""
        self._n2 = b""
        self._hello_body = b""
        self._session_key = b""

    @property
    def session_key(self) -> bytes:
        """The negotiated 16-byte AES-128-CCM session key (empty until done)."""
        return self._session_key

    def build_cert_request(self, n1: bytes | None = None) -> bytes:
        """Build the first handshake frame (center cert, app cert, nonce N1)."""
        self._n1 = n1 if n1 is not None else get_random_bytes(_NONCE_N1_LENGTH)
        center = self._bundle.center_cert
        app = self._bundle.app_cert
        body = bytearray()
        body += bytes([_CERT_STEP_HELLO, _CERT_STEP_HELLO])
        body += len(center).to_bytes(2, "little") + center
        body += len(app).to_bytes(2, "little") + app
        body += bytes([len(self._n1)]) + self._n1
        self._hello_body = bytes(body)
        return self._codec.encode(
            self._hello_body,
            MSG_TYPE_CERT_REQUEST,
            encrypt_type=ENCRYPT_TYPE_NONE,
            device_id=int(_ZERO_DEVICE_ID, 16),
        )

    def process_cert_response(self, frame: bytes) -> None:
        """Parse the device reply, verify it and derive the session key."""
        parsed = self._codec.decode(frame)
        if parsed.msg_type != MSG_TYPE_CERT_RESPONSE:
            raise CannotAuthenticate
        body = parsed.body
        if len(body) < _MIN_HELLO_BODY or body[0] != _CERT_STEP_HELLO:
            raise CannotAuthenticate
        if body[2] != _CERT_STATUS_OK:
            raise CannotAuthenticate
        len1 = _u16_le(body[3:5])
        offset = 5 + len1
        len2 = _u16_le(body[offset : offset + 2])
        offset += 2
        module_cert = body[offset : offset + len2]
        offset += len2
        n2_len = body[offset]
        offset += 1
        self._n2 = body[offset : offset + n2_len]
        offset += n2_len
        # The device HMAC's ``hello_body || body[:tag_len_index + 1]`` -- i.e.
        # the reply up to and including the one-byte tag length (Java's
        # ``bArr11 = body[0:i5 + 1]``).
        tag_len = body[offset]
        hmac_input_tail = body[: offset + 1]
        tag = body[offset + 1 : offset + 1 + tag_len]

        module_key = ECC.import_key(module_cert)
        shared = ecdh_shared_secret(self._bundle.cert_private_key, module_key)
        session_key = sha256(shared + self._n1 + self._n2).digest()[
            :_SESSION_KEY_LENGTH
        ]
        expected = _hmac_sha256(self._hello_body + hmac_input_tail, session_key)
        if not hmac.compare_digest(expected, tag):
            raise DataSignDoesntMatch
        self._session_key = session_key
        self._device_body = body

    def build_finish(self) -> bytes:
        """Build the handshake ``finished`` frame (HMAC of hello + device body)."""
        if not self._session_key:
            raise CannotAuthenticate
        tag = _hmac_sha256(
            self._hello_body + self._device_body,
            self._session_key,
        )
        body = bytes([_CERT_STEP_FINISH, _CERT_STEP_HELLO, len(tag)]) + tag
        return self._codec.encode(
            body,
            MSG_TYPE_CERT_REQUEST,
            encrypt_type=ENCRYPT_TYPE_NONE,
            device_id=int(_ZERO_DEVICE_ID, 16),
        )

    def process_finish(self, frame: bytes) -> None:
        """Verify the device's CCM-protected ``finished`` reply (status, N2)."""
        if not self._session_key:
            raise CannotAuthenticate
        # The finish frame itself is plaintext (encrypt_type 0); decode strips the
        # 2-byte version-3 counter. The CCM blob lives inside the handshake body.
        parsed = self._codec.decode(frame)
        if parsed.msg_type != MSG_TYPE_CERT_RESPONSE:
            raise CannotAuthenticate
        body = parsed.body
        if len(body) < _MIN_FINISH_BODY or body[0] != _CERT_STEP_FINISH:
            raise CannotAuthenticate
        inner_len = _u16_le(body[2:4])
        inner = body[4 : 4 + inner_len]
        nonce = inner[:CCM_NONCE_LENGTH]
        # The finish reply authenticates with an empty AAD.
        plaintext = ccm_decrypt(
            self._session_key,
            nonce,
            inner[CCM_NONCE_LENGTH:],
            b"",
        )
        status = plaintext[0]
        echoed_n2 = plaintext[1 : 1 + _NONCE_N2_EXPECTED]
        if status != _CERT_STATUS_OK or echoed_n2 != self._n2:
            raise CannotAuthenticate
