# commonware-parallel

## One Algorithm, Two Execution Policies

---

## Opening Apparatus

**Promise.** This chapter shows how `commonware-parallel` lets one algorithm
run sequentially or in parallel without changing what the algorithm means.

**Crux.** Parallelism is a scheduling choice, not permission to rewrite the
logic into a second code path with different edge cases.

**Primary invariant.** The strategy may change partitioning, locality, and
thread count, but it must not change the result the algorithm computes.

**Naive failure.** The easy mistake is to write one sequential loop and one
parallel loop and call them "equivalent." The loops quickly drift:

- one path gets a bug fix that the other never receives,
- one path preserves a boundary case the other drops,
- one path accidentally changes meaning when a chunk boundary moves.

**Reading map.**

- `parallel/src/lib.rs` defines the policy boundary.
- `Strategy` is the abstraction the rest of the workspace writes against.
- `Sequential` is the reference semantics.
- `Rayon` shows how the same fold shape becomes partitioned work.
- The property tests at the bottom are the proof that the two policies still
  compute the same result.

**Assumption ledger.**

- The reader is comfortable with folds, reductions, and partitions.
- The chapter is about CPU-bound work, not I/O concurrency.
- `Sequential` is not a fallback here. It is the meaning-preserving baseline.

## Background

Parallel work only helps when the algorithm can be split without changing its
meaning. That sounds obvious, but many "parallel" rewrites quietly break that
rule.

The useful vocabulary is small:

- **Partitioning** splits one input into independent chunks.
- **Local state** is the scratch space owned by one partition.
- **Reduction** merges partial results back into one answer.
- **Associativity** lets the merge happen in different groupings without
  changing the meaning.
- **Determinism** means the answer does not depend on scheduling luck.

The trap is to assume that "same final type" means "same algorithm." It does
not. A parallel rewrite can preserve the type and still lose the meaning.
Common failure modes include:

- pushing order-sensitive work into a `par_iter` and hoping order falls out the
  same way,
- sharing mutable state through locks and then pretending the lock made the
  algorithm equivalent,
- partitioning first and only later discovering that the partition boundary
  split the one place where the algorithm needed context.

That is why this crate treats the sequential path as the reference semantics.
Once the algorithm is written as a fold or reduction, the execution strategy
can change how the work is scheduled without changing what the algorithm says.

## 1. What Problem Does This Solve?

Some algorithms are obviously order-sensitive. Many are not. They look like
simple loops, but they are really reductions with hidden structure:

- parse items,
- accumulate local state,
- merge partial answers,
- and keep the result canonical.

The mistake is to treat the sequential version as the "real" implementation
and the parallel version as a later optimization. That leaves the codebase with
two places where meaning can drift.

`commonware-parallel` prevents that split. The algorithm says what the work
means. The strategy says how the work is scheduled. The whole crate is built
to keep that boundary visible.

## 2. Mental Model

Think of the algorithm as a contract and the strategy as the kitchen.

- `Sequential` is one cook following the recipe from start to finish.
- `Rayon` is several cooks preparing independent chunks and then combining the
  plates.

The recipe does not change when the kitchen changes. That is the point. The
policy changes. The meaning does not.

This is also why the trait is small. `Strategy` does not try to model threads,
work stealing, or queues. It models fold-shaped work:

- give each partition its own local state,
- process items against that state,
- then combine partial results.

If the problem does not fit that shape, forcing it through the abstraction is
usually the wrong move.

## 3. The Core Ideas

### 3.1 `Strategy` Marks the Boundary

`Strategy` is the center of the crate because it separates meaning from
scheduling. The methods are named after common reduction shapes, but they all
respect the same contract: the algorithm may describe local work and merge
work, yet it may not know whether one thread or many are doing it.

That is why the trait is more useful than a thread-pool wrapper. A wrapper
would expose execution machinery. `Strategy` exposes the algebra of the work.

### 3.2 `fold_init` Is the Primitive

`fold_init` is the most important method in the crate.

It gives each partition three things:

- the current accumulator,
- a partition-local init value,
- and the next item.

That local init value is the honest place for scratch state:

- a reusable buffer,
- a temporary encoder,
- a small cache,
- or any mutable state that should not be shared across partitions.

This is the key move in the crate. The algorithm can say, "I need mutable
state," without saying anything about mutexes or shared ownership.

### 3.3 Associativity Is the Real Requirement

Parallelism is safe only when the reduction is lawful. In practice, that means
the merge operator must be associative in the way the algorithm uses it.

Simple sums are easy:

```text
(a + b) + c == a + (b + c)
```

But many real algorithms are not plain sums. They have boundary effects.
That is where `fold_init` matters. It lets each partition produce a canonical
local summary, and then the reduction only has to merge summaries, not raw
items.

If the reduction is not associative, partitioning changes the meaning. A tree
of partial results is not the same as one left-to-right pass. That is not a
performance detail. It is a semantic change.

### 3.4 A Worked Algorithm: Coalescing Ranges

Suppose the input is a stream of possibly overlapping ranges, and the goal is
to produce one canonical list of disjoint ranges.

The sequential version is straightforward:

1. keep a current range,
2. merge the next range if it overlaps the current one,
3. otherwise emit the current range and start a new one,
4. repeat until the input ends.

That algorithm is reduction-shaped, but it is also boundary-sensitive. A range
can start in one chunk and finish in the next.

If you parallelize it badly, you get the classic drift:

- one partition emits `[1, 4]`,
- the next partition emits `[3, 5]`,
- and a naive concatenation returns both, even though the canonical answer is
  `[1, 5]`.

The fix is not "make it parallel anyway." The fix is to change the partition
summary so it is safe to merge.

One useful summary looks like this:

- `ranges`: the canonical disjoint ranges inside one partition,
- `head`: the first range, if any,
- `tail`: the last range, if any.

Each partition does local merging first. The reduction then only needs to look
at the boundary between the left tail and the right head. If those two ranges
overlap, it merges them and re-canonicalizes the seam. Everything inside each
partition is already normalized.

That reduction is associative because each intermediate result is itself a
canonical summary. The merge step only needs to repair the edge between two
summaries, and repairing that edge does not depend on whether the tree groups
the partitions as `((a b) c)` or `(a (b c))`.

That is the deeper lesson of the crate:

- if you only concatenate partition outputs, you lose meaning,
- if you reduce raw items without canonical summaries, you lose context,
- if you summarize each partition canonically, you can preserve meaning while
  changing execution policy.

### 3.5 `Sequential` Is the Reference Semantics

`Sequential` is deliberately boring.

It creates one init value, walks the iterator in order, folds every item on the
current thread, and ignores the reduce closure because there is only one
partition.

That simplicity is the point. `Sequential` is the clearest statement of what
the algorithm means before any scheduling policy is applied.

### 3.6 `Rayon` Makes Partitioning Explicit

The Rayon implementation does not just "use threads." It controls how work is
split.

It first collects the input into a `Vec`. That is a deliberate tradeoff:

- contiguous partitions preserve local order,
- each partition can accumulate privately,
- and the reduction sees one summary per partition instead of one summary per
  item.

That shape matters. A streaming bridge that hands one item at a time to worker
threads would produce much noisier reduction behavior. It would also make
boundary-sensitive work much harder to reason about.

So the `Vec` allocation is not accidental. It is the cost of buying a cleaner
partition structure.

### 3.7 `join` and `parallelism_hint` Expose the Same Boundary at Two Scales

`join` handles the small case: two independent closures.

- `Sequential` runs `a()` and then `b()`.
- `Rayon` can run them in parallel with the thread pool.

`parallelism_hint` handles the larger case: how wide the strategy can
plausibly run. It is only a hint, but it is still useful upstream when a caller
needs to choose chunk sizes or decide whether splitting is worth it.

## 4. How the System Moves

### 4.1 The Caller Writes Once Against `Strategy`

The caller writes against `&impl Strategy` and is forced to make the reduction
shape explicit:

- an identity element,
- a fold step,
- and a reduction step.

That is the real win. The algorithm is described in terms of meaning, not in
terms of threads.

### 4.2 The Sequential Path

The sequential path is the reference fold:

1. create the init state,
2. create the identity accumulator,
3. walk the iterator in order,
4. apply the fold closure for every item,
5. return the final accumulator.

There are no partial reductions because there is only one partition.

### 4.3 The Rayon Path

The Rayon path turns one fold into local folds plus one final reduction:

1. collect the items into a `Vec`,
2. turn the vector into a parallel iterator,
3. give each worker its own `(init_state, accumulator)` pair,
4. fold locally inside each partition,
5. reduce the partition outputs into the final result.

That means the true shape of the algorithm is:

```text
global input
  -> contiguous partitions
  -> one local fold per partition
  -> one final reduction across partition outputs
```

The property tests at the bottom of `parallel/src/lib.rs` are the contract.
They check that parallel `fold_init` matches sequential `fold_init`, that
`fold` matches `fold_init` when the init state is trivial, and that the helper
methods preserve the same meaning.

## 5. What Pressure It Is Designed To Absorb

### 5.1 CPU-Bound Work

If the task is large enough to benefit from multiple cores, `Rayon` gives the
caller that option without making the algorithm itself aware of threads.

### 5.2 Determinism

`Sequential` keeps the execution order fixed. That matters for tests, for
debugging, and for environments where threads are unavailable.

### 5.3 Private Per-Partition State

Many algorithms need mutable scratch space, but only within one partition of
the work. `fold_init` exists so that state can stay local instead of becoming a
shared bottleneck.

### 5.4 Reuse Across Execution Environments

Because `Sequential` works without `std`, the same algorithm can often be
reused in both threaded and non-threaded builds. The policy changes. The code
stays the same.

## 6. Failure Modes and Limits

### 6.1 Order-Sensitive Effects Do Not Magically Parallelize

If an algorithm depends on a strict left-to-right side effect, parallelism may
change its meaning. That is not a bug in the crate. It is a sign that the
algorithm needs a different shape.

### 6.2 Trait Bounds Are Part of the Contract

Items, closures, and results need to satisfy `Send`, and some pieces need
`Sync`, because the strategy may move work across threads. If a caller cannot
meet those bounds, that is useful feedback: the algorithm is not shaped for
this style of execution.

### 6.3 Parallelism Has Overhead

For small inputs, `Sequential` is often better.

The Rayon path allocates, partitions, schedules, and reduces. That overhead is
worth paying only when the local fold work is large enough to amortize it.

### 6.4 The Abstraction Preserves Results, Not Performance Guarantees

`parallelism_hint` is only a hint. The crate promises that the same algorithm
can run under different policies. It does not promise that the parallel policy
always wins.

## 7. How to Read the Source

Start with `parallel/src/lib.rs` and read `Strategy` first so the policy
boundary is clear before either implementation. Then read `Sequential` as the
reference meaning, `Rayon` as the same meaning under partitioning, and the
tests as the proof that the two policies still compute the same result.

## 8. Glossary and Further Reading

- **execution policy**: the rule that decides how work is scheduled.
- **fold**: an operation that accumulates a collection into one result.
- **partition-local state**: mutable scratch state owned by one worker.
- **reduce**: the operation that combines partial results into one final
  answer.
- **contiguous partitioning**: splitting collected items into stable chunks
  instead of streaming them one by one to workers.

Further reading:

- `parallel/src/lib.rs`
- `parallel/README.md`
- `commonware-runtime` for other places where execution policy matters
