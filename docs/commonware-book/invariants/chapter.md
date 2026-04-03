# commonware-invariants

## Make Invariant Testing the Default

---

You know, people have this funny idea about testing software. They tend to think there are really only two ways to do it, and they are miles apart.

The first way is to write down a few examples. You pick an input, you know exactly what the output should be, and you write a unit test. It's easy, it's fast, but it's narrow. You're only checking the exact cases you were smart enough to think of in advance. 

The second way is what they call "fuzzing." You build this giant, complicated machine that throws millions of random, garbage bytes at your program. It tracks which lines of code it hits, learns from it, and tries to find a path that makes the program crash. It's incredibly powerful, but it's a huge pain to set up. You have to build a separate target, manage a "corpus" of saved inputs, and wait around. Because of all this ceremony, people put it off. They say, "We'll write a real fuzzer later." And we all know "later" usually means "never."

`commonware-invariants` sits right in the gap between these two extremes. We aren't trying to replace the giant fuzzing machines. What we want is to make that *first useful search* so incredibly easy that you do it right there, next to your ordinary unit tests, before you even think about giving up and just writing a couple of manual examples.

We want to test *rules*, not just examples. And we want to do it cheaply.

---

## 1. What Problem Are We Actually Solving?

If you ask the question, "What should always be true here?", the answer shouldn't be, "Hold on, let me set up a separate fuzzing project." The answer should be, "Let me write down the rule, and let a tool wiggle the inputs around to see if it holds."

That's what `minifuzz` does. It's a tool designed to live right inside your standard Rust `#[test]` modules. It assumes that a lot of bugs are hiding just a few millimeters away from your happy path. If you shift the bytes a little, change the length of a string, or rearrange the order of a message, a broken assumption will pop right out.

But there's a catch. If a tool like this finds a bug by generating a bunch of random junk, and then it just says "Hey, it broke!", that's practically useless to you. You need to be able to reproduce the bug to fix it. So, a failure has to give you a clear, compact receipt—a token—that you can use to replay that exact failure tomorrow, or next week, on any machine.

---

## 2. The Mental Model: A Pocket Searcher

The cleanest way to think about `minifuzz` is as a **pocket searcher**.

Imagine an ordinary unit test, but instead of checking one hardcoded thing, it gets curious. You hand it a rule (we call this an "invariant"). It starts with a small buffer of raw bytes, tries to interpret those bytes as your structured data, and checks if the rule holds. 

If the rule holds, the searcher slightly nudges those bytes—adds some, flips some, copies a chunk—and asks again. It keeps doing this until it runs out of its allowed budget, which is just a time limit or a number of tries.

If the rule *breaks*, it stops immediately and hands you a receipt.

Here is the picture you should keep in your head:
- **The Invariant** is the promise your code makes.
- **The Sampler** is the curiosity, nudging the data.
- **The Budget** is the discipline, knowing when to stop.
- **The Replay Token** is the receipt, so you can find the bug again.

---

## 3. Breaking Down the Code

Let's look at how this is actually built in `invariants/src/minifuzz.rs`. It's beautifully simple once you see the parts.

### 3.1 Invariants Over Examples

We're dealing with structured inputs. Your code doesn't usually care about an array of random `u8` bytes; it cares about a `Message`, a `Tree`, or a `Plan`. Bugs usually happen because the system accepted a family of inputs it should have rejected, or a state machine got confused by a slightly weird order. 

An invariant turns a vague worry into a searchable rule. For example: *"No matter what tree we generate, following a valid path should never lead to a node with a value of 77."* That's an invariant.

### 3.2 `Branch`: The Search Identity

The most distinctive piece of the puzzle is a little struct called `Branch`.

```rust
#[derive(Copy, Clone)]
struct Branch {
    seed: u32,
    thread: u32,
    size: u32,
}
```

What is this? It’s just three numbers. But together, they make up the absolute identity of the current search path.
- `seed` is the starting point for the random number generator.
- `thread` tells us which local branch of exploration we are currently on.
- `size` keeps track of how far we've grown the input buffer.

When you print a `Branch`, you get a 24-character hex string. If your test fails, the harness spits out `MINIFUZZ_BRANCH = 0x...`. 

This isn't just debugging noise. It's the receipt! The test runner can take that exact hex string, parse it back into a `Branch`, and perfectly recreate the exact sequence of random numbers and mutations that found the bug. You don't have to guess what happened. You just paste the string into your test, and it walks right back to the crash.

### 3.3 The `Sampler`: Wiggling the Bytes

The `Sampler` is our mutation engine. It's intentionally modest. It doesn't have a giant database of past inputs (a corpus) or a map of your code's branches. 

```rust
struct Sampler {
    rng: ChaCha8Rng,
    buf: Vec<u8>,
    count: i64,
    last_bytes_used: usize,
}
```

Look at the strategies it uses to change the buffer:
- `strategy_add_bytes`: Make the buffer longer.
- `strategy_modify_prefix`: Scramble the beginning.
- `strategy_copy_portion`: Take a chunk and paste it somewhere else.
- `strategy_clear_non_prefix`: Zero out some bytes.
- `strategy_arithmetic_non_prefix`: Add or subtract small numbers from some bytes.

It's just blindly poking the data. But notice that `last_bytes_used` field? That's where it gets clever.

### 3.4 How the Search Learns

The whole search runs inside a loop in `Builder::test`. It tries an input and looks at what happens. But it doesn't just see "success" or "failure". It classifies the result into different signals:

1. **Panic!** A real failure. Your code crashed, or an `assert!` failed. The rule broke. The harness prints the branch token and stops.
2. **`NotEnoughData`**: The test body says, "Hey, I tried to build a structure out of these bytes, but there aren't enough of them." The harness learns from this and tells the sampler to forcibly grow the buffer next time.
3. **`IncorrectFormat`**: The bytes were long enough, but they didn't make a valid structure. *But*, the test tells the harness how many bytes it actually looked at before it gave up. The harness stores this in `last_bytes_used`. Now, the sampler knows not to bother mutating the unused garbage bytes at the end, saving time.
4. **Success (`Ok(())`)**: The test produced a valid structure and the rule held. This counts as a "real try".

This classification is brilliant. It's how this tiny tool extracts value from malformed or partial inputs without needing a massive coverage engine to guide it.

### 3.5 The `Builder`: Keeping Things Bounded

You have to tell the searcher when to stop, otherwise your `cargo test` will run forever. `Builder` is the control panel.

```rust
pub struct Builder {
    search_bound: SearchBound, // Either a Limit (count) or Time (duration)
    min_iterations: u64,
    seed: Option<u64>,
    reproduce: Option<Branch>,
}
```

You can cap the search by a fixed number of successful tries (`with_search_limit`), or by a wall-clock duration (`with_search_time`). 

But here is a very important detail: time bounds and count bounds coexist. `with_min_iterations` guarantees the harness will *always* perform at least some minimum number of real, successful tries, even if the time budget is zero. This stops a fast test from just giving up immediately and falsely reporting success.

And `with_reproduce` is the bridge back to debugging. You plug in the hex string you got from a failure, and it skips all the exploring and goes straight to recreating the bug.

### 3.6 The Magic Boundary: `arbitrary::Unstructured`

We start with raw bytes in the sampler. But as I said, your code doesn't care about raw bytes. Look at the signature of the test function:

```rust
pub fn test(
    self,
    mut s: impl FnMut(&mut arbitrary::Unstructured<'_>) -> Result<(), arbitrary::Error>,
)
```

First, let's decipher the Rust syntax: `impl FnMut(...)` just means "give me a closure (a block of code) that I can call multiple times, and it's allowed to modify its own internal state."

But the real magic is that `Unstructured<'_>` object. That is the boundary between chaos and order. It takes the meaningless stream of bytes generated by the sampler and provides methods to safely pull out numbers, booleans, strings, and nested structures. This is where bytes become *meaning*. `minifuzz` isn't searching abstract noise; it's searching the space of nearby structured objects.

---

## 4. How It All Moves Together

The control flow is incredibly short. That's a feature, not a bug. Here is the entire lifecycle of a search iteration:

1. **Start**: The harness decides where to begin. It looks for an explicit `with_reproduce` token. If it doesn't find one, it checks for an environment variable `MINIFUZZ_BRANCH`. If that's empty, it just picks a random seed.
2. **The Loop**: 
   - The sampler produces a slice of bytes.
   - The bytes are wrapped in `Unstructured`.
   - Your test closure runs and tries to interpret them.
   - The result is classified (Learn? Grow? Succeed? Fail?).
3. **Advance**: If one path runs out of local room (based on the branch size limit), the harness calls `branch.next()` and switches the sampler to a slightly different branch of the random search.

Notice what is missing: no external processes communicating over sockets, no compiling separate fuzzer targets, no global state. It's just a loop inside a unit test. 

And remember the rule about counting: **We only count successful tries.** If the harness spends fifty rounds generating malformed junk that returns `IncorrectFormat`, that doesn't count against your search budget. You only pay for fully explored cases.

---

## 5. What Is This Good For?

Why build it this way? What pressure does this absorb?

- **Low Ceremony**: If the fuzzer is small enough to be a unit test, you'll actually write the invariant today instead of putting it off until tomorrow.
- **Deterministic Replay**: You never have to guess how a bug happened. The branch token is an absolute guarantee that you can get back to the failing state.
- **Local Exploration**: Bugs love to hide right next to the happy path. A simple mutation loop finds them incredibly fast when the invariant is phrased well.
- **Habit Forming**: The real victory isn't replacing heavy fuzzers. It's tricking you into forming the habit of testing *rules* instead of examples, simply because it's so easy.

---

## 6. What It Cannot Do

Let's be honest about the limits. This crate is small on purpose, which means it has boundaries.

- **It is not coverage-guided.** It has no idea what lines of code it's hitting inside your program. It won't systematically solve complex mazes of `if` statements to reach a deep bug.
- **Weak rules mean weak tests.** If you write a bad invariant that only describes the obvious happy path, `minifuzz` will happily just confirm the obvious happy path.
- **Input shape matters.** If your structured data is extremely rigid, the harness might spend a lot of time generating malformed samples. It learns, but it's not a genius.
- **Deep bugs still need heavy tools.** If a bug requires a million specific state transitions over hours of execution to manifest, `minifuzz` probably won't find it. You still need real fuzzers for the deep ocean. `minifuzz` is for the shallow water near the beach.

---

## 7. How to Read the Source

If you really want to understand it, open up `invariants/src/minifuzz.rs` and read it yourself. 
- Start with `Branch` and `Sampler` to see exactly how the local search works.
- Look at `Builder` to understand the budgets and reproduction logic.
- Read the main `Builder::test` loop to see the classification engine in action.
- Finally, read the tests at the very bottom of the file. Those tests are the actual contract: they prove that time limits work, that bad formats aren't counted as real tries, and that failures reproduce perfectly. 

## Summary

Testing doesn't have to be a choice between a couple of lazy examples and a giant, scary fuzzing infrastructure. By keeping the search local, focusing on structured inputs, and insisting on reproducible receipts, `commonware-invariants` gives you a pocket searcher. It's a way to ask "what if?" a thousand times, right inside your unit tests.