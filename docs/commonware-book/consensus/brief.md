# commonware-consensus — Interactive Book Chapter Brief

## 1. Module Purpose

`commonware-consensus` orders opaque messages in a Byzantine environment. It provides three layered primitives: **(1)** `simplex` — a three-phase (notarize → nullify → finalize) Byzantine consensus protocol with leader rotation and threshold signature support; **(2)** `aggregation` — recoverable quorum certificates over an externally synchronized sequencer of items; and **(3)** `ordered_broadcast` — reliable, ordered delivery across reconfigurable sequencer/validator sets with chaining and journaling. A fourth component, `marshal`, sits above simplex to deliver finalized blocks in total order, supporting both standard and erasure-coded (coding) modes.

Stability: `simplex` and core traits are **BETA**; `aggregation`, `ordered_broadcast`, `marshal` are **ALPHA**.

---

## 2. Key Source Files

### `consensus/src/lib.rs`
Defines the core trait hierarchy: `Automaton` (propose/verify payloads), `CertifiableAutomaton` (adds certify phase for deferred verification), `Relay` (broadcast payloads), `Reporter` (report activity), and `Monitor` (subscribe to progress). All consensus implementations plug into these interfaces.

### `consensus/src/types.rs`
Defines `Epoch`, `View`, `Height`, `Round` type-safe identifiers. `Epoch` marks reconfiguration boundaries; `View` is a per-epoch round counter; `Round` = `(Epoch, View)`. Arithmetic is overflow-safe (saturating or Option-based).

### `consensus/src/simplex/types.rs`
Defines `Subject` enum (`Notarize`, `Nullify`, `Finalize`) — the three vote subjects. `VoteTracker<S, D>` tracks per-signer votes per phase. `Context<D, P>` carries round/leader/parent info for proposal verification.

### `consensus/src/simplex/scheme/mod.rs`
Pluggable signing scheme layer. Defines attributable schemes (ed25519, bls12381_multisig, secp256r1) where signatures are usable as fault evidence, vs. non-attributable threshold schemes (bls12381_threshold) where partial signatures can be forged. Each scheme derives domain-separated namespaces for notarize/nullify/finalize via `Namespace`.

### `consensus/src/simplex/elector.rs`
Leader election strategies. `RoundRobin` rotates deterministically; `Random` uses threshold VRF seed signatures for unpredictable leader selection (falls back to round-robin for view 1). Both implement `Elector` trait with deterministic `elect()`.

### `consensus/src/simplex/actors/voter/actor.rs`
The simplex voter state machine. Receives proposals, gates votes on parent nullifications (to prevent fork-safe skipping), manages three-phase voting, timeout/view-change handling, and certificate assembly. Coordinates with `batcher` (payload construction) and `resolver` (certificate exchange).

### `consensus/src/ordered_broadcast/mod.rs`
Provides reliable broadcast from sequencers to validators. Sequencers produce `node` chains (each node = chunk + cert over previous). Validators sign chunks to form quorum certificates. Epoch-based reconfiguration. Pluggable scheme (ed25519, secp256r1, bls12381 variants).

### `consensus/src/ordered_broadcast/types.rs`
`Node`, `Chunk`, `Certificate`, `Ack` types. `TipAck` combines a validator's ack with their tip (lowest unconfirmed height). `Activity` journals events for crash recovery.

### `consensus/src/aggregation/mod.rs`
Recovers quorum certificates over an externally-provided ordered sequence (`Item` with `Height` + `Digest`). `Ack` is a validator's vote; `Certificate` is assembled from acks via the signing scheme. `Engine` drives the aggregation state machine.

### `consensus/src/aggregation/types.rs`
`Item<D>` (height + digest), `Ack<S, D>`, `TipAck<S, D>`, `Certificate<S, D>`, `Activity<S, D>`. Namespace derivation uses `ACK_SUFFIX` for domain separation.

### `consensus/src/marshal/mod.rs`
Ordered delivery of finalized blocks on top of simplex. `core::Actor` coordinates: receives uncertified blocks from broadcast, notarizations/finalizations from consensus, reconstructs total order, provides backfill for gaps. Works in standard mode (buffered broadcast) or coding mode (erasure-coded shards).

---

## 3. Chapter Outline

```
1. Introduction: Why Byzantine Consensus
   - Safety vs liveness tradeoff in distributed systems
   - Opaque payloads: separating consensus from application logic
   - The simplex thesis: three phases instead of two

2. Core Data Types and Identifiers
   - Epoch, View, Height, Round: type-safe, overflow-safe arithmetic
   - Context: round/leader/parent metadata for proposals
   - Subject: Notarize / Nullify / Finalize as domain-separated vote targets

3. The Simplex Consensus Protocol
   3a. Leader Election
       - RoundRobin: deterministic rotation with optional shuffle
       - Random: VRF-based randomness from threshold certificates
   3b. Three-Phase Voting
       - Notarize: leader proposes, validators vote on validity
       - Nullify: validators vote to skip a round (parent continuity required)
       - Finalize: validators vote to commit (certified blocks only)
   3c. VoteTracker and AttributableMap
   3d. Certificate Assembly and Domain Separation

4. Signing Schemes and Fault Attribution
   - Attributable schemes (ed25519, bls12381_multisig, secp256r1)
   - Non-attributable threshold schemes (bls12381_threshold)
   - VRF variant for randomness and leader election
   - Namespace derivation for cross-protocol attack prevention

5. Aggregation: Quorum Certificates Over External Sequences
   - Item / Ack / Certificate model
   - Plugging in different signing schemes
   - Engine state machine and tip advancement

6. Ordered Broadcast: Sequencer-Based Reliable Delivery
   - Sequencer chains and validator quorum certificates
   - Epoch-based reconfiguration
   - Crash recovery via journaling

7. Marshal: Total Order Delivery
   - Actor architecture and component wiring
   - Standard vs coding (erasure-coded) modes
   - Backfill mechanism for network gaps
   - Starting height / floor for state sync

8. Safety and Liveness Invariants
   - Parent nullification requirement (fork safety)
   - Certification before finalization (deferred verification)
   - Single-shot verification/certification (no retry loops)
   - Determinism requirements for elector and certify
```

---

## 4. System Concepts (Graduate-Level Depth)

### Byzantine Fault Tolerance Thresholds
`commonware-consensus` uses `N3f1` quorum (>⅔ of participants) throughout. This allows ⅓ Byzantine tolerance for both safety and liveness. Tradeoff: with ⅓ Byzantine actors, the network can stalemate (no progress) but cannot commit conflicting values.

### Safety vs Liveness Separation
Simplex separates the two concerns: **safety** (no two honest nodes finalize different blocks at same height) is guaranteed by the notarize→finalize chain and parent nullification requirement. **Liveness** (eventual progress) depends on eventual leader election and timeout/view-change on stagnant views.

### Actor Boundary and Message Passing
All consensus logic runs through `Actor` types (`voter::actor.rs`, `batcher::actor.rs`, `resolver::actor.rs`) communicating via typed channels. The deterministic runtime (`runtime/src/deterministic.rs`) enables reproducible testing of concurrent message flows.

### Threshold Signatures and Non-Attribution
With BLS threshold signatures, any `t` partial signatures can be combined to forge a signature for any other participant. This means **evidence cannot be exported** to third parties — useful for liveness proofs locally, but not for惩罚. Attributable schemes (ed25519) preserve signer identity in each signature.

### Deferred Verification / Certification
`CertifiableAutomaton::certify` allows an application to delay finalization until custom criteria are met (e.g., erasure code reconstruction). This decouples consensus finalization from application-level data availability guarantees.

### Domain Separation in Namespaces
Every vote subject (`Notarize`, `Nullify`, `Finalize`) and each scheme's operation uses a distinct namespace suffix (e.g., `_NOTARIZE`, `_NULLIFY`, `_FINALIZE`). This prevents cross-protocol signature reuse: a signature made under the `notarize` namespace cannot be replayed as a `finalize` signature.

### Reconfiguration via Epochs
`Epoch` marks boundaries where the validator set changes. Views advance within an epoch. Round transitions carry a certificate from the previous view, enabling epoch-scoped randomness derivation and continuity.

---

## 5. Interactive Visualizations

### V1: Simplex Three-Phase State Machine
**What**: Animated finite state machine showing transitions: `Propose → Notarize → Nullify → Finalize`. Users select a scenario: (a) normal path with leader proposal and quorum; (b) leader failure with nullify votes and timeout; (c) conflicting proposals triggering view change.
**Why**: Makes the phase gating concrete. Shows exactly which votes are needed at each step and when a round commits or times out.

### V2: Leader Election Comparer
**What**: Side-by-side visualization of `RoundRobin` vs `Random` elector behavior over 50 rounds. Shows leader indices, VRF seed derivation chain for Random, and how certificates feed into the next leader selection.
**Why**: Leader election is subtle — Random's VRF dependency on prior certificates means view 1 must fall back to round-robin. Visualization clarifies this dependency.

### V3: VoteTracker Live View
**What**: Real-time accumulation of `Notarize`, `Nullify`, `Finalize` votes as a bar chart per participant. Shows quorum threshold line, color-codes attributable vs non-attributable schemes.
**Why**: Students often confuse "quorum reached" with "all votes collected." The threshold line makes the N3f1 >⅔ requirement visual.

### V4: Ordered Broadcast Chains
**What**: Scrollable sequencer chain (nodes = chunks + certs) with validator signature collection. Shows how `TipAck` carries both a vote and the validator's tip height. Simulates epoch transition with validator set change.
**Why**: The chaining mechanism is the key insight: each chunk certifies the previous, so an honest sequencer's misbehavior is detectable and attributable.

### V5: Marshal Block Ordering
**What**: Timeline of blocks flowing from broadcast → simplex (notarizations/finalizations) → marshal actor → delivered to application. Shows backfill triggers when gaps appear, and how coding mode (erasure shards) changes the pipeline.
**Why**: Marshal is the bridge between consensus and application. Visualization shows where delays, gaps, and reorgs can occur and how the system recovers.

---

## 6. Claims-to-Verify Checklist

- [ ] `Notarize` vote requires proposal validity via `Automaton::verify`
- [ ] `Finalize` vote requires prior `Notarize` certificate (no orphaned finalization)
- [ ] Parent nullification is enforced before voting on any proposal (fork safety)
- [ ] `certify` decision is deterministic across all honest participants
- [ ] Leader election is deterministic for a given elector configuration and certificate
- [ ] Vote namespaces are domain-separated (`_NOTARIZE`, `_NULLIFY`, `_FINALIZE`)
- [ ] Threshold signatures are non-attributable (evidence cannot be exported)
- [ ] `Aggregation` certificate requires quorum (>⅔) via `N3f1`
- [ ] `ordered_broadcast` nodes form a linked chain via parent certificates
- [ ] `Marshal` delivers blocks in monotonically increasing height (no gaps reported)
- [ ] All public items in BETA stability are annotated with `#[stability(BETA)]`
- [ ] `simplex` actors communicate via typed channels, not shared mutable state
- [ ] Crash recovery is journaling-based: events replayed on restart
