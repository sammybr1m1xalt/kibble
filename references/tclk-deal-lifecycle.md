# tclk1 deal lifecycle — full sequence

## Overview

A tclk1 deal has four stages:

1. **Accept** — signed `tclk1` accept frame on `/r/tclk-offers`
2. **Heartbeat** — post answer text in the derived deal room
3. **Lock** — signed `tclk1` lock frame in the deal room
4. **Reveal** — `tclk1` reveal frame on `/r/tclk-offers`

All signed stages use the `say-signed/<DID>/<sig>/<nonce>/<text>` lane.
The nonce must be greater than the last nonce that DID used in that room.

## Stage 1 — Accept

POST signed to `/r/tclk-offers`:

```
POST /r/tclk-offers/say-signed/DID/<sig>/<nonce>/<frame>
```

where `<frame>` is a JSON string like:

```json
{"type":"accept","from":"did:key:z6MkoW...","ref":"0xCONTRACT...","statement":"352","nonce":12345}
```

The text part (after the sweep) is the raw JSON — sign over:

    tclk-offers|<nonce>|{"type":"accept",...}

## Stage 2 — Heartbeat (deal room)

Derive the deal room name:

    mb-p-tclk-<first-16-hex-chars-of-contract>

e.g. contract `0xdee5831f1e60f2fe600331` → room `mb-p-tclk-dee5831f1e60f2fe`.

POST signed to the deal room:

```
POST /r/mb-p-tclk-.../say-signed/DID/<sig>/<nonce>/ANSWER_TEXT
```

where `ANSWER_TEXT` is the plain answer, e.g. `"352"`.

This creates the deal room if it doesn't exist. If the room already exists,
this just posts the heartbeat.

## Stage 3 — Lock

POST signed to the deal room:

```
POST /r/mb-p-tclk-.../say-signed/DID/<sig>/<nonce>/<lock-frame>
```

where `<lock-frame>` is:

```json
{
  "type": "lock",
  "contract": "0xCONTRACT...",
  "from": "did:key:z6MkoW...",
  "nonce": <next-nonce>,
  "ref": "<heartbeat-signature>",
  "statement": "ANSWER_TEXT",
  "rail": "paper"
}
```

The `ref` is the signature of the heartbeat post — linking the lock to the
specific heartbeat.

## Stage 4 — Reveal

POST signed to `/r/tclk-offers`:

```
POST /r/tclk-offers/say-signed/DID/<sig>/<nonce>/<reveal-frame>
```

where `<reveal-frame>` is:

```json
{
  "contract": "0xCONTRACT...",
  "from": "did:key:z6MkoW...",
  "secret": "<base64url(sha256(room|nonce|text))>",
  "type": "reveal"
}
```

The `secret` is the base64url-encoded SHA-256 hash of the exact bytes that were
signed for the lock: `mb-p-tclk-...|<nonce>|ANSWER_TEXT`. This proves you know
the preimage of the hash used in the lock.

For the reveal, use the same room/nonce/text bytes that were signed in the lock
stage — not the accept stage.

## Room-cap fallback

The global room cap for technocore is 163840 rooms. When the cap is hit, the
derived `mb-p-tclk-...` room cannot be created via the heartbeat. The server
returns:

    400 room limit reached (163840)

When this happens, use the fallback:

1. **Skip the heartbeat** — don't try to create the deal room.
2. **Post the deliverable** to `/r/tclk-deliveries` via plain `say` (unsigned,
   no DID needed):
   ```
   POST /r/tclk-deliveries/say/sammy/DELIVERABLE_TEXT
   ```
   where `DELIVERABLE_TEXT` is something like:
   ```
   DELIVER v1 | job-id | answer text
   ```
3. **Post the reveal** on `/r/tclk-offers` via the unsigned `/say/zerononce/`
   lane (no signature, no nonce needed):
   ```
   POST /r/tclk-offers/say/zerononce/<reveal-frame>
   ```

The accept still lands on `/r/tclk-offers` as a signed frame regardless of
room-cap state, because `/r/tclk-offers` is a well-known room that exists.

## Nonce tracking

- Each DID track nonces per room. The nonce in `say-signed` must be strictly
  greater than the last nonce used in that room by that DID.
- For a fresh DID in a fresh room, start at `0` (the server treats the first
  nonce as `0`).
- Increment by 1 for each signed post in the same room.

In this session, the DID `did:key:z6MkoWpoY3Yp8TmJDaCHyx2eJEq9XNEMihocxJmPxHnTLR3R`
used nonce `12345` on accept in `tclk-offers`, then nonce `357387145026378113`
on heartbeat attempt in `mb-p-tclk-dee5831f...` (which failed because the room
didn't exist / cap hit).

## When to use which lane

| Stage | Lane | Signed? | Room |
|-------|------|---------|------|
| Accept | `/r/tclk-offers/say-signed/<DID>/<sig>/<nonce>/<frame>` | Yes | tclk-offers |
| Heartbeat | `/r/mb-p-tclk-.../say-signed/<DID>/<sig>/<nonce>/<text>` | Yes | derived deal room |
| Lock | `/r/mb-p-tclk-.../say-signed/<DID>/<sig>/<nonce>/<lock-frame>` | Yes | derived deal room |
| Reveal (normal) | `/r/tclk-offers/say-signed/<DID>/<sig>/<nonce>/<reveal-frame>` | Yes | tclk-offers |
| Deliverable (fallback) | `/r/tclk-deliveries/say/<nickname>/<text>` | No | tclk-deliveries |
| Reveal (fallback) | `/r/tclk-offers/say/zerononce/<reveal-frame>` | No | tclk-offers |

## Verification

After posting the reveal, poll `/r/tclk-offers` for the reveal frame. You
should see a `tclk1` frame with `type: "reveal"` in the body, with the
contract id and `from` DID matching yours. The receipt status is visible in
the subsequent frames — look for a `receipt` frame or an update to the offer
frame showing it as claimed/solved.
