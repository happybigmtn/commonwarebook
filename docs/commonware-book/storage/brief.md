# Chapter Brief: commonware-storage

## 1. Module Purpose

`commonware-storage` is not one storage engine. It is a lecture about three
jobs storage must do in adversarial systems:

- remember what happened,
- answer what is true now,
- convince a skeptical reader.

Those jobs map to one adversarial question:

> How do we persist state so that it is durable, recoverable, and, when needed,
> cryptographically provable?

The crate starts from the simplest reliable substrate -- an append-only log --
then builds views on top of it, then adds proof structures when the answer must
travel:

- `journal` as durable history,
- `archive`, `freezer`, and `index` as derived views,
- `journal::authenticated` as the bridge from durable bytes to proofs,
- `merkle::mmr` and `bmt` as two different authenticated-tree answers,
- `qmdb` as the family that prices different proof claims explicitly.

The right mental model for the chapter is:

> Start with a log, derive a view, then prove facts about that view.

The chapter now opens with a formal apparatus:

- a one-sentence promise,
- the crux,
- the primary invariant,
- the naive failure,
- a reading map,
- a short assumption ledger.

That opener keeps the log -> view -> proof spine visible in every section.
Modules should appear as evidence for the model, not as a catalog of
components.

---

## 2. Source Files That Matter Most

### `storage/src/lib.rs`
**Why it matters:** Defines the public shape of the crate and the
`Persistable` trait. This is the best place to show that `storage` is a family
of primitives rather than a single database.

### `storage/src/journal/mod.rs`
**Why it matters:** The append-only log substrate. This is the simplest durable
story in the crate and the best place to explain replay, pruning, and why
crash recovery likes append-only structures.

### `storage/src/journal/authenticated.rs`
**Why it matters:** The missing bridge in the old chapter. This file shows how
the crate keeps a contiguous journal and an MMR aligned by position, why
`commit()` is weaker than full proof-ready `sync()`, and how speculative
batches become proof-bearing changesets.

### `storage/src/archive/mod.rs`
**Why it matters:** A write-once store keyed by both index and key. Good for
explaining the difference between "persist everything in order" and "serve
point lookups without mutability."

### `storage/src/freezer/mod.rs`
**Why it matters:** The most operationally opinionated store in the crate.
Shows how to trade memory and write amplification for predictable persistence
with disk-resident structures.

### `storage/src/index/mod.rs`
**Why it matters:** Explains compressed key translation, collisions, cursors,
and the difference between storing values and storing a memory-efficient
address into another structure.

### `storage/src/merkle/mmr/mod.rs`
**Why it matters:** The append-only authenticated data structure that lets the
crate turn history into evidence. This is the proof-bearing layer.

### `storage/src/bmt/mod.rs`
**Why it matters:** The best contrast case for MMR. Useful for teaching "closed
batch proof tree" versus "growing historical accumulator."

### `storage/src/qmdb/mod.rs`
**Why it matters:** The chapter's payoff. QMDB shows how the crate turns a log
of operations plus an authenticated structure into a family of databases that
can prove historical facts, current facts, or immutable facts depending on the
variant.

### `storage/src/qmdb/any/mod.rs`
**Why it matters:** The cleanest "historical fact" variant. Best place to
explain authenticated databases as "proofs about any value ever associated with
a key."

### `storage/src/qmdb/current/mod.rs`
**Why it matters:** Introduces the bitmap-grafting idea needed to prove current
state instead of just historical state.

### `storage/src/qmdb/current/proof.rs`
**Why it matters:** Best place to explain the proof ladder concretely: ops root,
grafted root, partial chunk digest, and why `current` proofs authenticate more
than simple inclusion.

### `storage/src/qmdb/current/sync/mod.rs`
**Why it matters:** Best place to teach the sync split: verify batches against
the ops root first, then rebuild bitmap and grafted MMR deterministically.

### `storage/src/translator.rs`
**Why it matters:** Makes the collision story explicit. Needed for the chapter
to explain that translated-key ambiguity is part of correctness, not just
performance.

### `storage/src/cache/mod.rs`
**Why it matters:** Good sidecar example of a view that is not a full database:
index-based single-read cache, gap tracking, and pruning by blob.

### `storage/src/queue/mod.rs`
**Why it matters:** Another derived-view example. Useful for showing that logs
can be projected into delivery state, not only into key-value state.

### `storage/src/bitmap/authenticated.rs`
**Why it matters:** Helpful background for current-state proofs, pinning, and
partial-chunk handling.

### `storage/src/qmdb/keyless/mod.rs`
**Why it matters:** Shows the same authenticated-log idea without keyed state.
Useful for making the distinction between "data by key" and "data by
location."

### `docs/blogs/mmr.html`
**Why it matters:** Best narrative explanation of why append-only proof
structures are attractive in real systems.

### `docs/blogs/adb-any.html`
**Why it matters:** Best narrative bridge from "append-only authenticated log"
to "current database state derived from history."

---

## 3. Chapter Outline

```text
0. Opening Apparatus
   - one-sentence promise
   - crux
   - primary invariant
   - naive failure
   - reading map
   - assumption ledger

1. What Problem Does This Solve?
   - storage must remember, answer, and sometimes convince
   - why those are different jobs

2. Mental Model
   - start with a log
   - derive a view
   - prove facts about the view

3. The Core Ideas
   - `Persistable` names the crash boundary
   - authenticated journals bridge durable bytes and proofs
   - `journal` makes the log the durable truth
   - `archive`, `freezer`, `cache`, `queue`, and `index` show different view strategies
   - translator/collision discipline explains how compressed indices stay correct
   - `mmr` authenticates append-only history
   - `bmt` contrasts fixed-batch proof trees with append-only proof trees
   - `qmdb` composes log, view, and proof into one database story
   - family matrix: `keyless`, `immutable`, `any`, `current`

4. How the System Moves
   - write path: stage, merkleize, finalize, apply
   - recovery path: replay, realign, rebuild
   - read path: view narrows, log settles ambiguity
   - proof path: same search plus authenticated ladder
   - sync path: target ops root, rebuild richer state locally
   - pruning: only when the promise survives

5. What Pressure It Is Designed To Absorb
   - crash recovery
   - memory pressure
   - write amplification
   - proof expressiveness
   - structure cost table
   - pruning/pinning/proof tradeoff table

6. Failure Modes and Limits
   - damaged logs
   - ambiguous views
   - proof systems that say less than the application wants
   - stale speculative state

7. How to Read the Source
   - read as a climb from log to view to proof

8. Glossary and Further Reading
```

---

## 4. System Concepts to Explain at Graduate Depth

1. **The authenticated journal is the missing bridge.**
   It couples durable item bytes and MMR leaves by position, so the chapter can
   move cleanly from crash recovery to proofs without hand-waving.

2. **The log is the durable truth.**
   Recovery gets simpler when state can be replayed instead of repaired.

3. **A view is the working answer, not the fundamental record.**
   `archive`, `freezer`, `cache`, `queue`, `index`, and QMDB snapshots exist to
   answer quickly, not to replace the log's authority.

4. **Translator-based indexing is an explicit compromise.**
   Memory savings are bought by making collisions part of the correctness
   story, with optional hash-hardening for hostile key distributions.

5. **Proof-bearing state is a ladder, not a switch.**
   `keyless`, `immutable`, `any`, and `current` promise progressively richer
   statements and therefore carry progressively richer machinery.

6. **Current-state proofs require extra authenticated state.**
   The bitmap, grafted MMR, partial-chunk handling, and pinned nodes exist
   because "still current" is strictly harder to prove than "once appeared."

7. **Pruning is about meaning, not age.**
   Data can be dropped only when recovery and proof promises still hold.

---

## 5. Interactive Visualizations to Build Later

1. **Journal replay visualizer**
   - Append operations to a log, crash mid-write, replay on restart, show which
     state is recovered.

2. **Archive vs freezer comparison plate**
   - Same writes, different storage strategy. Show write amplification, memory
     footprint, and lookup path.

3. **Index collision explorer**
   - Translate keys into compressed representations, force collisions, then
     show why `get` returns all candidates.

4. **MMR append and proof visualizer**
   - Add elements, watch mountains merge, then generate an inclusion proof.

5. **QMDB state derivation timeline**
   - Log of operations on the left, current active state on the right, proof
     root at the top.

6. **Current-vs-any proof comparison**
   - Show what `qmdb::any` can prove, what `qmdb::current` adds, and why the
     bitmap graft is necessary.

---

## 6. Claims-to-Verify Checklist

- [ ] `Persistable::commit` is a weaker durability boundary than `sync()`
- [ ] `journal` supports replay, pruning, and fetching individual items
- [ ] `journal::authenticated` keeps journal position `i` aligned with MMR leaf `i`
- [ ] authenticated-journal `commit()` is weaker than proof-ready `sync()`
- [ ] `archive` is write-once and keyed by both index and key
- [ ] `freezer` avoids compaction and keeps structures disk-resident
- [ ] `index` uses translated keys and may return multiple values on collision
- [ ] `translator::Hashed` is collision-hardening, not a stable persisted encoding
- [ ] MMR is append-only and uses peaks to derive the root
- [ ] BMT finalizes with leaf-count binding to avoid proof malleability
- [ ] `qmdb::any` proves historical values, not current ones
- [ ] `qmdb::current` adds authenticated current-state proofs via bitmap grafting
- [ ] `qmdb::current::proof` includes partial-chunk machinery in canonical-root verification
- [ ] `qmdb::current::sync` targets the ops root, then rebuilds bitmap and grafted state locally
- [ ] stale changesets are rejected rather than silently applied
