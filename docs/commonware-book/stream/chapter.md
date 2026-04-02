# commonware-stream

## Turning a Byte Pipe into a Trusted Conversation

---

## Chapter Opening Apparatus

### One-Sentence Promise
`commonware-stream` turns a raw byte pipe into a trusted conversation by
authenticating the peer, binding keys to the handshake transcript, framing
every payload, and sealing each direction with its own cipher.

### Crux
A secure transport is not "encryption plus bytes"; it is proof that the bytes
belong to this conversation, in this order, under this transcript.

### Primary Invariant
If a session is accepted, both peers must derive the same transcript-bound
keys, and every message must decrypt only under the correct direction-specific
counter and frame length.

### Naive Failure
If you encrypt a stream after the fact, you inherit ambiguous boundaries,
counter reuse, replayable transcripts, and a protocol that can no longer say
which bytes belong to which message.

### Reading Map
Start with `stream/src/encrypted.rs`, then follow the transcript binding in
`cryptography/src/handshake.rs`, then the framing rules in
`stream/src/utils/codec.rs`, and finish with the send and receive wrappers
that enforce the protocol end to end.

### Assumption Ledger
- The transport moves bytes, not messages.
- Peers know the namespace out of band.
- Clocks are close enough for timestamp checks.
- The application may reject the peer before the listener commits to the
  handshake.

---

## Background: Why a Byte Pipe Is Not Yet a Conversation

At first glance, a stream is just a channel that moves bytes. The deeper
problem is that bytes do not arrive with boundaries, identities, or trust
attached.

That gives us the core vocabulary for secure transport:

- a **byte stream** is a continuous flow with no built-in message edges,
- a **frame** adds an explicit boundary around one message,
- a **handshake** proves that both sides are in the same conversation,
- a **transcript** records the facts that define that conversation,
- a **cipher** protects payloads once the channel has been established.

The naive approach is to "just encrypt the bytes" and call the job done. That
fails for several reasons:

- the receiver still cannot tell where one message ends and the next begins,
- replayed or reordered bytes may still look syntactically valid,
- the same secret can be reused in the wrong protocol context,
- one direction can accidentally reuse the nonce space of the other.

The tradeoffs are real. Framing costs bytes and state. Handshakes add latency.
Transcript binding adds design complexity. But without those costs, the system
cannot answer the most basic question a transport must answer: which bytes
belong to this conversation, in this order, under this promise?

That is the background this chapter assumes. The Commonware-specific machinery
then takes those ideas and makes them concrete: authenticate the peer, bind the
keys to the transcript, frame each payload, and keep the two directions
separate.

---

## 1. What Problem Does This Solve?

A raw transport gives you motion, not meaning. Bytes can travel, but they do
not arrive with boundaries, identities, or proof that the other side saw the
same exchange you did. A byte pipe can carry data. It cannot yet carry a secure
conversation.

`commonware-stream` exists to close that gap. It takes a sink and a stream, and
builds the missing structure on top: an authenticated handshake, transcript-
bound session keys, framed messages, and direction-specific encryption. The
crate does not ask the transport to be reliable, message-oriented, or secure.
It takes responsibility for those layers itself.

That is the real job of the primitive: make the transport forgettable. Once the
session exists, higher layers should be able to think in terms of messages and
trust boundaries, not raw bytes and accidental byte order.

---

## 2. Mental Model

Picture a secure envelope machine sitting on top of an ordinary tube.

The tube moves bytes. The machine decides what counts as a message, who is
allowed to speak, and whether the other side really saw the same handshake
history. The handshake is the machine's act of establishing provenance: each
side introduces itself, signs the exchange, and commits the transcript into the
keys that will protect the session.

After that, the machine stops improvising. Every payload is stamped into a
length-prefixed frame, sealed with an AEAD tag, and sent under a cipher that
belongs to one direction only. The sender never guesses where a message ends.
The receiver never guesses which conversation a ciphertext belongs to. If the
proof does not line up, the machine refuses to invent a meaning.

That refusal is the design. Secure transport is not "encryption plus some
bytes." It is a sequence of proof steps that must all agree before a message is
allowed to exist.

---

## 3. The Core Ideas

### The handshake is where trust begins

The stream crate leans on `cryptography/src/handshake.rs` for the real
authentication work. The three handshake messages are small, but they are not
simple:

- `Syn` starts the conversation from the dialer.
- `SynAck` answers from the listener.
- `Ack` closes the loop from the dialer.

Those messages do not just exchange ephemeral keys. They bind the session to a
transcript that includes the namespace, the timestamps, the identities, the
ephemeral keys, and the derived shared secret. That transcript is the session's
memory. It is also the session's proof.

### Transcript binding is the difference between a key and a conversation

The same shared secret is not enough. A secret only says that two parties may
know the same value. A transcript says which exchange produced that value and
what else was committed along the way.

That matters because the protocol must resist more than passive eavesdropping.
It must resist substitution, replay, and man-in-the-middle games that try to
reuse a valid secret in the wrong context. Binding the keys to the transcript
makes the session specific. The key is not just "shared." It is shared inside a
particular history.

### Framing turns a stream back into messages

`stream/src/utils/codec.rs` supplies the defensive framing layer. It uses a
varint length prefix to say how many bytes belong to the next payload. The body
never gets to claim its own boundary. That boundary is asserted explicitly, and
the receiver checks it before doing real work.

This is why the framing code matters so much in a secure transport chapter. A
message that cannot be bounded is a message that can be misread, over-read, or
forced into memory pressure. Framing is not decorative. It is what turns a
continuous byte stream into a sequence of intentional records.

### Directionality keeps nonce spaces separate

Each direction owns its own cipher. One cipher sends dialer-to-listener data.
The other handles listener-to-dialer data. They do not share a nonce space, and
they do not share a counter.

That separation is the difference between a clean protocol and a fragile one.
The counter becomes the nonce, so the protocol does not need to spend bytes
announcing nonces on the wire. But the counter only stays safe if each
direction keeps its own ledger. `commonware-stream` does that by construction.

### The configuration defines the promise boundary

`Config` is not a bag of knobs. It is the operating envelope of the protocol:

- `signing_key` identifies the local peer.
- `namespace` keeps one application from replaying into another.
- `max_message_size` bounds memory use and frame size.
- `synchrony_bound` and `max_handshake_age` define what timestamps are still
  believable.
- `handshake_timeout` decides how long the system will wait before it stops
  trusting a stalled peer.

Those values do not make the protocol stronger in the abstract. They make the
protocol honest about its assumptions.

---

## 4. The Encrypted Session State Machine

The cleanest way to understand the crate is to stop thinking in terms of
"connect, then encrypt" and start thinking in terms of a small state machine
that refuses to enter `Established` until every proof obligation is satisfied.

There are really two machines here:

- the stream-layer machine in `stream/src/encrypted.rs`, which handles
  transport I/O, early peer rejection, framing, and timeouts,
- and the handshake machine in `cryptography/src/handshake.rs`, which decides
  when the transcript is valid enough to derive ciphers.

### The four wire records

The on-wire exchange has four framed records, not three:

| Wire order | Record | Produced by | Purpose |
| --- | --- | --- | --- |
| 1 | dialer public key | `stream::dial` | Reveal the caller before full handshake work |
| 2 | `Syn` | `dial_start` | Commit dialer timestamp, peer expectation, and dialer ephemeral key |
| 3 | `SynAck` | `listen_start` | Prove the listener saw the same transcript so far |
| 4 | `Ack` | `dial_end` | Prove dialer saw the same full transcript and derived the same secret |

That first record is easy to miss because it lives in the stream crate, not the
handshake crate. It is the reason the listener can run the `bouncer` callback
before it allocates handshake state. The stream layer exposes identity early so
policy can reject cheaply.

### Dialer states

The dialer's path is short but strict:

1. `PreHandshake`: send the local static public key as a framed record.
2. `DialStarted`: call `dial_start`, which generates an ephemeral X25519 secret
   key, derives the ephemeral public key, signs the opening transcript, and
   stores a `DialState`.
3. `AwaitSynAck`: read one frame, decode it as `SynAck`, and validate the
   listener timestamp, signature, shared-secret derivation, and confirmation.
4. `AckSent`: if all checks pass, send `Ack`.
5. `Established`: wrap the sink in `Sender` and the stream in `Receiver`.

`DialState` is the dialer's half-finished memory of the session. It holds the
ephemeral secret key, the expected peer identity, the running transcript, and
the acceptable timestamp range. Until `SynAck` verifies, the dialer has no
session ciphers and no right to send application data.

### Listener states

The listener has one extra policy gate:

1. `AwaitPeerIdentity`: read the dialer's static public key.
2. `PolicyCheck`: call `bouncer(peer)` and fail immediately if the application
   does not want this peer.
3. `AwaitSyn`: read and decode `Syn`.
4. `SynVerified`: call `listen_start`, which checks the dialer timestamp and
   signature, generates the listener ephemeral secret, derives the shared
   secret, and prepares the session ciphers.
5. `AwaitAck`: send `SynAck`, then wait for the dialer's confirmation.
6. `Established`: only after `listen_end` confirms the `Ack` value.

This is the subtle point: the listener derives the ciphers before the handshake
is finished, but it does not release them to the caller yet. `ListenState`
stores the expected final confirmation plus the already-derived send and
receive ciphers. In other words, the listener can prepare the session before it
trusts the session.

### Why the third message matters

Without `Ack`, the listener would know only that it derived *a* secret from the
dialer's `Syn`. It would not know that the dialer accepted the listener's
timestamp, ephemeral key, and transcript-dependent confirmation. The third
message closes that asymmetry.

This is why the state machine is worth naming explicitly:

```text
AwaitIdentity -> AwaitSyn -> AwaitAck -> Established
```

The machine is small because it is trying to eliminate ambiguity. Either both
sides prove the same transcript, or the connection never becomes a session.

---

## 5. Handshake Internals: Transcript, X25519, and Confirmation

The secure core of the protocol lives in the way it builds the transcript.
Shared secrets matter, but the protocol does not trust a shared secret by
itself. It trusts a shared secret only after it has been placed inside the
right history.

### What `Syn` really commits to

`dial_start` forks the application transcript with the fixed handshake
namespace, then commits:

1. the dialer's current timestamp,
2. the expected peer identity,
3. the dialer's ephemeral public key.

That committed transcript is then signed with the dialer's long-term signing
key. Only after that signature is produced does the transcript commit the
dialer's own public key.

Conceptually, `Syn` says: "At this time, I intended to talk to *you*, with this
ephemeral key, under this namespace."

### What `SynAck` adds

`listen_start` reconstructs the same transcript prefix from the listener side
and verifies the dialer's signature. Then it extends the transcript with:

1. the dialer's static public key,
2. the listener's current timestamp,
3. the listener's ephemeral public key.

The listener signs that extended transcript, performs X25519 with its new
ephemeral secret and the dialer's ephemeral public key, commits the resulting
shared secret bytes into the transcript, and only then derives:

- `cipher_l2d`,
- `cipher_d2l`,
- `confirmation_l2d`,
- `confirmation_d2l`.

At that moment the session stops being "a Diffie-Hellman result" and becomes
"this Diffie-Hellman result under this exact transcript."

### X25519 is necessary, but not sufficient

The key exchange itself is intentionally plain:

- `SecretKey::new` creates a fresh X25519 ephemeral secret,
- `public()` exposes the matching 32-byte ephemeral public key,
- `exchange()` performs Diffie-Hellman,
- non-contributory outputs are rejected.

This is important because the handshake is not trying to be clever at the
curve layer. Its sophistication is in composition: static signatures authenticate
the participants, ephemeral X25519 provides forward secrecy, and the transcript
ties the two together so the shared secret cannot be replayed in a different
conversation.

### Confirmation tags are transcript summaries, not extra signatures

The confirmation values in `SynAck` and `Ack` are not arbitrary MACs and not
second signatures. They are transcript summaries under direction-specific
labels:

- `confirmation_l2d` proves what the listener believes the transcript is,
- `confirmation_d2l` proves what the dialer believes the transcript is.

Because they are derived *after* committing the shared secret into the
transcript, they prove more than "I saw your message." They prove "I saw the
same handshake history and derived the same secret from it."

### Why the ciphers come in a pair

After the shared secret is committed, the transcript forks two independent
noise streams:

- `LABEL_CIPHER_L2D` for listener-to-dialer traffic,
- `LABEL_CIPHER_D2L` for dialer-to-listener traffic.

Those forked transcript outputs seed two separate ChaCha20-Poly1305 keys. This
is the protocol's way of hard-partitioning the nonce space. Even if both sides
send their first application message at the same moment, they are not using the
same key and nonce pair, because they are not using the same cipher instance.

### Handshake failure is intentionally vague

Most handshake mismatches collapse to `HandshakeFailed`. That is not a lack of
engineering detail. It is a policy choice. The application cannot safely do
much with "bad signature" versus "wrong confirmation," but an adversary might
learn from the distinction. The protocol therefore spends its detail on proof,
not on error disclosure.

---

## 6. Framing and the Data Path

Once the session exists, the chapter needs to zoom in on a simpler but equally
important truth: the ciphertext path only works because the framing path is
already disciplined.

### What exactly is framed

The wire format for post-handshake traffic is:

```text
varint(ciphertext_len) || ciphertext || tag
```

The length prefix covers the encrypted payload plus the 16-byte AEAD tag. The
prefix itself is not encrypted. That design keeps parsing simple and bounded,
but it also means packet length is visible on the wire.

### Sender fast path: contiguous assembly

`Sender::send` does not call the generic chunked framing path. It calls
`send_frame_with`, asks for a single pooled buffer large enough for:

- the varint prefix,
- the plaintext,
- the authentication tag,

then writes the prefix, copies the plaintext into the same allocation,
encrypts the plaintext region in place, appends the tag, and sends one frozen
buffer.

This is the send fast path. The point is to keep the hot path predictable:
one allocation, one contiguous plaintext, one ciphertext.

By contrast, plain `send_frame` uses a chunked layout: it prepends the varint
as one `IoBuf` and leaves the payload in its existing buffers. The handshake
records are small enough that this simpler path keeps the framing logic
obvious without paying for in-place encryption.

### Receiver fast path: decode length from peeked bytes

`recv_frame` begins by calling `recv_length`. That helper first tries the cheap
case:

1. `peek(MAX_U32_VARINT_SIZE)`,
2. feed the bytes into a varint decoder,
3. if the whole length prefix is visible already, return `(payload_len, skip)`.

No network wait is needed in that case. The receiver learned the record length
just by looking at bytes the stream had already buffered.

### Receiver slow path: advance byte by byte until the varint closes

If the entire prefix is not yet buffered, `recv_length` falls back to a
one-byte-at-a-time path:

1. fetch the first unread byte after the peeked region,
2. continue feeding the decoder,
3. keep calling `recv(1)` until the varint finishes or becomes invalid.

This is not an optimization failure. It is deliberate defensive parsing.
Varints are short, so byte-at-a-time fallback is cheap, and it lets the code
stay precise about malformed prefixes instead of over-reading the stream.

### Why malformed framing is rejected early

The framing layer rejects three broad classes of problems before the cipher is
even asked to help:

- lengths that decode as larger than `max_message_size`,
- invalid varint encodings,
- closed or failed underlying transport reads.

That ordering matters. The protocol first asks "How many bytes does this record
claim to have?" before it asks "Can I decrypt them?" A secure channel that
cannot bound a record is still vulnerable to resource abuse.

### Decryption is in-place, and failure is terminal for the session

`Receiver::recv` reads one ciphertext frame, copies it into a pooled mutable
buffer, and calls `RecvCipher::recv_in_place`. That function increments the
receive nonce counter before decrypting. If the ciphertext is truncated,
corrupted, duplicated, or delivered out of order, decryption fails.

The key consequence is easy to miss: the receive counter has still advanced.
The cipher cannot safely "rewind" and try again under the old nonce. So a bad
ciphertext is not a recoverable parsing error. It is the end of that session.

This is the right failure mode. The crate prefers to kill the conversation than
to guess which counter the peer "must have meant."

---

## 7. Cipher Mechanics and the Nonce Failure Model

The post-handshake transport uses ChaCha20-Poly1305. Each cipher instance owns
two pieces of hidden state:

- a 32-byte key,
- a 96-bit nonce counter.

### How the nonce is formed

The implementation stores the counter in a `u128`, starts at zero, serializes
it little-endian, and uses only the lower 12 bytes as the ChaCha20-Poly1305
nonce. The counter increments once per message.

That gives each direction an independent space of `2^96` nonces. The code
checks overflow explicitly and returns `MessageLimitReached` instead of risking
nonce reuse.

### What "ordered delivery" means here

The crate does not create reliability. It creates ordered *acceptance*.

If the peer sends messages `m1`, `m2`, `m3`, then the receiver will only accept
them in that order under receive counters `0`, `1`, `2`. If the network
duplicates `m1`, reorders `m2` and `m3`, or drops one of them, the receiver
does not attempt repair. It simply fails to decrypt under the expected counter.

So the guarantee is:

- if a message is accepted, it arrived under the expected direction and counter,
- but if the transport misbehaves, the stream layer terminates rather than
  repairing or reordering.

### Why no nonce is sent on the wire

Many protocols transmit an explicit nonce next to each ciphertext. This one
does not, because the state machine already knows which nonce must come next.
That saves bytes and removes a whole class of "nonce was repeated on the wire"
bugs. The cost is that the session depends on both sides staying perfectly
aligned on message count.

That trade is reasonable here because the crate is building an ordered message
channel, not a lossy datagram protocol.

---

## 8. Threat Model, Guarantees, and What Still Leaks

The stream chapter is strongest when it says exactly what the primitive proves,
exactly what attacker pressure it is built to absorb, and exactly what remains
visible anyway.

### Guarantee table

| Property | Mechanism | Boundary |
| --- | --- | --- |
| Mutual auth | `Syn` and `SynAck` signatures | Assumes expected peer identity |
| Forward secrecy | Fresh X25519 ephemeral keys | Static-key theft still exposes future sessions |
| Transcript binding | Commit shared secret before deriving keys | Blocks DH reuse elsewhere |
| Cross-app replay resistance | Namespace in base transcript | Needs unique namespaces |
| Ordered acceptance | Per-direction receive counter | Does not repair loss or reordering |
| Size bounds | Frame length checked before decrypt | Limited by `max_message_size` |
| Handshake stall resistance | Timeout races the handshake | Only covers handshake phase |
| Early listener veto | Peer identity arrives before `Syn` | Identity is already visible |

### Threat table

| Threat | Response |
| --- | --- |
| Passive eavesdropper | Cannot read sealed payloads without traffic keys |
| Active man in the middle | Breaks transcript-bound signatures or confirmations |
| Replay into another application | Fails when namespaces differ |
| Replay of stale handshake messages | Rejected by timestamp bounds |
| Ciphertext duplication or reordering | Usually becomes decryption failure |
| Oversized-frame memory attack | Length check fires before large allocation |
| Handshake abandonment | Timeout closes the attempt |

### What still leaks

This crate protects content more than metadata. The following remain visible to
an observer on the wire:

- the dialer's static public key in the first framed record,
- the fact that a handshake is happening,
- the timing and direction of records,
- the ciphertext length of each frame,
- the plaintext length up to the fixed 16-byte AEAD expansion and varint
  encoding,
- whether the listener rejected the peer early or let the handshake continue.

It also leaks structure at the session level:

- there is no padding, so message-size patterns remain,
- there is no cover traffic, so silence remains silence,
- there is no identity hiding, so who is talking to whom is exposed to network
  observers,
- there is no 0-RTT or resumption shortcut, so every session pays the full
  three-message proof cost,
- there is no transport reliability layer, so the session breaks under dropped
  or reordered ciphertext instead of healing.

That last point matters for threat modeling. `commonware-stream` is a secure
ordered channel over a working byte stream. It is not a censorship-resistant
anonymity protocol, a congestion-control layer, or a packet repair system.

---

## 9. How to Read the Source

Start in `stream/src/encrypted.rs`. Read it as the story of a session rather
than as a pile of methods.

1. `Config` tells you which limits and assumptions shape the protocol.
2. `dial` and `listen` show the handshake control flow in real time.
3. `Sender` and `Receiver` show how the established session is used after the
   proof is complete.
4. The error type shows where the crate draws its failure boundary.

Then move to `cryptography/src/handshake.rs` to see where the trust proof is
actually assembled.

1. `Syn`, `SynAck`, and `Ack` show the shape of the exchange.
2. `dial_start`, `listen_start`, `dial_end`, and `listen_end` show how the
   transcript is committed, checked, and turned into ciphers.
3. The directional cipher labels explain why send and receive stay separate.

Finally, read `stream/src/utils/codec.rs` to see how the protocol draws the
message boundary before encryption and after decryption. That file answers the
simple but essential question: "How does a stream become a frame?"

---

## 10. Glossary and Further Reading

- **Transcript** - The running record that binds the handshake to one
  specific conversation.
- **Frame** - One length-prefixed record the receiver can bound before
  decryption.
- **Nonce counter** - The per-direction message index that becomes the AEAD
  nonce.
- **Confirmation tag** - The final transcript summary that proves both sides
  derived the same session.
- **Bouncer** - The policy callback that lets the listener veto a peer before
  it spends the rest of the handshake.

Further reading:

- `stream/src/lib.rs` for the public module boundary.
- `stream/src/encrypted.rs` for the session wrapper and guarantees.
- `cryptography/src/handshake.rs` for the handshake itself.
- `stream/src/utils/codec.rs` for the framing layer.
