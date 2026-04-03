# commonware-utils

*Small, sharp tools for canonical shapes, coordination lifecycles, and replayable state.*

---

## Opening Apparatus

**Promise.** You see, people often look at a `utils` crate and think, "Ah, here's the junk drawer! This is where we throw all the random ten-line functions we couldn't figure out where else to put." But that's exactly what this chapter is *not* about. This chapter shows how `commonware-utils` is actually a very carefully curated belt of tools. It keeps recurring invariants—the promises our code makes to itself—in one canonical place, so the rest of the workspace doesn't have to constantly rediscover them.

**Crux.** This crate is where Commonware names small, but absolutely vital, facts of nature:
- What does a committee set actually look like?
- What does it mean for a value to be mathematically non-empty?
- How do we know when a job is truly complete, versus just canceled?
- How do we put a firm boundary on concurrency so the machine doesn't choke?
- And how on earth do you keep a historical record of a mutable bitmap without cloning the whole darn thing every time a bit flips?

**Primary invariant.** Once we give a recurring shape a trusted home, the rest of the workspace needs to use that shape directly. We stop re-inventing the wheel in slightly different, subtly broken ways.

**Naive failure.** The easy trap to fall into is saying, "Oh, I just need to sort and deduplicate this list. It's only a few lines, I'll just write it right here." But if you make enough of those decisions, the workspace starts to argue with itself:
- One crate sorts and deduplicates.
- Another accidentally preserves the insertion order.
- Another forgets to check if the list is empty.
- Yet another invents its own chaotic rule for what "canceled" means.

**Reading map.**
- `utils/src/ordered.rs` is where we define what a canonical collection is.
- `utils/src/acknowledgement.rs`, `futures.rs`, `concurrency.rs`, and `sync/mod.rs` explain how to coordinate tasks without pulling your hair out.
- `utils/src/bitmap/historical/` contains the most fascinating state machine in the crate.
- `utils/src/vec.rs` shows how a tiny structural promise changes everything downstream.

**Assumption ledger.**
- We assume you are comfortable with ordinary Rust collections and async control flow.
- We're talking about cross-cutting infrastructure here, not specific domain logic like consensus or crypto.
- The goal isn't to list every single helper function. We just want to explain the few fundamental shapes that matter.

## Background

When you write systems code long enough, you realize you keep bumping into the exact same physical realities over and over:
- You have a list, but it really needs to be sorted and have no duplicates.
- You have a vector, and you want to ask for its first item, but you don't want to deal with `Option` because you *know* it shouldn't be empty.
- You fan out a task to five workers, and you need to know when all five have checked back in—not just one, not just a boolean flag, but all of them.
- You want to enforce a limit on how much work happens at once, but you want to enforce it *once*, right at the gate.
- You have a massive bitmap of state, and you need to remember its history, but if you copy the whole thing on every commit, you'll run out of memory!

These aren't just "helpers." These are shared assumptions about how our universe operates. If these assumptions only live in comments and defensive `if` statements scattered across the code, they drift. One part of the code handles an edge case one way, another handles it differently, and soon, nobody knows what anything means anymore.

The tradeoff we make in this crate is that the code gets more explicit. You might have to jump through a small hoop—call a constructor, do a conversion—before you get the value you want. But that's a bargain! Up-front structure is infinitely cheaper than repeating defensive checks everywhere else.

## 1. What Problem Does This Solve?

If you look across the monorepo, the same questions keep coming up, just wearing different hats:
- How do we prove a committee is the *canonical* committee, and not just some random `Vec`?
- How do we guarantee a collection is non-empty so we can stop wrapping every single access in an `Option`?
- How do we tell the difference between "everybody finished" and "somebody gave up"?
- How do we throttle tasks without inventing another ad-hoc, buggy counter?
- How do we rewind a bitmap's history efficiently?

`commonware-utils` exists to answer those questions definitively, once and for all. It's a consistency layer. It takes these recurring, tiny invariants and turns them into named, reusable, ironclad contracts.

## 2. Mental Model

I want you to imagine a toolbelt. Not a sprawling taxonomy of every possible gadget, but a tight belt of sharp, specific tools for recurring work. You don't carry every tool; you carry the ones that solve the problems you face every day.

That's how this crate works:
- `ordered::Set` gives us a canonical shape for collections.
- `Participant` and `Faults` let us do committee math with real types instead of ad-hoc integers.
- `NonEmptyVec` makes a tiny, unbreakable structural promise.
- `Exact`, `Pool`, `AbortablePool`, `Limiter`, `KeyedLimiter`, and `UpgradableAsyncRwLock` give us a common language for lifecycle and coordination.
- `bitmap::historical` is the crown jewel on the belt: a state machine that handles snapshots and diffs with explicit commit, abort, and prune boundaries.

The beauty isn't that these tools are particularly fancy or complex. The beauty is that they allow the rest of the monorepo to stop improvising.

## 3. The Core Ideas

### 3.1 Canonical Collections Are a Type, Not a Convention

Take a look at `utils/src/ordered.rs`. This is the clearest example of what we mean by a canonical collection.

When you see `Set<T>`, it is *not* just a wrapper around `Vec<T>`. It is a promise. It promises:
- The items are sorted.
- Every item is unique.
- The indexing is stable.
- You can do binary-search lookups.

The collection has one agreed-upon shape. It's not "whatever order happened to be convenient when I created it." 

And the constructors make this policy totally transparent:
- `from_iter_dedup` is the friendly one: it silently removes duplicates.
- `TryFromIterator` is the strict one: if it sees a duplicate, it yells at you with an error.
- The codec decoding is the strictest of all: it outright rejects any encoded set if the items aren't already sorted and unique.

That last part is crucial. Think about it! The decoder doesn't politely sort the data for you. The sender is supposed to have emitted the canonical form. We enforce canonicalization at the boundary, not lazily after the fact. If the data comes in messy, we reject it. 

### 3.2 Structural Promises Belong in Types

`NonEmptyVec` (in `utils/src/vec.rs`) does the exact same thing, just on a smaller scale.

Once you hold a `NonEmptyVec<T>`, you are mathematically guaranteed certain things. You can:
- Ask for `first()` and `last()` and you get the item directly—no `Option`, no unwrapping.
- Map, resize, and convert it, knowing it will preserve its non-emptiness.
- Use mutation helpers that absolutely refuse to leave the structure empty.

Why do we do this? Not just for convenience! We do it to completely eliminate a whole category of mental overhead. We remove all those local comments that say `// this should probably never be empty`. If a precondition is going to appear in fifty different call sites, we take that precondition and bake it directly into the identity of the type.

### 3.3 Lifecycle and Coordination Objects Make Control Flow Explicit

Now, let's look at control flow. How do things start, coordinate, and stop?

Take `Exact` in `acknowledgement.rs`. It's a tiny protocol for completion. Imagine you're organizing a hike. You create a handle and a waiter. Every time a friend joins the hike, you clone the handle. The waiter sits there and waits. It only resolves to "success" when *every single clone* has explicitly acknowledged they are done. But here's the clever bit: if any friend drops their handle without acknowledging—if they just walk off the trail—the waiter immediately resolves to cancellation.

This is infinitely stronger than a boolean flag. It lets the code distinguish between two very different states: "All parties finished successfully" versus "Someone stopped participating."

`Pool<T>` and `AbortablePool<T>` in `futures.rs` do something similar for async tasks. They say:
- Keep an unordered set of in-flight futures.
- Always provide a safe `next_completed()` method, even if the pool is currently empty.
- Optionally give each task an `Aborter` so you can kill one specific task when you drop it.

`Limiter` and `KeyedLimiter` in `concurrency.rs` take the nebulous concept of "backpressure" and turn it into a physical law. 
- A `Limiter` hands out a reservation. When you drop the reservation, the slot opens up.
- A `KeyedLimiter` adds a rule: you can't acquire the same key twice concurrently, and the total number of active keys is bounded.

You see, we don't just put `// TODO: add backpressure` in a comment. We make backpressure a protocol rule enforced by the compiler.

### 3.4 The Historical Bitmap Is a Real State Machine

Now we get to `utils/src/bitmap/historical/bitmap.rs`. This is where the crate stops looking like a collection of handy wrappers and starts looking like a piece of finely-machined systems infrastructure.

The historical bitmap has to do two conflicting things:
1. Keep one full, prunable bitmap as the current "head" state so we can read it fast.
2. Keep a history of past commits so we can roll back, but without copying the entire universe.

How does it do it? By keeping historical commits as *reverse diffs*. 

The conceptual breakthrough is the clean/dirty split using Rust's type system (`BitMap<N, Clean>` vs `BitMap<N, Dirty>`):
- `Clean` means nothing is currently being mutated.
- `Dirty` means mutations are happening right now, but they aren't committed.

This split makes the lifecycle entirely visible and impossible to mess up:
1. You call `into_dirty()` to open a mutable batch. The type changes!
2. You make your edits through the dirty view.
3. You call `commit(height)` to seal the batch into history, OR you call `abort()` to throw it away.
4. You get back to a clean state.

And while it's dirty, it's not just a vague overlay. It tracks the physical reality of the future: `modified_bits` for edits, `appended_bits` for the tail, and `chunks_to_prune` for data we still need to recover later. If you read the bitmap while it's dirty, it projects the future state perfectly: it looks at appended bits first, then modified bits, and finally falls back to the base bitmap.

It answers the question, "What would this look like if we committed right now?" without actually having to commit! It's a beautiful, compact way to handle state boundaries.

## 4. How the System Moves

Let's look at the mechanics in motion.

### 4.1 Canonical Committee Data Arrives From the Outside
Suppose some bytes come over the wire, claiming to be a committee. 

If our protocol uses `Set<T>`, the very act of decoding forces a check: are these items sorted and unique? If the sender messed up and sent duplicates, or sent them out of order, the decoder just says "No." It fails immediately. Only if the bytes are perfect does the rest of the code get to use the committee. 

The rule is: *Canonicalization happens at the boundary, not after the fact.*

### 4.2 Completion Is Represented as an Object, Not a Comment
Suppose a task fans out work to three sub-tasks and needs to know when they're all done. 

Instead of juggling shared counters or raw channels, it creates an `Exact` acknowledgement handle, clones it three times, and awaits the waiter. 

The state machine is utterly precise: every clone increases the count, every `acknowledge()` decreases it, and if any clone is dropped unacknowledged, the whole thing cancels. We've taken the vague idea of "everyone should eventually signal completion" and turned it into an object you can hold in your hand and test.

### 4.3 Bounded Concurrency Becomes Declarative
Suppose we can only handle 10 simultaneous operations. 

We use a limiter. A slot is either acquired or it's not. A reservation exists or it doesn't. When the reservation is dropped, the capacity is released. There's no separate `cleanup()` function you have to remember to call. The capacity rule is physically bound to the lifetime of the object in memory. Nature takes its course.

### 4.4 The Historical Bitmap Is the Full Lifecycle
The historical bitmap is one explicit cycle:
`Clean` -> `into_dirty()` -> mutate -> `commit()` or `abort()` -> `Clean`.

What's important is what *doesn't* happen. Uncommitted mutations don't silently leak into history. Aborted mutations don't leave ghosts in the clean view. The transitions are named, narrow, and absolute.

## 5. What Pressure It Is Designed To Absorb

Why did we build this? To absorb specific forces that constantly push against a growing codebase:

- **Duplication Pressure**: The urge to rewrite the same tiny concept locally. This crate gives it one home.
- **Validation Pressure**: The exhaustion of re-checking if a value is valid everywhere it's used. We encode the shape in the type.
- **Shutdown and Overflow Pressure**: Channels and task pools always break down at the edges—when receivers vanish, tasks abort, or queues fill up. Our coordination tools turn these edge cases into explicit choices.
- **Canonicalization Pressure**: When a shape is used across many crates, having one true, stable answer is vastly better than five "almost right" ones.
- **History Pressure**: The problem of keeping the current state fast and the historical state compact, which the historical bitmap solves elegantly.

## 6. Failure Modes and Limits

Now, let's talk about what this crate *isn't*. 

First, its scope is strictly limited. `commonware-utils` is not for domain logic. You won't find consensus algorithms or application workflows here. 

Second, it is intentionally strict. In fact, several tools will gladly panic or fail if you misuse them:
- `Set` decoding rejects bad data.
- `NonEmptyVec::mutate` panics if your closure accidentally empties it.
- `NonZeroDuration::new_panic` refuses a zero duration.
- `Exact` treats an unacknowledged drop as a hard cancellation.

This is not an accident! In this crate, we believe that bad inputs are programmer errors. We prefer a loud, explicit failure over quietly repairing bad data and pretending everything is fine.

Third, these are building blocks, not the whole building. `KeyedLimiter` limits keys, but it doesn't know what the keys *mean*. `HistoricalBitMap` stores history, but it doesn't know *why* a commit is important. The crates around it provide the meaning.

## 7. How to Read the Source

If you want to read the code—and you should!—start with `utils/src/lib.rs` to see the public interface. Then, look at the canonical collections (`ordered.rs`, `vec.rs`), move on to the coordination tools, and finish with the historical bitmap (`bitmap/historical/bitmap.rs`). 

Read it with the "belt of tools" model in your mind. The files aren't just a random assortment of stuff; they are a carefully selected, highly polished kit designed to solve the physical realities of systems programming.

## 8. Glossary and Further Reading

- **canonical collection**: A collection where the rules of order and uniqueness are strictly enforced by the type itself.
- **receiver-owned policy**: The principle that a decoder should reject non-canonical data instead of trying to silently fix it.
- **acknowledgement**: An object (handle + waiter) that physically models task completion or cancellation.
- **reservation**: A claim on limited concurrency that is bound to the lifetime of the object.
- **dirty bitmap**: A projected view of future state that exists only while mutations are occurring, before they are committed or aborted.
- **reverse diff**: A clever way to store history by recording how to undo a commit, rather than copying the entire state.

Further reading:
- `utils/src/ordered.rs`
- `utils/src/acknowledgement.rs`
- `utils/src/futures.rs`
- `utils/src/concurrency.rs`
- `utils/src/bitmap/historical/mod.rs`
