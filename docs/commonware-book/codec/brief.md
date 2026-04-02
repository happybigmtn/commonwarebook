# Chapter Brief: commonware-codec

## 1. Module Purpose

`commonware-codec` is about more than serialization. It defines the byte
contract a protocol can trust when input may be adversarial.

The chapter should teach three linked ideas:

1. **stable bytes**: the wire form must not drift across runs or machines,
2. **canonical representation**: one logical value should have one accepted
   encoding,
3. **bounded decoding**: untrusted input does not get to choose unbounded work.

That is why the crate centers on `Write`, `EncodeSize`, `Read`, and `Decode`.

- `Write` defines how a value is packed into bytes.
- `EncodeSize` defines the exact size of that shipment.
- `Read` reconstructs the value under caller-supplied policy.
- `Decode` adds the final border rule: consume the whole buffer, or fail.

The chapter's main teaching frame should stay visible throughout: a customs
office enforcing a contract. Bytes arrive with paperwork. The codec checks the
declared shape, the allowed size, and the absence of hidden cargo before the
value is admitted.

The stronger point to emphasize in this expansion pass is that the crate's
strictness is not stylistic. It is how the wire format stays useful to higher
layers that hash, sign, compare, and pin those bytes over time.

That means the chapter now needs to teach these specifically:

- `RangeCfg` as receiver-owned policy rather than sender-owned data,
- varint as a grammar with canonical spellings,
- `Lazy<T>` as deferred work under unchanged validation rules,
- canonical collection ordering as an admission rule, not post-processing,
- the error enum as a map from failure modes to invariants,
- extension traits as ergonomic currying of real config shapes,
- and conformance as the mechanism that turns "stable bytes" into a checked
  regression boundary.

This is what makes the crate safe at protocol boundaries. The codec is not a
formatter. It is the border policy for meaning carried in bytes.

---

## 2. Source Files That Matter Most

### `codec/src/codec.rs`
Why it matters: contains the core contract and the exact divide between
outgoing size declarations, incoming policy-driven reads, and full-buffer
decoding.

### `codec/src/config.rs`
Why it matters: defines `RangeCfg`, the small generic type that makes bounded
decoding receiver-controlled policy.

### `codec/src/varint.rs`
Why it matters: contains both the public varint wrappers and the real grammar
enforcement in `Decoder<U>::feed`.

### `codec/src/types/primitives.rs`
Why it matters: establishes the baseline rules for big-endian fixed-width
primitives, `usize`, `bool`, `Option`, and the `u32` portability cap on
encoded lengths.

### `codec/src/types/lazy.rs`
Why it matters: shows how deferred decoding works, why `Lazy<T>` needs
`T: FixedSize` for `Read`, and how stored bytes can be re-emitted without a
decode-reencode cycle.

### `codec/src/types/mod.rs`
Why it matters: contains the ordered map and set helper loops that make
ascending-order and duplicate-free decoding mechanical.

### `codec/src/types/hash_map.rs` and `codec/src/types/hash_set.rs`
Why they matter: show how unordered in-memory collections are forced into one
canonical wire spelling.

### `codec/src/extensions.rs`
Why it matters: makes the real config shapes easier to call without changing
their semantics.

### `codec/src/error.rs` and `codec/src/util.rs`
Why they matter: define the failure vocabulary and the low-level helpers that
surface structural failures crisply.

### `codec/src/conformance.rs`
Why it matters: links `Encode` to the conformance system and turns byte
stability into an explicit regression boundary.

---

## 3. Chapter Outline

```text
1. Why a Codec Must Be a Contract
   - The problem is not "serialization"; the problem is trusted bytes
   - Stable bytes, canonical representation, and bounded decoding
   - Why protocol boundaries need stricter rules than convenience codecs

2. Mental Model: A Customs Office for Meaning
   - Bytes arrive with paperwork
   - The receiver verifies size, shape, and allowed limits
   - "Nothing hidden in the box" as the model for full-buffer decoding

3. Core Ideas
   - `Write` and `EncodeSize` as the outgoing contract
   - `Read` as bounded inspection with `Cfg`
   - `RangeCfg` as receiver-owned policy
   - `Decode` as final clearance
   - `usize` as compact but portable length encoding
   - varint as strict grammar with canonical spellings
   - canonical collection ordering as correctness
   - `Lazy<T>` as deferred work under unchanged rules
   - extension traits as ergonomic policy application
   - conformance as proof that stability survives revisions

4. How Bytes Move Through the Machine
   - Encode: declare size, allocate once, write once, verify
   - Decode: inspect fields, enforce bounds, reconstruct, consume all bytes
   - Concrete cases: primitives, length-bearing values, varints, collections,
     `Lazy<T>`, extensions, conformance linkage

5. What Pressure the Design Absorbs
   - Hostile length prefixes
   - Ambiguous compact integer spellings
   - Truncated and padded buffers
   - Cross-platform drift
   - Non-canonical collection encodings
   - Stability drift across time

6. Failure Modes and Limits
   - Implementation bugs versus decode errors
   - Error-to-invariant table
   - What the codec can verify structurally
   - What only the application can verify semantically

7. How to Read the Source
   - Start with `codec.rs`
   - Then `config.rs` and `varint.rs`
   - Then `primitives.rs`
   - Then collection, lazy, extension, error, and conformance files

8. Glossary and Further Reading
   - `EncodeSize`
   - `RangeCfg`
   - `UInt` and `SInt`
   - canonical representation
   - `Lazy`
   - conformance
```

---

## 4. System Concepts to Explain at Graduate Depth

1. **Encoding is a contract, not a guess.** `EncodeSize` lets the caller
   allocate the exact buffer size before writing. `Encode` checks that the write
   matched the declared size.

2. **Decoding is a policy decision.** `Read` takes a `Cfg` so the caller can
   bound lengths and decoded work instead of trusting sender-declared shape.

3. **`RangeCfg` belongs to the receiver.** It is not wire data. It is local
   admission policy, and its generic conversions let policy move between integer
   domains without being rewritten.

4. **Varint is strict syntax, not a free-for-all.** The incremental decoder
   rejects overlong zero spellings, impossible continuations, and values that do
   not fit the target width.

5. **`usize` is portable only because it is constrained.** Restricting encoded
   `usize` values to `u32` keeps the wire format stable across architectures.

6. **Canonical form is part of correctness.** A map or set should not admit
   several valid wire spellings. Canonical ordering makes byte identity usable
   by higher layers.

7. **`Lazy<T>` defers cost, not truth.** It postpones decoding work while
   preserving the same bytes, config, and eventual validation obligations.

8. **Extensions are ergonomic currying, not new semantics.** `ReadRangeExt` and
   `DecodeRangeExt` exist because real config shapes are nested tuples that
   callers should not have to spell repeatedly.

9. **The error enum names invariant failures.** Each variant corresponds to a
   different structural promise: completeness, singularity, policy, canonical
   grammar, or type-local validity.

10. **Conformance is operationalized stability.** `CodecConformance<T>` turns
    `Encode` into deterministic committed bytes so format drift becomes visible
    in fixtures rather than folklore.

---

## 5. Interactive Visualizations to Build Later

1. **Codec contract flow**: show `Write -> EncodeSize -> Encode -> Read ->
   Decode` as a customs-inspection loop with explicit rejection branches.

2. **Range policy explorer**: vary inclusive, exclusive, and exact `RangeCfg`
   bounds and show which decoded lengths are admitted or rejected.

3. **Varint grammar plate**: feed bytes one at a time and show when the
   incremental decoder accepts, continues, or rejects, including overlong
   spellings.

4. **Canonical collection demo**: insert unordered map or set entries in
   different orders and show the encoded bytes stay identical while non-canonical
   incoming orders are rejected.

5. **Lazy field walkthrough**: show a fixed-size field being carved out,
   deferred, and only decoded when accessed.

6. **Conformance bridge**: show deterministic value generation, encoding, and
   digest comparison as one stability pipeline.

---

## 6. Claims-to-Verify Checklist

- [ ] `EncodeSize` and `Write` agree for all covered primitive and collection
  types.
- [ ] `Decode` rejects inputs with trailing bytes.
- [ ] `RangeCfg` accepts inclusive, exclusive, exact, and unbounded cases as
  described.
- [ ] `usize` encoding rejects values above `u32::MAX`.
- [ ] canonical varint examples are accurate, including rejection of overlong
  zero spellings.
- [ ] ordered map and set decoding rejects duplicate or descending entries.
- [ ] `HashMap` and `HashSet` encode in deterministic sorted order.
- [ ] `Lazy<T>` is described with the correct `FixedSize` requirement on `Read`.
- [ ] extension traits are described as wrappers over existing config shapes,
  not alternate semantics.
- [ ] `CodecConformance<T>` is described as deterministic generation plus
  encoding, with hashing handled by the conformance layer.
