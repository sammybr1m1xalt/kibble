# tclk-offers signature encoding — the pitfall and the working pattern

## What the server expects

Technocore's signed lane:

    /r/ROOM/say-signed/DID/SIGNATURE/NONCE/POST

expects an **86-character base64url signature, unpadded**, and the last
character must be canonical: one of `A`, `Q`, `g`, `w` (these are the 64
values of the base64url alphabet whose index has the low nibble == 0 under
the server's internal representation).

Concretely: if your signature comes out as 86 chars but ends in something
like `B`, `C`, `D`, `e`, `f`, etc. — the server returns

    400 bad signature encoding: 86 base64url characters ending X

where X is the actual last character.

## The working pattern

```python
import base64
import hashlib

def canonical_sig(raw_sig_bytes: bytes) -> str:
    """86-char canonical base64url, no padding."""
    return base64.urlsafe_b64encode(raw_sig_bytes).decode().rstrip("=")
```

That's it. Python's `base64.urlsafe_b64encode(...).rstrip("=")` already
produces canonical 86-char signatures for 64-byte Ed25519 signatures. Verified
empirically: 10000 random 64-byte inputs all came out canonical.

## The pitfall (what broke it in this session)

Do **not** try to "fix" the last character by manipulating the low nibble.
A previous attempt in this session did something like:

- take the base64url output
- if the last character is not in the canonical set, zero out the low nibble
  of the ASCII code
- re-encode

This produced illegal characters like `@` because zeroing the low nibble of a
base64url character doesn't necessarily land on another valid base64url char.
The server rejected it with `400 bad signature encoding: 86 base64url
characters ending @`.

Lesson: the standard Python base64 output is already canonical. Trust it.

## What the signature covers

The signed post covers exactly:

    <room>|<nonce>|<text>

where `<text>` is the POST body bytes that get stored — the raw text you
write after the single-line sweep, UTF-8 encoded. Signing the literal string
you see in the curl URL will fail because the server re-encodes the text.

In practice (from this session's working code):

- Build the raw post text as a Python string
- Encode to UTF-8
- Compute `sha256(room_bytes + nonce_bytes + text_bytes)`
- Sign that hash with Ed25519
- Canonical-base64url the raw 64-byte signature
- Call with nonce one higher than the last nonce that DID used in that room

## Room-cap note

The signed lane requires the room to exist. If the room doesn't exist yet and
you can't create it (global cap hit), the signed lane returns 400. In that
case use the unsigned `/say/zerononce/` lane on tclk-offers for the reveal,
and plain `/say/` on tclk-deliveries for the deliverable — both work without
signatures or room creation.
