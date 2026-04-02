# Chapter Brief: commonware-utils

## 1. Module Purpose

`commonware-utils` should be taught as the crate that gives repeated low-level
invariants one canonical home.

The chapter should resist the lazy framing of a "misc helpers" crate. The real
systems question is:

> which tiny shapes recur often enough across the monorepo that they should be
> named once, enforced once, and reused everywhere instead of being re-created
> in slightly different local forms?

The answer is selective:

- ordered committee-shaped collections,
- non-empty and non-zero wrappers,
- quorum policy,
- explicit coordination objects for acknowledgement and in-flight futures,
- concurrency limiters and upgrade-safe locking,
- environment-facing policy for time and networking,
- and the historical bitmap as a compact state machine for current-plus-history.

The governing metaphor should remain **a belt of small sharp tools**, but the
expanded chapter needs to make clear that some of those tools are wrappers and
some are genuine state machines.

---

## 2. Source Files That Matter Most

### `utils/src/lib.rs`
**Why it matters:** The crate map and stability split. It shows what this crate
considers part of the shared low-level vocabulary.

### `utils/src/ordered.rs`
**Why it matters:** The strongest chapter driver for canonical collection
meaning. `Set`, `Map`, `Participant`, and `Quorum` are where committee-shaped
data becomes a type instead of a loose `Vec`.

### `utils/src/vec.rs`
**Why it matters:** `NonEmptyVec` is the cleanest example of a tiny structural
guarantee being moved into the type system.

### `utils/src/acknowledgement.rs`
**Why it matters:** `Exact` is a compact but deep example of completion versus
cancellation being modeled explicitly rather than with comments or booleans.

### `utils/src/futures.rs`
**Why it matters:** `Pool`, `AbortablePool`, and `OptionFuture` show how the
crate gives recurring async-control-flow shapes one shared vocabulary.

### `utils/src/concurrency.rs`
**Why it matters:** `Limiter` and `KeyedLimiter` turn "bounded in flight" and
"at most one per key" into lifetime-backed contracts.

### `utils/src/sync/mod.rs`
**Why it matters:** This file is a miniature locking style guide, especially
around `UpgradableAsyncRwLock`.

### `utils/src/net.rs` and `utils/src/time.rs`
**Why they matter:** These show that even environment-facing policy benefits
from shared meaning: subnets, global-address classification, duration parsing,
jitter, and saturating time arithmetic.

### `utils/src/bitmap/historical/mod.rs`
**Why it matters:** The richest subsystem in the crate. This is where the
chapter can teach typestate, commit/abort/prune lifecycle, and snapshot-plus-
diff history.

### `utils/fuzz/fuzz_targets/*`
**Why they matter:** The fuzz surface reveals which boundaries the crate treats
as subtle enough to deserve randomized invariant checking.

---

## 3. Expanded Chapter Outline

```text
0. Opening apparatus
   - promise, crux, invariant, naive failure, reading map, assumptions

1. What problem does this solve?
   - repeated low-level invariants across the monorepo
   - why local helper drift is a real systems problem

2. Mental model
   - a belt of small sharp tools
   - wrappers versus mini-subsystems

3. Core ideas
   - the crate standardizes recurring shapes, not random helpers
   - ordered collections turn committee-like data into a type
   - tiny structural guarantees belong in types
   - coordination semantics are part of the contract
   - concurrency limits are protocol state
   - lock choice is policy, not accident
   - environment-facing helpers still encode policy
   - historical bitmap as a real state machine

4. How the system moves
   - canonical collection decode path
   - acknowledgement lifecycle
   - in-flight future pool lifecycle
   - reservation lifecycle
   - historical bitmap clean -> dirty -> commit/abort cycle
   - fuzz targets as maintenance evidence

5. What pressure it absorbs
   - duplication, validation, shutdown, canonicalization, concurrency, history

6. Failure modes and limits
   - strictness by design
   - narrow scope
   - support tools rather than domain logic

7. How to read the source / glossary
```

---

## 4. System Concepts To Explain At Graduate Depth

1. **Canonicalization should happen at the boundary.** `Set` decoding is a
   strong example: the receiver rejects non-canonical order instead of fixing
   it silently.

2. **Committee data is more than a `Vec`.** Ordered participant sets plus
   `Faults` and `Quorum` create a shared language for threshold policy.

3. **Completion versus cancellation deserves a real object.** `Exact` is a
   compact example of a mini protocol, not just a helper.

4. **Async control flow has reusable shapes.** Pools, abortable pools, and
   option futures are all ways of making "what is in flight right now?" a
   stable abstraction.

5. **Backpressure and uniqueness can be expressed as lifetimes.** The limiter
   types make capacity and exclusivity explicit without requiring manual
   release calls.

6. **Locking strategy is part of correctness.** `UpgradableAsyncRwLock`
   exists to preserve a specific upgrade invariant, not to be fancy.

7. **Historical bitmap is the chapter's proof that utils can still contain
   real mechanisms.** It is a typestate snapshot/diff state machine, not a
   wrapper.

8. **Fuzzing matters even for tiny helpers.** The crate's fuzz surface shows
   that small boundaries can still be correctness-critical.

---

## 5. Interactive Visualizations To Build Later

1. **Tool-belt plate**  
   Show wrappers, coordination tools, and the historical bitmap as different
   classes of recurring infrastructure.

2. **Canonical collection plate**  
   Compare raw `Vec` input with `Set` decode and the resulting stable committee
   semantics.

3. **Acknowledgement plate**  
   Show `Exact` handles being cloned, acknowledged, or dropped, and how the
   waiter resolves in each case.

4. **Future-pool plate**  
   Show tasks entering a pool, resolving, and being aborted individually.

5. **Historical bitmap plate**  
   Show clean state, dirty mutations, commit, abort, and prune.

---

## 6. Claims-To-Verify Checklist

- [ ] The chapter makes clear that `commonware-utils` is a consistency layer,
      not a miscellaneous helper bag.
- [ ] `Set`/`Quorum`/`Faults` are explained as canonical committee policy, not
      just collection wrappers.
- [ ] `NonEmptyVec` and `NonZeroDuration` are used to illustrate moving
      repeated preconditions into types.
- [ ] `Exact`, future pools, and limiters are taught as coordination contracts.
- [ ] `UpgradableAsyncRwLock` is explained in terms of the writer-interleaving
      invariant it protects.
- [ ] The chapter treats `bitmap::historical` as a genuine state machine with
      typestate and commit/abort lifecycle.
- [ ] The fuzz targets are referenced as evidence that these small helpers sit
      on correctness-critical boundaries.
