# commonware-invariants

## Make Invariant Testing the Default

---

## Opening Apparatus

**Promise.** This chapter shows how `commonware-invariants` makes
invariant-driven testing cheap enough to live beside ordinary unit tests.

**Crux.** The crate is not trying to replace serious fuzzing. It is trying to
make the *first useful invariant search* so easy that authors reach for it
before they resign themselves to a handful of examples.

**Primary invariant.** A failure should be both discoverable by exploring many
nearby structured inputs and replayable through one compact branch token.

**Naive failure.** The usual trap is to stand between two bad defaults: either
write one or two example tests and hope they generalize, or postpone the whole
effort until there is time for a full fuzz target. `minifuzz` exists in that
gap.

**Reading map.**

- Start with `invariants/src/minifuzz.rs`; almost everything important lives
  there.
- `Builder` is the search contract: it sets the budget, the replay token, and
  the stopping rules.
- `Branch` and `Sampler` show how the search stays local while still moving to
  nearby possibilities.
- The tests at the bottom pin down the replay and termination behavior that the
  harness must preserve.

**Assumption ledger.**

- The reader is comfortable with property-style testing and `arbitrary`.
- The chapter is about local search inside unit-test territory, not
  coverage-guided fuzzing infrastructure.
- A good invariant still matters more than the tool.

## Background

Testing has three broad modes. Example tests check a few hand-picked cases.
Property tests check a rule across many generated cases. Fuzzers explore a much
larger input space and try to uncover unexpected states. `commonware-invariants`
borrows the most useful idea from each one: state a rule, explore nearby
inputs, and keep the failure reproducible.

The basic vocabulary is worth naming clearly:

- **Invariant**: something that should stay true across many inputs.
- **Search space**: the family of nearby cases the harness can explore.
- **Structured input**: raw bytes interpreted as a typed object.
- **Mutation**: a small change that moves one case to a nearby case.
- **Replay**: the ability to reproduce the same failing path later.

The naive alternatives are both familiar. One is to stop at a few examples and
hope the examples cover the real boundary cases. The other is to jump straight
to a heavyweight fuzzing setup when the first useful question is still small.
The first fails because it is too narrow. The second fails because the setup
cost can outrun the bug hunt.

This crate sits in the middle. It assumes many bugs live near the happy path,
where small shifts in shape, length, or ordering reveal a broken assumption. It
also assumes that a useful test must be repeatable, because a discovered bug is
not much help if nobody can get back to it.

The tradeoff is depth. A local invariant search is not coverage-guided fuzzing,
and it does not try to be. It gives you a cheap, deterministic way to ask,
"what if this structure is slightly different?" That is often enough to expose
the bug that plain examples would miss.

---

## 1. What Problem Does This Solve?

Most teams already know the two extremes. Ordinary unit tests are cheap and
clear, but they only check the few examples we remembered to write down. Full
fuzzing is stronger, but it often arrives with enough harnessing, build setup,
and replay machinery that the first useful invariant never gets a fair hearing.

`commonware-invariants` exists to close that gap. Its job is to make
invariant-driven testing cheap enough to live beside the unit test. The crate
does not try to replace serious fuzzing. It tries to make the first useful step
so light that people actually take it.

When the question is, "what should always be true here?", the answer should not
be, "first build a separate fuzzing project." The answer should be, "write the
invariant, then let `minifuzz` search a small space of structured inputs."

That is the habit this crate wants to teach: test the rule, not just the
example, and make that habit easy enough to repeat.

---

## 2. Mental Model

The cleanest mental model is a **pocket searcher**.

Imagine a unit test that can get curious. You give it a rule instead of a
single sample. It starts from a small buffer, nudges that buffer in simple
ways, interprets the bytes as structured data, and keeps asking whether the
rule still holds. If the answer is no, it keeps the evidence. If the answer is
yes, it keeps trying until the search budget says stop.

That is not full fuzzing. It is smaller, local, and intentionally modest. But
it keeps the best part of fuzzing: many related questions instead of one
example. And it keeps the best part of unit tests: it is cheap enough to live
next to the code it protects.

The useful picture is this:

- the invariant is the promise,
- the sampler is the curiosity,
- the search budget is the discipline,
- and the replay token is the receipt.

If a failure appears, the test does not just say "something went wrong." It
prints a token you can paste back in and reproduce the same path.

---

## 3. The Core Ideas

### 3.1 Invariants Are the Unit of Thought

The crate does not ask you to organize tests around a pile of hand-picked
examples. It asks you to state a rule that should survive many inputs.

That matters because protocol bugs are usually not "this one example string is
wrong." They are "the system accepted a family of inputs it should have
rejected" or "the state machine breaks when the input is slightly rearranged."
An invariant turns that into something searchable.

This is why the chapter should begin from the rule, not from the harness. The
harness only matters if the property says something wider than "this one case
worked."

### 3.2 `Branch` Is the Search Identity

The most distinctive type in `minifuzz.rs` is `Branch`.

It stores three numbers:

- `seed`,
- `thread`,
- `size`.

Together these become the branch token printed on failure as
`MINIFUZZ_BRANCH = 0x...`.

That token is not just a debugging ornament. It is the identity of the current
search path:

- `seed` anchors the overall random family,
- `thread` distinguishes one local branch of exploration from the next,
- `size` tracks how far this branch has grown its input.

The `Display` implementation turns that state into a 24-hex-digit receipt. The
parser turns it back into a `Branch`. That makes failures portable. The test
runner can rediscover the same path without the author reconstructing the seed,
iteration count, or mutation sequence by hand.

### 3.3 `Sampler` Is a Small Mutation Engine, Not a Corpus Manager

The sampler is intentionally modest.

It keeps:

- one RNG,
- one current buffer,
- one remaining-count budget for the current branch,
- and one memory of how many bytes the test body actually consumed last time.

That last field, `last_bytes_used`, is more important than it first appears.
When the test returns `IncorrectFormat`, the harness learns how much of the
sample was actually meaningful before parsing failed. Later strategy choices can
use that information to avoid blindly growing unused suffix bytes.

The mutation strategies themselves are deliberately simple:

- add more bytes,
- modify the prefix,
- copy a portion of the existing bytes,
- clear non-prefix bytes,
- apply arithmetic nudges outside the prefix.

This is not trying to rival a coverage-guided engine. It is trying to explore a
useful local neighborhood around the current structured shape.

### 3.4 Result Classification Is How the Search Learns

The search loop in `Builder::test` does not treat every non-success the same.
It classifies outcomes into different search signals.

If the test body panics, that is a real failure. The harness reports the branch
token and stops.

If the test returns `arbitrary::Error::NotEnoughData`, that means the current
sample was simply too short to instantiate the structured case. The harness
responds by forcibly growing the buffer.

If the test returns `arbitrary::Error::IncorrectFormat`, that means the sample
did become structured enough to say something about the prefix, even though it
did not become a valid full case. The harness records how many bytes were
actually consumed so the next mutation can be smarter.

If the test succeeds, the attempt counts as a real try and advances the search
budget.

This classification is the quiet center of the crate. It is how a tiny harness
extracts value from malformed or partial samples without needing global coverage
feedback.

### 3.5 `Builder` Keeps Search Bounded but Replayable

`Builder` is the crate's control surface. It sets the seed, the search limit,
the wall-clock limit, the minimum iteration floor, and the reproduction token.
The important design choice is that time and count bounds are allowed to
coexist.

`with_search_limit` caps the number of successful tries directly. `with_search_time`
caps runtime by wall-clock duration. `with_min_iterations` says the harness
must still perform at least some minimum number of real tries even if the time
budget is already exhausted.

That last rule is what keeps a zero-time or near-zero-time search from
degenerating into "did nothing." The test
`min_iterations_overrides_search_time` exists precisely to nail that down.

`with_reproduce` is the bridge from discovery back to development. It turns the
printed token into the initial branch and skips all the guesswork.

### 3.6 `arbitrary::Unstructured` Is the Boundary Between Bytes and Meaning

The harness starts from raw bytes, but the test body almost never cares about
raw bytes by themselves. It cares about a structure:

- a plan,
- a message,
- a fragment,
- a tree,
- a set of options,
- or some other typed object the code actually reasons about.

`Unstructured` is where those bytes become a meaningful question.

This is why the crate belongs in the book of a systems library. Many bugs hide
exactly at the point where a byte stream first becomes structure. `minifuzz`
does not search abstract entropy. It searches nearby structured cases.

---

## 4. How the System Moves

The control flow is short, which is part of the design.

### 4.1 The Search Starts From Either Reproduction or Exploration

`Builder::test` begins by choosing the starting branch.

The priority order is:

1. explicit `with_reproduce(...)`,
2. explicit `with_seed(...)`,
3. `MINIFUZZ_BRANCH` from the environment,
4. otherwise a random branch seed.

That ordering matters because it makes reproduction a first-class mode, not an
afterthought. The same API handles both "go look around" and "re-run this exact
failure."

### 4.2 One Search Iteration Has a Clear Lifecycle

A single iteration looks like this:

```text
branch
  -> sampler produces bytes
  -> bytes become Unstructured
  -> test body interprets structure
  -> result is classified
  -> sampler learns or branch advances
```

That lifecycle is why the crate feels light. There is no external corpus, no
coverage engine, and no out-of-process fuzzer handshake. The whole search is a
loop inside a test.

### 4.3 Search Budgets Count Successful Tries, Not Every Allocation of Bytes

One subtle but important rule: the harness increments `tries` only on `Ok(())`.

That means malformed inputs do not count as fully explored cases. A test that
spends ten samples merely discovering that the current buffer is too short or
poorly shaped has not yet consumed ten units of real search budget.

This is another place where the tests act as a contract:

- `incorrect_format_does_not_count_as_try`
- `search_limit_reduces_min_iterations`

Together they explain how the crate thinks about "enough search."

### 4.4 Branch Advancement Is the Smallest Form of Search-Tree Traversal

When one sampler path runs out of local room, the harness calls `branch.next()`
and switches the sampler to the new branch.

This is not a deep search tree, but it is enough to give the harness a second
dimension beyond "keep mutating the same bytes forever." The search can move to
nearby branches while keeping the same overall format and replay discipline.

### 4.5 The Tests at the Bottom Are the Real Spec

The tests in `minifuzz.rs` are unusually important because they pin the
behavior that makes the harness useful: structured searches still find real
panics, replay tokens reproduce the same failure, malformed inputs do not fake
progress, and time limits never erase the minimum-iteration rule. That is a
better spec than prose alone.

---

## 5. What Pressure It Is Designed To Absorb

### 5.1 Low Ceremony

If the harness is small enough to live in a test module, the invariant gets
written sooner. That is the economic argument behind the crate.

### 5.2 Deterministic Replay

A failure must be reproducible without guesswork, and the branch token gives the
bug a handle.

### 5.3 Local Exploration

Many useful bugs are not far away from the happy path, and a small mutation loop
can find them quickly when the invariant is phrased well.

### 5.4 Bounded Time

Full fuzzing is valuable, but not every check deserves a long-running setup.
This crate gives you a version of the same idea that can run as part of a
normal test workflow.

### 5.5 Habit Formation

The real win is not that this harness is powerful enough to replace other
testing. The real win is that it is simple enough to become a habit.

---

## 6. Failure Modes and Limits

This crate is intentionally smaller than a full fuzzing system, so it has to be
honest about what it cannot do.

### 6.1 It Is Not Coverage-Guided

There is no coverage feedback loop, no corpus minimization, and no claim that
the harness will discover the deepest state-space bugs on its own.

### 6.2 Weak Invariants Stay Weak

If the property is vague, the test will be vague. If the property only
describes the obvious happy path, the harness will only keep confirming the
obvious happy path.

### 6.3 Input Shape Matters

If the structure induced by `arbitrary` is too rigid, the harness may spend much
of its time on malformed samples. That is not always wasted work, but it can
limit how much semantic territory the current budget explores.

### 6.4 Long-Horizon Bugs Still Need Heavier Tools

A protocol bug that appears only after a long execution history, or only after
coverage-guided exploration finds a narrow branch, may still deserve a real
fuzzing target.

The right reading of these limits is not "the crate is weak." It is "the crate
is small on purpose." It is a bridge, not the whole road.

---

## 7. How to Read the Source

Start with `invariants/src/minifuzz.rs` itself, then read `Branch` and
`Sampler` as the mechanism for local search, `Builder` as the budget and replay
policy, `Builder::test` as the full loop, and the tests as the contract for
what counts as progress or failure. `invariants/README.md` is only the shortest
external summary; the real explanation is in the source.

---

## 8. Glossary and Further Reading

- **invariant**: a rule the code should satisfy across many inputs.
- **branch token**: the compact hex identity of a specific search path.
- **sampler**: the local mutation engine that turns one buffer into many nearby
  cases.
- **NotEnoughData**: a signal that the current sample is too short and should be
  grown.
- **IncorrectFormat**: a signal that the sample had partial structure and
  revealed how many bytes were meaningfully consumed.
- **successful try**: a search iteration that produced a well-formed structured
  case and therefore counts against the search budget.

Further reading:

- `invariants/src/minifuzz.rs`
- `invariants/README.md`
- `commonware-codec` and `commonware-coding` chapters for good examples of
  invariants that become especially valuable under structured search
