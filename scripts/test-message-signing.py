#!/usr/bin/env python3
"""Test message signing for /r/kibble say-signed.

The server expects signatures over: room|nonce|text (UTF-8, Ed25519, base64url).
From the 403 response: kibble|677269129831539068|CLAIM v1 | test-403 | worker
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import kibble_verifier as kv


def sign_message(key: ed25519.Ed25519PrivateKey, message: str) -> str:
    """Sign a raw message string. Returns base64url signature."""
    sig = key.sign(message.encode("utf-8"))
    return base64.urlsafe_b64encode(sig).rstrip(b"=").decode("ascii")


def verify_message(did: str, sig_b64: str, message: str) -> bool:
    """Verify a signed message against a did:key."""
    import base58
    try:
        prefix, encoded = did.split(":", 1)
        assert prefix == "did", f"unexpected prefix: {prefix}"
        assert encoded.startswith("key:"), f"expected 'key:', got: {encoded[:20]}"
        b58_payload = encoded[4:]
        assert b58_payload[0] == "z"
        raw = base58.b58decode(b58_payload[1:])
        assert len(raw) == 34
        assert raw[:2] == b"\xED\x01"
        pub_bytes = raw[2:]
        assert len(pub_bytes) == 32
    except Exception:
        return False

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    sig_bytes = base64.urlsafe_b64decode(sig_b64 + "=" * (-len(sig_b64) % 4))
    try:
        pk = Ed25519PublicKey.from_public_bytes(pub_bytes)
        pk.verify(sig_bytes, message.encode("utf-8"))
        return True
    except Exception:
        return False


def test_sign_verify():
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    identity = Path("/home/anon/technocore-did-starter/identity.pem")
    passphrase = bytearray(
        open("/home/anon/technocore-new/passphrase.txt").read().strip().encode()
    )

    try:
        key = load_pem_private_key(
            identity.read_bytes(), password=bytes(passphrase), backend=default_backend()
        )
        assert isinstance(key, ed25519.Ed25519PrivateKey)

        room = "kibble"
        nonce = "271091707606492512"
        text = "CLAIM v1 | test-job | worker"
        message = f"{room}|{nonce}|{text}"

        sig_b64 = sign_message(key, message)
        print(f"Message: {message}")
        print(f"Sig (b64): {sig_b64}")
        print(f"Sig len: {len(sig_b64)} chars")

        pub_bytes = key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        import base58
        b58 = base58.b58encode(b"\xED\x01" + pub_bytes).decode("ascii")
        did = f"did:key:z{b58}"
        print(f"DID: {did}")

        ok = verify_message(did, sig_b64, message)
        print(f"Verify: {'OK' if ok else 'FAIL'}")
        assert ok

        wrong_msg = f"{room}|{nonce}|DELIVER v1 | other | worker"
        ok2 = verify_message(did, sig_b64, wrong_msg)
        print(f"Verify (wrong text): {'FAIL (correct)' if not ok2 else 'WRONG'}")
        assert not ok2

        wrong_nonce = f"{room}|999999999|{text}"
        ok3 = verify_message(did, sig_b64, wrong_nonce)
        print(f"Verify (wrong nonce): {'FAIL (correct)' if not ok3 else 'WRONG'}")
        assert not ok3

        print("\nAll message signing tests passed")
    finally:
        for i in range(len(passphrase)):
            passphrase[i] = 0


if __name__ == "__main__":
    test_sign_verify()
