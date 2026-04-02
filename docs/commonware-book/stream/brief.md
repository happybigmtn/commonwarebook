# Chapter Brief: commonware-stream

## 1. Module Purpose

`commonware-stream` turns a plain sink/stream pair into a secure, framed,
ordered message channel. The crate only asks the transport for a way to send
and receive bytes. Everything else - peer authentication, key agreement,
message boundaries, replay resistance, and per-message encryption - is built
above that byte pipe.

The chapter's teaching arc should stay anchored on one idea: the handshake
proves which conversation we are in, the transcript binds that proof to the
session keys, framing turns the byte stream back into messages, and per-
direction counters keep the nonces safe. The point is not "encrypt bytes." The
point is "turn an arbitrary transport into a trusted conversation with clear
guarantee boundaries."

### Chapter Opening Apparatus

The chapter should begin with a compact apparatus that states the promise
before the lecture starts:

- one-sentence promise
- crux
- primary invariant
- naive failure
- reading map
- short assumption ledger

That opening should give readers the promise boundary in one glance, then let
the body teach the handshake, framing, and directional cipher machinery in the
usual secure-envelope-machine style.

---

## 2. Key Source Files

### `stream/src/lib.rs`
The public face of the crate. It exposes the `encrypted` and `utils` modules
and sets the stability boundary for the stream primitive.

### `stream/src/encrypted.rs`
The main protocol implementation. It contains the dialer and listener
handshakes, the `Config` type, the `Sender` and `Receiver` wrappers, and the
security notes that spell out what the crate guarantees and what it does not.

### `stream/src/utils/codec.rs`
The framing layer. This file shows how length-prefixed frames are encoded and
decoded, how invalid varints are rejected, and how oversized messages fail
before they can consume too much memory.

### `cryptography/src/handshake.rs`
The protocol engine underneath the stream crate. It defines the `Syn`,
`SynAck`, and `Ack` messages, transcript-bound key derivation, and the
directional send/receive ciphers built from the shared secret.

---

## 3. Chapter Outline

0. **Opening apparatus** - Promise, crux, primary invariant, naive failure,
   reading map, and assumption ledger.
1. **Why a stream needs ceremony** - A byte pipe is not a conversation, so we
   have to build identity, framing, ordering, and replay resistance ourselves.
2. **The mental model** - A secure envelope machine sitting on top of any
   sink/stream pair.
3. **The encrypted session state machine** - Teach the real wire exchange as
   four framed records: dialer public key, `Syn`, `SynAck`, `Ack`. Show the
   dialer and listener states separately, with the listener's early `bouncer`
   veto and the fact that `ListenState` holds prepared ciphers before the final
   confirmation arrives.
4. **Handshake internals** - Walk through the exact transcript shape: what
   `dial_start` commits and signs, what `listen_start` verifies and extends,
   where the shared secret is committed, and how confirmation tags come from
   transcript summaries rather than ad hoc MACs.
5. **Cipher and key-exchange mechanics** - Explain the X25519 ephemeral key
   exchange, rejection of non-contributory outputs, transcript-derived
   ChaCha20-Poly1305 traffic keys, and the direction split between
   `cipher_l2d` and `cipher_d2l`.
6. **Framing and the real data path** - Cover the sender's contiguous
   `send_frame_with` path, the generic chunked `send_frame` path, the
   receiver's peek-based varint fast path, the byte-by-byte slow path, and the
   size checks that run before decryption.
7. **Nonce and failure model** - One counter per direction, no nonce on the
   wire, ordered acceptance rather than reliability, and session termination on
   decryption mismatch because the receive counter cannot be safely rewound.
8. **Guarantees, threats, and visible metadata** - Put the promise boundary
   into tables: what the crate proves, which attacks it is designed to absorb,
   and what still leaks anyway such as identities, lengths, timing, and
   handshake progress.
9. **How to read the source** - Start from `encrypted.rs`, then descend into
   `cryptography/src/handshake.rs`, `handshake/cipher.rs`,
   `handshake/key_exchange.rs`, and `stream/src/utils/codec.rs`.

---

## 4. System Concepts to Explain at Graduate Depth

1. **The transport is not the protocol.** The crate assumes the transport can
   move bytes, not messages. The framing layer creates message boundaries.
2. **The first record is policy, not crypto.** The dialer's static public key
   is sent before `Syn` so the listener can reject early without paying the
   full handshake cost.
3. **The transcript is the root of trust.** Keys are not derived from the
   shared secret alone. They are derived from the shared secret plus the full
   handshake transcript, so the same secret with a different history produces
   different keys.
4. **Confirmation is transcript agreement.** `SynAck` and `Ack` confirm that
   both peers derived the same transcript-dependent summaries, not merely that
   they exchanged matching public keys.
5. **Direction matters.** Each side gets a separate cipher for sending and
   receiving. That keeps the two traffic directions from sharing a nonce
   space.
6. **Counters are the nonces.** The 12-byte nonce is implicit in the send or
   receive counter. The protocol does not spend bytes on explicit nonces.
7. **Framing is defensive, not decorative.** The varint prefix stops the reader
   from guessing where one message ends and the next begins, and the max size
   check keeps a malicious frame from becoming a memory problem.
8. **The failure boundary is explicit.** If timestamps, signatures, framing, or
   confirmations do not line up, the connection fails instead of limping along
   in a half-authenticated state.
9. **Metadata confidentiality is limited.** Payloads are sealed, but identity,
   timing, direction, and frame size remain visible.

---

## 5. Interactive Visualizations to Build Later

1. **Handshake timeline** - Animate the four wire records: dialer public key,
   `Syn`, `SynAck`, and `Ack`, then show the transcript-derived keys appearing.
2. **Envelope machine** - Show plaintext entering, getting length-prefixed,
   encrypted, tagged, and then recovered on the far side.
3. **State-machine view** - Show dialer and listener states separately, with
   the listener preparing ciphers before `Ack` but not releasing them yet.
4. **Nonce counter view** - Display separate send and receive counters for each
   direction and show why nonce reuse never happens unless the counter wraps.
5. **Frame parser** - Feed in well-formed, oversized, and malformed varints and
   show the peek fast path versus the byte-at-a-time slow path.
6. **Guarantees vs limits panel** - A simple two-column matrix that makes the
   promise boundary visually obvious.

---

## 6. Claims-to-Verify Checklist

- [ ] Dialer and listener derive matching send/receive ciphers after the same
  transcript is assembled.
- [ ] The listener's early peer-identity frame is outside the handshake proper
  and enables rejection before `Syn` is processed.
- [ ] Replaying or substituting handshake messages causes handshake failure.
- [ ] Shared-secret bytes are committed into the transcript before confirmation
  tags and traffic keys are derived.
- [ ] A message larger than `max_message_size` is rejected before encryption or
  decryption work proceeds.
- [ ] Invalid varint prefixes fail fast instead of looping forever.
- [ ] The receiver uses a peek-based fast path when the varint prefix is
  already buffered and a byte-at-a-time slow path otherwise.
- [ ] Out-of-order or duplicated ciphertext fails to decrypt rather than being
  accepted as a different message.
- [ ] Decryption failure advances the receive counter, so the session should be
  treated as dead rather than retried.
- [ ] Handshakes time out when the other side stalls.
- [ ] Listener rejection through the bouncer returns the peer identity to the
  caller.
- [ ] The chapter states clearly that identity, timing, and frame lengths still
  leak on the wire.
