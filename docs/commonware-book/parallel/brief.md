# Chapter Brief: commonware-parallel

## 1. Module Purpose

`commonware-parallel` should be taught as a chapter about **preserving one
algorithm while changing only its execution policy**.

The chapter should begin from the real failure mode: duplicated sequential and
parallel implementations do not stay equivalent for long. The better design is
to make the algorithm speak only in fold/reduce terms and let a `Strategy`
decide how that work is scheduled.

The chapter's most important claim is:

> parallelism is a scheduling policy layered on top of one algorithmic shape,
> not permission to fork the algorithm into a second implementation history.

That framing makes the crate about correctness first and performance second.

---

## 2. Source Files That Matter Most

### `parallel/src/lib.rs`
**Why it matters:** This file carries almost the whole argument. It defines the
policy boundary, the sequential reference semantics, the Rayon implementation,
and the equivalence tests.

### `parallel/src/lib.rs` test module
**Why it matters:** The property tests are the executable form of the crate's
main theorem: the helper methods are really fold shapes, and the parallel
policy should preserve the same meaning as the sequential one.

### `parallel/README.md`
**Why it matters:** Useful only as the shortest external summary. The real
substance lives in the source file.

---

## 3. Expanded Chapter Outline

```text
0. Opening apparatus
   - promise, crux, invariant, naive failure, reading map, assumptions

1. What problem does this solve?
   - why duplicated sequential/parallel code drifts
   - one algorithm, two execution policies

2. Mental model
   - recipe versus kitchen
   - same work, different scheduling

3. Core ideas
   - `Strategy` as the boundary
   - `fold_init` as the key primitive for partition-local state
   - `map_*` helpers as named folds
   - `Sequential` as reference semantics
   - `Rayon` as contiguous partitioning plus final reduction
   - `join` and `parallelism_hint` as policy at two scales

4. How the system moves
   - caller writes once against `Strategy`
   - sequential direct fold path
   - rayon partition -> local fold -> reduce path
   - tests as the real contract

5. Pressure and tradeoffs
   - CPU-bound work
   - determinism
   - private scratch state
   - reuse across `no_std` and `std`
   - small splits versus large reductions

6. Failure modes and limits
   - order-sensitive effects
   - trait-bound constraints
   - parallel overhead
   - no promise of speedup

7. How to read the source / glossary
```

---

## 4. System Concepts To Explain At Graduate Depth

1. **The algorithm and the execution policy are different kinds of thing.**
   The caller names the fold shape; the strategy names the schedule.

2. **`fold_init` is the real primitive.** It is what lets the algorithm keep
   partition-local mutable state without shared locking.

3. **Contiguous partitioning is an algorithmic execution choice.** Rayon
   collects into a `Vec` so each worker can produce one local result rather
   than one result per item.

4. **`Sequential` is the reference semantics.** It is not a fallback path but
   the cleanest statement of the algorithm's meaning.

5. **The property tests carry the theorem.** They are the evidence that the
   convenience helpers are really fold shapes and that the two strategies
   agree on meaning.

6. **Parallelism can lose.** The chapter should say explicitly that the policy
   boundary preserves meaning, not throughput guarantees.

---

## 5. Visualizations To Build Later

1. **Policy switch plate**  
   Show one fold-shaped algorithm body running under `Sequential` and `Rayon`.

2. **Partition-and-reduce plate**  
   Show one input being collected, chunked into partitions, folded locally, and
   reduced globally.

3. **Scratch-state plate**  
   Show `fold_init` giving each worker its own local mutable state.

4. **Equivalence plate**  
   Show the tests as a contract: same result, different schedule.

---

## 6. Claims-To-Verify Checklist

- [ ] The chapter presents `Strategy` as the meaning/scheduling boundary.
- [ ] `fold_init` is explained as the key primitive for worker-local state.
- [ ] `map_collect_vec`, `map_init_collect_vec`, and
      `map_partition_collect_vec` are taught as named fold shapes.
- [ ] `Sequential` is treated as the reference semantics rather than a fallback.
- [ ] The Rayon discussion explains why it collects into a `Vec` before
      partitioning.
- [ ] The chapter references the property tests as the main equivalence
      evidence.
- [ ] The chapter says plainly that parallelism can lose on small inputs.
