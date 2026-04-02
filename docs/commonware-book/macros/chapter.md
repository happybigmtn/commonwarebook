# commonware-macros

## Syntax for the Repeated Parts of Protocol Code

---

## Opening Apparatus

**Promise.** This chapter shows how `commonware-macros` turns a few repeated
protocol shapes into shared syntax so the rest of the workspace can speak one
control-flow, stability, and test language.

**Crux.** A macro in Commonware is not primarily a convenience feature. It is a
way to keep repeated protocol grammar from drifting across crates.

**Primary invariant.** When a pattern is standardized here, the call site
should expose the important protocol decision more clearly than the hand-written
version it replaces.

**Naive failure.** The easy mistake is to say, "it is only a little boilerplate,
I will just write it inline." Do that enough times and the workspace starts
speaking in dialects: one actor loop treats shutdown differently, one test
harness names groups differently, one stability gate excludes a different set of
items than another.

**Reading map.**

- Start with `macros/src/lib.rs` for the vocabulary the rest of the workspace
  is meant to speak.
- Then read `macros/impl/src/lib.rs` for the grammar and the exclusion rules
  that make the macros safe to use.
- `macros/impl/src/nextest.rs` shows how grouped tests become a build-time
  naming contract instead of a string convention.
- `macros/tests/select.rs` and `macros/tests/stability.rs` show the edges the
  macros must preserve.

**Assumption ledger.**

- The reader is comfortable with proc macros and async control flow.
- The chapter is about preserving recurring shapes, not about macro cleverness.
- Shared syntax is only useful if it makes the protocol easier to read.

---

## Background

Macros matter when the same control shape keeps reappearing and humans start
copying it by hand. A function can reuse behavior, but it cannot change syntax.
A macro can. That makes macros useful anywhere the important thing is not just
what code does, but how the code is spelled.

The vocabulary here is simple:

- **Token trees** are the raw shapes a macro receives.
- **Expansion** is the rewritten Rust the compiler actually checks.
- **Hygiene** is the rule that keeps names and scopes from colliding by
  accident.
- **Control-flow macros** keep branch order and loop exits visible.
- **Attribute macros** attach policy to items without repeating the policy at
  every call site.

The naive alternative is copy and paste. That works until the repeated shape
drifts. One loop remembers to prioritize shutdown. Another forgets. One test
harness names groups one way. Another names them differently. At that point the
workspace still compiles, but the shared meaning has started to splinter.

There is also a second naive alternative: hide the pattern in a helper
function. That is better than copy and paste when the repeated part is behavior.
It is not enough when the repeated part is syntax. A helper function cannot
make `else` sit beside a refutable pattern, cannot turn branch order into an
explicit policy, and cannot make a stability gate look like a local item
annotation.

The tradeoff is indirection. Macros can make a protocol easier to read once the
pattern is familiar, but they can also make debugging harder if the expansion is
too clever. That is why the right macro is small, explicit, and narrowly
focused. It should preserve a recurring shape, not invent a new language.

In this chapter, the main background idea is that syntax itself can be a form
of coordination. If several crates need the same policy, compile-time
rewriting can keep that policy uniform without forcing every caller to spell out
the same ceremony.

---

## 1. What Problem Does This Solve?

Protocol code keeps saying the same things:

- wait for whichever future is ready first,
- keep looping until shutdown wins,
- hide this item at higher stability levels,
- run this async test like a normal test,
- capture traces the same way everywhere,
- rename this test so nextest can filter it predictably.

Those are not random conveniences. They are repeated protocol moves. If every
crate hand-writes them, the workspace starts speaking in dialects. One actor
loop handles shutdown one way, another handles it a little differently, and the
reader has to relearn the same control flow in every file.

`commonware-macros` exists to stop that drift. It turns the repeated parts into
shared syntax so the call site can say the protocol directly instead of spelling
the surrounding ceremony every time.

That is why this crate belongs in the book. It is the grammar of recurring
protocol habits.

---

## 2. Mental Model

Think of the crate as a tiny compiler front end.

Each macro starts with syntax that humans already want to write, parses that
syntax into a structured shape, and then emits ordinary Rust with one
carefully chosen policy baked in. The important distinction is that the macro
is not "doing work" so much as lowering a small protocol grammar into explicit
code.

That lowering happens in three distinct ways:

- `select!` is a thin reexport around `tokio::select!` in biased mode.
- `select_loop!` parses a mini language, then expands it into a loop with a
  persistent shutdown future and ordinary select branches.
- the stability and test macros attach compile-time policy to items, then
  make the generated item shape match the policy exactly.

Once you read the crate this way, the interesting question stops being "what
macro should I call?" and becomes "what expansion shape does the protocol need?"

---

## 3. The Core Ideas

### 3.1 `select!` Makes Priority Visible

Protocols spend a lot of time waiting on many things at once. A message
arrives, a timer fires, a connection closes, a cancellation signal comes in.
The real question is not "how do I poll futures?" It is "which event should
win if two are ready?"

`select!` answers that question by generating a biased `tokio::select!` block.
The source order of the branches is therefore part of the protocol. An earlier
branch is not merely earlier in the file. It is earlier in the scheduling
policy.

That matters because priority is often a semantic choice. If shutdown should
win before work drains, or if a control channel should be checked before a
bulk-data branch, the source order needs to say so directly. The macro keeps
that choice visible instead of hiding it in a helper function or a nested
`match`.

### 3.2 `select_loop!` Turns One Choice Into an Actor Lifecycle

The richer macro is `select_loop!`.

Its parser is intentionally narrow. `SelectLoopInput` expects a context
expression, an optional `on_start`, a required `on_stopped`, a sequence of
branches, and an optional `on_end`. Each branch is parsed as `pattern = future
[else expr] => body`, with `Pat::parse_single` ensuring the pattern is already
in a form the compiler understands.

That grammar exists so the expansion can be honest. The emitted code is not a
magical runtime. It is a `let mut shutdown = context.stopped();` binding, a
plain `loop`, a biased select, and a couple of lifecycle hooks placed at exact
points in that loop.

Two implementation details are worth calling out.

First, refutable patterns must carry an `else` clause. The macro checks that at
parse time with a tiny irrefutability test, so `Some(msg) = rx.recv()` without
an `else` is rejected immediately instead of becoming a confusing runtime
branch.

Second, `expr_to_tokens` inlines block contents instead of wrapping them in an
extra block every time. That preserves lexical scope for `on_start`, the select
arms, and `on_end`. A variable introduced in `on_start` is supposed to be
visible in the rest of the iteration, and the expansion keeps that promise.

The resulting shape is roughly:

```text
let mut shutdown = context.stopped();
loop {
    on_start
    select! {
        _ = &mut shutdown => { on_stopped; break; }
        branches...
    }
    on_end
}
```

That is a lifecycle, not just a convenience wrapper.

### 3.3 The Stability Macros Encode an Exclusion Ladder

The stability family looks simple from the outside:

- `#[stability(LEVEL)]`
- `stability_mod!(LEVEL, pub mod name)`
- `stability_scope!(LEVEL { ... })`

The interesting part is how the proc macro lowers the level into cfg guards.
`StabilityLevel` accepts either the integer levels `0..4` or the named levels
`ALPHA` through `EPSILON`. `exclusion_cfg_names(level)` then constructs every
higher stability cfg plus `commonware_stability_RESERVED`.

That reserved cfg is the key systems detail. It gives CI a way to hide every
annotated public item at once and then inspect rustdoc output for stragglers.
Any public item that still appears under the reserved cfg is an unmarked item,
which is exactly the sort of omission the stability checks are meant to catch.

`stability_scope!` makes the same rule local to a block of items. If the caller
provides `cfg(feature = "std")`, the macro emits `#[cfg(all(feature = "std",
not(any(...))))]` on every item. The macro is therefore not "just" adding
attributes. It is making one visibility policy apply to a whole scope without
letting the items drift apart.

### 3.4 `stability_scope!` Shows That Compile-Time Control Flow Can Also Be Local
`stability_scope!` deserves separate attention because it teaches the same idea
as `select_loop!`, but at compile time.

A module can say, in one place, "these items are all the same stability level,
and they also all share the same `cfg` predicate." The macro then rewrites each
item with the same exclusion guard. That makes the scope itself the unit of
policy instead of each item becoming a tiny snowflake of `#[cfg]` logic.

The tests in `macros/tests/stability.rs` are valuable because they show that
the grouped form is not a different meaning. It is the same exclusion ladder
applied to a block instead of repeated per item.

### 3.5 The Test Macros Standardize Harness Semantics

The test macros are best understood as harness shims.

`test_async` strips the `async` from the function signature, keeps the original
item shape, and wraps the body in `futures::executor::block_on`. The point is
not just convenience. It keeps async tests in the same class as ordinary
tests, which matters when a suite needs to mix both styles.

`test_traced` validates the requested log level, builds a subscriber with
`FmtSpan::CLOSE`, and runs the test under that dispatcher. `test_collect_traces`
goes one step further: it creates a `TraceStorage`, builds both a formatting
layer and a collecting layer, and uses `crate_name("commonware-runtime")` to
find the right path to the runtime crate even if the workspace renamed it.

`test_group` is the smallest macro with the sharpest policy. It sanitizes the
group name, checks it against `.config/nextest.toml` when that file exists, and
then rewrites the function name so the group is part of the binary-level test
identity. That makes nextest filters a build-time contract instead of a string
convention.

### 3.6 `test_group` Treats Nextest Names as Build-Time Policy
The smallest-seeming macro may be the one that matters most.

`test_group("...")` turns test naming into a build-time contract. Group names
are normalized, validated against `.config/nextest.toml`, and rejected early if
they are unknown. Only when the config file is absent entirely does the macro
fall back quietly.

That is the Commonware pattern in miniature: keep policy close to the call
site, but make the policy visible to the compiler.

---

## 4. How the System Moves

The easiest way to understand the crate is to follow one repeated pattern from
call site to expansion to tests.

### 4.1 Control-Flow Syntax Starts as a Small Local Claim

A protocol actor says:

```text
wait on these futures,
prefer shutdown,
prefer higher-priority branches,
loop until a refutable pattern or shutdown says stop.
```

At the call site that becomes `select!` or `select_loop!`, which keeps the
policy visible in source order and branch structure.

### 4.2 The Proc Macro Expands That Claim Into Explicit Runtime Machinery

Inside `macros/impl/src/lib.rs`, the parser converts the branch syntax into
structured inputs, then expands them into real `tokio::select!` code with the
appropriate lifecycle around it.

The result is not a hidden runtime. It is ordinary Rust generated from a shared
grammar.

### 4.3 The Tests Then Nail Down the Semantic Edges

`macros/tests/select.rs` proves the details that matter:

- priority is source-order biased,
- lifecycle hooks run at the documented times,
- shutdown wins when it should,
- and refutable patterns plus `else` clauses behave like explicit actor-exit
  edges.

`macros/tests/stability.rs` does the same thing for compile-time visibility:

- level-gated items compile or disappear together,
- scoped gating behaves like repeated per-item gating,
- and cfg predicates compose with stability levels.

### 4.4 The Test Harness Macros Repeat the Same Pattern

The call site says:

- this test is async,
- or this test wants tracing,
- or this test wants trace storage,
- or this test belongs to a nextest group.

The proc macro expands the harness shape, and the small unit tests confirm the
edge behavior.

That is the repeated lesson of the whole crate:

> the macro should preserve a recurring protocol shape, and the tests should
> prove the preserved edges.

---

## 5. What Pressure It Is Designed To Absorb

The first pressure is **cancellation and shutdown**. Protocol actors spend most
of their lives waiting, so the shutdown path must be boring and uniform.

The second pressure is **boilerplate drift**. Without macros, each crate
invents its own small ritual for loops, tests, trace capture, and stability
gates. Those rituals diverge.

The third pressure is **release discipline**. Stability levels are part of the
API story, so the visibility rule needs to be visible in the source and
inspectable by CI.

The fourth pressure is **observability**. Tests need consistent tracing and
predictable names, or debugging becomes a scavenger hunt.

The fifth pressure is **cross-crate composability**. Shared syntax keeps the
workspace sounding like one system instead of many similar but slightly
different ones.

---

## 6. Failure Modes and Limits

This crate is powerful, but it is not magic.

### 6.1 Biased Selection Can Starve Later Branches

`select!` is biased on purpose. That is useful when priority matters and
dangerous when an earlier branch is almost always ready.

### 6.2 `select_loop!` Does Not Make the Body Correct

The macro standardizes the loop shape. It does not decide when the protocol
should `break`, `continue`, or persist state.

### 6.3 Stability Macros Enforce Visibility, Not Semantic Stability

The macros can make API fences consistent. They cannot prove that the behavior
behind a visible item stayed compatible.

### 6.4 A Clean Harness Still Needs a Good Test

`test_traced` and `test_collect_traces` standardize observability. They do not
make a weak assertion strong.

The limit is therefore the same in every family: the syntax can protect the
pattern, but not the truth of the protocol using that pattern.

---

## 7. How to Read the Source

Start with `macros/src/lib.rs` to see the public surface. Then read
`macros/impl/src/lib.rs` for the grammar that preserves control-flow and
stability rules, `macros/impl/src/nextest.rs` for the naming contract, and the
tests for the cases where the abstraction must stay honest.

---

## 8. Glossary and Further Reading

- **biased selection**: source-order priority among simultaneously ready
  branches.
- **refutable pattern**: a pattern that may fail to match and therefore needs an
  `else` path.
- **stability exclusion ladder**: the cfg sequence that hides lower-stability
  items at higher stability levels.
- **reserved stability cfg**: the synthetic `commonware_stability_RESERVED`
  level used to exclude all annotated items during CI visibility checks.
- **nextest group**: a validated suffix that keeps nextest filtering
  predictable.
- **TraceStorage**: the runtime trace collector handed into
  `test_collect_traces`.

Further reading:

- `macros/src/lib.rs`
- `macros/impl/src/lib.rs`
- `macros/impl/src/nextest.rs`
- `macros/tests/select.rs`
- `macros/tests/stability.rs`
