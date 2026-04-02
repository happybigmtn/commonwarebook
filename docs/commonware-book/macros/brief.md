# Chapter Brief: commonware-macros

## 1. Module Purpose

`commonware-macros` should be taught as the crate where repeated protocol
grammar becomes syntax.

The real systems question is not "when are macros convenient?" It is:

> when does a repeated control-flow, visibility, or test-harness pattern become
> important enough that hand-spelling it would let the workspace drift?

The answer in Commonware clusters around three families:

1. **control flow** - biased selection and shutdown-aware actor loops,
2. **stability** - compile-time visibility fences tied to release levels,
3. **test harnesses** - async tests, trace collection, and nextest grouping.

The chapter should therefore frame the crate as a **grammar**, not a helper
basket.

---

## 2. Source Files That Matter Most

### `macros/src/lib.rs`
**Why it matters:** The public vocabulary. It shows the spellings the rest of
the workspace is expected to use.

### `macros/impl/src/lib.rs`
**Why it matters:** The main engine. It contains the stability parser and
exclusion ladder, test harness rewrites, and select/select_loop parsing and
expansion.

### `macros/impl/src/nextest.rs`
**Why it matters:** Explains how `test_group` validates and normalizes names
against `.config/nextest.toml`.

### `macros/tests/select.rs`
**Why it matters:** The best executable spec for biased selection, lifecycle
hooks, and refutable-branch behavior.

### `macros/tests/stability.rs`
**Why it matters:** The clearest source for how the stability family behaves at
compile time, including `stability_scope!` and cfg predicates.

### `macros/tests/test_async.rs` and `macros/tests/test_traced.rs`
**Why they matter:** Smallest concrete examples of the test-harness shims.

---

## 3. Expanded Chapter Outline

```text
0. Opening apparatus
   - promise, crux, invariant, naive failure, reading map, assumptions

1. What problem does this solve?
   - repeated protocol grammar
   - why hand-spelling the same loop or gate drifts

2. Mental model
   - three stencils: control flow, stability, tests

3. Core ideas
   - `select!` makes branch priority visible
   - `select_loop!` turns one choice into an actor lifecycle
   - stability macros encode an exclusion ladder
   - `stability_scope!` makes compile-time control flow local
   - test macros standardize harness semantics
   - `test_group` treats nextest naming as build-time policy

4. How the system moves
   - call-site grammar
   - proc-macro expansion
   - tests as semantic edge checks

5. Pressure and tradeoffs
   - cancellation and shutdown
   - boilerplate drift
   - release discipline
   - observability
   - cross-crate composability

6. Failure modes and limits
   - biased starvation
   - syntax does not make logic correct
   - visibility fences do not prove semantic stability
   - harness quality still depends on the test

7. How to read the source / glossary
```

---

## 4. System Concepts To Explain At Graduate Depth

1. **Syntax can be an invariant.** The real value of `select_loop!` is that
   the shutdown branch and lifecycle shape become part of the call site.

2. **Biased selection is a protocol decision.** `select!` is not merely a thin
   wrapper; the `biased` keyword makes source order part of the semantics.

3. **Compile-time visibility is another kind of control flow.** The stability
   macros implement an exclusion ladder, and `commonware_stability_RESERVED`
   exists to let CI exclude all annotated items at once.

4. **Test harnesses are infrastructure.** `test_async`, `test_traced`, and
   `test_collect_traces` standardize execution and observability around the
   actual assertion logic.

5. **Name validation is a policy surface.** `test_group` plus `nextest.rs`
   turns grouping into a compile-time checked convention instead of a naming
   habit.

---

## 5. Visualizations To Build Later

1. **Event-loop stencil**  
   Show a hand-written actor loop versus `select_loop!`.

2. **Exclusion-ladder plate**  
   Show ALPHA through EPSILON items being hidden by higher stability cfgs, plus
   the special RESERVED level.

3. **Harness shim plate**  
   Show how `test_async` and `test_collect_traces` wrap a plain function into a
   standardized test envelope.

4. **Nextest naming plate**  
   Show raw group input being normalized, validated, and turned into a suffix.

---

## 6. Claims-To-Verify Checklist

- [ ] The chapter presents macros as shared protocol grammar rather than generic
      convenience.
- [ ] `select!` is explained in terms of biased branch priority.
- [ ] `select_loop!` is explained in terms of actor lifecycle and refutable
      branches.
- [ ] The stability family is taught as an exclusion ladder, including
      `commonware_stability_RESERVED`.
- [ ] The chapter explains why `test_group` validates against nextest config
      instead of blindly suffixing names.
- [ ] The tests are referenced as the real semantic evidence for the macro
      families.
