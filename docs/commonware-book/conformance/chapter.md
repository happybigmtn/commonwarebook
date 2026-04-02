# commonware-conformance

## Catching Silent Compatibility Drift

---

## 1. What Problem Does This Solve?

Imagine a release that looks harmless.

The code still compiles.
The unit tests still pass.
Peers still exchange bytes.
The storage layer still opens old files.

And yet the release is wrong.

Maybe a message variant now writes a different tag. Maybe a journal section now
lands at a different offset. Maybe a handshake still completes, but the
transcript, ciphertext framing, or derived state no longer matches the previous
release. Nothing crashes. Nothing announces itself as broken. The system simply
drifts away from the compatibility story it claimed to keep.

That is the class of failure `commonware-conformance` exists to catch.

The crate is not a correctness prover. It is a drift detector for deterministic
behavior. It is meant for surfaces where "can still decode" or "one fixture
still passes" is too weak:

- wire formats,
- storage layouts,
- deterministic handshakes,
- root computations,
- and any other mechanism whose output must stay reproducible across releases.

The main enemy is silent compatibility drift.

A single golden fixture is too small a witness. One example can survive while
the real behavior envelope has already moved. `commonware-conformance` does
something stricter: it replays a deterministic seed sweep, records the whole
sweep as one digest, and checks that digest into the repository.

That gives us the right headline for the whole chapter:

> conformance protects behavior, not isolated bytes.

Or, more operationally:

> it keeps a checked-in ledger of what a stable mechanism does, then asks
> whether the new release still tells the same story.

---

## Backgrounder: Determinism, Regression Tests, and Compatibility Promises

The broad problem here is not "does the code work once?" It is "does the code
keep doing the same thing after it changes?" That is a different question.

A unit test checks a particular behavior on a particular input. A conformance
check asks whether the observable behavior of a deterministic surface is still
the same across a whole replay. That replay matters because compatibility bugs
often hide in the seams: a different tag byte, a reordered output, a changed
offset, or a transcript that still looks plausible to a human.

The classical shortcut is a golden file or one or two example fixtures. That can
catch obvious breakage, but it is easy to fool. A change can preserve the exact
examples while still moving the broader behavior envelope. The system then keeps
passing the sample while drifting away from the real contract.

`commonware-conformance` treats that envelope as the thing worth protecting.
Deterministic seeds give a reproducible input space. Replaying many cases turns
compatibility into a measured sweep instead of a single anecdote. Hashing the
whole sweep makes the result compact enough to check into the repository and
hard enough to ignore during review.

The tradeoff is simple:

- broader sweeps catch more drift,
- but they cost more test time,
- and they make intentional behavior changes explicit instead of silent.

That is a good bargain for stable protocol surfaces. If a release changes how a
wire format, transcript, or persistent structure behaves, the change should be
visible and reviewable. Conformance makes that visibility the default.

---

## 2. Mental Model: A Compatibility Ledger

The best mental model is an accountant's ledger for compatibility promises.

Each tracked type or mechanism gets one ledger entry in a crate-local
`conformance.toml` file. The entry does not store every generated sample. That
would be too large and too fragile. Instead, it stores three things:

- the fully qualified key for the tracked surface,
- the size of the deterministic sweep, `n_cases`,
- and the digest of replaying that sweep.

That changes the question from:

> Did this one example still work?

to:

> If we replay the exact deterministic walk we recorded last time, do we still
> observe the same behavior envelope?

This is why `conformance.toml` is not a cache and not a convenience file. It is
the checked-in statement of record:

- this surface is tracked,
- this many cases define the tracked envelope,
- and this digest is the current compatibility receipt.

CI then acts like an auditor. It recomputes the live digest from the code under
test and asks whether the ledger still balances.

That is stronger than example-based testing in two ways.

First, it forces the repository to say what part of the surface is covered.
`n_cases` is visible. Reviewers can see whether the envelope is broad or narrow.

Second, it forces compatibility changes into review. A changed digest cannot
hide inside a refactor. It becomes a visible diff, a failing test, or an
explicit regeneration.

---

## 3. What Counts As Behavior?

At the center is a deliberately small trait:

```rust
pub trait Conformance: Send + Sync {
    fn commit(seed: u64) -> impl Future<Output = Vec<u8>> + Send;
}
```

That method answers the first lecture question:

> For a given deterministic seed, what bytes does this mechanism commit to?

The crate does not require the bytes to come from one source. `commit(seed)` is
allowed to mean different things in different domains:

- encode one generated value,
- run a complete protocol transcript and log the resulting messages,
- build an on-disk structure and return its storage audit,
- compute a deterministic root after a sequence of inserts.

That flexibility matters. The crate is not tied to one notion of stability. It
only asks for a deterministic commitment that can be replayed.

This is the first place where many readers underestimate the design. The point
is not merely that `commit` returns bytes. The point is that `commit` defines
what the project chooses to treat as the observable compatibility surface.

If you commit only encoded bytes, you are protecting encoding.
If you commit a protocol log, you are protecting transcript-level behavior.
If you commit a storage audit, you are protecting file layout and persistence
effects.

The choice of `commit` is the choice of what story the ledger remembers.

---

## 4. How The Digest Is Actually Built

The digest is built as an ordered replay, not a bag of outputs.

`compute_conformance_hash` does not hash a set of outputs. It hashes one
ordered replay:

```rust
pub async fn compute_conformance_hash<C: Conformance>(n_cases: usize) -> String {
    let mut hasher = Sha256::new();

    for seed in 0..n_cases as u64 {
        let committed = C::commit(seed).await;
        hasher.update((committed.len() as u64).to_le_bytes());
        hasher.update(&committed);
    }

    hex_encode(&hasher.finalize())
}
```

Let us unpack exactly what this means.

### 4.1 The replay order is part of the contract

Seeds are replayed in ascending order: `0, 1, 2, ..., n_cases - 1`.

So the digest is not "the multiset of outputs." It is the ordered transcript of
the sweep. Reordering cases changes the digest. Changing `n_cases` changes the
digest. Changing even one byte for one seed changes the digest.

That is important because many deterministic mechanisms are order-sensitive. If
the ledger ignored order, it would be protecting a weaker claim than the code
actually needs.

### 4.2 The length prefix is not a small detail

Before hashing the committed bytes for a seed, the crate hashes the committed
length as a `u64` in little-endian form.

That prevents ambiguity between concatenated outputs.

Without length-prefixing, these two replays would collapse into the same raw
byte stream:

- case A commits `[0x01]`, case B commits `[0x02, 0x03]`
- case A commits `[0x01, 0x02]`, case B commits `[0x03]`

Both would concatenate to `[0x01, 0x02, 0x03]`.

With length-prefixing, the digest sees the shape of the replay, not just the
flattened bytes. This is a ledger of a sequence, not a bag of octets.

### 4.3 The crate hashes committed values directly, not per-case digests

There is no intermediate per-seed hash tree. The hasher absorbs one replay
stream directly:

1. seed 0 length,
2. seed 0 bytes,
3. seed 1 length,
4. seed 1 bytes,
5. and so on.

That design is simple, deterministic, and easy to reason about in review. When
the final SHA-256 digest changes, the cause is always some change in the replay
stream itself.

### 4.4 The final ledger value is lowercase hex

After finalization, the bytes are encoded with the crate's own `hex_encode`
helper into lowercase hexadecimal. That keeps the checked-in ledger readable
and makes diffs reviewable.

### 4.5 What this protects, precisely

The digest protects the deterministic replay surface induced by:

- the choice of `commit(seed)`,
- the seed order,
- the case count,
- the length-prefixing rule,
- and SHA-256 over the resulting stream.

That is the full compatibility contract. If any one of those rules changes, the
ledger has changed, even if no human noticed by eye.

---

## 5. The Ledger File Is A Shared Resource

The subtle part of the design is not the hash. It is the file discipline.

Conformance tests are meant to run in parallel across a large workspace. That
means the repository needs two things at once:

- expensive digest computation should not serialize unnecessarily,
- shared `conformance.toml` access must still be race-free.

The crate solves this by separating computation from bookkeeping.

### 5.1 Hash first, lock later

Both verification mode and regeneration mode compute the digest before they
touch the file lock.

That is a serious design choice, not a micro-optimization.

Digest computation is the expensive part. It may mean generating sixty-five
thousand arbitrary values, replaying a protocol thousands of times, or building
many storage layouts. Locking around that work would turn the whole workspace
into a queue.

Instead, the crate allows many tests to do the expensive replay in parallel,
then serializes only the small critical section that reads and rewrites the TOML
ledger.

### 5.2 `acquire_lock` is about process safety, not convenience

The lock helper opens the file with read/write/create enabled and
`truncate(false)`, then acquires an exclusive OS-level lock:

```rust
fn acquire_lock(path: &Path) -> fs::File {
    let file = fs::OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(path)
        .unwrap_or_else(|e| panic!("failed to open conformance file: {e}"));

    file.lock()
        .unwrap_or_else(|e| panic!("failed to lock conformance file: {e}"));

    file
}
```

Three details matter here:

1. The file is created if missing, so a first writer can bootstrap a ledger.
2. The file is not truncated on open, so a reader can inspect existing
   contents safely after taking the lock.
3. The lock is OS-level, so concurrent tests and concurrent processes cannot
   interleave ledger updates.

The comment in the source also notes that the lock is released when the process
exits, even if the process is killed. That is exactly the sort of operational
detail a compatibility ledger needs. A stale lock would turn the system into an
availability problem.

### 5.3 Verification mode does not trust unlocked reads

The public helpers `ConformanceFile::load` and `load_or_default` exist, but the
hot verify/regenerate paths do not use them for the core bookkeeping. Once the
lock is acquired, the code reads the current file contents through the locked
handle, parses them, mutates the in-memory `BTreeMap`, then truncates, seeks
back to the beginning, and writes the new pretty TOML.

That is exactly right. If the code loaded the file first and locked later, two
parallel tests could compute against the same stale ledger snapshot and race
while writing. The crate avoids that by treating the locked file handle as the
single source of truth for the mutation step.

### 5.4 Why a `BTreeMap` is the right ledger shape

`ConformanceFile` stores entries in a `BTreeMap<String, TypeEntry>`.

That buys two useful properties:

- stable key ordering in the pretty TOML output,
- one canonical entry per fully qualified type name.

Stable ordering matters in review. A ledger that rewrites entries in random
order would generate noise and hide the real compatibility change.

---

## 6. Verification And Regeneration Are Different Modes

This is the second area where the original chapter needed more operational
detail.

`run_conformance_test` is not one path. It dispatches between two different
behaviors at compile time:

- normal verification mode,
- regeneration mode under `--cfg generate_conformance_tests`.

Those modes serve different social purposes.

### 6.1 Verification mode: detect drift, do not normalize it away

In normal mode, `verify_and_update_conformance` computes the live digest, locks
the file, and then handles three cases:

| Ledger state | Code path | Why it matters |
| --- | --- | --- |
| Entry missing | insert and write | bootstraps a newly added test surface |
| Entry present, hash differs | panic on mismatch | turns silent drift into a review event |
| Entry present, `n_cases` differs | panic on mismatch | treats coverage drift as its own decision |

Notice that hash mismatch and `n_cases` mismatch are checked separately. That is
good design because they ask different review questions.

- A hash mismatch means: did the behavior change?
- An `n_cases` mismatch means: did we redefine the sampled envelope?

Those are not the same event.

### 6.2 Regeneration mode: acknowledge a new ledger on purpose

Under `generate_conformance_tests`, the crate takes a different stance. It still
computes the digest first and locks only around file I/O, but after reading the
ledger it simply updates or inserts the entry and writes the result back out.

That is not a hidden escape hatch. It is the explicit acknowledgement path for
intentional change.

The project-level documentation names the intended command:

```bash
RUSTFLAGS="--cfg generate_conformance_tests" cargo test
```

At the repository level, the book should also point readers to the higher-level
workflow commands:

```bash
just test-conformance
just regenerate-conformance
```

The important concept is not the exact command spelling. It is the review
discipline:

- verification mode says "prove the release still matches the ledger,"
- regeneration mode says "we are deliberately updating the ledger."

### 6.3 Why missing entries are treated differently from mismatches

The missing-entry path surprises some readers. Why not fail instead of writing a
new entry?

Because the crate has to support first admission into the ledger. When a new
surface is brought under conformance control, there is no prior record yet. The
first write is how the ledger begins.

Once the entry exists, however, mismatch is no longer bootstrapping. It is
drift. That is why mismatches panic.

---

## 7. Macro Expansion Is Part Of The Safety Story

`conformance_tests!` is easy to misread as mere ergonomics. It is the layer
that keeps ownership, naming, and file paths coherent across the workspace.

The macro accepts entries of the form:

```rust
commonware_conformance::conformance_tests! {
    CodecConformance<Message<u8>>,
    Handshake => 4096,
}
```

Each entry is either:

- `Type`, which uses `DEFAULT_CASES`,
- or `Type => n_cases`, which overrides the sweep size.

For each entry, the macro does four important things.

### 7.1 It derives a stable test function name

The macro's `type_to_ident` routine converts a Rust type into a snake_case
suffix by:

- splitting PascalCase boundaries,
- replacing punctuation such as `<`, `>`, `,`, spaces, and `::` separators with
  underscores,
- collapsing repeated separators.

That is why types like `CodecConformance<BTreeMap<u32, u32>>` become test names
like `test_codec_conformance_b_tree_map_u32_u32`.

This matters because test names show up in the test runner, logs, and failure
output. The name is part of the operational ergonomics of the ledger.

### 7.2 It fixes the ledger key to module ownership

The generated test passes a type key built as:

```rust
concat!(module_path!(), "::", #type_name_str)
```

That means the ledger entry is anchored to the module that declared the
conformance test, not merely to the bare type name.

For the resolver wire tests, that produces keys like:

- `commonware_resolver::p2p::wire::tests::conformance::CodecConformance<Message<u8>>`
- `commonware_resolver::p2p::wire::tests::conformance::CodecConformance<Payload<u8>>`

That module qualification is not cosmetic. It prevents collisions across the
workspace and keeps the ledger aligned with code ownership.

### 7.3 It roots the ledger file at the owning crate

The macro also hardcodes the path:

```rust
::std::path::Path::new(concat!(env!("CARGO_MANIFEST_DIR"), "/conformance.toml"))
```

That means each test writes only to the `conformance.toml` of the crate that
defined it.

Again, this is not mere convenience. Without this rule, hand-written tests could
accidentally update the wrong ledger file or scatter entries across arbitrary
paths. The macro makes the ownership rule uniform.

### 7.4 It standardizes the test runner grouping

The macro attaches `#[::commonware_conformance::commonware_macros::test_group("conformance")]`
and `#[test]`, then blocks on the async runner with
`futures::executor::block_on(...)`.

That means every generated conformance test participates in the same test-group
machinery and has the same execution shape.

### 7.5 A near-literal expansion

For a concrete feel, this resolver declaration:

```rust
commonware_conformance::conformance_tests! {
    CodecConformance<Message<u8>>,
}
```

expands to the moral equivalent of:

```rust
#[::commonware_conformance::commonware_macros::test_group("conformance")]
#[test]
fn test_codec_conformance_message_u8() {
    ::commonware_conformance::futures::executor::block_on(
        ::commonware_conformance::run_conformance_test::<CodecConformance<Message<u8>>>(
            concat!(
                module_path!(),
                "::",
                "CodecConformance<Message<u8>>"
            ),
            ::commonware_conformance::DEFAULT_CASES,
            ::std::path::Path::new(
                concat!(env!("CARGO_MANIFEST_DIR"), "/conformance.toml")
            ),
        )
    );
}
```

That example shows why macro expansion belongs in a concept chapter. The macro
is not ornamental syntax. It is how the system preserves ledger hygiene at
scale.

---

## 8. Wrapper-Style Versus Bespoke Conformance

The workspace uses two different patterns, and both matter.

### 8.1 Wrapper-style: `CodecConformance<T>`

`codec/src/conformance.rs` is the admission gate for most wire-format surfaces.

The wrapper combines three ideas:

1. deterministic seed input,
2. `Arbitrary` value generation,
3. `Encode` serialization.

Its `commit(seed)` path is:

- seed a `ChaCha8Rng` from the `u64` seed,
- fill a buffer,
- use `arbitrary::Unstructured` to construct a deterministic `T`,
- retry with larger buffers when generation runs out of data,
- encode the resulting value to bytes.

This pattern is powerful because it turns "any type with deterministic
generation plus deterministic encoding" into a conformance surface without
hand-written glue.

The wrapper is ideal when the compatibility claim is:

> for this family of values, encoding must stay stable.

### 8.2 Bespoke: domain-specific `commit(seed)`

Some mechanisms cannot be reduced to one encoded value. In those cases the
workspace writes a custom `Conformance` implementation.

That is the right move whenever the compatibility claim is broader than simple
serialization:

- a full protocol exchange,
- an on-disk layout after writes and syncs,
- a derived root after algorithmic updates.

### 8.3 When to choose which

| Pattern | Best for | Protected behavior |
| --- | --- | --- |
| `CodecConformance<T>` | wire formats and records | deterministic encoding of generated values |
| bespoke `Conformance` | protocols, storage, roots | domain behavior in custom replay bytes |

The key lesson is that `commonware-conformance` does not force one level of
abstraction. It gives the workspace a common ledger while letting each domain
decide what bytes best represent its stability promise.

---

## 9. Real Consumer Case Studies

The best way to understand the crate is to look at what real callers choose to
record.

### 9.1 Resolver wire types: wrapper-style protocol stability

In `resolver/src/p2p/wire.rs`, the nested test module registers:

```rust
commonware_conformance::conformance_tests! {
    CodecConformance<Message<u8>>,
    CodecConformance<Payload<u8>>,
}
```

This is wrapper-style conformance doing exactly what it should: keeping the
ledger on encoding drift.

`Message<Key>` contains a `u64` message id plus a `Payload<Key>`.
`Payload<Key>` is an enum with three variants:

- `Request(Key)` tagged with `0`,
- `Response(Bytes)` tagged with `1`,
- `Error` tagged with `2`.

Putting these types under `CodecConformance` means the ledger now watches for
drift in:

- field ordering,
- tag assignment,
- length encoding of response bytes,
- and the behavior of the derived `Arbitrary` instances that populate the test
  surface.

This is exactly the class of surface where a few hand-written examples are too
weak. The wrapper subjects a large generated family of messages to the same
stability discipline.

### 9.2 Handshake: bespoke transcript-level stability

`cryptography/src/handshake/conformance.rs` takes a different approach.

Its `Handshake` implementation does not encode one type. It replays an entire
two-party handshake:

- generate dialer and listener keys,
- run `dial_start`,
- run `listen_start`,
- run `dial_end`,
- run `listen_end`,
- send a random plaintext from dialer to listener,
- record the ciphertext and the recovered plaintext,
- then do the same in the other direction.

Each stage appends encoded artifacts to a log vector.

That means the resulting ledger entry protects more than one wire type. It
protects the protocol transcript as exercised by that deterministic replay:

- greeting formats,
- acknowledgement formats,
- transcript wiring,
- transport framing,
- send/receive symmetry,
- and the fact that ciphertext differs from plaintext while decryption still
  recovers the original message.

This is the right kind of bespoke conformance. The compatibility promise is not
"one type still encodes the same way." It is "the handshake mechanism still
behaves the same way."

### 9.3 Journal storage: bespoke file-layout stability

`storage/src/journal/conformance.rs` is even more instructive because it shows
how conformance reaches past bytes on the wire and into storage layout.

It defines bespoke `Conformance` implementations for several journal shapes:

- `ContiguousFixed`,
- `ContiguousVariable`,
- `SegmentedFixed`,
- `SegmentedGlob`,
- `SegmentedVariable`,
- `SegmentedOversized`.

Each implementation follows the same high-level pattern:

1. create a deterministic runtime runner seeded from the conformance seed,
2. initialize a journal with partition names derived from that seed,
3. generate deterministic data through the runtime context,
4. append data, often across multiple sections,
5. `sync` the data,
6. drop the journal,
7. return `context.storage_audit().to_vec()`.

That last step is the conceptual heart of the case study.

The ledger is not recording the input data itself. It is recording the audited
storage outcome after the journal has executed its writes and syncs. So the
ledger protects facts such as:

- which blobs were created,
- how sections were distributed,
- how fixed versus variable records were laid out,
- how oversized value/index partitions interacted,
- and whether the persisted footprint still matches prior releases.

This is a strong example of concept-first conformance design. The storage layer
does not ask, "Did one record still encode?" It asks whether the engine still
produced the same durable layout story.

### 9.4 MMR root stability: bespoke algorithmic stability

`storage/src/merkle/mmr/conformance.rs` is the smallest bespoke example, and
that makes it especially clear.

`MmrRootStability` builds an MMR using `seed` as the number of inserted
elements, then returns the final root bytes.

That means the ledger entry protects the algorithmic semantics of root
computation across a range of tree sizes. It is not a storage layout and not a
codec. It is the claim that:

> after replaying this deterministic sequence of insertions, the derived root is
> still the same.

This is exactly what bespoke conformance is for: protecting a deterministic
mechanism that matters even though its natural output is not "a single encoded
message."

---

## 10. The Workspace Really Uses This

The repository answers the question directly: this crate is used across the
workspace, not just in one corner of it.

At the time of writing, the workspace contains **10** crate-local
`conformance.toml` files with **219** tracked entries in total:

| Crate | Ledger entries |
| --- | ---: |
| `codec` | 53 |
| `cryptography` | 47 |
| `consensus` | 42 |
| `storage` | 41 |
| `utils` | 15 |
| `p2p` | 7 |
| `math` | 5 |
| `coding` | 4 |
| `runtime` | 3 |
| `resolver` | 2 |

That distribution tells us something important.

The ledger is not confined to one layer. It appears in:

- foundational encoding crates,
- cryptography and handshake machinery,
- storage engines and proof structures,
- consensus and networking layers,
- support utilities.

In other words, the crate has become a cross-workspace compatibility
discipline, not a local testing trick.

---

## 11. Operational CI And Release Flow

Once you understand the code paths, the release discipline becomes clear.

### 11.1 Adding a new conformance surface

When an author introduces a new conformance test:

1. they define the surface, either via `CodecConformance<T>` or a bespoke
   `Conformance` implementation,
2. they register it with `conformance_tests!`,
3. they run the test locally,
4. if the ledger entry does not yet exist, the test bootstraps it into the
   crate's `conformance.toml`,
5. the resulting ledger diff is committed and reviewed.

The important review artifact is not only the code. It is the combination of:

- the new `commit(seed)` definition,
- the chosen `n_cases`,
- and the new ledger entry.

### 11.2 Verifying a normal release

On a routine change, the intended path is verification:

```bash
just test-conformance
```

or a targeted crate-level equivalent.

CI recomputes the live digests and expects the checked-in ledger to match.
If not, the release candidate is saying something different than the repository
previously promised.

### 11.3 Handling an intentional compatibility change

If a change is deliberate, the team regenerates the ledger:

```bash
just regenerate-conformance
```

or, at the lower level:

```bash
RUSTFLAGS="--cfg generate_conformance_tests" cargo test
```

That is the moment when a compatibility event becomes explicit in version
control. The ledger diff is now part of the review discussion.

### 11.4 How this interacts with Commonware stability levels

The repository-level guidance matters here.

- At **ALPHA**, breaking changes are permitted, but conformance still makes them
  visible.
- At **BETA** and above, wire and storage compatibility carry stricter
  obligations. A ledger diff is no longer just a test update. It may imply a
  migration path, release notes, or a stronger review bar.

That is one reason the crate is valuable even when breakage is allowed. The
ledger turns "we changed something" into a concrete, reviewable artifact.

---

## 12. Failure Modes And Limits

`commonware-conformance` is strong, but it is not magical.

It does not prove semantic correctness. It proves that the recorded
deterministic replay surface did or did not drift.

That leaves several limits:

- if the bug lives outside the sampled seed space, the ledger will not see it;
- if `commit(seed)` is not actually deterministic across runs or platforms, the
  ledger becomes noise;
- if the chosen commitment bytes omit an important aspect of behavior, the
  ledger cannot protect that omitted aspect;
- if the behavior change is intentional, a human still has to decide whether it
  is an acceptable release event.

The main failure modes line up exactly with the ledger model:

- a missing entry means the surface is not yet recorded,
- a hash mismatch means the recorded behavior changed,
- an `n_cases` mismatch means the recorded envelope changed.

That is why conformance belongs beside unit tests, integration tests, the
deterministic runtime, and fuzzing. It is excellent at catching silent
compatibility drift. It is not a replacement for every other kind of evidence.

---

## 13. How To Read The Source

Read the code in the order the lecture built the argument.

1. Start with `conformance/src/lib.rs`.
   This is the ledger engine: `Conformance`, digest construction, file locking,
   verification mode, regeneration mode, and panic messages.

2. Then read `conformance/macros/src/lib.rs`.
   This is where the ledger becomes enforceable at scale. Watch how the macro
   standardizes function names, type keys, manifest-rooted file paths, and test
   grouping.

3. Then read `codec/src/conformance.rs`.
   This is the wrapper admission gate for most real wire-format surfaces.

4. Then compare bespoke callers.
   Use `cryptography/src/handshake/conformance.rs`,
   `storage/src/journal/conformance.rs`, and
   `storage/src/merkle/mmr/conformance.rs` to see how different domains choose
   different commitment bytes.

5. Then inspect real ledger files.
   Read `resolver/conformance.toml`, `cryptography/conformance.toml`, and
   `storage/conformance.toml` to see what the checked-in receipts actually look
   like in practice.

If you read in that order, the crate stops looking like a helper and starts
looking like what it really is: a repository-wide discipline for making
compatibility claims auditable.

---

## 14. Glossary

- **silent compatibility drift**: a stable surface changes meaning without an
  obvious runtime failure.
- **compatibility ledger**: the checked-in `conformance.toml` record of expected
  digests.
- **behavior, not bytes**: the principle that conformance protects a
  deterministic replay surface, not one example fixture.
- **`commit(seed)`**: the deterministic function that turns one seed into the
  bytes recorded by the ledger.
- **`n_cases`**: the size of the deterministic sweep that defines the sampled
  surface.
- **verification mode**: the default mode that compares live behavior against
  the checked-in ledger and panics on drift.
- **regeneration mode**: the explicit mode that rewrites the ledger for an
  intentional compatibility change.
- **wrapper-style conformance**: using `CodecConformance<T>` to protect the
  encoding of generated values.
- **bespoke conformance**: writing a domain-specific `Conformance`
  implementation to protect a higher-level mechanism such as a handshake,
  storage layout, or root computation.
