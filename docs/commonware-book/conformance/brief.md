# Chapter Brief: commonware-conformance

## 1. Module Purpose

`commonware-conformance` is the repository's compatibility ledger. It exists to
catch silent drift in deterministic behavior before that drift ships as an
accidental release promise.

The core idea is simple but stronger than ordinary fixtures:

- define a deterministic commitment for a type or mechanism,
- replay a visible seed sweep `0..n_cases`,
- hash the whole ordered replay,
- check the digest into `conformance.toml`,
- and make CI compare live behavior against that checked-in receipt.

That framing should stay front and center throughout the chapter:

> conformance is not about preserving one example byte string; it is about
> preserving the recorded behavior envelope of a deterministic mechanism.

The expanded chapter should teach five implementation-backed ideas especially
well:

1. **Digest construction is the contract.** The crate hashes each committed
   value in seed order, prefixing each value with its little-endian `u64`
   length before feeding the bytes into SHA-256.
2. **Ledger file discipline is deliberate.** Hash computation happens before the
   file lock; the lock only covers the shared read/parse/update/write critical
   section for `conformance.toml`.
3. **Verification and regeneration are different social modes.** Default mode
   detects drift and panics on mismatches. Regeneration mode rewrites the
   ledger only when maintainers explicitly opt in.
4. **Macro expansion is part of the safety story.** `conformance_tests!`
   standardizes test naming, type keys, manifest-rooted file paths, and test
   grouping across the workspace.
5. **Real consumers span layers.** The chapter should compare wrapper-style
   wire-format callers with bespoke callers for handshakes, storage audits, and
   root computations.

---

## 2. Source Files That Matter Most

### `conformance/src/lib.rs`
**Why it matters:** This is the ledger engine. It defines `Conformance`,
computes the digest, locks and rewrites `conformance.toml`, verifies mismatches,
and implements regeneration mode.

### `conformance/macros/src/lib.rs`
**Why it matters:** This is the hygiene layer. It turns types into concrete test
functions, derives canonical type keys from `module_path!()`, roots the ledger
path at `CARGO_MANIFEST_DIR`, and attaches the `conformance` test group.

### `codec/src/conformance.rs`
**Why it matters:** This is the main wrapper admission path. It shows how a
seeded `ChaCha8Rng`, `arbitrary::Unstructured`, and `Encode` become
`CodecConformance<T>`.

### `resolver/src/p2p/wire.rs`
**Why it matters:** This is the cleanest wrapper-style case study. It puts
`Message<u8>` and `Payload<u8>` under conformance and makes wire-level drift
visible.

### `cryptography/src/handshake/conformance.rs`
**Why it matters:** This is the best bespoke protocol case study. It records a
full handshake transcript plus encrypted message exchange rather than a single
encoded value.

### `storage/src/journal/conformance.rs`
**Why it matters:** This is the strongest storage case study. It uses the
deterministic runtime to build journals, sync them, then records the storage
audit instead of the input data.

### `storage/src/merkle/mmr/conformance.rs`
**Why it matters:** This is the compact algorithmic case study. It protects MMR
root computation across a deterministic range of tree sizes.

### Real ledger files
**Why they matter:** `resolver/conformance.toml`, `cryptography/conformance.toml`,
and `storage/conformance.toml` prove the ledger is not theoretical. The current
workspace has 10 ledger files and 219 tracked entries.

---

## 3. Updated Chapter Outline

```text
1. Why silent compatibility drift is the real enemy
   - Releases can stay "working" while their promises move
   - Why fixtures are too weak for this job

2. Mental model: a compatibility ledger
   - Checked-in receipt per tracked surface
   - `n_cases` as the declared sampled envelope

3. What counts as behavior
   - `Conformance::commit(seed)` as the definition of the protected surface
   - Encoding, transcript, storage audit, root computation as different choices

4. Digest construction, step by step
   - ordered seed replay
   - length-prefixing as ambiguity protection
   - direct SHA-256 over the replay stream
   - lowercase hex as ledger representation

5. Ledger load/lock/write discipline
   - compute first, lock later
   - exclusive OS-level lock around shared file mutation
   - locked read/parse/update/write path
   - `BTreeMap` as stable ledger ordering

6. Verification vs regeneration workflow
   - missing entry bootstrapping
   - hash mismatch failure
   - `n_cases` mismatch failure
   - regeneration mode as explicit acknowledgement
   - repository commands: `just test-conformance`,
     `just regenerate-conformance`

7. Macro expansion as hygiene
   - how `conformance_tests!` parses entries
   - type-to-function-name derivation
   - key construction from `module_path!()`
   - path construction from `CARGO_MANIFEST_DIR`
   - near-literal expansion example

8. Wrapper-style vs bespoke conformance
   - `CodecConformance<T>` as the standard wrapper
   - custom `Conformance` impls for higher-level mechanisms

9. Real consumer case studies
   - resolver wire messages
   - cryptography handshake transcript
   - journal storage audits
   - MMR root stability

10. Operational CI and release flow
    - first admission into the ledger
    - normal verification in CI
    - intentional regeneration
    - interaction with Commonware stability levels

11. Failure modes and limits
    - sampled surface limits
    - determinism assumptions
    - omission risk in poorly chosen commitments

12. How to read the source
```

---

## 4. System Concepts To Explain At Graduate Depth

1. **The digest records an ordered replay, not a set of samples.**
   Seed order is part of the contract. Reordering or resizing the sweep changes
   the meaning of the ledger.

2. **Length-prefixing is what makes the replay unambiguous.**
   The crate hashes each committed length as little-endian `u64` before hashing
   the committed bytes so different case boundaries cannot collapse into the
   same concatenation.

3. **The ledger file is a concurrency boundary.**
   The expensive replay happens without a lock. The shared TOML mutation happens
   under an exclusive lock. This is how the crate stays parallel without
   allowing racy ledger updates.

4. **Verification and regeneration are intentionally different workflows.**
   Default mode protects the existing promise. Regeneration mode writes a new
   promise. The difference is social as much as technical.

5. **The macro is a repository-wide bookkeeping rule.**
   `conformance_tests!` keeps test names, type keys, file paths, and grouping
   consistent so the ledger remains attributable and collision-free.

6. **`CodecConformance<T>` is a large-scale leverage point.**
   Once a type supports deterministic `Arbitrary` generation and deterministic
   `Encode`, it can join the ledger without bespoke code.

7. **Bespoke commitments let the ledger protect mechanisms, not just values.**
   The handshake logs a transcript. The journal returns a storage audit. The
   MMR case records a derived root. These are different kinds of stability
   claims built on the same ledger infrastructure.

8. **The checked-in TOML files are part of the release process.**
   A conformance diff is not test noise. It is a compatibility event that
   review, CI, and release notes may need to account for, especially at BETA or
   higher stability levels.

---

## 5. High-Value Tables And Examples To Keep

1. **Operational outcomes table**
   Rows: missing entry, hash mismatch, `n_cases` mismatch, regeneration mode.

2. **Wrapper vs bespoke comparison table**
   Columns: pattern, best use case, protected behavior.

3. **Ledger coverage table from real `conformance.toml` files**
   Current counts:
   - `codec`: 53
   - `cryptography`: 47
   - `consensus`: 42
   - `storage`: 41
   - `utils`: 15
   - `p2p`: 7
   - `math`: 5
   - `coding`: 4
   - `runtime`: 3
   - `resolver`: 2
   - total: 219 across 10 files

4. **Near-literal macro expansion example**
   Use the resolver `CodecConformance<Message<u8>>` case because it shows all of
   the important generated pieces without much domain noise.

---

## 6. Claims-To-Verify Checklist

- [ ] `compute_conformance_hash` hashes seeds in ascending order `0..n_cases`.
- [ ] Each committed value contributes its `u64` little-endian length before its
      bytes.
- [ ] The final digest is SHA-256 encoded as lowercase hex.
- [ ] Digest computation happens before the file lock in both verification and
      regeneration paths.
- [ ] The ledger file is opened with read/write/create and then exclusively
      locked before mutation.
- [ ] Verification mode inserts missing entries but panics on hash mismatch.
- [ ] Verification mode treats `n_cases` mismatch separately from hash mismatch.
- [ ] Regeneration mode rewrites or inserts the entry without comparing against
      the old hash.
- [ ] The macro keys entries with `concat!(module_path!(), "::", type_name)`.
- [ ] The macro roots the ledger path at
      `concat!(env!("CARGO_MANIFEST_DIR"), "/conformance.toml")`.
- [ ] `CodecConformance<T>` uses seeded `ChaCha8Rng` plus `Arbitrary` plus
      `Encode`.
- [ ] The handshake case study records a multi-step transcript, not one message.
- [ ] The journal case study records `storage_audit()` output after writes and
      syncs.
- [ ] The MMR case study records final root bytes after deterministic inserts.
