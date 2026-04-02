# Chapter Brief: commonware-math

## 1. Module Purpose

`commonware-math` is the algebra engine room beneath coding, interpolation, and
cryptography. Its job is not to "contain some math." Its job is to make
algebraic promises precise, executable, and cheap enough that higher crates can
depend on them directly.

The chapter should answer one systems question:

> If the rest of Commonware wants algebra it can trust during evaluation,
> interpolation, NTT, and erasure recovery, what has to exist down here?

The answer should read as one continuous argument:

- `algebra.rs` defines the contract ladder.
- the test suites and `math/src/test.rs` enforce that the contracts are real,
  not rhetorical,
- Goldilocks makes the contracts concrete in a field with fast reduction and a
  deep root-of-unity tower,
- `poly.rs` turns those contracts into semantic polynomial objects,
- `ntt.rs` reorganizes the same meaning into matrix, vector, and recovery
  machinery.

The promise of the crate is not abstract elegance. The promise is that other
Commonware crates can evaluate, interpolate, encode, and recover data without
quiet arithmetic drift.

---

## 2. Source Files That Matter Most

### `math/src/algebra.rs`
**Why it matters:** This is the contract deck. It defines the ladder from
`Object` through `FieldNTT`, the borrowed-operator discipline, the generic
`monoid_exp` engine behind both scaling and exponentiation, and the reusable
property-test suites that enforce the laws.

### `math/src/test.rs`
**Why it matters:** This file proves the generic story is real. The tiny field
`F_89` and the tiny subgroup-based crypto group `G` let the crate exercise
`Field`, `Space`, and `CryptoGroup` logic outside the optimized Goldilocks path.

### `math/src/fields/goldilocks.rs`
**Why it matters:** This is where the contracts become metal. It contains the
single-subtraction add/sub reductions, the `reduce_128` derivation for the
modulus `2^64 - 2^32 + 1`, inversion, specialized `div_2`, canonical decoding,
and the roots-of-unity / coset-shift constants that power NTT and division on a
coset.

### `math/src/poly.rs`
**Why it matters:** This is the semantic layer. It explains what the system is
actually moving: polynomials whose identity survives trailing zero padding,
whose evaluation can use Horner or MSM, and whose constant can be recovered
through precomputed interpolation weights.

### `math/src/ntt.rs`
**Why it matters:** This is the fast path and recovery layer. It contains the
in-place butterfly engine, bit-reversed storage helpers, vanishing-polynomial
construction, matrix/polynomial/evaluation vector structures, coset division,
and the real erasure-recovery flow.

---

## 3. Chapter Outline

1. **Why the engine room exists**
   - coding, interpolation, and recovery need shared algebra, not crate-local
     arithmetic conventions
   - correctness and speed have to be designed together

2. **The contract deck**
   - `Object`, `Additive`, `Multiplicative`, `Space`, `Ring`, `Field`,
     `FieldNTT`, `CryptoGroup`
   - borrowed operators as a performance contract
   - `monoid_exp` as the shared double-and-add / square-and-multiply engine

3. **The law-checking engine**
   - `test_suites` as executable algebraic law enforcement
   - what `math/src/test.rs` adds by testing against a tiny field and group

4. **Goldilocks in detail**
   - why `2^64 - 2^32 + 1` is useful
   - `reduce_64` and `reduce_128`
   - roots of unity, `div_2`, canonical decoding, and stream packing

5. **Polynomial semantics**
   - `degree()` versus `degree_exact()`
   - Horner evaluation, MSM evaluation, and linear-combination evaluation
   - interpolation weights, zero-point shortcut, and Montgomery-style batch
     inversion

6. **NTT as a representation change**
   - butterfly derivation from even/odd splitting
   - bit-reversed coefficient storage
   - `Matrix`, `PolynomialVector`, and `EvaluationVector`

7. **Vanishing polynomials and erasure recovery**
   - `VanishingPoints`
   - `EvaluationColumn::vanishing`
   - multiply by a vanishing polynomial, interpolate, divide on a coset, and
     recover rows
   - `lagrange_coefficients` as the lighter interpolation-at-zero path

8. **Pressure absorbed, limits, and reading order**
   - what higher layers no longer need to think about
   - what assumptions the crate refuses to fake

---

## 4. System Concepts To Explain

- **The law engine is part of the design, not an appendix.** The chapter should
  make clear that `test_suites` and `math/src/test.rs` are part of how the
  crate earns trust.
- **The contract ladder is broader than field arithmetic.** `Space`,
  `CryptoGroup`, and `FieldNTT` are where the later layers get their shape.
- **`monoid_exp` is the hidden unifier.** One generic bit-walking engine powers
  both scalar multiplication and field exponentiation.
- **Goldilocks reduction should feel derived, not asserted.** The reader should
  see why `2^64 = 2^32 - 1 mod P` and `2^96 = -1 mod P` make `reduce_128`
  possible.
- **Polynomial identity is semantic.** Equality ignores meaningless trailing
  zero coefficients; `degree_exact()` exists because storage length is not
  semantic degree.
- **Interpolation is precomputation plus a weighted sum.** The chapter should
  explain how the weights depend only on the points, and why batch inversion
  matters.
- **Bit-reversed storage is a structural choice.** It is how the recursive NTT
  split becomes contiguous in memory.
- **Recovery is algebra, not guesswork.** Missing rows are recovered by
  multiplying by a vanishing polynomial and dividing back on a coset.

---

## 5. Interactive Visualizations To Build Later

1. **Contract deck plate**
   - Show the ladder from `Object` to `FieldNTT` and `CryptoGroup`, with one
     systems promise per rung.
2. **Law engine plate**
   - Show trait laws flowing into `test_suites`, then into Goldilocks and the
     tiny `F_89` / `G` proving ground.
3. **Goldilocks reduction plate**
   - Walk `x = c 2^96 + b 2^64 + a` into `(a - c) + b(2^32 - 1)`.
4. **Interpolation plate**
   - Show precomputed weights turning evaluations into the constant term, with
     the zero-point shortcut called out.
5. **NTT layout plate**
   - Show ordinary coefficient order versus reverse-bit order and where each
     butterfly stage acts.
6. **Recovery plate**
   - Show missing rows, the vanishing polynomial, multiplication into `D(X)V(X)`,
     coset division, and recovered rows.

---

## 6. Claims-To-Verify Checklist

- [ ] The chapter presents `commonware-math` as infrastructure beneath coding,
  interpolation, and recovery, not as isolated theory.
- [ ] The law-checking engine in `algebra.rs` and `math/src/test.rs` is
  explained as part of the crate's core design.
- [ ] The algebra ladder includes `Space`, `FieldNTT`, and `CryptoGroup`, not
  just `Additive` / `Field`.
- [ ] The double-and-add / square-and-multiply story is tied to `monoid_exp`.
- [ ] Goldilocks reduction is derived from the modulus shape instead of merely
  summarized.
- [ ] `degree()` versus `degree_exact()` is explained with a concrete trailing-
  zero example.
- [ ] Interpolation explains both the generic weight construction and the
  special handling of an evaluation point at zero.
- [ ] `Matrix`, `PolynomialVector`, and `EvaluationVector` are introduced as
  the real data structures behind NTT and recovery.
- [ ] The reader can finish the chapter understanding why coset division is
  necessary during erasure recovery.
