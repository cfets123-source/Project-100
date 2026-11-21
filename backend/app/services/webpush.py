"""Standards Web Push (RFC 8291 aes128gcm + RFC 8292 VAPID) using only `cryptography`.

Sends phone/desktop notifications for trades without any paid service. VAPID keys are
generated once and stored Fernet-encrypted in the app database; the private key is
never returned by any endpoint.
"""
from __future__ import annotations

import base64
import json
import os
import struct
import time
from urllib.parse import urlparse

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64u(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _raw_public(key) -> bytes:
    return key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def generate_vapid() -> dict:
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    return {"private_pem": pem, "public_key": b64u(_raw_public(key))}


def _hkdf(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def encrypt(payload: bytes, ua_public_b64: str, auth_b64: str, *, salt: bytes | None = None,
            sender_key=None) -> bytes:
    """aes128gcm body for one push message (single record)."""
    ua_public = unb64u(ua_public_b64)
    auth = unb64u(auth_b64)
    sender = sender_key or ec.generate_private_key(ec.SECP256R1())
    as_public = _raw_public(sender)
    peer = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)
    shared = sender.exchange(ec.ECDH(), peer)
    ikm = _hkdf(auth, shared, b"WebPush: info\x00" + ua_public + as_public, 32)
    salt = salt or os.urandom(16)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    record = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)
    return salt + struct.pack("!I", 4096) + bytes([len(as_public)]) + as_public + record


def vapid_authorization(endpoint: str, private_pem: str, public_key: str, subject: str) -> str:
    u = urlparse(endpoint)
    key = serialization.load_pem_private_key(private_pem.encode(), password=None)
    header = b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    claims = b64u(json.dumps({"aud": f"{u.scheme}://{u.netloc}", "exp": int(time.time()) + 12 * 3600,
                              "sub": subject}, separators=(",", ":")).encode())
    signing_input = f"{header}.{claims}".encode()
    r, s = decode_dss_signature(key.sign(signing_input, ec.ECDSA(hashes.SHA256())))
    sig = b64u(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
    return f"vapid t={header}.{claims}.{sig}, k={public_key}"


def send(subscription: dict, message: dict, vapid: dict, subject: str, client=None) -> int:
    """POST one notification; returns the push service status (201 ok, 404/410 = gone)."""
    body = encrypt(json.dumps(message).encode(), subscription["p256dh"], subscription["auth"])
    headers = {"TTL": "86400", "Urgency": "high", "Content-Encoding": "aes128gcm",
               "Content-Type": "application/octet-stream",
               "Authorization": vapid_authorization(subscription["endpoint"], vapid["private_pem"],
                                                    vapid["public_key"], subject)}
    http = client or httpx
    return http.post(subscription["endpoint"], content=body, headers=headers, timeout=10).status_code
