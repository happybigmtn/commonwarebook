# Chapter Brief: commonware-invariants

## 1. Module Purpose

`commonware-invariants` should be taught as the crate that makes
invariant-driven testing cheap enough to become a normal development habit.

The chapter should resist the framing of "tiny fuzzing helper." The deeper
question is:

> how do we search enough nearby structured inputs to stress a rule, while
> keeping the harness small enough to live in an ordinary test module?

That is why `minifuzz` matters. It occupies the space between example tests and
full fuzzing:

- examples are too narrow,
- full fuzzing can be too heavy,
- `minifuzz` gives the first useful search loop a cheap home.

The chapter's governing image should remain the **pocket searcher**:

- the invariant is the promise,
- the sampler is the curiosity,
- the branch token is the receipt,
- the builder is the search discipline.

---

## 2. Source Files That Matter Most

### `invariants/src/minifuzz.rs`
**Why it matters:** This file is almost the whole chapter. It contains the
search identity (`Branch`), mutation engine (`Sampler`), control surface
(`Builder`), result-classification logic, and the tests that specify replay and
stopping behavior.

### `invariants/README.md`
**Why it matters:** Useful as the shortest public positioning statement, but
the real lecture lives in the source file.

---

## 3. Expanded Chapter Outline

```text
0. Opening apparatus
   - promise, crux, invariant, naive failure, reading map, assumptions

1. What problem does this solve?
   - examples are too narrow
   - full fuzzing can be too heavy
   - why the first invariant search should be cheap

2. Mental model
   - pocket searcher
   - replay receipt
   - bounded curiosity

3. Core ideas
   - invariants as the unit of thought
   - `Branch` as the search identity
   - `Sampler` as a small mutation engine
   - result classification as learning
   - `Builder` as bounded-but-replayable control surface
   - `Unstructured` as the boundary between bytes and meaning

4. How the system moves
   - starting from reproduce or exploration mode
   - one full search iteration lifecycle
   - successful tries versus malformed probes
   - branch advancement
   - tests as the real spec

5. Pressure and tradeoffs
   - low ceremony
   - deterministic replay
   - local exploration
   - bounded time
   - habit formation

6. Failure modes and limits
   - not coverage-guided
   - weak invariants stay weak
   - rigid input formats can waste budget
   - long-horizon bugs still need heavier tools

7. How to read the source / glossary
```

---

## 4. System Concepts To Explain At Graduate Depth

1. **The branch token is the real bridge from discovery to debugging.**
   Failure only becomes useful once the same path can be replayed exactly.

2. **Mutation strategy and result classification work together.** The sampler
   does not just mutate blindly; `NotEnoughData` and `IncorrectFormat` feed back
   into how the search proceeds.

3. **Search budgets count successful tries, not every byte mutation.** This is
   a subtle but important part of why the harness feels fair in unit-test
   territory.

4. **`minifuzz` is about structured search, not raw entropy.** `arbitrary`
   gives the bytes semantic meaning, which is where the invariant really lives.

5. **The tests at the bottom are the social contract.** Replay, min-iterations,
   malformed input handling, and panic reporting are all pinned down there.

6. **The crate is intentionally a bridge, not a competitor to full fuzzing.**
   The chapter should say that positively rather than apologetically.

---

## 5. Visualizations To Build Later

1. **Bridge plate**  
   Show example tests on one side, full fuzzing on the other, and `minifuzz`
   as the middle tool.

2. **Branch-token plate**  
   Show a failure printing `MINIFUZZ_BRANCH = 0x...` and then being replayed via
   `with_reproduce(...)`.

3. **Search-iteration plate**  
   Show sample generation, `Unstructured`, classification, and branch advance.

4. **Budget plate**  
   Show the difference between successful tries and malformed non-counting
   probes.

---

## 6. Claims-To-Verify Checklist

- [ ] The chapter makes clear that `minifuzz` is a bridge between examples and
      heavier fuzzing.
- [ ] `Branch`, `Sampler`, and `Builder` are all taught as conceptual pieces,
      not just as type names.
- [ ] The chapter explains the role of `NotEnoughData` and `IncorrectFormat`
      in steering the search.
- [ ] The chapter explains why only successful tries count against the budget.
- [ ] The replay story centers on `MINIFUZZ_BRANCH`.
- [ ] The tests are referenced as the main semantic evidence for the harness.
