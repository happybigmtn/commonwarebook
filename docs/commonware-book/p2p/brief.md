# commonware-p2p Interactive Book Chapter - Brief

## 1. Module Purpose

The `commonware-p2p` crate provides authenticated, encrypted peer-to-peer networking for
distributed applications operating in adversarial environments. It has two distinct control planes:
**discovery** mode learns addresses by propagating signed peer knowledge across synchronized peer
sets, while **lookup** mode treats the application as the source of truth for
`(PublicKey, Address)` mappings and pushes those mappings directly into the tracker. Both modes
share the same transport machinery: encrypted stream handshakes, peer actors, router/spawner
plumbing, channelized application delivery, and connection admission control. A third,
ALPHA-quality **simulated** layer swaps out real I/O for a deterministic in-process network with
latency, loss, partitions, and optional bandwidth fairness.

---

## 2. Key Source Files

### `p2p/src/types.rs`
Defines `Ingress` and `Address`, which encode the chapter's most important addressing distinction:
what we dial is not always the same as what source IP we should accept from. `Symmetric` and
`Asymmetric` addresses, DNS ingress, and private-IP validation all start here.

### `p2p/src/authenticated/discovery/mod.rs`
The cleanest conceptual statement of discovery mode: peers maintain synchronized `u64`-indexed peer
sets, exchange bitvectors over those sets, and gossip signed `Info` records only when they have
useful knowledge to share.

### `p2p/src/authenticated/discovery/network.rs`
The assembly diagram for the five-actor discovery topology: tracker, router, spawner, listener, and
dialer. This file shows who owns which mailbox and how the system is wired, but not yet where the
interesting state transitions live.

### `p2p/src/authenticated/discovery/types.rs`
Defines the four wire `Payload` variants and the `Info<C>` trust boundary. `InfoVerifier` rejects
self-announcements, future timestamps beyond `synchrony_bound`, and wrong-namespace signatures.
The chapter should now pair this file with the tracker record logic so readers see that freshness is
enforced by both validation and update discipline.

### `p2p/src/authenticated/discovery/actors/tracker/directory.rs`
The discovery tracker's source of truth. `Directory` owns the per-peer `Record`s, the tracked peer
sets, and the blocked-peer timer queue. It derives the knowledge bitmaps from `Record::want(...)`,
not from an independent cache, and its `infos()` path performs important safety checks before
re-sharing peer info.

### `p2p/src/authenticated/discovery/actors/tracker/record.rs`
The real discovery state machine. `Record` combines address knowledge (`Unknown`, `Bootstrapper`,
`Discovered`, `Myself`), connection state (`Inert`, `Reserved`, `Active`), peer-set reference
counting, persistence, and reservation/dial timers. This is the right file to explain reservation
and cooldown as distributed admission control.

### `p2p/src/authenticated/lookup/actors/tracker/directory.rs`
Lookup mode's distinct control plane. `add_set()` returns `deleted_peers` and `changed_peers`,
`overwrite()` mutates addresses in place, `acceptable(peer, source_ip)` enforces egress-IP checks,
and `listenable()` computes which inbound source IPs are worth accepting. This is how the chapter
should explain that lookup is not just "discovery without gossip."

### `p2p/src/authenticated/lookup/actors/tracker/record.rs`
The stripped-down lookup record model: peers are either `Myself` or `Known(Address)`, but they
still use the same reservation, cooldown, and set-membership machinery as discovery. This contrast
is pedagogically useful.

### `p2p/src/authenticated/discovery/actors/peer/actor.rs`
The protocol core for one authenticated connection. The actor splits into sender and receiver
halves, sends greeting first, requires greeting first from the remote peer, rate-limits repeated
gossip messages, validates channel IDs before channel-labeled metrics, and drops application data
when the app-side queue is full so discovery traffic keeps moving.

### `p2p/src/authenticated/relay.rs` + `p2p/src/authenticated/mailbox.rs`
Explain the data-plane plumbing around actor communication: priority relay, bounded versus
unbounded mailboxes, and where the system chooses backpressure versus "never block this control
path."

### `p2p/src/utils/mux.rs`
The local subchannel demultiplexer. It prefixes a varint channel ID, allows routes to be
registered after startup, and uses `try_send` into each subchannel queue so one slow subchannel
does not create head-of-line blocking for all others.

### `p2p/src/utils/limited.rs`
The send-side quota wrapper. `LimitedSender` subscribes lazily to the current connected-peer set,
resolves `Recipients::All` against a live snapshot, applies keyed rate limits per recipient, and
returns retry-time feedback when everyone is over quota.

### `p2p/src/simulated/mod.rs`
The simulator's top-level contract: dynamic link changes, deterministic execution, in-order delivery
per link, optional bandwidth simulation, and API compatibility with the production `Manager` and
`AddressableManager` traits.

### `p2p/src/simulated/bandwidth.rs`
The simulator's under-covered substance. It models each transmission as a `Flow` and uses
progressive filling to allocate max-min fair bandwidth across sender egress and receiver ingress
constraints. `duration()` and `transfer()` preserve rational-valued progress across rescheduling.

### `p2p/src/authenticated/mod.rs`
Defines the shared trait surface for discovery and lookup: `Provider`, `Manager`,
`AddressableManager`, `Sender`, `Receiver`, `Recipients`, `Blocker`, and related channel traits.

---

## 3. Chapter Outline

1. **Framing: Two Networking Problems** - Discovery as knowledge propagation over peer sets; lookup
   as application-authoritative address management.
2. **Address Model** - `Ingress` versus `Address`, symmetric versus asymmetric routing, and NAT
   egress filtering.
3. **The Wire Protocol** - `Greeting`, `BitVec`, `Peers`, and `Data`, plus what `Info` signatures
   do and do not prove.
4. **Tracker State Machine** - `Directory`, `Record`, tracked peer sets, knowledge-bit derivation,
   reservation state, cooldown, blocking, and deletion rules.
5. **Actor Topology and Control Flow** - Five actors overall, then a code-substantive walkthrough of
   the peer actor's split sender/receiver loop and greeting-first discipline.
6. **Application Delivery Utilities** - Relay priority lanes, mailbox semantics, `Muxer`, and
   `LimitedSender`.
7. **Lookup Mode Internals** - Why lookup has a distinct control plane, how `add_set()` and
   `overwrite()` mutate authority, and why address changes imply reconnect.
8. **Simulated Network Internals** - Latency, jitter, loss, ordering, queueing, and fairness-aware
   bandwidth scheduling.
9. **Abuse and Failure Scenarios** - Stale gossip, future timestamps, invalid channels, slow
   applications, shared-IP poisoning, reconnect storms, and bounded blocking.

---

## 4. System Concepts to Explain at Graduate Depth

- **Gossip-based peer discovery with compact bitvectors** - A `1` bit means "I currently claim
  useful reachability knowledge for this peer." The bit is derived from tracker record state, not
  from the transport alone.
- **Tracker records as the real discovery state machine** - `Record` combines address knowledge,
  reservation state, set membership, persistence, and retry scheduling. Discovery converges because
  these states change in disciplined ways.
- **Reservation and cooldown as admission control** - Only one actor may own a peer reservation at a
  time, and retry windows are jittered to avoid synchronized reconnect storms.
- **Signed peer records and the `Info`/`InfoVerifier` trust model** - Signatures prove ownership of
  `(ingress, timestamp)` under the tracker namespace. The tracker then decides whether the info is
  newer, sharable, and worth re-gossiping.
- **Peer actor as protocol interpreter** - Greeting must come first, repeated gossip is rate-limited,
  invalid channel IDs are rejected early, and application backpressure is isolated so discovery
  traffic does not deadlock.
- **Lookup as application-authoritative address management** - The application owns address updates.
  `changed_peers` and `overwrite()` mean "reconnect under the new mapping," not "wait for gossip to
  catch up."
- **Local subchannel isolation and rate-checked broadcast** - `Muxer` prevents one slow subchannel
  from stalling the rest, and `LimitedSender` applies quotas per recipient with retry-time
  feedback.
- **Simulator fairness model** - Optional bandwidth limits induce a progressive-filling planner that
  enforces max-min fairness across sender egress and receiver ingress while preserving in-order
  delivery per link.
- **Bounded abuse impact** - The implementation does not eliminate all bad behavior; it bounds it.
  Stale updates do not overwrite fresher state, slow apps lose data instead of stalling gossip, and
  temporary blocks expire.

---

## 5. Interactive Visualizations to Build Later

1. **Tracker Record State Machine** - Show one peer moving through `Unknown -> Discovered ->
   Reserved -> Active -> Inert`, including dial failures, knowledge-bit changes, and block timers.
2. **Peer Actor Timeline** - Animate greeting exchange, first `BitVec`, `Peers` response, then
   ongoing data and keepalive flow. Highlight which events happen in the sender half versus the
   receiver half.
3. **Lookup Control Plane Diff** - Two views of the same network: discovery mode learning addresses
   through gossip versus lookup mode receiving `changed_peers` from the application and reconnecting.
4. **Mux and Backpressure Diagram** - One p2p channel splitting into subchannels, showing why a full
   subchannel queue drops locally instead of freezing unrelated traffic.
5. **Bandwidth Fairness Simulator** - Visualize active flows, shared ingress/egress bottlenecks, and
   progressive filling as rates freeze when resources saturate.
6. **Attack/Abuse Matrix Explorer** - Click a scenario such as stale gossip, invalid channel IDs, or
   shared-IP poisoning to see the relevant invariants, mitigations, and residual impact.

---

## 6. Claims-to-Verify Checklist

- [ ] `InfoVerifier` rejects self-announcements, future timestamps beyond `synchrony_bound`, and
  wrong-namespace signatures.
- [ ] `Record::update()` never overwrites discovery state with an equal or older timestamp.
- [ ] `Record::sharable()` only exposes discovered peer info while the record is `Active`.
- [ ] Reservation is single-owner: once a record is `Reserved`, concurrent dial/listen attempts for
  that peer fail until release.
- [ ] `release()` only attributes a dial failure when the failed ingress still matches the record's
  current discovered ingress.
- [ ] `add_set()` preserves old tracked peers long enough to bridge epoch transitions and only
  deletes records when they are unreferenced, non-persistent, and inert.
- [ ] The first inbound peer payload must be `Greeting`; duplicate greetings fail the peer.
- [ ] Invalid channel IDs are rejected before channel-labeled metrics are emitted.
- [ ] A full application receive queue drops `Data` but does not stall `BitVec`/`Peers` handling.
- [ ] `Muxer` isolates slow or dropped subchannels instead of causing head-of-line blocking.
- [ ] `LimitedSender` resolves `Recipients::All` against a peer snapshot and returns retry-time
  feedback when all recipients are over quota.
- [ ] In lookup mode, `changed_peers` and `overwrite()` surface address changes without requiring a
  new peer-set index.
- [ ] Lookup inbound acceptance rejects unexpected egress IPs unless `bypass_ip_check` is enabled.
- [ ] Simulated runs with the same deterministic seed and same link schedule produce identical
  delivery order.
- [ ] Simulated bandwidth allocation is max-min fair across active flows sharing sender egress and
  receiver ingress constraints.
- [ ] Blocking is temporary: reconnect attempts are rejected until `block_duration`, then become
  eligible again.
