# Chapter Brief: commonware-sync

## 1. Module Purpose

`commonware-sync` should be taught as a lecture about **proof-backed
reconciliation against a moving target**.

The surface story is simple: a client wants to stay aligned with a server's
database. The deeper story is that the server keeps moving while the client is
still catching up, so synchronization becomes a live systems problem rather than
a copy operation.

The chapter should keep four ideas tied together from the start:

- **targeting**: the client needs a concrete root and range to chase;
- **proof**: the target only matters if the transition to it is justified;
- **correlation**: request IDs and typed replies keep wire disorder from
  becoming semantic disorder;
- **interpretation**: `any`, `current`, and `immutable` share one sync loop
  without meaning the same thing internally.

The chapter's governing image is a **surveyor chasing a boundary that keeps
moving**:

- the server keeps redrawing the line,
- the target names the current line,
- the proof shows how the old line connects to the new one,
- the client advances only after checking the segment it is about to trust.

That framing is stronger than "client/server example." It turns the example
into a lecture about how proof-backed state transfer survives motion.

---

## 2. Source Files That Matter Most

### `examples/sync/src/databases/mod.rs`
**Why it matters:** Defines `Syncable`, the abstraction boundary that makes
three different database flavors legible to one reconciliation loop.

### `examples/sync/src/net/wire.rs`
**Why it matters:** Shows that the protocol really asks only two questions:
what target should I chase, and what proof-backed operation segment gets me
closer to it.

### `examples/sync/src/net/request_id.rs`
**Why it matters:** Tiny file, big lesson. It gives the request-response
conversation a memory so late or wrong-shaped replies can be rejected cleanly.

### `examples/sync/src/net/io.rs`
**Why it matters:** Teaches the cancellation-safe I/O pattern. `recv_frame`
is isolated in a dedicated task so partially read frames are never dropped by
an async select.

### `examples/sync/src/net/resolver.rs`
**Why it matters:** The narrow trust boundary on the client side. It turns
typed wire replies into sync targets and fetch results without becoming a
second sync algorithm.

### `examples/sync/src/bin/server.rs`
**Why it matters:** The moving source of truth. It serves targets, historical
proofs, optional pinned nodes, and keeps adding new operations while clients
are still syncing.

### `examples/sync/src/bin/client.rs`
**Why it matters:** The repeated reconciliation loop. It asks for a target,
spawns a background target-update task, runs sync with bounded fetch/apply
work, then starts the process again.

### `examples/sync/src/databases/current.rs`
**Why it matters:** Best place to teach the subtle distinction between the
sync root and the richer canonical root. The chapter should explain why
`current` syncs to `ops_root()` and reconstructs the bitmap/grafted state
afterward.

### `examples/sync/src/databases/any.rs` and `immutable.rs`
**Why they matter:** They provide the clean comparison cases: direct log-root
sync in `any`, and retained-operation semantics in `immutable`.

---

## 3. Chapter Outline

```text
0. Opening apparatus
   - promise, crux, primary invariant, naive failure, reading map, assumptions

1. What problem does this solve?
   - why one-shot copying fails
   - synchronization as proof-backed reconciliation

2. Mental model
   - the surveyor and the moving boundary
   - target, proof, and terrain

3. Core ideas
   - `Syncable` as the shared contract
   - the wire protocol's two real questions
   - request IDs as conversation memory
   - resolver as narrow trust boundary
   - three database meanings, one reconciliation surface

4. How the system moves
   - server manufacturing new targets
   - root plus range as the actual target
   - bounded proof ladder in `GetOperations`
   - client's two-loop structure
   - cancellation-safe I/O split
   - re-anchoring when the target moves

5. Database semantics and why they matter
   - `any` as baseline
   - `current` as ops-root-first sync with later canonical reconstruction
   - `immutable` as a different meaning of activity

6. Pressure and tradeoffs
   - continuous writes
   - verification pressure
   - reconnection pressure
   - bounded work
   - transport disorder
   - async cancellation hazards

7. Failure modes and limits
   - unauthenticated server
   - server-sourced target
   - rate limiting omitted
   - target trust still comes from outside the example

8. How to read the source / glossary
```

---

## 4. System Concepts to Explain at Graduate Depth

1. **A sync target is more than a digest.** The range matters because the
   client is chasing a live interval of relevant history, not only a head root.

2. **The wire protocol is deliberately narrow.** Two core questions are enough
   to build the whole mechanism if the proof surface is well chosen.

3. **Request correlation is part of correctness.** A late or wrong-shaped
   reply should be rejected as a protocol error, not treated as "close enough."

4. **Cancellation safety is a systems property, not a runtime detail.** The
   split recv loop exists because abandoning a partial frame read can corrupt
   the stream.

5. **`current` teaches root stratification.** The right sync root is not
   always the richest application root. Sometimes the protocol should target a
   lower-level operations root and reconstruct richer state afterward.

6. **Pinned nodes are proof-shape artifacts, not miscellaneous extra data.**
   They exist because the sync engine sometimes needs additional MMR anchors to
   verify a specific historical segment.

7. **Re-anchoring is the real success case.** The example is strongest when the
   client notices that the target moved and keeps reconciling anyway.

---

## 5. Interactive Visualizations to Build Later

1. **Moving target plate**  
   Show the server root advancing while the client keeps re-anchoring to the
   newest proof-backed target.

2. **Wire protocol plate**  
   Show the two main request types and how `request_id` ties each reply back to
   one logical question.

3. **Cancellation-safe I/O timeline**  
   Contrast the dedicated recv task with the main request/response loop so the
   reader sees why `recv_frame` is isolated.

4. **Three database views plate**  
   Compare `any`, `current`, and `immutable` as different interpretations of
   the same sync contract.

5. **Ops-root versus canonical-root plate**  
   Show why `current` syncs the operations history first and rebuilds richer
   state later.

---

## 6. Claims-to-Verify Checklist

- [ ] The chapter explains sync as proof-backed reconciliation, not database copying.
- [ ] The chapter names the two real wire questions and the role of `request_id`.
- [ ] The chapter explains why the I/O loop is split to keep frame reads
      cancellation-safe.
- [ ] The chapter explains `include_pinned_nodes` and why the sync engine may
      need extra anchors.
- [ ] The chapter distinguishes `any`, `current`, and `immutable` by semantics,
      not just by type names.
- [ ] The chapter explains why `current` targets `ops_root()` instead of the
      richer canonical root.
- [ ] The chapter keeps target, proof, and re-anchoring central throughout.
- [ ] The chapter stays focused on the mechanism rather than becoming a CLI guide.
