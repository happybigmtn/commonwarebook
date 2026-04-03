# commonware-storage

*Logs first, views second, proofs when the reader must be convinced*

---

## Opening Apparatus

**Promise:** This chapter shows how `commonware-storage` keeps a durable log
first, derives useful views second, and adds proofs only when facts need to
travel.

**Crux:** Storage in adversarial systems is not one job; durability, fast
answers, and cryptographic evidence pull in different directions, so the
design must keep those responsibilities separate.

**Primary invariant:** The log is the durable authority. Views may be rebuilt,
compressed, or discarded, but every answer must still trace back to that
history.

**Naive failure:** Treating the current snapshot as the truth makes recovery
guessy, pruning dangerous, and proofs impossible to explain once history
changes.

**Reading map:**

- Section 2 names the mental model: log, then view, then proof.
- Section 3 walks the core primitives from `Persistable` to QMDB.
- Section 4 follows the system through write, recovery, proof, and pruning.
- Section 5 names the pressure each layer absorbs.
- Section 6 names the failure modes and limits.
- Section 7 shows how to read the source in order.
- Section 8 closes with a glossary and further reading.

**Assumptions:**

- You already know the basics of crash recovery.
- You are comfortable reading append-only data structures.
- You want the storage story in adversarial terms, not generic database terms.

---

## Background: Why Storage Becomes a Systems Problem

Storage looks like a simple question until a crash, a prune, or a skeptical
reader enters the picture.

The broad vocabulary is worth separating early:

- a **log** preserves the sequence of events,
- a **snapshot** captures one current view,
- an **index** speeds up lookup for a subset of the history,
- a **proof** lets someone else check that a returned fact really came from the
  right history,
- a **prune** discards history that is no longer needed.

The naive approach is to treat the latest snapshot as the truth and ignore the
path that produced it. That works only until recovery, compaction, or proof
generation matters. Once that happens, you need to know what happened before
the current answer existed.

The main tradeoff is that the best structure for recovery is not usually the
best structure for serving fast reads, and neither one is automatically good at
producing evidence. Logs are durable and easy to replay. Views are fast and
cheap to query. Proof-bearing structures are convincing to outsiders. Real
storage systems have to keep those roles separate instead of pretending one
representation can do all three.

That separation is the point of this chapter. The Commonware design starts from
the durable record of events, derives useful views from that record, and only
then adds proof machinery where the reader needs to be convinced.

---

## 1. What Problem Does This Solve?

Storage sounds simple until a distributed system asks three questions at once.

1. What survives the crash?
2. What is the state now?
3. How do I prove that answer to someone who does not trust me?

Those questions overlap, but they are not the same. A local application can
often stop after the first two. An adversarial system usually cannot. A node
may need to restart from disk, rebuild a snapshot, serve current answers, and
later justify those answers to a peer, a client, or another chain.

That is the problem `commonware-storage` is built around. It does not present
storage as one giant database with feature flags. It presents storage as a
sequence of stronger promises:

- remember the history durably,
- derive a useful view from that history,
- attach evidence to the facts that matter.

The crate matters because those promises pull in different directions. A log is
good at surviving crashes. A lookup structure is good at answering quickly. A
proof system is good at convincing skeptics. The interesting design question is
how to get all three without pretending they are the same thing.

The Commonware answer is to start from the only part you really trust after a
crash: the record of what happened.

---

## 2. Mental Model

The chapter's mental model is:

> Start with a log, derive a view, then prove facts about that view.

If you keep that sentence in mind, the crate stops looking like a collection of
unrelated modules.

Consider a key `alice` whose value changes over time:

- assign `alice = 5`
- delete `alice`
- assign `alice = 6`

If you think like a conventional database user, the only thing that feels real
is the last line. The earlier lines look like stale intermediate state.

If you think like `commonware-storage`, the durable truth is the whole sequence.
The current value is a view derived from that sequence. And a proof, when you
need one, must somehow connect the answer you served back to an authenticated
commitment over that history.

That gives us a clean vocabulary for the rest of the chapter:

- **Log** means the durable record of operations or records.
- **View** means the structure that turns that record into useful answers.
- **Proof** means the evidence that ties an answer to a trusted root.

The modules fit onto that ladder naturally.

- `journal` is the plainest log.
- `archive`, `freezer`, and `index` are different ways to turn durable history
  into usable views.
- `merkle::mmr` turns append-only history into evidence.
- `qmdb` composes the three layers into proof-bearing state.

Every later section is a different resolution of the same claim: keep history
durable, derive views from that history, and export proofs only when a reader
needs them.

---

## 3. The Core Ideas

### 3.1 Storage starts by naming the crash boundary

The crate's smallest public idea is also one of its most important ones:
durability is explicit.

In [`storage/src/lib.rs`](/home/r/coding/monorepo/storage/src/lib.rs), the
`Persistable` trait says that a storage structure can `commit()`, `sync()`, and
`destroy()`. That is not ornamental API design. It tells you what kind of crate
this is.

The important distinction is that `sync()` is stronger than `commit()`. The
docs say `sync()` not only preserves the current state across a crash, but also
guarantees that recovery work will not be needed on the next open. In other
words, the crate refuses to smudge over the line between "my bytes survived"
and "my structure is immediately ready."

That is the right opening move for a storage lecture. Before we ask how to
serve queries or generate proofs, we ask the simpler question: where is the
durable boundary, and what exactly do we get when we cross it?

### 3.2 The authenticated journal is the bridge from bytes to proofs

The plain journal explains why append-only history is a good crash boundary.
The authenticated journal explains how that same history becomes evidence.

[`storage/src/journal/authenticated.rs`](/home/r/coding/monorepo/storage/src/journal/authenticated.rs)
keeps two append-only structures in lockstep:

- a contiguous journal of items,
- an MMR leaf for each item digest.

The file repeats the key invariant explicitly: item `i` in the journal
corresponds to leaf `i` in the MMR. That is the bridge. Durable bytes and
proof-bearing positions advance together.

This is why the authenticated batch API matters. An `UnmerkleizedBatch`
collects items and hashes them into speculative leaves. `merkleize()` computes
the root that would result if the batch were published. `finalize()` turns the
speculative state into an owned changeset. The design separates three moments
that a weaker system would blur together:

- **staging** what to append,
- **merkleizing** to learn the implied root,
- **applying** to make journal and MMR advance together.

That separation is not decorative. It is what lets higher layers fork
speculative states, inspect roots before publication, and reject stale work
later.

The other important idea in this file is alignment on recovery. The code does
not assume the journal and MMR still agree after a crash. It realigns them and
then `sync()`s the MMR so the next open does not need to repeat the work. The
authenticated journal is therefore the first place the crate makes a subtle but
foundational distinction:

> "durable enough to replay" and "already aligned to serve proofs" are not the
> same state.

### 3.3 The log is still the durable truth

The cleanest evidence for the chapter's mental model is
[`storage/src/journal/mod.rs`](/home/r/coding/monorepo/storage/src/journal/mod.rs).
Its module docs describe an append-only log with fast replay, historical
pruning, and item-oriented reads.

Append-only storage is attractive because it makes failure legible. A partial
append has a clear shape: history ends here, this checksum fails, this section
is incomplete. An in-place mutation is harder to reason about because the old
state and the new state overlap destructively.

So the first Commonware move is to make history explicit. Once operations are
laid down in order, recovery becomes replay instead of repair. A restart no
longer asks, "what did the mutable structure probably mean before the crash?"
It asks, "what durable operations do I trust, and what view do they imply?"

That is why the chapter keeps insisting that the log comes first. In this
crate, the log is not a backup of the database. The log is the durable truth
from which the database view is rebuilt.

### 3.4 A view is the working answer, not the fundamental truth

Once we have the log, we can ask the next question: how do we answer quickly
without replaying the entire history on every lookup?

This is where the crate's middle layer appears. The point of that layer is not
to introduce "more storage engines." The point is to show several ways of
building views over durable history.

[`storage/src/archive/mod.rs`](/home/r/coding/monorepo/storage/src/archive/mod.rs)
is the simplest example. It is a write-once store whose records are tied to
both an index and a key. That tells you exactly what kind of view it is: one
that assumes historical order matters and mutation does not.

[`storage/src/freezer/mod.rs`](/home/r/coding/monorepo/storage/src/freezer/mod.rs)
is more revealing because its docs explain the bargain in detail. It keeps
lookup structures on disk, avoids compaction, and accepts that older data may
take longer to fetch. That is not "yet another key-value store." It is a
deliberate answer to the question: how do we keep a durable view when memory is
scarce and rewriting is expensive?

The smaller sidecars make the same point from different angles.

- [`storage/src/cache/mod.rs`](/home/r/coding/monorepo/storage/src/cache/mod.rs)
  is a narrow view optimized for index-based reads. It tracks offsets and
  lengths in memory so a caller that already knows an index can usually read the
  item in one disk operation.
- [`storage/src/queue/mod.rs`](/home/r/coding/monorepo/storage/src/queue/mod.rs)
  turns durable history into delivery state. Its promise is not "truth now" but
  "durable at-least-once replay until acknowledged and pruned."

These modules are conceptually helpful because they show that a view does not
have to be a database index. A queue cursor, a gap finder, or a position map
are all working answers layered on top of durable history.

### 3.5 An index is a compressed memory of where truth lives

[`storage/src/index/mod.rs`](/home/r/coding/monorepo/storage/src/index/mod.rs)
makes the trade-off even sharper. Its docs open by warning that translated keys
can collide. That is a good sign. The crate does not hide the price of memory
savings behind a friendly map-like interface.

The important method is `get()`: it returns every value that maps to the same
translated key. The ambiguity is the point. The index is a shortlist, not a
verdict.

The index is not pretending to be the truth. It is a compressed memory of where
the truth probably lives. If compression introduces ambiguity, the ambiguity
surfaces in the type. Callers must resolve collisions by checking the real key
or the real operation in the underlying log.

The translator layer in
[`storage/src/translator.rs`](/home/r/coding/monorepo/storage/src/translator.rs)
shows how disciplined this compromise is.

1. **Collisions are part of correctness.** A translated-key hit is a compact
   lead, not yet a fact about the real key.
2. **Hasher choice matters.** `UintIdentity` makes sense only because the
   translator has already shrunk keys into a form that should be cheap to place
   directly in a table.
3. **Collision hardening is explicit.** `Hashed<T>` salts the full key before
   translation so an attacker cannot cheaply engineer predictable collision
   clusters.

The warning in `Hashed<T>` is especially important: it is not a stable encoding
format. It is an in-memory collision-hardening layer. The chapter therefore has
to keep three different notions separate:

- stable log encoding on disk,
- possibly unstable translated keys in memory,
- cryptographic commitments over operation bytes.

Those layers can cooperate without being interchangeable.

### 3.6 Proof-bearing state starts when history becomes authenticated

At this point we have a log and some ways to derive views from it. The final
step is to make facts about that history portable.

[`storage/src/merkle/mmr/mod.rs`](/home/r/coding/monorepo/storage/src/merkle/mmr/mod.rs)
provides the key proof structure: the Merkle Mountain Range. Its docs define it
as an append-only authenticated data structure whose node positions never
change. That stable, append-only character is the reason it belongs here.

An MMR matches the log story. New elements are appended. Old nodes are not
rewritten. Inclusion proofs talk about a growing history rather than a mutable
tree with arbitrary rewrites. The accompanying blog post
[mmr.html](/home/r/coding/monorepo/docs/blogs/mmr.html) makes the systems case
plainly: append-only authentication avoids scattered rewrites and turns growing
history into something that can be certified compactly.

This is the right place to distinguish the two Merkle families in the crate.

| Structure | What it commits to | Best at | Awkward at |
| --- | --- | --- | --- |
| `bmt` | a fixed batch of leaves | compact batch and range proofs | ongoing append-heavy history |
| `mmr` | a growing append-only history | persistent logs and stable locations | arbitrary in-place mutation |

[`storage/src/bmt/mod.rs`](/home/r/coding/monorepo/storage/src/bmt/mod.rs) is a
stateless batch tree. It hashes leaves with positions, folds upward level by
level, duplicates the final odd node when needed, and finalizes with
`hash(leaf_count || tree_root)` so proofs cannot be replayed against another
tree size. That is exactly what you want when a batch is a closed set.

The MMR solves a different problem. Its great virtue is not "Merkle tree, but
fancier." Its great virtue is that appending new history does not force the
system to pretend old positions moved.

### 3.7 QMDB is where the three layers snap together

[`storage/src/qmdb/mod.rs`](/home/r/coding/monorepo/storage/src/qmdb/mod.rs)
states the central idea outright: a database's state is derived from an
append-only log of state-changing operations.

That sentence is the whole chapter restated in code.

QMDB matters because it composes all three layers:

- the durable log of operations,
- the derived snapshot or active view,
- the authenticated structure used to prove facts.

The batch lifecycle in the docs is part of that story. You stage mutations,
merkleize them, inspect the resulting root, finalize the changeset, and only
then apply it. That keeps speculation separate from commitment. The stale
changeset error keeps the separation honest.

The variants read best as a proof matrix rather than as an implementation menu.

| Variant | State model | Main proof claim | Extra machinery it must carry |
| --- | --- | --- | --- |
| `keyless` | append-only values by location | "this value was written here" | authenticated journal only |
| `immutable` | keyed inserts only | "this key was set to this value" | snapshot over insert-only log |
| `any` | mutable keyed state | "this key had this value at some point" | snapshot plus update/delete semantics |
| `current` | mutable keyed state with liveness | "this value appeared and is still current" | `any` plus bitmap and grafted MMR |

The
[adb-any.html](/home/r/coding/monorepo/docs/blogs/adb-any.html) essay says the
same thing in more narrative form: the database is not authenticated by hashing
a mutable snapshot directly. It is authenticated by committing to the
historical log of operations and deriving active state from that log.

`current` is especially instructive. Its module docs explain why proving a
historical value is easier than proving a current one. A historical proof only
needs to show that an operation was in the log. A current proof must also show
that no later operation displaced it. The authenticated bitmap and grafted MMR
exist to carry that extra burden.

The crucial move is *grafting*. At a chosen height, the system replaces the raw
ops-subtree digest with a digest that commits to both the ops subtree root and
the bitmap chunk covering the same operations:

```text
grafted_leaf = hash(bitmap_chunk || ops_subtree_root)
```

unless the chunk is all zeros, in which case the ops subtree root is reused as
an identity. That identity case matters because it lets pruned, all-inactive
regions stay structurally compatible with the underlying ops MMR.

That is the climax of the chapter's mental model. The proof layer does not
float above the storage layer. It changes which views are affordable and which
facts remain provable.

---

## 4. How the System Moves

The best way to test the mental model is to follow the system through time.

### 4.1 Write path: record, derive, then publish

A write begins by recording some operation or record durably. In the simplest
case, that is an append to a journal. In the authenticated cases, it is also an
append to the structure that will later support proofs.

Only after the durable record exists does the crate update the view that makes
future answers cheap.

That order matters. It means the fast path for queries is derived state, but
the recovery path always knows where to start: the log.

For QMDB, the write path is best understood as four separate jobs:

1. stage operations in a batch,
2. resolve them against the current snapshot while merkleizing,
3. apply the finalized changeset to the log and the active view,
4. choose `commit()` or `sync()` as the durability boundary.

The first two jobs can fork speculatively. The third cannot. That is why stale
changesets are rejected rather than merged. The batch's expected base state is
part of correctness, not just concurrency hygiene.

### 4.2 Recovery path: replay, realign, rebuild

This is where append-only design pays for itself.

After a restart, the system rebuilds what it needs from the durable record:

- journals replay operations,
- authenticated journals realign the journal and MMR if `commit()` happened
  without a full `sync()`,
- archives and freezers reopen their durable lookup structures,
- QMDB rebuilds the snapshot from the operation log,
- authenticated variants restore enough Merkle state to keep proofs valid.

The helper in `qmdb/mod.rs` is named `build_snapshot_from_log`, and the name
is unusually direct for a reason: the snapshot is not the stored truth. It is
rebuilt from the stored truth.

In the keyed QMDB variants, replay is not just "recompute the latest value."
The replay callback reports both whether the current operation is active and
which older location, if any, became inactive. `current` turns that callback
into bitmap state.

That distinction matters for evaluation too. A storage recovery claim is only
useful if it says which boundary the system crossed. Did the process stop after
`commit()` but before `sync()`? Did replay have to realign the authenticated
state before serving proofs? Did pruning preserve the semantic promise the
proof layer still needs? The Commonware code is strongest when it reports
recovery in those exact terms, because the recovery path is an explicit
derivation from durable history rather than a hand-waved "reopen the DB"
story.

### 4.3 Read path: the view finds the candidate, the log settles it

The read path is easy to summarize and important not to romanticize.

The system does not usually walk the log first. It asks the view to narrow the
search, then asks the log to settle any ambiguity the view cannot resolve.

That is exactly how translated-key indices are supposed to behave. A
translated-key hit is not yet a fact about the real key. It is a compact lead.
The authoritative answer still comes from the stored operation bytes.

This is why collision discipline belongs in the chapter's core logic rather
than in a performance appendix. The crate stays correct because collision
resolution falls back to durable data, not because collisions are assumed rare.

### 4.4 Proof path: the same search, plus an authenticated ladder

A proof-bearing query repeats the same sequence in compressed form.

1. Identify the operation or record in the durable history.
2. Use the derived view to find the relevant location efficiently.
3. Attach the Merkle path or supporting structure that ties that location to a
   trusted root.

In `mmr`, that supporting structure is an inclusion proof over append-only
history. In `qmdb::any`, it is proof that some operation for a key exists in
the authenticated log. In `qmdb::current`, it is proof of both the operation
and its activity status under the same root.

The important point is that the proof path does not replace the view path. It
rides on top of it. Views help us find the right place in history. Proof
structures help us convince somebody else that the place and the answer are
authentic.

`current/proof.rs` makes the richer path concrete. A `RangeProof` carries:

- the MMR proof material,
- the ops root,
- and, when needed, a digest of the partial trailing bitmap chunk.

That last field is the tell. The trailing chunk is often incomplete, so it is
not yet represented by a full grafted leaf in the MMR. Rather than lie about
that, the canonical root folds the partial chunk digest and `next_bit` into the
final hash. The verifier reconstructs the grafted root, then recomputes the
canonical root.

### 4.5 Sync path: target the ops root, rebuild the rest deterministically

The sync story in
[`storage/src/qmdb/current/sync/mod.rs`](/home/r/coding/monorepo/storage/src/qmdb/current/sync/mod.rs)
is subtle and worth teaching directly.

State sync does **not** target the canonical `current` root first. It targets
the raw ops root. The engine downloads operation batches, verifies them against
standard MMR range proofs, and only then rebuilds the bitmap and grafted MMR
locally. The canonical root is computed afterward from three ingredients:

- the ops root,
- the grafted MMR root,
- the partial chunk data, if the last chunk is incomplete.

This split is elegant because it keeps network sync on the simpler proof
surface while letting current-state proofs remain richer. The sync engine only
needs to trust that operations are authenticated by the ops MMR and that bitmap
state is a deterministic function of replayed operations.

The all-zero identity rule does real work here. For pruned zero chunks, grafted
peaks are recoverable from the ops MMR because a zero chunk leaves the ops
subtree root unchanged. That is the bridge between sync simplicity and
current-proof richness.

### 4.6 Pruning only works if the promise survives

Pruning is where weak mental models fail.

If you think storage is just bytes on disk, pruning means deleting old bytes.
If you think in terms of log, view, and proof, pruning becomes a semantic
question: after I remove this history, what can I still recover, and what can I
still prove?

That is why the crate's pruning stories differ.

- A journal can prune old sections once its replay contract still makes sense.
- A write-once store can prune historical ranges only if its lookup story
  remains intact.
- QMDB must preserve enough structure to rebuild the active view and
  authenticate the facts each variant promises.

For `current`, that means pruning is never just "drop old bitmap chunks." The
system first persists pinned digests for the grafted peaks covering the pruned
region. Those pins become opaque siblings during future upward propagation.
Without them, the db might still know the active set locally while no longer
being able to reconnect that set to old authenticated history.

The `adb-any` essay makes this concrete with the inactivity floor. Old
operations become inactive, but that does not mean they were meaningless. They
were part of the history from which current state was derived. The art of
pruning is to drop what no longer matters without lying about what remains
recoverable or provable.

---

## 5. What Pressure It Is Designed To Absorb

The storage crate is interesting because it absorbs several different kinds of
pressure without pretending one mechanism solves them all.

### Crash pressure

The first pressure is obvious: crashes happen. Append-only logs, explicit sync
boundaries, checksums, and replay-friendly formats all exist to make crash
recovery boring.

### Memory pressure

The second pressure is memory. Large keys and large histories are expensive to
index directly. That is why translators exist and why the index exposes
collisions instead of concealing them.

### Write amplification pressure

The third pressure is storage churn. `freezer` is the clearest answer here:
keep the view durable, but avoid compaction loops and repeated rewrites of old
values. The MMR story points the same way. Append-only authenticated structures
are attractive because new writes stay localized.

### Proof expressiveness pressure

The last pressure is conceptual rather than operational: not every fact costs
the same to prove.

It is cheap to prove that some value appeared in history.
It is harder to prove that the value is current.
It is harder still to prove exclusion.

The crate's variant structure is really a pricing table for proof obligations.
`qmdb::any` is smaller because it promises less. `qmdb::current` does more
work because it must authenticate activity status. The crate is strongest when
the reader sees those as different evidence products, not as a menu of random
database flavors.

Two compact tables make those pressures easier to compare.

### 5.1 Structure cost table

| Layer | Memory profile | Rewrite profile | Recovery cost | Proof value |
| --- | --- | --- | --- | --- |
| plain journal | low, mostly append state | append-only | replay retained history | none |
| authenticated journal | low plus MMR metadata | append-only plus MMR tip work | replay and realign | inclusion in history |
| translated index | compressed, collision-prone | cheap updates | rebuild from log if needed | none by itself |
| cache | small explicit tracking map | append journal plus map update | replay tracked offsets | none |
| freezer | disk-heavy, RAM-light | avoids compaction | reopen plus targeted reads | none |
| QMDB `any` | snapshot plus ops MMR | append log, mutable snapshot | replay ops to rebuild state | historical keyed facts |
| QMDB `current` | `any` plus bitmap and graft cache | dirty chunk updates and graft propagation | replay plus graft rebuild | current-state facts |

### 5.2 Pruning and proof tradeoff table

| Mechanism | What pruning removes | What must remain pinned | What claim survives |
| --- | --- | --- | --- |
| journal | old sections | enough history to satisfy replay window | recent durable history |
| cache | old blobs and their offsets | first retained index boundary | index-based reads after floor |
| QMDB `any` | inactive old ops below floor | MMR nodes needed to bridge pruned range | historical facts above floor |
| QMDB `current` | inactive ops plus old bitmap chunks | grafted or equivalent ops peaks for zero chunks | current-state proofs above floor |

The lesson is that pruning pressure and proof pressure are coupled. The richer
the claim, the more carefully the system must preserve authentication context
even after discarding raw data.

---

## 6. Failure Modes and Limits

The shadow of the design is easy to name once the mental model is clear.

### The log can be damaged

Recovery only works if corruption is recognizable. That is why the journal
types care about invalid sizes, missing blobs, checksum mismatches, and
corruption errors. Append-only history helps, but it does not abolish bad
storage. It makes damage detectable and localized.

### The view can be ambiguous

Translated keys can collide. That is not an implementation accident. It is the
explicit cost of compressing the in-memory view. When collisions get worse,
lookups degrade because the view is no longer a unique answer. The system must
go back to the real key or the real operation to decide which candidate is
correct.

The more adversarial version of this failure is not merely "slower lookups."
It is skewed translation creating hot buckets or ordered neighborhoods that no
longer mean what the caller thinks they mean. That is why `Hashed<T>` comes
with strong caveats: it can harden unordered lookups against crafted
collisions, but it destroys lexical ordering and therefore cannot be used
blindly in ordered proof schemes.

### The proof may say less than the application hopes

This is the most important limit in the chapter.

If you only authenticate the log of operations, you can prove history, not
current truth. That is why `qmdb::any` stops where it does. If you need current
state proofs, the system must authenticate activity as well. If you need
absence proofs, you need still more structure.

Proof-bearing storage is not a key-value store with hashes sprinkled on top.
The proof structure decides what statements are cheap, what statements are
possible, and what statements are out of scope.

This is where the family matrix matters. `keyless`, `immutable`, `any`, and
`current` are not interchangeable implementations. They are different answers
to the question "which statement do you need another machine to believe?"

### Pruning can destroy meaning, not just bytes

Over-pruning is dangerous because the lost thing is often not raw data but
interpretation. Remove the wrong history and you may still have a root, but no
longer the ability to reconstruct the view or justify the guarantee your API
claims to provide.

The current-proof machinery makes this especially sharp. If the bitmap chunk is
gone, the grafted pins are missing, or the verifier can no longer reconstruct
the partial trailing chunk rules, the db may still answer local reads while no
longer being able to export the proof the root once promised.

### Speculation can drift from reality

QMDB's stale changeset error is a reminder that speculative batching is only
safe if branches fail loudly when the base state has moved. A proof-bearing
system cannot silently merge a view built from one history onto a different
history. The result would be fast, wrong, and hard to detect.

---

## 7. How to Read the Source

Read the storage crate as a climb from durable history to proof-bearing state.

1. Start with
   [`storage/src/lib.rs`](/home/r/coding/monorepo/storage/src/lib.rs).
   Learn the crate families and the `Persistable` contract.
2. Read
   [`storage/src/journal/mod.rs`](/home/r/coding/monorepo/storage/src/journal/mod.rs).
   This is the purest statement of the log layer.
3. Read
   [`storage/src/archive/mod.rs`](/home/r/coding/monorepo/storage/src/archive/mod.rs),
   [`storage/src/freezer/mod.rs`](/home/r/coding/monorepo/storage/src/freezer/mod.rs),
   and
   [`storage/src/index/mod.rs`](/home/r/coding/monorepo/storage/src/index/mod.rs).
   These are the view layer. Notice how each one answers a different operational
   question.
4. Read
   [`storage/src/merkle/mmr/mod.rs`](/home/r/coding/monorepo/storage/src/merkle/mmr/mod.rs).
   This is where history becomes portable evidence.
5. Compare it with
   [`storage/src/bmt/mod.rs`](/home/r/coding/monorepo/storage/src/bmt/mod.rs).
   That contrast helps fix when the crate wants a closed batch tree versus a
   growing historical accumulator.
6. Finish with
   [`storage/src/qmdb/mod.rs`](/home/r/coding/monorepo/storage/src/qmdb/mod.rs)
   and then the `keyless`, `immutable`, `any`, and `current` variants in that
   order. Once the earlier layers are clear, QMDB reads as composition instead
   of magic.

If you jump straight into `qmdb/current`, the bitmap grafting details will feel
like a trick. If you arrive there by way of log, view, and proof, the same code
reads like a necessary answer to a precise question.

---

## 8. Glossary and Further Reading

### Glossary

**Log**  
The durable sequence of records or operations that survives crashes and can be
replayed.

**View**  
A structure derived from the log that makes queries practical without being the
fundamental source of truth.

**Proof-bearing state**  
State whose answers can be tied to a trusted root with a compact proof.

**Archive**  
A write-once ordered view over stored records, addressed by index or key.

**Freezer**  
An immutable on-disk view optimized for low memory use and minimal rewriting.

**Translator**  
A function that compresses keys for indexing, accepting collisions as an
explicit trade-off.

**Authenticated journal**  
An append-only journal paired position-for-position with an authenticated MMR,
so durable items and proof-bearing leaves advance together.

**Grafting**  
The act of combining a bitmap chunk and an ops-MMR subtree root into one digest
at a chosen height, so current-state proofs can ride a single path.

**MMR**  
An append-only authenticated structure that commits to growing history and
supports compact inclusion proofs.

**BMT**  
A closed binary Merkle tree for fixed batches, finalized with leaf-count
binding to prevent proof malleability.

**QMDB**  
A family of authenticated databases that derive active state from an operation
log and prove facts about that state.

### Further Reading

- [mmr.html](/home/r/coding/monorepo/docs/blogs/mmr.html)
- [adb-any.html](/home/r/coding/monorepo/docs/blogs/adb-any.html)
- [lib.rs](/home/r/coding/monorepo/storage/src/lib.rs)
- [journal/mod.rs](/home/r/coding/monorepo/storage/src/journal/mod.rs)
- [freezer/mod.rs](/home/r/coding/monorepo/storage/src/freezer/mod.rs)
- [qmdb/mod.rs](/home/r/coding/monorepo/storage/src/qmdb/mod.rs)
