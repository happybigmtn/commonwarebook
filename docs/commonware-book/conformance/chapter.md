# commonware-conformance

## Catching Silent Compatibility Drift

---

## 1. What Problem Does This Solve?

Imagine you just made a new release. Everything looks perfect. 

The code still compiles. The unit tests all pass with flying colors. Your peers are still exchanging bytes over the network, and your storage layer happily opens all the old files. 

And yet, the release is completely wrong.

How can that be? Well, maybe a message variant now writes a slightly different tag. Maybe a section of your journal lands at a different byte offset. Maybe a handshake still completes, but the secret transcript—the ciphertext framing, or some derived state—no longer perfectly matches the *last* release. Nothing crashes! Nothing raises a red flag and announces itself as broken. But your system has silently drifted away from the compatibility story it promised to keep.

That, right there, is the exact class of failure `commonware-conformance` exists to catch.

This crate isn't a mathematical correctness prover. It's a *drift detector* for deterministic behavior. It is built for those critical surfaces where "it can still decode" or "this one test fixture still passes" is just too weak of a guarantee. We're talking about:

- Wire formats,
- Storage layouts,
- Deterministic handshakes,
- Cryptographic root computations,
- And any other mechanism where the output *must* stay perfectly reproducible across versions.

The main enemy here is silent compatibility drift.

Usually, people try to solve this with a single "golden fixture"—a file with some bytes they check against. But one example is too small a witness! It's easy to accidentally change the broader behavior envelope while keeping that one example intact. `commonware-conformance` does something much stricter: it replays a massive, deterministic "sweep" of cases, records the entire sweep as one single mathematical digest, and checks *that* digest into the repository.

So, here's the headline for the whole chapter:

> **Conformance protects behavior, not isolated bytes.**

Or, to put it operationally:

> It keeps a checked-in ledger of what a stable mechanism does, and then asks whether the new release still tells the exact same story.

---

## 2. A Mental Model: The Compatibility Ledger

The best way to think about this—the best mental model—is an accountant's ledger for compatibility promises.

Every type or mechanism you track gets one entry in a local `conformance.toml` file. Now, it doesn't store every single generated sample. That would be enormous and fragile. Instead, it stores just three things:

1. The fully qualified key for the tracked surface.
2. The size of the deterministic sweep (we call this `n_cases`).
3. The cryptographic digest (hash) of replaying that entire sweep.

This brilliantly changes the question you're asking. You are no longer asking:

> *Did this one isolated example still work?*

Instead, you are asking:

> *If we replay the exact, deterministic walk we recorded last time, do we still observe the exact same behavior envelope?*

This is why `conformance.toml` isn't a cache, and it isn't just a convenience file. It is the checked-in statement of record. It says: "This surface is tracked, this many cases define the envelope, and this hash is the current receipt."

Your CI system then acts like an auditor. It recalculates the live digest from the new code, looks at the ledger, and makes sure the books still balance.

This is much stronger than example-based testing. First, it forces you to state exactly how much of the surface is covered (`n_cases` is right there for reviewers to see). Second, it forces any compatibility changes into the open. A changed hash can't hide inside a refactoring PR. It creates a visible diff, a failing test, or requires an explicit update.

---

## 3. What Actually Counts As "Behavior"?

At the very center of all this is a deliberately simple trait:

```rust
pub trait Conformance: Send + Sync {
    fn commit(seed: u64) -> impl Future<Output = Vec<u8>> + Send;
}
```

That method, `commit`, answers a fundamental question:

> For a given deterministic `seed`, what bytes does this mechanism commit to?

Notice that the crate doesn't force these bytes to come from any one specific place. `commit(seed)` is allowed to mean wildly different things depending on what you're testing:

- It could encode a single generated value.
- It could run a complete network protocol transcript and log the resulting messages.
- It could build an entire on-disk data structure and return a storage audit.
- It could compute a deterministic Merkle root after a sequence of inserts.

That flexibility is beautiful! The crate isn't tied to one rigid idea of stability. It only asks for a deterministic commitment that can be replayed.

People often underestimate this design. The point isn't just that `commit` spits out bytes. The point is that `commit` *defines what you choose to treat as the observable compatibility surface*. If you commit encoded bytes, you're protecting encoding. If you commit a storage audit, you're protecting file layout. You get to choose what story the ledger remembers.

---

## 4. How The Digest Is Actually Built

Now, let's look at the machinery. How is this digest built? It's built as an ordered replay, not just a random bag of outputs. Look at `compute_conformance_hash`:

```rust
pub async fn compute_conformance_hash<C: Conformance>(n_cases: usize) -> String {
    let mut hasher = Sha256::new();

    for seed in 0..n_cases as u64 {
        let committed = C::commit(seed).await;

        // Write length prefix to avoid ambiguity between concatenated values
        hasher.update((committed.len() as u64).to_le_bytes());
        hasher.update(&committed);
    }

    hex_encode(&hasher.finalize())
}
```

Let's unpack exactly what this means, because every line is there for a reason.

### 4.1 The Replay Order Matters

Notice the loop: `for seed in 0..n_cases as u64`. The seeds are replayed in strictly ascending order. 

So the digest isn't a "multiset" of outputs. It's an ordered transcript. If you reorder the cases, the hash changes. If you change `n_cases`, the hash changes. If you change a single bit in a single seed's output, the hash changes. Many deterministic mechanisms are order-sensitive, so the ledger needs to respect that.

### 4.2 The Length Prefix Is Not A Small Detail

Look at this line: `hasher.update((committed.len() as u64).to_le_bytes());`.

Before hashing the bytes for a seed, it hashes the length of those bytes as a 64-bit integer. Why? To prevent ambiguity when you stick all these bytes together.

Imagine if we didn't do this. 
- Case A commits `[0x01]`, Case B commits `[0x02, 0x03]`. That concatenates to `[0x01, 0x02, 0x03]`.
- Case A commits `[0x01, 0x02]`, Case B commits `[0x03]`. That *also* concatenates to `[0x01, 0x02, 0x03]`!

Without the length prefix, completely different behaviors would collapse into the exact same hash. By hashing the length first, the digest "sees" the shape of the replay.

### 4.3 Direct Hashing

There's no fancy Merkle tree of per-seed hashes here. The SHA-256 hasher just absorbs the whole continuous stream: length, bytes, length, bytes. It's simple, it's deterministic, and if the final hash changes, you know exactly why: the stream changed.

---

## 5. The Ledger File Is A Shared Resource

Here is where the engineering gets really clever.

Conformance tests are designed to run in parallel across a massive workspace. This means we have competing requirements:
1. The expensive part (computing the hashes) shouldn't be forced to run one-at-a-time.
2. Writing to the shared `conformance.toml` file *must* be safe from race conditions.

How does the crate solve this? By beautifully separating the computation from the bookkeeping.

### 5.1 Hash First, Lock Later

If you look at `verify_and_update_conformance`, it does something very important:

```rust
// Compute the hash first WITHOUT holding the lock - this is the expensive part
let actual_hash = compute_conformance_hash::<C>(n_cases).await;

// Now acquire the lock only for file I/O
let mut lock = acquire_lock(path);
```

This is not a micro-optimization; it is a profound design choice. Computing the digest might involve generating 65,000 values or running a protocol thousands of times. If you locked the file during that work, the entire workspace would turn into a massive traffic jam. Instead, tests do the hard work in parallel, and only lock the file for the fraction of a millisecond it takes to read and update the TOML.

### 5.2 Safe Locking

The `acquire_lock` function uses an OS-level file lock. It creates the file if it's missing, but it *doesn't* truncate it immediately. This allows it to safely read the existing ledger. And because it's an OS-level lock, if a test panics or gets killed, the operating system cleans up the lock automatically. You never end up with a stuck ledger.

### 5.3 BTreeMap for Stability

When the ledger is written to memory, it uses a `BTreeMap`. Why? Because a `BTreeMap` guarantees alphabetical ordering of the keys. When you look at the TOML file diff in your pull request, the entries are always in a stable, predictable order. It removes the noise so you can see what actually changed.

---

## 6. Verification vs. Regeneration

The crate has two distinct modes of operation, and they serve completely different social purposes.

### 6.1 Verification Mode: Catching Drift

In normal mode (what your CI runs), the crate computes the actual hash, locks the file, and checks the ledger.

- If the entry is missing, it adds it (this is how you bootstrap a new test).
- If the hash differs, **it panics**.
- If `n_cases` differs, **it panics**.

This turns silent drift into a loud, reviewable event. Notice that a hash mismatch ("the behavior changed") and an `n_cases` mismatch ("we changed how much we test") are checked separately because they are different kinds of events.

### 6.2 Regeneration Mode: Intentional Change

Sometimes, you *want* to break compatibility. Maybe you upgraded a protocol version. If you run tests with:

```bash
RUSTFLAGS="--cfg generate_conformance_tests" cargo test
```

(Or, more simply via the workspace script: `just regenerate-conformance`)

The crate changes its attitude. It computes the hash, and simply overwrites the ledger entry. This isn't a backdoor; it's an explicit acknowledgment. You are intentionally updating the ledger, and that change will show up in your git diff for everyone to review.

---

## 7. The Macro: Keeping Things Tidy

You'll see tests defined using a macro like this:

```rust
commonware_conformance::conformance_tests! {
    CodecConformance<Message<u8>>,
    Handshake => 4096,
}
```

This macro isn't just syntactic sugar. It does some heavy lifting to keep the workspace sane.

First, it generates a clean, predictable function name. `CodecConformance<Message<u8>>` becomes `test_codec_conformance_message_u8`.

Second, and most importantly, it ties the ledger key to the module path (`module_path!()`). So the key isn't just `Message`, it's `commonware_resolver::p2p::wire::tests::conformance::CodecConformance<Message<u8>>`. This absolutely prevents name collisions across a massive codebase.

Finally, it hardcodes the path to the `conformance.toml` file to be at the root of the crate (`env!("CARGO_MANIFEST_DIR")`). You can't accidentally write to the wrong ledger. The macro enforces hygiene at scale.

---

## 8. Two Flavors: Wrapper vs. Bespoke

How do you actually use this in practice? The workspace uses two main patterns.

### 8.1 Wrapper-Style: `CodecConformance<T>`

If you just want to guarantee that a data structure encodes the same way over the wire, you use a wrapper. 

The `CodecConformance<T>` wrapper takes a seed, uses it to deterministically generate a random instance of type `T` (using `arbitrary::Unstructured`), and then encodes it to bytes. 

This is brilliant for wire formats. You just hand it a type, and it blasts thousands of deterministic variations of that type through your encoder and hashes the result. 

### 8.2 Bespoke Conformance

But what if you aren't just encoding a struct? What if you're testing a whole system? That's when you write your own `Conformance` implementation.

For example, in the cryptography module, the `Handshake` conformance test actually generates keys, runs a dialer and a listener, exchanges messages, encrypts them, decrypts them, and appends the whole transcript into a log. The hash protects the *entire protocol dance*.

In the storage layer, the journal conformance test generates random data, appends it across partitions, syncs to disk, and then returns a *storage audit* of the file layout. The ledger protects the actual on-disk footprint!

You choose the bytes that best represent your stability promise.

---

## 9. Operational Workflow

So, how do you work with this day-to-day?

1. **Adding a test:** You write your `commit` logic, add it to `conformance_tests!`, and run the tests. The crate automatically creates the new entry in `conformance.toml`. You commit that file.
2. **Normal CI:** You run `just test-conformance`. It verifies everything matches.
3. **Intentional breakage:** You realize you need to change a wire format. You make the change. Tests fail. You run `just regenerate-conformance`. The TOML file updates. You commit the diff, and the reviewer clearly sees the hash changed.

---

## 10. The Limits of Conformance

As wonderful as this is, we have to be honest about its limits. It is not magic.

- It only tests the cases you sample. If a bug hides outside your `n_cases` sweep, the ledger won't see it.
- Your `commit` function **must** be deterministic. If it relies on the current time, or a random number generator that isn't seeded from the provided `seed`, the hash will change every time you run it, and the test becomes useless noise.
- It doesn't prove your code is *correct*, it only proves that your code *hasn't changed its mind* about what to do.

But for catching that terrifying, silent drift where things subtly break compatibility? It's exactly the tool for the job.

---

## 11. Glossary

- **Silent compatibility drift**: When a stable mechanism changes its behavior without causing a crash or test failure.
- **Compatibility ledger**: The `conformance.toml` file that stores the expected hashes.
- **`commit(seed)`**: The deterministic function that translates a seed into the bytes we care about.
- **`n_cases`**: The number of deterministic iterations we run to define our behavior envelope.
- **Verification mode**: The default mode that panics if the live hash doesn't match the ledger.
- **Regeneration mode**: The explicit mode used to intentionally update the ledger.
- **Wrapper-style**: Using tools like `CodecConformance<T>` to automatically test serialization.
- **Bespoke conformance**: Writing a custom `commit` to protect complex behaviors like protocol transcripts or disk layouts.
