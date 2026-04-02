# commonware-codec

## A Customs Office for Stable Bytes

---

## Backgrounder: Bytes, Grammars, and Canonical Forms

Before a value becomes protocol data, it has to leave the comfortable world of
language-level types and enter the rough world of bytes. That transition is
where many systems get into trouble.

At the representation level, one logical value can often be written in several
ways. Endianness can flip the byte order. Variable-length encodings can spell
the same number with different lengths. Collection encodings can ignore or keep
ordering, padding, and trailing bytes. If the decoder is casual about any of
those choices, two machines may disagree about what the same wire data means.

The naive approach is to say, "just serialize it" and trust the library. That
works only if all sides already agree on the exact spelling rules, the parser
rejects ambiguity, and the input cannot make the decoder do unbounded work. In
practice, those assumptions break quickly:

- a permissive parser may accept multiple byte strings for one value,
- a length prefix may be trusted too early,
- a trailing blob may be ignored instead of rejected,
- and an attacker can turn decoding into a memory or CPU drain.

That is why byte formats need to be thought of as grammars, not just blobs.
Each format says what sequences are legal, how one value is delimited from the
next, and which spelling is the canonical one. Canonical form matters because it
lets the rest of the protocol use bytes as stable names rather than as fuzzy
suggestions.

There is also a tradeoff between flexibility and safety. A format that accepts
many spellings is easy to evolve in the short term, but it becomes hard to
compare, hash, sign, or store deterministically. A format that is too rigid may
be less convenient, but it gives the rest of the system one consistent story.

`commonware-codec` stands on that stricter side of the line. It treats bytes as
a public contract with exact spelling rules and exact bounds, because protocol
code cannot afford to guess what the sender meant.

## 1. What Problem Does This Solve?

When a protocol crosses a machine boundary, a value stops being a Rust type and
becomes bytes. At that moment, "it serialized" is not a meaningful guarantee.
The real questions are harsher:

- Do these bytes mean exactly one value?
- Will every machine encode that value the same way?
- Can the decoder bound how much memory and work it will spend?
- Will the boundary reject trailing junk instead of quietly ignoring it?

`commonware-codec` exists to answer those questions with a contract.

That contract has three parts.

1. **Stable bytes**: a value must have a predictable wire form.
2. **Canonical representation**: one logical value gets one accepted encoding.
3. **Bounded decoding**: untrusted input does not get to choose unlimited work.

That is why the crate is built around `Write`, `EncodeSize`, `Read`, and
`Decode`.

- `Write` says how a value becomes bytes.
- `EncodeSize` says exactly how many bytes that write will need.
- `Read` says how to reconstruct the value, with caller-supplied policy.
- `Decode` adds the last protocol rule: consume the whole buffer, or fail.

Many libraries can turn values into bytes. Fewer treat the wire format as a
discipline. `commonware-codec` does. It assumes the sender may be careless,
malicious, or simply running on a different machine. The crate's job is to make
those differences irrelevant at the byte boundary.

That is the right way to read the rest of the chapter. This is not a tour of a
serializer. It is a lecture about how to make bytes safe enough to carry
meaning.

---

## 2. Mental Model: The Customs Office and the Contract

The most useful mental model is a customs office.

A package arrives at the border with paperwork attached. The paperwork says what
the package is, how large it may be, and what shape the contents should have.
The officer does not trust the label. The officer opens the box, counts what is
inside, compares the contents against the declared limits, and refuses entry if
anything is off.

That is what `commonware-codec` does for protocol bytes.

Keep that border picture in mind through the rest of the crate:

- `Write` is the packing procedure.
- `EncodeSize` is the declared shipment size.
- `Read` is the inspection process.
- `RangeCfg` is the import policy.
- `Decode` is the clearance stamp that says, "nothing else was hidden in the
  box."

The contract behind that office is simple:

1. the sender must present a stable byte layout,
2. the wire format must not admit multiple spellings for the same value,
3. and the receiver must stay within a caller-chosen budget while decoding.

Once you adopt that model, the crate becomes easier to reason about. Every
trait and concrete impl either defines the paperwork, checks it, or enforces
the budget.

That is also why later sections keep returning to the same theme. Stable bytes,
canonical form, and bounded decoding are not three separate features. They are
three faces of the same border policy.

---

## 3. The Core Ideas

With the customs office in view, the core traits divide cleanly by job.

### `Write` and `EncodeSize` define the outgoing contract

`Write` knows how to put a value into a `BufMut`. `EncodeSize` knows how many
bytes that operation must consume.

Those traits are separate on purpose. Writing and counting are different
obligations, and a codec becomes unreliable as soon as it treats them as a
fuzzy estimate. `Encode` joins the two together and checks its own work after
the write. That is how the outgoing path produces stable bytes instead of
"roughly the right layout."

In the customs model, the package and the paperwork must match exactly.

If they do not, `Encode` panics. That is not framed as recoverable input
failure. It is a bug in the codec implementation.

### `Read` makes decoding a policy decision

`Read` reconstructs a value from a `Buf`, but it also takes a `Cfg` parameter.
That small design choice is what turns decoding into a controlled operation.

The config lets the caller say, "I will accept a vector up to this length," or
"this field may occupy only this range." Without that hook, the decoder would
be forced to trust the sender's declared shape. With it, the caller sets the
budget, and the decoder enforces it.

That is bounded decoding in one sentence: the receiver decides how much work a
piece of untrusted input is allowed to cause.

### `RangeCfg` is policy, not data

`RangeCfg` is the simplest expression of that idea. It is not a value carried on
the wire. It is a value supplied by the reader.

That distinction matters because it decides who is in charge.

- The sender may declare a length.
- The receiver decides whether that length is admissible.

`RangeCfg` is deliberately small. It stores a start bound and an end bound and
implements `RangeBounds<T>`, so callers can construct policy from ordinary Rust
ranges: `0..=1024`, `1..`, `..=32`, `..`, or `RangeCfg::exact(7)`.

The design gets stronger when you notice what is *not* there. `RangeCfg` does
not know anything about `Vec`, `Bytes`, or `HashMap`. It is generic over `T`.
That makes it portable policy rather than container-specific policy.

The conversion impls in `config.rs` sharpen that point. A range over
`NonZeroU32` can become a range over `u32` or `usize`. That means higher layers
can express the most specific local invariant they know, and lower layers can
still consume the policy in the integer type they need.

So `RangeCfg` is not just a guardrail. It is where authority changes hands from
the sender to the receiver.

### `Decode` seals the border

`Read` can successfully parse one value from the front of a buffer. Protocol
boundaries usually need something stricter: they need proof that the buffer held
exactly one value and nothing else.

`Decode` adds that rule. If bytes remain, decoding fails with `ExtraData`.

This is the part that makes the customs-office model feel complete. It is not
enough to inspect the declared item. The officer must also confirm that the box
contains no hidden compartment.

### `FixedSize` marks the easy cases

Some values always occupy the same number of bytes. For those types, size is not
a computation. It is part of the type's identity.

That matters because fixed-size values are the simplest proof that stable bytes
are possible. A `u32`, `bool`, `Ipv4Addr`, or fixed-size array does not need a
length prefix, and it does not need negotiation with the caller. The contract is
short and exact.

It also explains a later design choice: `Lazy<T>` can only implement `Read` when
`T: FixedSize`. If the outer decoder does not know where `T` ends, it cannot
defer parsing safely. A lazy boundary still needs a precise byte window.

### `usize` is variable-size by policy, not by accident

Most primitive types in `types/primitives.rs` are fixed-width and big-endian.
`usize` is the exception.

It is varint-encoded because lengths and counts are often small, but it is also
restricted to values that fit in `u32`. That is the portability rule that keeps
the same logical length from acquiring different wire forms on 32-bit and 64-bit
machines.

So the `usize` story has three layers:

1. use a compact representation for small counts,
2. reject architecture-dependent magnitudes,
3. run the result through `RangeCfg` before trusting it.

That is a good example of the crate's style. A convenience choice is accepted
only after it has been fenced by stability and policy.

### Varint is a grammar, not a byte trick

Varint is easy to describe loosely and dangerous to implement loosely.

In this crate, varint is treated as a language with syntax rules:

- each byte contributes 7 data bits,
- the top bit says whether another byte must follow,
- the final byte must be the first byte whose continuation bit is clear,
- and the encoding must stop as soon as the value is fully spelled.

That last rule is what turns compactness into canonicality.

For example:

- `0` is accepted as `[0x00]`,
- `300` is accepted as `[0xAC, 0x02]`,
- but overlong zero such as `[0x80, 0x00]` is rejected.

The incremental `Decoder<U>::feed` in `varint.rs` makes the grammar explicit.
Once decoding has progressed beyond the first byte, a later all-zero byte is
illegal because it proves the sender kept talking after the value was already
finished. On the last possible byte, any set bits beyond the target width are
illegal because they would overflow the type or imply an impossible extra
continuation.

That is why `InvalidVarint` means more than "could not parse." It means the byte
sequence violated the unique spelling rules for this integer width.

`SInt` adds ZigZag encoding on top of the same grammar. Negative numbers are not
given a separate varint language. They are mapped into the unsigned one.

### Canonical collections are part of correctness

Stable bytes are not enough if the same logical value can appear on the wire in
many different forms. Canonical representation closes that gap.

The crate handles ordered and unordered collections differently.

- `BTreeMap` and `BTreeSet` already have a defined iteration order, so the wire
  form can follow it directly.
- `HashMap` and `HashSet` do not, so the writer sorts entries before emitting
  them.

The important part is the read path. `read_ordered_map` and `read_ordered_set`
do not merely deserialize items and then sort them in memory. They require the
incoming bytes to already be in ascending order and to be duplicate-free.

So the decoder is not saying, "I can recover a valid map from this mess." It is
saying, "I will only accept the one wire spelling this logical map is supposed to
have."

That difference is what makes the encoded bytes safe to hash, sign, compare, and
pin in conformance fixtures.

### `Lazy<T>` defers work without changing truth

`Lazy<T>` is the crate's most instructive "advanced" type because it looks like
an optimization and turns out to be a policy statement.

`Lazy<T>` stores either:

- an already available `T`, or
- pending bytes plus the `Cfg` needed to decode `T` later.

That means laziness here is not "skip validation forever." It is "capture the
same future decode that would have happened now, but move the cost."

Two details in `types/lazy.rs` are worth noticing.

First, on `std`, the actual decode is protected by a `OnceLock<Option<T>>`. The
first `get()` performs the work and caches either success or failure. Later
calls do not decode again.

Second, `Write` and `EncodeSize` prefer the pending raw bytes when they exist.
That lets `Lazy<T>` round-trip the original accepted encoding without forcing a
decode and re-encode cycle first.

`Lazy<T>` is also intentionally narrow. The `Read` impl exists only when
`T: FixedSize`. A lazy reader can safely take exactly `T::SIZE` bytes from the
buffer and hold them for later. Without a fixed width, the codec would need some
other framing story before deferral would be sound.

### Extension traits improve ergonomics, not semantics

`ReadExt`, `DecodeExt`, `ReadRangeExt`, and `DecodeRangeExt` do not weaken the
contract. They only compress recurring call patterns.

The config shapes in real implementations make the point concrete:

- primitives usually use `Cfg = ()`,
- a `Vec<T>` uses `(RangeCfg<usize>, T::Cfg)`,
- a `HashMap<K, V>` uses `(RangeCfg<usize>, (K::Cfg, V::Cfg))`.

The extension traits exist so callers can keep using the real policy while
writing shorter code.

`ReadExt` means "this type needs no config." `DecodeExt` means "this type's
config is unit-like and can be defaulted." `ReadRangeExt` and `DecodeRangeExt`
mean "this type starts with a length policy, and the rest of the config can be
defaulted."

They are shorthand for the same policy. The law does not change; the call site
gets shorter.

### Conformance turns the contract into a regression boundary

The last core idea lives slightly outside the encode and decode path, but it is
where the chapter's promises become operational.

`codec/src/conformance.rs` defines `CodecConformance<T>`, a tiny wrapper that
adapts any `T: Encode + Arbitrary` to the `commonware_conformance::Conformance`
trait. Its `commit(seed)` implementation does two things:

1. generate a deterministic `T` from `arbitrary` using a seeded `ChaCha8Rng`,
2. encode that value and return the bytes.

The conformance crate hashes those committed bytes and compares the digest
against the checked-in fixture.

So conformance is not "some tests exist." It is the place where stable bytes
become a versioned promise. If canonical collection ordering, varint grammar, or
primitive layout changes, the digest moves. The crate has to treat that as a
real event.

---

## 4. How Bytes Move Through the Machine

The encode path is intentionally dull in the best way. A predictable codec
should feel procedural.

1. Ask the value for its encoded size.
2. Allocate exactly that many bytes.
3. Write the value into the buffer.
4. Assert that the observed count matches the declared count.

That is the outgoing half of the contract. The sender does not guess, append,
and hope. It commits to an exact layout up front.

The decode path mirrors that discipline.

1. Read the next fixed-width field or declared length.
2. Apply the caller's config and bounds.
3. Reconstruct the value.
4. If the boundary asked for `Decode`, confirm that no bytes remain.

The sequence matters. First inspect the paperwork, then enforce the budget, then
admit the value, then check that nothing else came with it.

That abstract path becomes concrete in the type impls.

### Primitives: fixed-width values establish the baseline

In `types/primitives.rs`, fixed-width integers and floats use big-endian
encoding. That makes the wire form independent of host architecture, which is
the simplest possible example of stable bytes.

`bool` is also instructive. It is one byte wide, but the decoder accepts only
`0` and `1`. That means fixed-width does not imply permissive. Even simple
primitive layouts still get structural validation.

`Option<T>` shows the same style one layer up: a boolean tag first, then the
payload only when the tag is true. The crate does not use out-of-band nullability
or magic values. The wire form says what branch is present.

### `RangeCfg` in motion: the length is a claim, not an order

Length-bearing values such as `Vec<T>`, `Bytes`, `HashMap<K, V>`, and
`HashSet<K>` all share the same first move:

1. decode a `usize`,
2. check it against `RangeCfg`,
3. only then allocate or iterate.

That is why `usize::read_cfg` is so central. The length prefix does not directly
control memory allocation. It first passes through a local policy gate.

If the caller says "this field may be at most 64 bytes," then a sender-declared
length of 10,000 is not an expensive parse. It is `InvalidLength(10000)`.

Seen this way, `RangeCfg` is the codec's answer to a classic adversarial
question: who gets to choose the work budget? In this crate, the answer is
always the receiver.

### Varint worked example: accepted and rejected spellings

The varint grammar becomes clearer with concrete cases.

Accepted spellings:

- `0` -> `[0x00]`
- `1` -> `[0x01]`
- `127` -> `[0x7F]`
- `128` -> `[0x80, 0x01]`
- `300` -> `[0xAC, 0x02]`

Rejected spellings:

- `[0x80, 0x00]` for zero
  because the second byte proves the first byte should not have continued.
- any spelling whose final byte sets bits outside the target width
  because the value would overflow the chosen integer type.
- any spelling that continues past the last possible byte
  because the continuation bit itself becomes impossible at that point.

This is why the crate has both `UInt` and the incremental `Decoder<U>`. The
wrappers give ordinary encode and decode. The decoder exposes the grammar one
byte at a time for stream-oriented code without weakening the same rules.

### Canonical collections: accepted bytes versus "recoverable" bytes

Hash collections are where the distinction between "recoverable" and
"acceptable" matters most.

Suppose a `HashSet<u32>` logically contains `{1, 5}`.

Accepted encoding:

- length `2`,
- item `1`,
- item `5`.

Rejected encodings:

- length `2`, item `5`, item `1`
  because items do not ascend.
- length `2`, item `1`, item `1`
  because duplicate items are not canonical.

The same pattern holds for maps, with key order driving canonicality.

The loops in `types/mod.rs` make the check mechanical. They keep the previous
item in hand, read the next item, compare adjacency, and only then insert the
previous item into the target collection. The reader validates the local
ordering proof before committing each step.

That is a small algorithmic detail, but it reveals the crate's attitude. Canonical
representation is not a cosmetic post-processing pass. It is an admission rule.

### `Lazy<T>` worked example: defer the parse, keep the contract

Imagine a fixed-size type `T` whose decode is expensive because it performs extra
validation after reading its bytes.

With `Lazy<T>`, the outer decoder can:

1. carve out exactly `T::SIZE` bytes from the buffer,
2. store those bytes and the `Cfg`,
3. continue parsing the rest of the enclosing message,
4. decode `T` only if some later code actually asks for it.

That is useful for large message trees where only a subset of fields are needed
on every path.

The important point is what does *not* change:

- the bytes must still be structurally valid when `get()` runs,
- the same config is still used,
- and re-encoding can still emit the original stored bytes.

So `Lazy<T>` is not "maybe decode later if convenient." It is "freeze a future
decode with all of its original rules intact."

### Extensions: shorter calls to the same policy

The extension traits sit close to the API boundary because that is where config
noise is most visible.

Without them, callers often have to spell nested tuples just to say something
simple. A bounded vector of `u8` wants `(RangeCfg<usize>, ())`.
With `DecodeRangeExt`, the caller can instead say `Vec::<u8>::decode_range(buf,
0..=1024)`.

That is not a new decoding mode. It is the same `Read::Cfg`, assembled for you.

### Conformance linkage: why canonicality pays off

The conformance wrapper is where all of the chapter's local rules line up.

If `HashMap` encoding depended on hash iteration order, a deterministic seed
would still generate the same logical map, but the committed bytes could drift.
If varint accepted overlong spellings, two encoders could both be "compatible"
while disagreeing on the bytes that conformance is supposed to pin down.

Canonical collections and strict varint grammar are what make codec conformance
worth having. They make `encode()` behave like a proof artifact rather than a
mere transport convenience.

---

## 5. What Pressure This Design Is Built To Absorb

The answer is adversarial pressure.

A codec at a protocol boundary gets pushed on at every seam. Attackers lie about
lengths. Honest peers send truncated buffers. Different platforms disagree about
native representation. Unordered containers try to drift into many byte
spellings. Performance shortcuts tempt the decoder to trust the sender more than
it should.

`commonware-codec` is shaped by those pressures.

### Pressure 1: hostile length prefixes

If the sender chooses the work budget, the receiver loses. That is why lengths
flow through `RangeCfg` and why `usize` decoding is constrained. A length prefix
is treated as a claim to verify, not a command to obey.

### Pressure 2: ambiguous compact integers

Varint buys smaller length prefixes, but only if the grammar is tight. The crate
rejects overlong and impossible spellings because ambiguity in "small" integers
would infect every length-bearing type built on top of them.

### Pressure 3: truncated or padded buffers

If the buffer ends early, the crate returns `EndOfBuffer`. If extra bytes remain
after `Decode`, it returns `ExtraData`.

Those are two versions of the same principle: the border is exact at both ends.
The value must be complete, and it must be alone.

### Pressure 4: cross-platform drift

Big-endian fixed-width encoding and the `u32` cap on `usize` keep a value from
quietly changing its wire form when the architecture changes. Stable bytes have
to mean stable across machines, not just stable on the machine that wrote them.

### Pressure 5: non-canonical collection encodings

If the same logical map can appear in several byte orders, higher layers cannot
rely on the wire form. Canonical sorting on write and strict ordering checks on
read remove that ambiguity.

This is how the crate protects not just round-tripping, but byte-level identity.

### Pressure 6: deferred work without deferred rules

`Lazy<T>` exists because some protocols need to postpone cost. But it postpones
only cost. The bytes, the config, and the eventual decode obligations stay the
same. That is what keeps laziness from turning into a hidden side channel for
"parse this field differently later."

### Pressure 7: stability over time

Conformance is the time dimension of the same problem. A codec can look strict
today and still drift tomorrow. The conformance layer turns encoded bytes into a
checked regression boundary so the project can notice when "stable" has changed.

Once you see the crate as a response to those pressures, its strictness stops
looking ornamental. It looks like engineering.

---

## 6. Failure Modes and Limits

A strict customs office still has boundaries. This section matters because it
separates what the crate guarantees from what it intentionally refuses to guess.

If `EncodeSize` and `Write` disagree, `Encode` panics. That is not a recoverable
decode error. It is a bug in the implementation.

If a `usize` does not fit in `u32`, encoding panics as well. That is the price
of portable wire stability. The crate would rather fail loudly than let the same
logical value acquire architecture-dependent bytes.

On the incoming side, the error vocabulary is the border report:

| Error | What invariant failed |
| --- | --- |
| `EndOfBuffer` | Completeness: the declared structure ran past the available bytes. |
| `ExtraData(n)` | Singularity: one value parsed, but `n` trailing bytes remained. |
| `InvalidLength(len)` | Policy: a decoded length violated the caller's `RangeCfg`. |
| `InvalidVarint(width)` | Syntax or canonicality: the varint spelling was malformed, overlong, or impossible for that width. |
| `InvalidUsize` | Portability: a decoded `u32` length could not be represented as `usize` on this target. |
| `InvalidBool` | Domain of representation: a boolean byte was not `0` or `1`. |
| `InvalidEnum(tag)` | Tag validity: the variant byte did not identify any allowed case. |
| `Invalid(ctx, msg)` | Type-local structural rule: bytes had the right general shape but violated a stricter invariant such as ascending keys or non-zero values. |
| `Wrapped(ctx, err)` | Delegated validation failed and was preserved with source context. |

Two small helpers in `util.rs` keep the error surface crisp.

- `at_least` turns underfilled fixed-width reads into `EndOfBuffer`.
- `ensure_zeros` lets reserved padding bytes be checked rather than ignored.

Those errors tell you what went wrong structurally. They do not tell you whether
the decoded value is semantically acceptable for the protocol above.

That final point is important. The crate can verify paperwork. It can enforce
stable bytes, canonical representation, and bounded decoding. It cannot decide
whether a decoded public key belongs to the right peer, whether a message is
timely, or whether a range makes business sense for the application. Those are
questions for the next layer.

So the line is clean:

- below the line, the crate governs byte truth;
- above the line, the application governs domain truth.

---

## 7. How to Read the Source

The source is easiest to read in the same order as the contract.

Start with `codec/src/codec.rs`. It names the grammar of the crate: `Write`,
`Read`, `EncodeSize`, `Encode`, `Decode`, and the convenience wrapper traits
built on top of them.

Then read `codec/src/config.rs`. `RangeCfg` is the compact statement of bounded
decoding, and it shows how caller policy enters the read path without being put
on the wire.

Then read `codec/src/varint.rs`. Focus on two things:

- `UInt` and `SInt` as the public wrappers,
- `Decoder<U>::feed` as the place where canonical varint syntax is enforced.

After that, move to `codec/src/types/primitives.rs`. This is where the baseline
rules become tangible: big-endian numbers, `bool`, `Option`, unit, fixed-size
arrays, and the special handling of `usize`.

Once those foundations are clear, the rest of `codec/src/types/` reads naturally
as applications of the same contract:

- `vec.rs` and `bytes.rs` show bounded, length-prefixed payloads,
- `btree_map.rs`, `btree_set.rs`, `hash_map.rs`, and `hash_set.rs` show
  canonical representation for collections,
- `range.rs` and `net.rs` show stable structured encodings for ordinary types,
- `tuple.rs` shows product types,
- and `lazy.rs` shows deferred decoding without weaker guarantees.

If ordered collection decoding still feels magical, read `codec/src/types/mod.rs`
alongside the map and set impls. The loops there are where duplicate rejection
and ascending-order enforcement become mechanical.

Keep `codec/src/extensions.rs` nearby as well. It shows how the public API makes
common policy shapes shorter without inventing new semantics.

Finally, read `codec/src/error.rs` and `codec/src/conformance.rs` together. One
names the failure modes. The other turns the accepted wire image into something
the project can pin and re-check across time.

That reading order mirrors the lecture you just read: define the contract, study
the policy object, inspect the compact-length language, then watch the same
rules play out across concrete types and across releases.

---

## 8. Glossary and Further Reading

- `EncodeSize`: the exact number of bytes a value must write.
- `FixedSize`: a marker for types whose encoded width never varies.
- `Read`: the inbound trait that reconstructs a value from bytes and config.
- `RangeCfg`: a caller-supplied policy object that bounds accepted values.
- `Decode`: `Read` plus the requirement that the buffer be fully consumed.
- `UInt` / `SInt`: wrappers that encode integers in varint form.
- `Canonical representation`: one logical value, one accepted wire spelling.
- `Lazy`: a wrapper that stores bytes now and decodes later under the same
  config.
- `Conformance`: the testing layer that pins encoded bytes across revisions.

For further reading, the most useful source paths are:

- `codec/src/codec.rs`
- `codec/src/config.rs`
- `codec/src/varint.rs`
- `codec/src/types/primitives.rs`
- `codec/src/types/mod.rs`
- `codec/src/types/hash_map.rs`
- `codec/src/types/hash_set.rs`
- `codec/src/types/lazy.rs`
- `codec/src/extensions.rs`
- `codec/src/error.rs`
- `codec/src/conformance.rs`
