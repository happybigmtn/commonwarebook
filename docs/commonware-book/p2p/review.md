# Review: commonware-p2p Book Chapter

## What is solid

- **Actor topology**: The five-actor model (tracker, router, spawner, listener, dialer) is accurate and the description of their roles is correct. `network.rs` confirms this exact topology.
- **Payload variants and prefix bytes**: `DATA_PREFIX=0`, `GREETING_PREFIX=1`, `BIT_VEC_PREFIX=2`, `PEERS_PREFIX=3` match the chapter's wire format explorer exactly.
- **Namespace suffix construction**: The chapter correctly identifies `_TRACKER` and `_STREAM` as suffixes, not standalone namespaces. The source uses `union(&cfg.namespace, TRACKER_SUFFIX)` which produces the full namespace from user input.
- **Bitvector semantics**: "1 means knowledge; 0 means unknown or dial failed after `dial_fail_limit`" matches `discovery/mod.rs`.
- **`InfoVerifier` rejection classes**: The three checks (self-announcement, future timestamp, wrong-namespace signature) are confirmed in `types.rs` lines 371-386.
- **`SocketManager` silently discards addresses**: Confirmed in `simulated/ingress.rs` line 354-355: `// Ignore all addresses (simulated network doesn't use them)`.
- **`block!` macro exists**: Confirmed in `lib.rs` line 317. The chapter's description of its purpose (tracing + block combo) is accurate, just the location claim is slightly imprecise (it's in `p2p/src/lib.rs`, not the `authenticated` module).
- **Private IP policy**: Correctly described for both `Ingress::Socket` and `Ingress::Dns` (resolution happens then filtered).
- **Tracker uses `UnboundedMailbox`**: Confirmed in `network.rs` line 40.
- **`Info` `timestamp` is epoch milliseconds**: Confirmed in `types.rs` line 222 comment and `sign` method encoding.

---

## What still needs deeper verification

### 1. CRITICAL — Relay backpressure semantics are inverted

**Chapter claim (Section 3.4 + Section 4.1 table + visuals)**: "If `low` is full, a low-priority sender **blocks** (backpressure) rather than silently dropping."

**Actual behavior** (`relay.rs` line 19):
```rust
pub fn send(&self, message: T, priority: bool) -> Result<(), TrySendError<T>> {
    let sender = if priority { &self.high } else { &self.low };
    sender.try_send(message)  // <-- NON-BLOCKING
}
```

`try_send` is non-blocking — it returns an error immediately if the channel is full. The sender does **not** block. The error must be handled by the caller.

The chapter's claim that "a low-priority sender blocks when the low lane is full" describes **blocking** semantics, but the implementation uses **non-blocking** semantics. The visuals (priority-relay scene "low_queue": "clock icon" = blocked) also get this wrong.

**What actually happens**: When `relay.send()` returns `Err(TrySendError::Full(_))` for a low-priority message, the **router actor** must handle this — it may drop the message and increment a metric, or handle it some other way. The backpressure is at the **caller of `relay.send()`**, not inside `relay.send()` itself.

**Fix required**:
- Chapter: Rewrite Section 3.4 to say the relay returns an error on full, and describe how the router handles this error (drops + metric increment).
- Section 4.1 table: Change "Backpressure" from "Blocks sender when full" to "Returns error; caller handles via drop + metric."
- Visuals: The "blocked" state with clock icon on the relay input is wrong — the send returns an error immediately; the sender does not sit inside the relay.

### 2. CRITICAL — `Info` signature coverage is misstated

**Chapter claim (Section 3.3 + mental model)**: `Info` signs `(ingress, timestamp, public_key)` — all three fields.

**Actual behavior** (`types.rs` line 258-259):
```rust
let signature = signer.sign(namespace, &(ingress.clone(), timestamp).encode());
```

Only `(ingress, timestamp)` is signed. The `public_key` field is **not** covered by the signature. It is included in the `Info` struct and validated separately.

This matters because the chapter says: "The `Info` structure signs `(ingress, timestamp, public_key)` so peers cannot forge address announcements from others." The implication that the `public_key` is cryptographically bound to the `Info` is incorrect — the `public_key` is the identifier used to look up the key for signature verification, not part of what is signed.

**Fix required**: Chapter should say `Info` signs `(ingress, timestamp)`. The `public_key` field is included in the struct for identification purposes but is not covered by the signature.

### 3. NEEDS VERIFICATION — `InfoVerifier` timestamp direction

**Chapter claim (Section 3.3)**: "reject if `info.timestamp > current_epoch + synchrony_bound`"

**Actual code** (`types.rs` lines 377-379):
```rust
if Duration::from_millis(info.timestamp)
    > clock.current().epoch().saturating_add(self.synchrony_bound)
```

This compares `Duration::from_millis(info.timestamp)` (a `Duration` constructed from the raw u64 timestamp) against `Instant + Duration`. This is type-mismatched comparison — `Duration` and `Instant` cannot be directly compared.

The `clock.current().epoch()` returns an `Instant` (based on `SystemTime::now()`), and adding a `Duration` to it produces another `Instant`. The comparison `Duration > Instant` would not compile in safe Rust...

Wait — looking more carefully: `Duration::from_millis(info.timestamp)` creates a `Duration`. But then `clock.current().epoch()` returns what? If it returns a `u64` epoch value in milliseconds (matching the timestamp's unit), then the comparison makes sense: `Duration` wrapping a u64 vs another u64. But `epoch()` returning a `Duration` is unusual — typically epochs are raw `u64` values, not `Duration` types.

The semantic intent matches: reject if timestamp is too far in the future. The direction (>`current + bound`) is correct. But the type description in the chapter ("epoch milliseconds" vs "current epoch") should be verified against the actual `Clock` trait.

### 4. NEEDS VERIFICATION — `Asymmetric` egress IP filtering in listener

**Chapter claim (Section 3.1 + Section 4.3 + NAT traversal scene)**: "a connection from an unexpected egress IP is rejected even if the dialed ingress was correct"

**Actual code**: The `listener.rs` (lines 173-189) performs private IP filtering and rate limiting but does NOT appear to validate egress IP against `Address::Asymmetric { egress }` at that level.

The check `tracker.listen(peer.clone())` is called after the listener extracts the peer, and the tracker likely performs the egress check. But I did not verify the tracker's `listen` method.

The brief's checklist marks this as needing verification: "Asymmetric address filtering: a connection from an unexpected egress IP is rejected even if the dialed ingress is correct."

### 5. `log₂(N)` gossip convergence is stated as fact but unverified

The chapter states: "With N fully-connected honest peers and zero failures, all bits converge to 1 within ⌈log₂(N)⌉ gossip rounds."

The source has no test or proof of this property. The `discovery/mod.rs` doc comment describes the mechanism but does not claim this bound. The brief's checklist also flags this as needing verification.

This is theoretically correct for epidemic broadcast with full knowledge, but stating it as fact in the chapter without referencing the source is potentially misleading.

---

## Recommended next workflow

1. **Fix the Relay semantics** (Issue #1 above) in both `chapter.md` and `visuals.json` before anything else — it is a foundational behavioral claim that affects how readers understand the entire system.

2. **Clarify `Info` signature coverage** (Issue #2) — a subtle but important cryptographic distinction. The `public_key` is **not** signed, which changes the trust model.

3. **Verify `Asymmetric` egress filtering** in the tracker (Issue #4) by reading `discovery/actors/tracker/actor.rs`. If the chapter's description is correct, cite the specific code path. If not, update the chapter.

4. **Verify `InfoVerifier` timestamp comparison** (Issue #3) — confirm whether `clock.current().epoch()` returns a `u64` or a `Duration`-like type, and whether the comparison `Duration::from_millis(info.timestamp) > clock.current().epoch().saturating_add(...)` is actually comparing compatible types.

5. **Weaken or qualify the `log₂(N)` claim** (Issue #5) — either add "in theory" or remove the specific bound claim, and reference the mechanism description in `discovery/mod.rs` instead.

6. **Then update visuals.json** to match any chapter corrections, particularly the priority-relay backpressure visualization.

---

## Page QA — Post-Generation Review (2026-03-18)

### Issues found and fixed

1. **Missing TOC entry 3.6** — The `Shared Trait Surface` section (3.6) was absent from both the mobile inline TOC and the desktop rail TOC. Added to both.

2. **Section 5 backpressure column imprecise** — The actor table in Section 5 said "Blocks sender when full" for router and spawner without distinguishing Mailbox-level blocking from relay-level `try_send` drop semantics. Updated router row to: "App sender blocks at Mailbox when full; relay drops low-priority via `try_send`". Updated spawner row to clarify listener/dialer stall behavior.

3. **Section 7 reading guide incomplete** — Missing `mailbox.rs`, `listener.rs`, `dialer.rs`, and the expanded descriptions for tracker and router. Reading order expanded from 8 to 12 items with fuller per-file descriptions. Spawner and dialer, previously omitted, now included.

4. **No source file citations on figure plates** — `visuals.json` specifies `source_files` for each visualization but these were not surfaced in the HTML. Added a `plate-source` line (mono, faint ink) before the caption of all six plates. Key files now linked per plate.

5. **Missing InfoVerifier timestamp verification callout** — Section 3.3 listed the three InfoVerifier checks but had no flag for the type-level verification gap (Issue #3 in review). Added a `callout-src` with label "Verification" noting the direction is confirmed correct but the `Clock` type comparison warrants further verification.

### Verified correct (no changes needed)

- Both critical corrections from review.md (Issues #1 and #2) were already propagated to `chapter.md` and correctly carried into the HTML: relay non-blocking `try_send` semantics and Info `(ingress, timestamp)` signature coverage.
- All six `visuals.json` visualizations have corresponding figure plates with controls and scene scaffolds.
- BOOK-DESIGN.md cues satisfied: serif-plus-mono hierarchy, paper palette, centered editorial header, slim sticky reading bar, substantial figure plates with captions, chapter-progression footer navigation.
- The `callout-fix` correction boxes for both relay semantics and Info signature coverage are present and prominent.
- `chapter.md` Section 5 already qualifies the `log₂(N)` bound as theoretical (Issue #5 from review.md), and the HTML correctly reflects this.

