"""Tests for the udp_version>=4 TLS transport (midealan.tls)."""

import base64
import hmac
import re
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path

import pytest
from Crypto.PublicKey import ECC
from Crypto.Random import get_random_bytes

from midealan.exceptions import (
    CannotAuthenticate,
    DataSignDoesntMatch,
    DataUnexpectedLength,
    MessageWrongFormat,
)
from midealan.tls import (
    CCM_NONCE_LENGTH,
    CCM_TAG_LENGTH,
    ENCRYPT_TYPE_CCM,
    ENCRYPT_TYPE_NONE,
    FRAME_MAGIC,
    HEADER_LENGTH,
    MSG_TYPE_CERT_RESPONSE,
    MSG_TYPE_DATA_TRANSMIT,
    SIGNATURE_LENGTH,
    CertBundle,
    MSDatagram,
    TLSSession,
    build_csr,
    ccm_decrypt,
    ccm_encrypt,
    ecdh_shared_secret,
    generate_ec_keypair,
)

_DEVICE_ID = 0x0102030405
_KEY_ID = "0123456789abcdef0123456789abcdef"
_AP_PRIVATE_KEY = "deadbeefdeadbeefdeadbeefdeadbeef"
_TAG_LENGTH = 32


def _fake_cert(key: ECC.EccKey) -> bytes:
    """Return a stand-in DER "certificate" carrying ``key``'s public key.

    ``ECC.import_key`` parses both a SubjectPublicKeyInfo blob and a full X.509
    certificate, so the exported SPKI serves as a certificate substitute that
    exposes the same public key the handshake needs for ECDH.
    """
    return key.public_key().export_key(format="DER")


class TestCsr:
    """PKCS#10 CSR builder."""

    def test_build_csr_is_base64_der(self) -> None:
        """A CSR round-trips through base64 to a DER SEQUENCE."""
        csr = build_csr(generate_ec_keypair(), _KEY_ID)
        raw = base64.b64decode(csr)
        assert raw[0] == 0x30

    def test_subject_common_name_is_sha_of_keyid(self) -> None:
        """The subject CN is sha256(key_id) truncated to 32 hex chars."""
        csr = base64.b64decode(build_csr(generate_ec_keypair(), _KEY_ID))
        expected_cn = sha256(_KEY_ID.encode("utf-8")).hexdigest()[:32]
        assert expected_cn.encode("ascii") in csr

    @pytest.mark.skipif(
        shutil.which("openssl") is None,
        reason="openssl not installed",
    )
    def test_openssl_verifies_csr(self, tmp_path: Path) -> None:
        """Verify the CSR with openssl: signature, subject order, extension."""
        csr = base64.b64decode(build_csr(generate_ec_keypair(), _KEY_ID))
        path = tmp_path / "csr.der"
        path.write_bytes(csr)
        result = subprocess.run(  # noqa: S603
            [  # noqa: S607
                "openssl",
                "req",
                "-inform",
                "DER",
                "-in",
                str(path),
                "-noout",
                "-verify",
                "-text",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        # OpenSSL version/platform differences: the verification result may land
        # on stdout or stderr, and OpenSSL 3 prints subject RDNs with spaces
        # around "=" (``OU = MideaCAOperation``). Search the combined output.
        output = result.stdout + result.stderr
        assert "verify OK" in output
        assert re.search(r"OU\s*=\s*MideaCAOperation", output)
        assert "CA:TRUE" in output


class TestCcm:
    """AES-128-CCM helpers."""

    def test_roundtrip(self) -> None:
        """Encrypt then decrypt returns the plaintext with a 16-byte tag."""
        key = get_random_bytes(16)
        nonce = get_random_bytes(CCM_NONCE_LENGTH)
        aad = get_random_bytes(HEADER_LENGTH)
        plaintext = b"hello midea"
        data = ccm_encrypt(key, nonce, plaintext, aad)
        assert len(data) == len(plaintext) + CCM_TAG_LENGTH
        assert ccm_decrypt(key, nonce, data, aad) == plaintext

    def test_roundtrip_empty_aad(self) -> None:
        """CCM works with an empty AAD (the handshake finish reply case)."""
        key = get_random_bytes(16)
        nonce = get_random_bytes(CCM_NONCE_LENGTH)
        plaintext = b"\x00" + get_random_bytes(16)
        data = ccm_encrypt(key, nonce, plaintext, b"")
        assert ccm_decrypt(key, nonce, data, b"") == plaintext

    def test_decrypt_rejects_short(self) -> None:
        """A ciphertext shorter than the tag is rejected."""
        with pytest.raises(DataUnexpectedLength):
            ccm_decrypt(get_random_bytes(16), get_random_bytes(13), b"short", b"")

    def test_tampered_tag_fails(self) -> None:
        """A corrupted tag fails verification."""
        key = get_random_bytes(16)
        nonce = get_random_bytes(CCM_NONCE_LENGTH)
        data = bytearray(ccm_encrypt(key, nonce, b"abc", b""))
        data[-1] ^= 0xFF
        with pytest.raises(ValueError, match="MAC check failed"):
            ccm_decrypt(key, nonce, bytes(data), b"")


class TestEcdh:
    """ECDH shared-secret agreement."""

    def test_shared_secret_matches(self) -> None:
        """Both parties derive the same 32-byte shared secret."""
        a = generate_ec_keypair()
        b = generate_ec_keypair()
        s1 = ecdh_shared_secret(a, b.public_key())
        s2 = ecdh_shared_secret(b, a.public_key())
        assert s1 == s2
        assert len(s1) == 32


class TestMSDatagram:
    """MSWifiDatagram framing."""

    def test_plaintext_roundtrip(self) -> None:
        """A plaintext frame round-trips and strips the counter on decode."""
        codec = MSDatagram(_DEVICE_ID, ap_private_key=_AP_PRIVATE_KEY)
        payload = b"\xaa\x1e\xac\x00"
        frame = codec.encode(
            payload,
            MSG_TYPE_DATA_TRANSMIT,
            encrypt_type=ENCRYPT_TYPE_NONE,
        )
        assert frame[0:2] == FRAME_MAGIC
        parsed = codec.decode(frame)
        assert parsed.msg_type == MSG_TYPE_DATA_TRANSMIT
        assert parsed.encrypt_type == ENCRYPT_TYPE_NONE
        assert parsed.body == payload

    def test_ccm_roundtrip(self) -> None:
        """A CCM frame round-trips under a session key."""
        codec = MSDatagram(
            _DEVICE_ID,
            ap_private_key=_AP_PRIVATE_KEY,
            session_key=get_random_bytes(16),
        )
        payload = b"\xaa\x20\xac\x00\x01\x02"
        frame = codec.encode(payload, MSG_TYPE_DATA_TRANSMIT)
        parsed = codec.decode(frame)
        assert parsed.encrypt_type == ENCRYPT_TYPE_CCM
        assert parsed.body == payload

    def test_signature_is_present(self) -> None:
        """The trailing 16-byte MD5 signature is non-zero."""
        codec = MSDatagram(_DEVICE_ID, ap_private_key=_AP_PRIVATE_KEY)
        frame = codec.encode(
            b"abc",
            MSG_TYPE_DATA_TRANSMIT,
            encrypt_type=ENCRYPT_TYPE_NONE,
        )
        length = int.from_bytes(frame[4:6], "little")
        assert frame[length - SIGNATURE_LENGTH : length] != bytes(SIGNATURE_LENGTH)

    def test_ccm_without_session_key_raises(self) -> None:
        """Encoding a CCM frame without a session key fails."""
        codec = MSDatagram(_DEVICE_ID, ap_private_key=_AP_PRIVATE_KEY)
        with pytest.raises(CannotAuthenticate):
            codec.encode(b"abc", MSG_TYPE_DATA_TRANSMIT)

    def test_decode_rejects_bad_magic(self) -> None:
        """A frame without the 5a5a magic is rejected."""
        codec = MSDatagram(_DEVICE_ID)
        with pytest.raises(MessageWrongFormat):
            codec.decode(b"\x00" * 64)

    def test_decode_rejects_bad_length(self) -> None:
        """A declared length past the buffer end is rejected."""
        codec = MSDatagram(_DEVICE_ID, ap_private_key=_AP_PRIVATE_KEY)
        frame = bytearray(
            codec.encode(
                b"abc",
                MSG_TYPE_DATA_TRANSMIT,
                encrypt_type=ENCRYPT_TYPE_NONE,
            ),
        )
        frame[4:6] = (len(frame) + 100).to_bytes(2, "little")
        with pytest.raises(DataUnexpectedLength):
            codec.decode(bytes(frame))

    def test_decode_ccm_without_session_key_raises(self) -> None:
        """Decoding a CCM frame without a session key fails."""
        sender = MSDatagram(
            _DEVICE_ID,
            ap_private_key=_AP_PRIVATE_KEY,
            session_key=get_random_bytes(16),
        )
        frame = sender.encode(b"abc", MSG_TYPE_DATA_TRANSMIT)
        receiver = MSDatagram(_DEVICE_ID, ap_private_key=_AP_PRIVATE_KEY)
        with pytest.raises(CannotAuthenticate):
            receiver.decode(frame)

    def test_set_session_key(self) -> None:
        """set_session_key enables CCM encode/decode after construction."""
        codec = MSDatagram(_DEVICE_ID, ap_private_key=_AP_PRIVATE_KEY)
        codec.set_session_key(get_random_bytes(16))
        frame = codec.encode(b"abc", MSG_TYPE_DATA_TRANSMIT)
        assert codec.decode(frame).body == b"abc"

    def test_send_counter_wraps(self) -> None:
        """The send counter wraps back to 1 after 0xFFFF."""
        codec = MSDatagram(_DEVICE_ID, ap_private_key=_AP_PRIVATE_KEY)
        codec._send_cnt = 0xFFFF
        codec.encode(b"a", MSG_TYPE_DATA_TRANSMIT, encrypt_type=ENCRYPT_TYPE_NONE)
        assert codec._send_cnt == 1

    def test_ccm_with_device_id_override(self) -> None:
        """A device-id override lands in the frame header."""
        codec = MSDatagram(
            _DEVICE_ID,
            ap_private_key=_AP_PRIVATE_KEY,
            session_key=get_random_bytes(16),
        )
        frame = codec.encode(b"abc", MSG_TYPE_DATA_TRANSMIT, device_id=0x55)
        assert frame[20] == 0x55
        assert codec.decode(frame).body == b"abc"

    def test_ccm_decode_body_too_short(self) -> None:
        """A CCM body shorter than the nonce is rejected."""
        codec = MSDatagram(
            _DEVICE_ID,
            ap_private_key=_AP_PRIVATE_KEY,
            session_key=get_random_bytes(16),
        )
        header = bytearray(HEADER_LENGTH)
        header[0:2] = FRAME_MAGIC
        header[2] = 3
        header[3] = ENCRYPT_TYPE_CCM | (1 << 4)
        length = HEADER_LENGTH + 5 + SIGNATURE_LENGTH
        header[4:6] = length.to_bytes(2, "little")
        header[6:8] = MSG_TYPE_DATA_TRANSMIT.to_bytes(2, "little")
        frame = bytes(header) + b"\x00" * 5 + b"\x00" * SIGNATURE_LENGTH
        with pytest.raises(DataUnexpectedLength):
            codec.decode(frame)

    def test_decode_version_below_3_keeps_body(self) -> None:
        """A version<3 frame does not strip a counter prefix."""
        codec = MSDatagram(_DEVICE_ID, ap_private_key=_AP_PRIVATE_KEY)
        payload = b"\x01\x02\x03\x04"
        header = bytearray(HEADER_LENGTH)
        header[0:2] = FRAME_MAGIC
        header[2] = 1
        header[3] = ENCRYPT_TYPE_NONE | (1 << 4)
        length = HEADER_LENGTH + len(payload) + SIGNATURE_LENGTH
        header[4:6] = length.to_bytes(2, "little")
        header[6:8] = MSG_TYPE_DATA_TRANSMIT.to_bytes(2, "little")
        frame = bytes(header) + payload + b"\x00" * SIGNATURE_LENGTH
        parsed = codec.decode(frame)
        assert parsed.version == 1
        assert parsed.body == payload


class _SimulatedDevice:
    """A minimal udp_version>=4 device that mirrors TLSSocket for handshakes.

    It parses the hello, runs ECDH against the app cert's public key, replies
    with its module cert chain + N2 + HMAC tag, then answers the finished frame
    with a CCM-protected status/N2 echo.
    """

    def __init__(self, bundle: CertBundle, device_id: int) -> None:
        """Create the simulated device from the app's provisioned bundle."""
        self._bundle = bundle
        self._module_key = generate_ec_keypair()
        self._module_cert = _fake_cert(self._module_key)
        self._codec = MSDatagram(device_id, ap_private_key=bundle.ap_private_key)
        self._n2 = get_random_bytes(16)
        self._session_key = b""

    def respond_hello(self, frame: bytes) -> bytes:
        """Parse the hello and build the module cert + N2 + HMAC reply."""
        body = self._codec.decode(frame).body
        offset = 2
        center_len = int.from_bytes(body[offset : offset + 2], "little")
        offset += 2 + center_len
        app_len = int.from_bytes(body[offset : offset + 2], "little")
        offset += 2
        app_cert = body[offset : offset + app_len]
        offset += app_len
        n1_len = body[offset]
        offset += 1
        n1 = body[offset : offset + n1_len]

        app_key = ECC.import_key(app_cert)
        shared = ecdh_shared_secret(self._module_key, app_key)
        self._session_key = sha256(shared + n1 + self._n2).digest()[:16]

        reply = bytearray([1, 0, 0])
        center = self._bundle.center_cert
        reply += len(center).to_bytes(2, "little") + center
        reply += len(self._module_cert).to_bytes(2, "little") + self._module_cert
        reply += bytes([len(self._n2)]) + self._n2
        reply += bytes([_TAG_LENGTH])
        mac = hmac.new(self._session_key, body + bytes(reply), sha256).digest()
        reply += mac
        return self._codec.encode(
            bytes(reply),
            MSG_TYPE_CERT_RESPONSE,
            encrypt_type=ENCRYPT_TYPE_NONE,
            device_id=0,
        )

    def respond_finish(self) -> bytes:
        """Build the CCM-protected finish reply echoing status and N2."""
        nonce = get_random_bytes(CCM_NONCE_LENGTH)
        plaintext = bytes([0]) + self._n2
        ct = ccm_encrypt(self._session_key, nonce, plaintext, b"")
        inner = nonce + ct
        body = bytes([2, 0]) + len(inner).to_bytes(2, "little") + inner
        return self._codec.encode(
            body,
            MSG_TYPE_CERT_RESPONSE,
            encrypt_type=ENCRYPT_TYPE_NONE,
            device_id=0,
        )


def _make_bundle() -> CertBundle:
    """Build a provisioning bundle with stand-in certificates for tests."""
    cert_key = generate_ec_keypair()
    return CertBundle(
        cert_private_key=cert_key,
        app_cert=_fake_cert(cert_key),
        center_cert=_fake_cert(generate_ec_keypair()),
        root_cert=_fake_cert(generate_ec_keypair()),
        ap_private_key=_AP_PRIVATE_KEY,
        key_id=_KEY_ID,
    )


class TestHandshake:
    """Full 0x75 handshake against a simulated device."""

    def test_handshake_derives_matching_session_key(self) -> None:
        """The handshake derives a session key matching the device's."""
        bundle = _make_bundle()
        device = _SimulatedDevice(bundle, _DEVICE_ID)
        session = TLSSession(bundle, _DEVICE_ID)

        session.process_cert_response(
            device.respond_hello(session.build_cert_request()),
        )
        assert session.session_key == device._session_key
        assert len(session.session_key) == 16

        finish = session.build_finish()
        assert finish[0:2] == FRAME_MAGIC
        session.process_finish(device.respond_finish())

    def test_process_cert_response_wrong_msgtype(self) -> None:
        """A non-cert response message type is rejected."""
        bundle = _make_bundle()
        session = TLSSession(bundle, _DEVICE_ID)
        session.build_cert_request()
        codec = MSDatagram(_DEVICE_ID, ap_private_key=_AP_PRIVATE_KEY)
        bad = codec.encode(
            bytes([1, 0, 0]),
            MSG_TYPE_DATA_TRANSMIT,
            encrypt_type=ENCRYPT_TYPE_NONE,
        )
        with pytest.raises(CannotAuthenticate):
            session.process_cert_response(bad)

    def test_process_cert_response_bad_step(self) -> None:
        """A wrong step byte in the hello reply is rejected."""
        bundle = _make_bundle()
        session = TLSSession(bundle, _DEVICE_ID)
        session.build_cert_request()
        codec = MSDatagram(_DEVICE_ID, ap_private_key=_AP_PRIVATE_KEY)
        bad = codec.encode(
            bytes([9, 0, 0]),
            MSG_TYPE_CERT_RESPONSE,
            encrypt_type=ENCRYPT_TYPE_NONE,
        )
        with pytest.raises(CannotAuthenticate):
            session.process_cert_response(bad)

    def test_process_cert_response_bad_status(self) -> None:
        """A non-zero status in the hello reply is rejected."""
        bundle = _make_bundle()
        session = TLSSession(bundle, _DEVICE_ID)
        session.build_cert_request()
        codec = MSDatagram(_DEVICE_ID, ap_private_key=_AP_PRIVATE_KEY)
        bad = codec.encode(
            bytes([1, 0, 1]),
            MSG_TYPE_CERT_RESPONSE,
            encrypt_type=ENCRYPT_TYPE_NONE,
        )
        with pytest.raises(CannotAuthenticate):
            session.process_cert_response(bad)

    def test_process_cert_response_bad_hmac(self) -> None:
        """A corrupted HMAC tag in the hello reply is rejected."""
        bundle = _make_bundle()
        device = _SimulatedDevice(bundle, _DEVICE_ID)
        session = TLSSession(bundle, _DEVICE_ID)
        reply = bytearray(device.respond_hello(session.build_cert_request()))
        length = int.from_bytes(reply[4:6], "little")
        reply[length - SIGNATURE_LENGTH - 1] ^= 0xFF
        with pytest.raises(DataSignDoesntMatch):
            session.process_cert_response(bytes(reply))

    def test_process_cert_response_truncated_body(self) -> None:
        """A hello reply truncated mid-field raises DataUnexpectedLength."""
        bundle = _make_bundle()
        session = TLSSession(bundle, _DEVICE_ID)
        session.build_cert_request()
        codec = MSDatagram(_DEVICE_ID, ap_private_key=_AP_PRIVATE_KEY)
        # step/pad/status OK, then a cert length that runs past the body end.
        bad = codec.encode(
            bytes([1, 0, 0]) + (0xFF).to_bytes(2, "little"),
            MSG_TYPE_CERT_RESPONSE,
            encrypt_type=ENCRYPT_TYPE_NONE,
        )
        with pytest.raises(DataUnexpectedLength):
            session.process_cert_response(bad)

    def test_process_cert_response_bad_module_cert(self) -> None:
        """A module certificate that is not a valid key raises auth failure."""
        bundle = _make_bundle()
        session = TLSSession(bundle, _DEVICE_ID)
        session.build_cert_request()
        codec = MSDatagram(_DEVICE_ID, ap_private_key=_AP_PRIVATE_KEY)
        # Well-formed framing (len1=0, a 4-byte garbage module cert, N2, tag)
        # but the module cert cannot be imported as an EC key.
        garbage_cert = b"\x00\x01\x02\x03"
        body = bytearray([1, 0, 0])
        body += (0).to_bytes(2, "little")  # len1 (center cert) = 0
        body += len(garbage_cert).to_bytes(2, "little") + garbage_cert
        body += bytes([2]) + b"\xaa\xbb"  # n2_len + N2
        body += bytes([1]) + b"\xcc"  # tag_len + tag
        bad = codec.encode(
            bytes(body),
            MSG_TYPE_CERT_RESPONSE,
            encrypt_type=ENCRYPT_TYPE_NONE,
        )
        with pytest.raises(CannotAuthenticate):
            session.process_cert_response(bad)

    def test_build_finish_requires_session_key(self) -> None:
        """Building the finish frame before the key is derived fails."""
        bundle = _make_bundle()
        session = TLSSession(bundle, _DEVICE_ID)
        with pytest.raises(CannotAuthenticate):
            session.build_finish()

    def test_process_finish_requires_session_key(self) -> None:
        """Processing the finish reply before the key is derived fails."""
        bundle = _make_bundle()
        session = TLSSession(bundle, _DEVICE_ID)
        with pytest.raises(CannotAuthenticate):
            session.process_finish(b"\x5a\x5a" + b"\x00" * 60)

    def test_process_finish_wrong_msgtype(self) -> None:
        """A non-cert finish message type is rejected."""
        bundle = _make_bundle()
        device = _SimulatedDevice(bundle, _DEVICE_ID)
        session = TLSSession(bundle, _DEVICE_ID)
        session.process_cert_response(
            device.respond_hello(session.build_cert_request()),
        )
        codec = MSDatagram(_DEVICE_ID, ap_private_key=_AP_PRIVATE_KEY)
        bad = codec.encode(
            bytes([2, 0, 0, 0]),
            MSG_TYPE_DATA_TRANSMIT,
            encrypt_type=ENCRYPT_TYPE_NONE,
        )
        with pytest.raises(CannotAuthenticate):
            session.process_finish(bad)

    def test_process_finish_bad_step(self) -> None:
        """A wrong step byte in the finish reply is rejected."""
        bundle = _make_bundle()
        device = _SimulatedDevice(bundle, _DEVICE_ID)
        session = TLSSession(bundle, _DEVICE_ID)
        session.process_cert_response(
            device.respond_hello(session.build_cert_request()),
        )
        codec = MSDatagram(_DEVICE_ID, ap_private_key=_AP_PRIVATE_KEY)
        bad = codec.encode(
            bytes([9, 0, 0, 0]),
            MSG_TYPE_CERT_RESPONSE,
            encrypt_type=ENCRYPT_TYPE_NONE,
        )
        with pytest.raises(CannotAuthenticate):
            session.process_finish(bad)

    def test_process_finish_bad_status(self) -> None:
        """A finish reply that echoes the wrong N2 is rejected."""
        bundle = _make_bundle()
        device = _SimulatedDevice(bundle, _DEVICE_ID)
        session = TLSSession(bundle, _DEVICE_ID)
        session.process_cert_response(
            device.respond_hello(session.build_cert_request()),
        )
        device._n2 = get_random_bytes(16)
        with pytest.raises(CannotAuthenticate):
            session.process_finish(device.respond_finish())

    def test_process_finish_bad_mac(self) -> None:
        """A finish reply whose CCM tag fails to verify raises auth failure."""
        bundle = _make_bundle()
        device = _SimulatedDevice(bundle, _DEVICE_ID)
        session = TLSSession(bundle, _DEVICE_ID)
        session.process_cert_response(
            device.respond_hello(session.build_cert_request()),
        )
        reply = bytearray(device.respond_finish())
        # Corrupt a byte inside the CCM ciphertext so the MAC check fails.
        reply[-SIGNATURE_LENGTH - 1] ^= 0xFF
        with pytest.raises(CannotAuthenticate):
            session.process_finish(bytes(reply))
