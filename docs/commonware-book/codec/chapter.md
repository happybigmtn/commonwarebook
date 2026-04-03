# commonware-codec

## A Customs Office for Stable Bytes

---

## Backgrounder: Bytes, Grammars, and Canonical Forms

Let's think about something fundamental. Before a value—say, the number 300, or a list of public keys—can leave the comfortable, safe world of your program's memory and go out onto the network, it has to become bytes. It has to leave the world of "types" and enter the rough, unforgiving world of wire formats. And that transition is exactly where almost everyone gets into trouble.

You see, at the physical representation level, one logical value can often be written down in several different ways. Endianness can flip the byte order. Variable-length encodings can spell the exact same number using a different number of bytes. Collection encodings might keep or ignore ordering, or throw in padding and trailing bytes. If the computer on the receiving end is casual about any of those choices, two machines might look at the exact same data and disagree about what it means.

The naive approach is to say, "Ah, just serialize it and trust the library." But that only works if both sides already agree perfectly on the exact spelling rules, the parser never gets confused by ambiguity, and the incoming bytes can't make the decoder do an unbounded amount of work. In the real world, those assumptions fall apart fast:

- A permissive parser might accept multiple byte strings for one single value.
- A length prefix might be trusted blindly before the memory is even allocated.
- A trailing blob of junk might be ignored instead of rejected.
- An attacker can craft a tiny message that tricks the decoder into exhausting all its memory or CPU.

That is why you have to stop thinking of byte formats as just "blobs." You have to think of them as *grammars*. Each format must state exactly what sequences are legal, how one value is separated from the next, and—most importantly—which spelling is the *canonical* one. Canonical form matters because it lets the rest of the protocol use those bytes as stable names, rather than fuzzy suggestions.

There is a tradeoff between flexibility and safety. If a format accepts many different spellings, it's easy to evolve in the short term. But it becomes incredibly hard to compare, hash, sign, or store deterministically. If the format is rigid, it might be a bit less convenient, but it gives the entire system one consistent story to tell.

`commonware-codec` stands firmly on that stricter side of the line. It treats bytes as a public contract with exact spelling rules and exact bounds. Why? Because when you are writing protocol code, you cannot afford to guess what the sender meant. You have to know.

## 1. What Problem Does This Solve?

When a protocol crosses a machine boundary, a value stops being a Rust type and becomes a sequence of bytes. At that exact moment, saying "it serialized" is not a meaningful guarantee. The real questions are much harsher:

- Do these bytes mean *exactly one* value?
- Will every machine out there encode that value the exact same way?
- Can the decoder limit how much memory and work it's going to spend?
- Will the boundary reject trailing junk, instead of quietly ignoring it?

`commonware-codec` exists to answer those questions with a contract.

The contract has three parts:

1. **Stable bytes**: A value must have a predictable, unchanging wire form.
2. **Canonical representation**: One logical value gets exactly one accepted encoding. No synonyms.
3. **Bounded decoding**: Untrusted input does not get to dictate an unlimited amount of work for the receiver.

That is why the crate is built around four core ideas: `Write`, `EncodeSize`, `Read`, and `Decode`.

- `Write` is simply how a value becomes bytes.
- `EncodeSize` tells you exactly how many bytes that write operation will need. No guessing.
- `Read` is how to reconstruct the value, but it requires a policy supplied by the caller.
- `Decode` adds the final, crucial protocol rule: consume the whole buffer, or fail.

Many libraries out there can turn values into bytes. Far fewer treat the wire format as a strict discipline. `commonware-codec` does. It assumes the sender might be careless, malicious, or simply running on a totally different architecture. The crate's job is to make those differences completely irrelevant at the byte boundary.

That is the right way to read the rest of this chapter. We are not taking a tour of a serializer. This is a lecture about how to make bytes safe enough to carry meaning.

---

## 2. Mental Model: The Customs Office and the Contract

If you want to really understand this, the most useful mental model is a customs office at a national border.

Imagine a package arrives at the border. It has paperwork attached. The paperwork says what the package is, how large it is, and what shape the contents should have. The customs officer doesn't just trust the label! The officer opens the box, counts what is inside, compares the contents against the declared limits, and absolutely refuses entry if anything is off.

That is exactly what `commonware-codec` does for protocol bytes.

Keep that border crossing picture in your head through the rest of the crate:

- `Write` is the packing procedure.
- `EncodeSize` is the declared size on the shipping label.
- `Read` is the physical inspection process.
- `RangeCfg` is the import policy. (e.g., "No liquids over 100ml.")
- `Decode` is the final clearance stamp that says, "I checked, and nothing else was hidden in the box."

The contract behind this customs office is simple:

1. The sender must present a stable byte layout.
2. The wire format must not allow multiple spellings for the same value.
3. The receiver must stay within a strict budget (chosen by the caller) while decoding.

Once you adopt this model, the code makes complete sense. Every trait, every implementation either defines the paperwork, checks the paperwork, or enforces the budget.

That's why we keep returning to the same themes. Stable bytes, canonical form, and bounded decoding aren't three separate features. They are three faces of the exact same border policy.

---

## 3. The Core Ideas

With the customs office in view, let's look at how the core traits divide up the work.

### `Write` and `EncodeSize` define the outgoing contract

`Write` knows how to put a value into a `BufMut`. `EncodeSize` knows exactly how many bytes that operation will take.

Why are these separate? Because writing and counting are different obligations! A codec becomes unreliable the moment it treats the size as a "fuzzy estimate." `Encode` joins the two together, and it checks its own work after writing. That is how the outgoing path produces perfectly stable bytes instead of "roughly the right layout."

In our customs model, the physical package and the paperwork have to match exactly.

If they don't, `Encode` panics. Notice that this isn't framed as some recoverable error. If `EncodeSize` says "4 bytes" and `Write` writes 5, that's a bug in the codec. The machine must stop.

### `Read` makes decoding a policy decision

`Read` reconstructs a value from a buffer, but it does something very special: it takes a `Cfg` (config) parameter. That tiny design choice is what turns decoding into a controlled, safe operation.

The config lets the caller say, "I will accept a vector, but only up to this length," or "This field must fit in this specific range." Without that hook, the decoder would have to blindly trust whatever shape the sender declared. With it, the receiver sets the budget, and the decoder enforces it.

That is bounded decoding in a nutshell: the receiver decides how much work a piece of untrusted input is allowed to cause.

### `RangeCfg` is policy, not data

`RangeCfg` is the simplest expression of that idea. It is not a value carried over the network. It's a rule supplied by the reader.

This distinction is vital because it decides who is in charge.

- The sender gets to declare a length.
- The receiver gets to decide if that length is allowed.

`RangeCfg` is deliberately small. It holds a start bound and an end bound, and it implements Rust's `RangeBounds<T>`, so you can build your policies using ordinary Rust syntax: `0..=1024`, `1..`, `..=32`, `..`, or even `RangeCfg::exact(7)`.

The design is brilliant because of what it *doesn't* know. `RangeCfg` doesn't know anything about `Vec` or `HashMap`. It is generic over `T`. It is a portable policy.

Because of the conversion implementations in `config.rs`, a range over `NonZeroU32` can seamlessly become a range over `usize`. Higher layers of your protocol can express the tightest local rule they know, and the lower layers can still consume that policy using the integer type they need.

So `RangeCfg` isn't just a guardrail. It's the exact moment where authority shifts from the sender to the receiver.

### `Decode` seals the border

`Read` can successfully parse one value off the front of a buffer. But protocol boundaries usually need something stricter: they need proof that the buffer held *exactly* one value and nothing else.

`Decode` adds that rule. It calls `Read`, and then it checks the buffer. If any bytes remain, it fails with `ExtraData`.

This completes our customs-office model. It's not enough for the officer to inspect the declared item; the officer has to check the bottom of the box to make sure there's no hidden compartment.

### `FixedSize` marks the easy cases

Some values always take up the same number of bytes. A `u32` is always 4 bytes. For these types, size isn't something you have to compute; it's a fundamental property of the type's identity.

This matters because fixed-size values are the simplest proof that stable bytes are possible! A `bool`, an `Ipv4Addr`, or a fixed array doesn't need a length prefix, and it doesn't need a complex negotiation with the caller. The contract is absolute.

This also explains a rule you'll see later: `Lazy<T>` can only implement `Read` when `T: FixedSize`. If the outer decoder doesn't know where `T` ends without parsing it, it can't safely set it aside for later. A lazy boundary still needs a precise physical size.

### `usize` is variable-size by policy, not by accident

Most primitive numbers in `types/primitives.rs` are fixed-width and big-endian. But `usize` is the exception.

It is varint-encoded because lengths are usually small numbers. But crucially, it is restricted to values that fit in a `u32`. Why? Because `usize` changes size depending on the machine's architecture! That restriction is the portability rule that keeps the same logical length from magically changing its wire form just because you moved from a 32-bit machine to a 64-bit machine.

So the story for `usize` has three layers:

1. Use a compact representation for small counts.
2. Reject any magnitude that depends on the architecture.
3. Run the final result through `RangeCfg` before trusting it to allocate anything.

This is the crate's style in a nutshell: we allow a convenience, but only after we've fenced it in with stability and policy.

### Varint is a grammar, not a byte trick

Varint (variable-length integers) is very easy to describe loosely, and incredibly dangerous to implement loosely.

In this crate, we treat varint like a language with strict syntax rules:

- Each byte contributes 7 bits of data.
- The top bit of the byte says whether another byte is coming (the continuation bit).
- The final byte *must* be the first byte where that continuation bit is a zero.
- The encoding must stop the moment the value is fully spelled out.

That last rule is the magic one. It turns compactness into canonicality.

For example:

- `0` is accepted as `[0x00]`.
- `300` is accepted as `[0xAC, 0x02]`.
- But an overlong zero, like `[0x80, 0x00]`, is aggressively rejected.

If you look at the incremental `Decoder<U>::feed` in `varint.rs`, you see the grammar in action. Once you move past the first byte, an all-zero byte is illegal—it proves the sender kept talking after they had nothing left to say. And on the final byte, any bits set beyond the target width are illegal, because they would overflow the type.

That's why `InvalidVarint` doesn't just mean "could not parse." It means the byte sequence violated the unique spelling rules for this integer.

`SInt` adds ZigZag encoding on top of this. Negative numbers aren't given a separate language; they are cleverly folded into the unsigned one.

### Canonical collections are part of correctness

Stable bytes aren't enough if the same logical dictionary can be sent in six different byte orders. We need canonical representation to close that gap.

The crate handles ordered and unordered collections differently:

- `BTreeMap` and `BTreeSet` already have a defined, sorted order. We just follow it.
- `HashMap` and `HashSet` do not. So the writer must sort the entries before emitting them.

But pay attention to the read path! `read_ordered_map` and `read_ordered_set` do not just deserialize items and throw them into a map. They *require* the incoming bytes to already be in strictly ascending order, with no duplicates.

The decoder isn't saying, "I can recover a valid map from this jumbled mess." It's saying, "I will only accept the *one true spelling* this logical map is supposed to have."

That rule makes the encoded bytes safe to hash, safe to sign, safe to compare, and safe to use in conformance tests.

### `Lazy<T>` defers work without changing truth

`Lazy<T>` is a fascinating type because it looks like a performance trick, but it's actually a policy statement.

`Lazy<T>` stores either:

- An already available `T`, or
- Pending bytes plus the `Cfg` needed to decode `T` later.

Laziness here doesn't mean "skip validation." It means "capture the exact same future decode operation that would have happened now, and move the cost."

Two beautiful details in `types/lazy.rs`:

First, on `std`, the decode is hidden behind a `OnceLock`. The first time you ask for it, it does the work and caches the result (success or failure). It never decodes twice.

Second, `Write` and `EncodeSize` will prefer the raw pending bytes if they exist. That lets `Lazy<T>` round-trip a message perfectly without forcing a pointless decode and re-encode cycle!

But remember, `Lazy<T>` is intentionally narrow. It only works if `T: FixedSize`. Without a fixed width, the codec wouldn't know exactly how many bytes to scoop up and freeze.

### Extension traits improve ergonomics, not semantics

You'll see `ReadExt`, `DecodeExt`, `ReadRangeExt`, and `DecodeRangeExt`. They don't weaken the contract. They just save typing.

Think about the configs in real code:

- Primitives usually use `Cfg = ()`.
- A `Vec<T>` needs a config for its length, and a config for its items: `(RangeCfg<usize>, T::Cfg)`.
- A `HashMap<K, V>` needs even more: `(RangeCfg<usize>, (K::Cfg, V::Cfg))`.

The extension traits let callers use the real policy while writing less code. `ReadExt` means "this type's config is `()`." `DecodeRangeExt` means "this type starts with a length policy, and the rest can be defaulted."

It's just shorthand. The law doesn't change; the code just gets easier to read.

### Conformance turns the contract into a regression boundary

Here is where all the theory pays off.

In `codec/src/conformance.rs`, there's a wrapper called `CodecConformance<T>`. It takes any encodable type, generates a deterministic version of it from a random seed, encodes it, and hashes the resulting bytes. The conformance test compares that hash against a checked-in fixture.

This isn't just a test. This is where stable bytes become a promise across time. If someone changes the varint grammar, or alters how a map is sorted, the hash changes. The test fails. The project notices. Canonicality is verified.

---

## 4. How Bytes Move Through the Machine

The encode path is wonderfully boring. A predictable codec should feel like a simple procedure:

1. Ask the value: "What is your encoded size?"
2. Allocate exactly that many bytes.
3. Write the value into the buffer.
4. Assert that the number of bytes written matches the number promised.

The sender doesn't guess, append, and cross its fingers. It commits to a layout up front.

The decode path mirrors this exactly:

1. Read the fixed-width field or the declared length.
2. Apply the caller's config (the budget!).
3. Reconstruct the value.
4. If asked to `Decode`, confirm no bytes are left over.

The sequence is everything. Inspect the paperwork. Enforce the budget. Admit the value. Check for hidden compartments.

### Primitives: The Baseline

In `types/primitives.rs`, integers and floats use big-endian encoding. It doesn't matter what your CPU uses; the wire form is always the same.

Look at `bool`. It's one byte wide. But the decoder will only accept `0` or `1`. Fixed-width doesn't mean "accept any garbage in that width." It gets structural validation.

`Option<T>` is similar: a boolean tag, followed by the payload *only* if the tag is true. No magic null values. The bytes say exactly which branch to take.

### `RangeCfg` in motion

Whenever you see a `Vec<T>`, `Bytes`, or `HashMap`, the very first move is:

1. Decode a `usize`.
2. Check it against the `RangeCfg`.
3. *Only then* allocate memory or iterate.

The length prefix is a claim. `RangeCfg` verifies the claim. If the caller says "Max length is 64," and the sender sends a length of 10,000, we don't try to parse it. We instantly return `InvalidLength(10000)`.

Who gets to choose the work budget? In this crate, the answer is always the receiver.

### Varint Worked Example

Let's look at the varint spellings to make it concrete.

Accepted:
- `0` -> `[0x00]`
- `1` -> `[0x01]`
- `127` -> `[0x7F]`
- `128` -> `[0x80, 0x01]` (The first byte's top bit is set, meaning "more to come". The 7 data bits are 0. The next byte is 1. `1 << 7 + 0 = 128`)

Rejected:
- `[0x80, 0x00]` for zero. Why? Because the second byte says the first byte shouldn't have had its continuation bit set!
- Any spelling where the final byte sets bits that would overflow the target integer.
- Any spelling that just keeps going past the maximum possible length.

This strictness is why we have `UInt` wrappers and the incremental `Decoder<U>`. They enforce the grammar perfectly.

### Canonical Collections: Accepted vs. "Recoverable"

Let's say a `HashSet<u32>` contains `{1, 5}`.

Accepted encoding:
- Length `2`, item `1`, item `5`.

Rejected encodings:
- Length `2`, item `5`, item `1`. (Items must be ascending!)
- Length `2`, item `1`, item `1`. (No duplicates allowed!)

The code in `types/mod.rs` makes this mechanical. It remembers the last item read, reads the next, ensures it is strictly greater, and then inserts it. Canonical representation is not an afterthought; it is an absolute admission rule.

### `Lazy<T>` Worked Example

Imagine a fixed-size type `T` that takes a long time to validate after reading its bytes.

With `Lazy<T>`, the decoder can:
1. Slice off exactly `T::SIZE` bytes.
2. Store those bytes and the `Cfg`.
3. Keep parsing the rest of the message.
4. Only decode `T` if the application actually needs it later.

What *doesn't* change? The bytes still have to be structurally valid when you eventually parse them. The original config still applies. And you can re-encode the original bytes perfectly. Laziness doesn't change the truth; it just reschedules the work.

---

## 5. What Pressure This Design Absorbs

Why build something this strict? Because of adversarial pressure.

A codec at a protocol boundary is under constant attack. Attackers lie about lengths. Honest nodes send truncated data. CPUs disagree about memory layouts. Maps sort themselves randomly. Performance shortcuts tempt you to skip validation.

`commonware-codec` is designed to absorb all of it.

- **Hostile Lengths:** Senders don't get to choose the budget. `RangeCfg` stops memory exhaustion before allocation happens.
- **Ambiguous Integers:** The strict varint grammar prevents tiny numbers from having infinite valid representations.
- **Truncated/Padded Buffers:** `EndOfBuffer` and `ExtraData` mean the boundary is perfectly tight on both sides.
- **Cross-Platform Drift:** Big-endian layouts and `u32` limits on `usize` guarantee the bytes stay exactly the same on any architecture.
- **Non-Canonical Collections:** Ascending-order enforcement guarantees that equal maps have equal bytes.
- **Lazy Parsing Risks:** `Lazy<T>` only defers cost, never the rules.
- **Stability over Time:** The `conformance` wrapper turns the whole system into a testable proof that "stable" means "stable forever."

When you see it this way, the strictness isn't pedantic. It's excellent engineering.

---

## 6. Failure Modes and Limits

Even a strict customs office has a defined scope. It's important to know what the crate guarantees, and what it explicitly ignores.

First, bugs: If `EncodeSize` and `Write` disagree, or if a `usize` is too big for a `u32`, the code panics. Those aren't data errors; those are programmer errors. The program stops.

For incoming data, the errors are a precise report of the border inspection:

| Error | What invariant failed |
| --- | --- |
| `EndOfBuffer` | Completeness: The buffer ran out before the declared structure finished. |
| `ExtraData(n)` | Singularity: The value parsed perfectly, but `n` bytes were left in the box! |
| `InvalidLength(len)` | Policy: The declared length violated the caller's `RangeCfg`. |
| `InvalidVarint(width)` | Syntax: The varint was malformed, overlong, or impossible. |
| `InvalidUsize` | Portability: A length didn't fit in the target's `usize`. |
| `InvalidBool` | Domain: A boolean byte wasn't exactly `0` or `1`. |
| `InvalidEnum(tag)` | Tag validity: The byte didn't match any known enum variant. |
| `Invalid(ctx, msg)` | Structural rule: Bytes looked right but failed a local rule (like ascending keys). |
| `Wrapped(ctx, err)` | Delegated error: An inner validation failed. |

Two neat helpers in `util.rs` keep this clean:
- `at_least` safely checks for bytes before you read them.
- `ensure_zeros` makes sure padding bytes are actually zeros, rather than ignoring them.

Here is the vital limit: The crate tells you if the bytes are structurally correct. **It does not tell you if they make sense for your application.**

The crate verifies the paperwork. It ensures canonical form. It bounds decoding. But it cannot tell you if that decoded public key is authorized, or if the timestamp is fresh.

The line is crystal clear:
- Below the line, the codec governs the truth of the *bytes*.
- Above the line, the application governs the truth of the *domain*.

---

## 7. How to Read the Source

If you want to read the code, follow the contract.

1. Start in `codec/src/codec.rs`. Look at `Write`, `Read`, `EncodeSize`, and `Decode`. That is the grammar.
2. Go to `codec/src/config.rs`. Look at `RangeCfg`. See how policy is injected into the read path without touching the wire.
3. Read `codec/src/varint.rs`. Look at `UInt`, `SInt`, and especially `Decoder<U>::feed` to see how the varint grammar rejects ambiguity.
4. Move to `codec/src/types/primitives.rs`. See the baseline: big-endian fixed-width numbers, strict booleans, and the portable handling of `usize`.
5. Now the rest of `codec/src/types/` will read like a breeze. Look at `vec.rs` for length limits, and `hash_map.rs` / `mod.rs` for the brilliant sorted-iteration logic. Look at `lazy.rs` for deferred parsing.
6. Check out `codec/src/extensions.rs` to see how the API makes the rules ergonomic.
7. Finally, look at `codec/src/error.rs` and `codec/src/conformance.rs` together. One defines failure, the other pins success across time.

Read it in that order, and you'll see the customs office at every step.

---

## 8. Glossary and Further Reading

- **`EncodeSize`**: The absolute, exact number of bytes a value will write.
- **`FixedSize`**: A marker for types that always take the exact same amount of space.
- **`Read`**: The inbound trait that turns bytes and a config back into a value.
- **`RangeCfg`**: The caller-supplied budget policy.
- **`Decode`**: `Read`, plus the guarantee that no bytes are left over.
- **`UInt` / `SInt`**: Wrappers for integers to give them varint spellings.
- **Canonical representation**: One value, one spelling. Period.
- **`Lazy`**: A wrapper that captures bytes now to decode later, preserving all the original rules.
- **Conformance**: The testing layer that mathematically pins byte layouts across versions.

Dive into the source:

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