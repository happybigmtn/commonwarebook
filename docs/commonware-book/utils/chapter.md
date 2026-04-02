# commonware-utils

*Small, sharp tools for canonical shapes, coordination lifecycles, and
replayable state.*

---

## Opening Apparatus

**Promise.** This chapter shows how `commonware-utils` keeps recurring
invariants in one canonical place instead of letting every crate rediscover
them locally.

**Crux.** The crate is not a junk drawer. It is the place where Commonware
names small but important facts:

- what a committee set looks like,
- what it means for a value to be non-empty,
- how completion and cancellation should behave,
- how bounded concurrency should unwind,
- and how a mutable bitmap can keep history without cloning itself on every
  commit.

**Primary invariant.** Once a recurring shape gets a trusted home, the rest of
the workspace should talk about that shape directly instead of re-encoding it
in slightly different helpers.

**Naive failure.** The easy mistake is to say, "this helper is only ten lines,
I will just write it here." Enough of those decisions and the workspace starts
to disagree with itself:

- one crate sorts and deduplicates,
- another preserves insertion order,
- another forgets to reject emptiness,
- another invents its own cancellation rule.

**Reading map.**

- `utils/src/ordered.rs` explains canonical collections.
- `utils/src/acknowledgement.rs`, `futures.rs`, `concurrency.rs`, and
  `sync/mod.rs` explain lifecycle and coordination.
- `utils/src/bitmap/historical/` is the richest state machine in the crate.
- `utils/src/vec.rs` shows how a small structural promise changes downstream
  code.

**Assumption ledger.**

- The reader is comfortable with ordinary Rust collections and async control
  flow.
- The chapter is about cross-cutting infrastructure, not domain logic.
- The goal is not to catalog every helper. It is to explain the few shapes
  that matter most.

## Background

Systems code keeps running into the same small facts:

- a collection should really be sorted and deduplicated,
- a vector should not be empty if callers are going to ask for its first item,
- a task should count as complete only when every participant has
  acknowledged it,
- a limit should be enforced once instead of rechecked everywhere,
- and a stateful bitmap should be able to remember history without cloning the
  whole thing every time it changes.

Those are not "just helpers." They are shared assumptions. If the assumptions
live only in comments and call-site checks, they drift. One caller handles an
edge case one way, another caller handles it differently, and the workspace
starts to lose a single shared meaning.

The tradeoff is that the code gets more explicit. Callers may need a
constructor, a conversion, or a small amount of ceremony before they get the
value they want. That is usually the right price to pay. Up-front structure is
cheaper than repeated defensive checks everywhere else.

## 1. What Problem Does This Solve?

Across the monorepo, the same questions keep returning in different clothes:

- How do we say a committee is canonical rather than merely stored in a `Vec`?
- How do we guarantee a collection is non-empty so callers stop wrapping every
  access in `Option`?
- How do we distinguish completion from cancellation?
- How do we keep a fixed number of tasks in flight without inventing another
  ad hoc counter?
- How do we retain historical bitmap state without cloning the full bitmap on
  every commit?

`commonware-utils` exists to answer those questions once.

The crate is a consistency layer. It turns recurring tiny invariants into
named, reusable contracts.

## 2. Mental Model

The cleanest mental model is a belt of small sharp tools. That image matters
because a belt is organized around recurring work, not taxonomy. You do not
carry every possible helper. You carry the few tools that solve the same class
of problem every time it appears.

That is how this crate behaves:

- `ordered::Set` gives the workspace a canonical collection shape.
- `Participant` and `Faults` let committee math stay typed instead of ad hoc.
- `NonEmptyVec` makes a tiny structural promise that downstream code can rely
  on.
- `Exact`, `Pool`, `AbortablePool`, `Limiter`, `KeyedLimiter`, and
  `UpgradableAsyncRwLock` give lifecycle and coordination a common vocabulary.
- `bitmap::historical` is the richest tool on the belt: a snapshot-plus-diff
  state machine with explicit commit, abort, and prune boundaries.

The important part is not that these tools are fancy. The important part is
that they let the rest of the monorepo stop improvising the same semantics.

## 3. The Core Ideas

### 3.1 Canonical Collections Are a Type, Not a Convention

`utils/src/ordered.rs` is the clearest example of what this crate means by a
canonical collection.

`Set<T>` is not just a wrapper around `Vec<T>`. It promises:

- sorted order,
- uniqueness,
- stable indexing,
- and binary-search lookup by value.

That means the collection has one agreed shape. It is not "whatever order was
convenient locally."

The constructors make the policy visible:

- `from_iter_dedup` is tolerant and silently removes duplicates,
- `TryFromIterator` is strict and returns an error when duplicates appear,
- codec decoding is stricter still and rejects any encoded set whose items are
  not already sorted and unique.

That last detail matters. The decoder does not sort for the caller. The sender
must already have emitted the canonical form. Canonicalization happens at the
boundary, not lazily after the fact.

`Participant` and `Faults` connect that canonical set back to committee math.
`Participant` gives a stable, codec-friendly committee index. The `Quorum`
extension trait turns a `Set` into explicit threshold math. The path from
"these keys form a committee" to "this committee tolerates `f` faults and
requires quorum `q`" stays typed and shared.

### 3.2 Structural Promises Belong in Types

`NonEmptyVec` in `utils/src/vec.rs` is a smaller example with the same idea.

Once a value is a `NonEmptyVec<T>`, callers may:

- ask for `first()` and `last()` without `Option`,
- preserve non-emptiness across `map`, `resize`, and `into_vec`,
- and rely on mutation helpers that will not quietly leave the structure
  empty.

The important move is not convenience. It is removing a whole category of
local "this should probably never be empty" reasoning from downstream code.

This is one of the crate's recurring design moves: if the same precondition
would otherwise appear in many call sites, make it part of the value's
identity.

### 3.3 Lifecycle and Coordination Objects Make Control Flow Explicit

Several of the crate's most useful helpers are about lifecycle rather than raw
data shape.

`Exact` in `acknowledgement.rs` is a tiny protocol for completion. It creates a
handle plus a waiter, counts clones as additional required acknowledgements,
and resolves only when every clone acknowledges. If any outstanding handle is
dropped unacknowledged, the waiter resolves to cancellation instead.

That is stronger than a boolean flag. It lets the code distinguish:

- "all parties finished",
- from "someone stopped participating."

`Pool<T>` and `AbortablePool<T>` in `futures.rs` do something similar for
collections of asynchronous work. They say:

- keep an unordered set of in-flight futures,
- always have a safe `next_completed()` even when the logical pool is empty,
- optionally give each task an `Aborter` whose drop aborts only that task.

The dummy future inside each pool looks odd the first time you read it, but it
exists for a clean reason: `select_next_some()` should not collapse instantly
just because the current pool is empty. The abstraction is trying to give the
rest of the code a stable control-flow shape.

`Limiter` and `KeyedLimiter` in `concurrency.rs` make another common pattern
explicit: some work is allowed to proceed only up to a global bound, and some
work is allowed at most once per key.

- `Limiter` hands out a reservation if capacity remains, and the reservation
  releases on drop.
- `KeyedLimiter` adds a second rule: a key may not be acquired twice
  concurrently, and the total number of active keys is also bounded.

That is often the difference between "backpressure" as a comment and
backpressure as a protocol rule.

`UpgradableAsyncRwLock` in `sync/mod.rs` is the same idea at the lock level.
It uses a gate so that an upgradable read can later become a writer without
letting another writer slip in between. The point is not to prefer async locks
everywhere. The point is to make the rare upgradable path honest about its
invariant.

### 3.4 The Historical Bitmap Is a Real State Machine

`utils/src/bitmap/historical/mod.rs` is where the crate stops looking like a
collection of wrappers and starts looking like a compact systems component.

The historical bitmap maintains:

- one full prunable bitmap as the current head state,
- and historical commits as reverse diffs rather than full clones.

Its clean/dirty split is the key conceptual move:

- `CleanBitMap` means there are no pending mutations,
- `DirtyBitMap` means mutations are in progress and not yet committed.

That split makes the lifecycle explicit:

1. `into_dirty()` opens a mutable batch,
2. mutate through the dirty view,
3. `commit(height)` seals the batch into history,
4. `abort()` discards uncommitted edits,
5. return to a clean state.

The dirty state is not a vague overlay. It tracks concrete pieces of future
state:

- `modified_bits` for edits to existing bits,
- `appended_bits` for new tail bits,
- `chunks_to_prune` for data that must remain recoverable after pruning.

Read-through semantics make the current projected state visible before commit:

- appended bits win first,
- then modified bits,
- then the base bitmap.

That priority order is why the type can answer "what would this look like if we
committed now?" without actually committing yet.

The edge cases are part of the design, not afterthoughts:

- commit numbers must be strictly monotonic,
- `u64::MAX` is reserved,
- no-op batches still record a commit if the caller asked for one,
- `prune_commits_before` drops old history without changing the current head.

The whole point is to keep current state cheap, history compact, and lifecycle
boundaries visible.

## 4. How the System Moves

### 4.1 Canonical Committee Data Arrives From the Outside

Suppose a protocol decodes a committee from bytes.

If it uses `Set<T>`, the decoder checks that the items are already sorted and
unique. If the sender emitted duplicates or arbitrary order, decoding fails.
Only after that does the rest of the code gain access to indexing, `position`,
and quorum helpers.

That is the first large pattern of the crate:

> canonicalization happens at the boundary, not after the fact.

### 4.2 Completion Is Represented as an Object, Not a Comment

Suppose one task fans out work to several children and wants to know when all
of them are finished.

Instead of passing around a raw channel or shared counter, it can create an
`Exact` acknowledgement handle, clone it for each required participant, and
await the paired waiter.

The resulting state machine is precise:

- every clone increases the remaining count,
- every `acknowledge()` decrements it,
- any unacknowledged drop cancels the whole acknowledgement,
- the waiter wakes only on success or cancellation.

That turns "everyone should eventually signal completion" into something the
type system and tests can observe directly.

### 4.3 Bounded Concurrency Becomes Declarative

Suppose a subsystem should allow at most `N` simultaneous operations, or at
most one operation per key.

The limiter types make that rule a value:

- a slot is acquired or not,
- a reservation exists or not,
- and dropping the reservation is the release.

No extra cleanup call is required. The capacity rule is bound to lifetime.

### 4.4 The Historical Bitmap Is the Full Lifecycle

The historical bitmap is easiest to understand as one explicit mutation cycle:

```text
clean state
  -> into_dirty()
  -> mutate through dirty view
  -> commit(height) or abort()
  -> clean state again
```

The important part is what does *not* happen:

- uncommitted mutations do not silently become history,
- and aborted mutations do not leak into the clean view.

That makes the bitmap a strong example of how this crate likes to model state:
through named transitions with narrow responsibilities.

### 4.5 The Fuzz Targets Show Where the Crate Thinks It Is Fragile

The fuzz surface under `utils/fuzz/` clusters around the boundaries where a
small mistake spreads quickly: canonical sets, sequencing helpers,
acknowledgement state, future pools, channel behavior, historical bitmaps, and
time math. That is the right place to spend fuzzing effort because those
helpers are small and widely reused.

## 5. What Pressure It Is Designed To Absorb

### 5.1 Duplication Pressure

The monorepo has many places where the same tiny concept could be
reimplemented locally. This crate keeps that from happening.

### 5.2 Validation Pressure

If a value is only valid in one shape, the shape should be encoded in the
type, not rechecked by every caller.

### 5.3 Shutdown and Overflow Pressure

Channels and task pools often fail at the edges: a receiver disappears, a task
must be aborted, or the newest state matters more than the oldest. The crate's
coordination helpers turn those edge behaviors into explicit choices.

### 5.4 Canonicalization Pressure

When a shape recurs across crates, the system benefits from one stable answer
instead of many almost-right ones.

### 5.5 History Pressure

The historical bitmap shows how the crate handles the problem of preserving
current state plus reversible mutation history without cloning full structures
every time.

## 6. Failure Modes and Limits

The first limit is scope. `commonware-utils` is not where domain logic lives.
It should not grow into a second place for consensus algorithms, codec policy,
or application-specific workflows.

The second limit is strictness. Several helpers intentionally fail or panic on
misuse:

- `Set` decoding rejects non-canonical order,
- `NonEmptyVec::mutate` panics if the closure empties the vector,
- `NonZeroDuration::new_panic` rejects zero,
- `Exact` treats an unacknowledged drop as cancellation,
- `ring` channels intentionally drop the oldest buffered item when capacity is
  exhausted.

Those are not accidents. In this crate, many bad inputs are better treated as
programmer errors or explicit cancellation states than as values that deserve
quiet repair.

The third limit is that these are support tools, not full domain abstractions.
`KeyedLimiter` does not decide what keys mean. `HistoricalBitMap` does not
know why a commit matters. The surrounding crates still provide the application
semantics.

## 7. How to Read the Source

Start with `utils/src/lib.rs` to see the crate's public shape and stability
split. Then read the canonical collection files, the coordination files, and
finish with the historical bitmap. That order keeps the recurring invariants
grouped by the problem they solve instead of by file name.

If you keep the belt-of-tools model in mind, the files stop feeling like an
assortment and start feeling like a carefully selected kit.

## 8. Glossary and Further Reading

- **canonical collection**: a collection whose order and uniqueness rules are
  part of its contract.
- **receiver-owned policy**: the idea that a decoder should reject non-
  canonical input rather than silently normalize it.
- **acknowledgement**: a handle-plus-waiter pair that models task completion
  or cancellation explicitly.
- **reservation**: a lifetime-bound claim on limited concurrency.
- **upgradable read**: a read lock that may later become a write lock without
  letting another writer slip in.
- **dirty bitmap**: a projected future state that has not yet been committed.
- **reverse diff**: history data that lets the current state be rolled back to
  an earlier commit.

Further reading:

- `utils/src/ordered.rs`
- `utils/src/acknowledgement.rs`
- `utils/src/futures.rs`
- `utils/src/concurrency.rs`
- `utils/src/bitmap/historical/mod.rs`
