# Package Safety Verification

This document records the origin, author, license, and version of every
third-party package used by kibble-verifier, and how each was installed.

## Installed packages

### cryptography==50.0.0

- **Author:** Python Cryptographic Authority (PyCA) + individual contributors
- **Maintainer:** PyCA (pyca/cryptography on GitHub, ~4k stars, 600+ contributors)
- **License:** Apache-2.0 OR BSD-3-Clause (dual-licensed, both permissive)
- **Home page:** https://github.com/pyca/cryptography
- **Install source:** PyPI (pip install cryptography)
- **Purpose in this repo:** Ed25519 signing + identity PEM decryption (private key
  loading, sign/verify). This is the standard Python crypto library; it is
  widely audited and used by pip, requests, OpenID Connect libraries, and most
  Python tools that touch TLS or signing.
- **Why this version:** pinned to match the pyca/cryptography release tested
  against this codebase. The venv pins it explicitly.

### base58==2.1.1

- **Author:** David Keijser (keis)
- **Maintainer:** keis/base58 on GitHub (~200 stars, single-maintainer, stable)
- **License:** MIT
- **Home page:** https://github.com/keis/base58
- **Install source:** PyPI (pip install base58)
- **Purpose in this repo:** Encode/decode Ed25519 public keys as base58 for
  `did:key` derivation (did:key:z6M... addresses use base58btc encoding).
- **Why this version:** 2.1.1 is the latest stable release at time of writing.
  It provides `b58encode`/`b58decode` for raw base58 (no checksum), which is
  what the did:key spec requires.

## Why these two

kibble-verifier has exactly two third-party dependencies, both pulled from PyPI:

1. `cryptography` — for the Ed25519 operations (sign, verify, private key load).
   No alternatives are needed; this is the de-facto Python crypto library.
2. `base58` — for base58 encoding of the public key bytes when deriving the
   `did:key` string. The did:key spec uses multibase base58btc, and this library
   provides the raw encode/decode.

No other packages are imported at runtime. The repo ships with:
- Standard library modules only (json, hashlib, base64, urllib, pathlib, etc.)
- `pytest` as a dev dependency (optional, for running tests) — not required to
  use the tool.

## Installation safety

Both packages are installed via `pip install -r requirements.txt`, which pulls
from PyPI over HTTPS. The venv is isolated from the system Python. No packages
are installed from git URLs, no pre-built wheels from unknown sources, no
`setup.py` execution from untrusted repos.

To rebuild the venv from scratch and verify:

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/python -c "import cryptography, base58; print('ok')"
.venv/bin/python -m pytest tests/ -v
.venv/bin/python kibble_verifier.py --help
```

## What is NOT installed

- No packages from git repos, no private indexes, no `--find-links` hacks.
- No pre-release versions (requirements.txt pins exact versions).
- No system-wide installs — everything is inside `.venv/`.
- No packages fetched at runtime — all imports are at module load time, from
  the venv site-packages.

## Pinning policy

The requirements.txt pins exact versions:

```
cryptography==50.0.0
base58==2.1.1
```

This means a re-install will get the same versions tested against this codebase.
If a future version breaks something, the pinned versions keep the tool working
until the pin is deliberately updated.
