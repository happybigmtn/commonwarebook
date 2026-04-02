# commonware-math

*The executable algebra engine room beneath coding, interpolation, and recovery.*

---

## 1. Why This Crate Exists

Start with the systems pressure, not the notation.

Commonware has crates that encode data into parity rows, commit to structured
objects, interpolate secrets from shares, and recover missing evaluations after
erasures. None of those crates can afford their own private arithmetic folklore.
If one crate treats trailing zero coefficients as meaningful, another decodes
field elements non-canonically, and a third "optimizes" a transform with the
wrong root ordering, the bug will not announce itself as a bug. It will look
like a different result.

That is why `commonware-math` exists. It gives the rest of the system one place
to ask:

> What algebraic promises are real, which concrete field satisfies them, and
> how do we reorganize the same polynomial meaning into a form that coding and
> recovery can execute quickly?

This crate answers that question in layers.

1. [`algebra.rs`](../../../math/src/algebra.rs) states the contracts.
2. [`test_suites` in `algebra.rs`](../../../math/src/algebra.rs) and
   [`math/src/test.rs`](../../../math/src/test.rs) turn those contracts into
   executable law checks.
3. [`fields/goldilocks.rs`](../../../math/src/fields/goldilocks.rs) makes the
   contracts concrete in a field with a useful modulus shape.
4. [`poly.rs`](../../../math/src/poly.rs) gives the contracts an object whose
   meaning must survive multiple execution strategies.
5. [`ntt.rs`](../../../math/src/ntt.rs) changes the route, not the meaning, so
   evaluation and recovery become fast enough to use in real protocol code.

Read the chapter as one argument. The lower layers exist so the upper ones can
trust algebra as infrastructure instead of re-deriving it in every crate.

---

## Backgrounder: Algebra as an Execution Environment

Most people meet algebra as symbol pushing on a whiteboard. In systems code, it
shows up as an execution environment with rules. A value is not just "some
numbers." It lives in a structure that decides what addition means, whether
division is always possible, and how much representation freedom is allowed.

That distinction matters because naive integer arithmetic is not stable enough
for protocol logic. Integers overflow. Fractions do not always stay inside the
same set. Floating point introduces rounding. Different machines can preserve
the same abstract idea only if they share the same algebraic rules.

The central structures are familiar:

- a **ring** supports addition and multiplication,
- a **field** adds multiplicative inverses for nonzero elements,
- a **vector space** or module lets scalars weight structured objects,
- and a **polynomial** packages many related values into one object that can be
  evaluated, shifted, or reconstructed from samples.

Those structures are not abstract decoration. They are what make interpolation
and fast recovery possible. If you know enough points of a polynomial, you can
reconstruct the whole thing. If you can move the same polynomial into a more
convenient basis, you can evaluate or multiply it much faster. That is the
reason finite fields and roots of unity matter here.

The classical alternatives are slower or less robust:

- work directly with large integers and accept overflow bugs,
- use rationals and pay for expensive normalization,
- or use floating point and accept rounding noise where exact equality matters.

`commonware-math` chooses exact algebra instead. The tradeoff is that the code
has to respect the laws very carefully, but the payoff is that higher-level
protocols can treat algebra as a dependable substrate rather than a source of
surprises.

---

## 2. The Contract Deck and the Law-Checking Engine

The most important design choice in `commonware-math` is that it begins with
traits, not with a favorite field or polynomial type. The crate first asks what
other crates may rely on without knowing the concrete implementation.

That question produces a ladder in
[`math/src/algebra.rs`](../../../math/src/algebra.rs).

- `Object` says a value can be cloned, compared, and debug-printed.
- `Additive` says it behaves like a commutative group under `+`, `-`, and `-x`.
- `Multiplicative` says it supports `*` and `square`.
- `Space<R>` says an additive object can be scaled by `R`.
- `Ring` adds `one()` and exponentiation.
- `Field` adds inversion.
- `FieldNTT` adds roots of unity, coset shifts, and `div_2`.
- `CryptoGroup` says a group is also a `Space` over its scalar field.
- `HashToGroup` and `Random` add sampling capabilities used by higher layers.

The crate is not merely naming textbook structures. Each rung corresponds to a
systems promise.

- If something is `Additive`, callers may form cancellations and linear sums.
- If something is `Space<R>`, callers may do weighted combinations, MSMs, and
  commitment-style aggregation.
- If something is `FieldNTT`, callers may move into a root-of-unity domain and
  expect the inverse transform to exist.

That is the first engine-room lesson: the laws are the interface.

### Borrowed operators are part of the interface

The operator signatures are not cosmetic. `algebra.rs` consistently prefers
borrowed right-hand sides such as `T + &T`, `&mut T += &T`, `T * &R`, and
`&mut T *= &R`.

That choice protects the rest of the crate from accidental cloning when the
"number" is not a single machine word. A polynomial, vector, or group element
can be large enough that ownership churn becomes part of the algorithmic cost.
The traits therefore encode not just which operations exist, but how to use
them cheaply.

### One generic engine powers scale and exponentiation

There is a deeper unification near the top of `algebra.rs`: `monoid_exp`.

It takes:

- an identity element,
- an associative binary operation,
- a "self operation" that doubles or squares,
- a base element,
- and exponent limbs in little-endian `u64` form.

The algorithm scans the exponent bits from low to high. If the current bit is
set, it folds the current working value into the accumulator. Then it applies
the self-operation to the working value.

For `Additive::scale`, the operation is addition and the self-operation is
doubling. For `Ring::exp`, the operation is multiplication and the self-
operation is squaring. One generic routine therefore implements both
double-and-add and square-and-multiply.

Take exponent `13 = 1101₂`.

- In additive mode, the accumulator collects `x`, then `4x`, then `8x`, for a
  final result of `13x`.
- In multiplicative mode, the accumulator collects `x`, then `x^4`, then
  `x^8`, for a final result of `x^13`.

That is a compact example of the crate's style. Instead of shipping separate
ad hoc loops for every algebraic flavor, it identifies the common contract and
lets one implementation serve several layers.

### `Space<R>` is the bridge most readers should linger on

`Space<R>` is where the contract ladder starts doing concrete systems work.

Mathematically, it is a right module action. Operationally, it says:

> I can take additive objects, weight each by a scalar, and sum the results in
> a structured way.

That is why `Space<R>` carries `msm`, the multi-scalar multiplication hook.
The default implementation is naive. It simply computes

`sum_i points[i] * scalars[i]`.

But the trait makes a stronger promise: callers may ask for that shape without
knowing whether the implementation uses the naive loop or something faster.
This becomes important in `poly.rs`, where polynomial evaluation can switch
between Horner accumulation and MSM without changing the semantic request.

### The laws are executed, not merely written down

The important part of the crate is that `algebra.rs` does not stop at trait
definitions. Under `#[cfg(any(test, feature = "arbitrary"))]`, it ships a real
law-checking engine in `test_suites`.

Those tests do not "unit test a concrete type once." They express laws that any
implementer must survive:

- `check_add_assign` verifies `+=` agrees with `+`.
- `check_add_commutes` and `check_add_associates` verify additive structure.
- `check_sub_vs_add_neg` verifies subtraction is really addition with negation.
- `check_mul_assign`, `check_mul_commutes`, and `check_mul_associative` do the
  same for multiplication.
- higher suites compose these into `fuzz_field`, `fuzz_space`, and
  `fuzz_field_ntt`.

This matters because algebraic breakage often appears in optimized code first.
A field implementation can compile and still violate a law at a carry boundary.
A transform-specific helper can work on normal inputs and still return the
wrong root of unity order. The test suites force implementations to satisfy the
contract deck across generated inputs.

### `math/src/test.rs` is the proving ground for generic code

The law engine gets an important companion in
[`math/src/test.rs`](../../../math/src/test.rs). It defines a tiny field
`F_89` and a tiny prime-order group `G`, realized as a subgroup of the units of
`F_179`.

Why does that matter when Goldilocks already exists?

Because generic algebra code should not only work for the one optimized field
the crate uses in production. The tiny field and group let the crate test
`Field`, `Space`, `CryptoGroup`, codec behavior, and interpolation logic in a
small setting where the arithmetic is easy to reason about. If a supposedly
generic routine only works because Goldilocks has a lucky modulus shape, these
toy types are where the illusion breaks.

That is the second engine-room lesson: `commonware-math` does not trust laws
because the author wrote them in a doc comment. It runs them.

---

## 3. Goldilocks: When the Contracts Become Metal

Abstract laws are necessary, but no higher-level crate can encode or recover a
row with trait bounds alone. Eventually the chapter has to land on a concrete
field, and in Commonware that field is Goldilocks in
[`math/src/fields/goldilocks.rs`](../../../math/src/fields/goldilocks.rs).

Its modulus is:

`P = 2^64 - 2^32 + 1`

This constant is not special because it sounds elegant. It is special because
its binary shape makes reduction fast and because its multiplicative group has
enough two-adic structure for the NTT layer.

### The easy reductions come first

`add_inner` and `sub_inner` show the basic discipline.

For addition, each input is already less than `P`, so the integer sum is at
most `2P - 2`. That means one conditional subtraction of `P` is enough. The
implementation handles both the no-overflow and overflow cases carefully, but
the algebraic point is simple: the modulus is close enough to `2^64` that a
single correction step suffices.

For subtraction, if the raw `u64` subtraction underflows, adding `P` once
restores the canonical representative. Again, one correction is enough.

`reduce_64` follows the same pattern. Because `2P > 2^64 - 1`, a raw `u64`
input also needs at most one subtraction.

### The real trick is `reduce_128`

The essential reduction trick sits in `reduce_128`, where the modulus shape
pays for itself.

Suppose we multiply two field elements as `u64`s. The product lives in `u128`,
so we must reduce a 128-bit integer modulo `P`.

Write the 128-bit value as

`x = c * 2^96 + b * 2^64 + a`

where:

- `a` is the low 64 bits,
- `b` is the next 32 bits,
- `c` is the high 32 bits.

Now use the modulus relation

`P = 2^64 - 2^32 + 1`

which implies

`2^64 = 2^32 - 1 (mod P)`.

Multiply both sides by `2^32` and you get

`2^96 = 2^32 * (2^32 - 1) = 2^64 - 2^32 = -1 (mod P)`.

Substitute those identities into `x`:

`x = a + b * 2^64 + c * 2^96`

`  = a + b * (2^32 - 1) - c  (mod P)`

`  = (a - c) + b * (2^32 - 1)  (mod P)`.

That is exactly the structure `reduce_128` uses. It extracts `a`, `b`, and `c`
from the `u128`, computes `(a - c)`, computes `b * (2^32 - 1)` as
`(b << 32) - b`, and then combines the two pieces with the already-tested field
addition and subtraction helpers.

The point is not that the code is clever. The point is that the chosen modulus
lets the code collapse a general 128-bit reduction into a handful of word-sized
operations and one field addition path the crate already knows how to trust.

### Inversion and halving both exploit field structure

Goldilocks inversion is implemented as exponentiation by `P - 2`:

`x^-1 = x^(P-2)` for nonzero `x`.

That is a standard field fact, but in this crate it also shows why the generic
`Ring::exp` machinery mattered. The same little-endian square-and-multiply
engine used for generic exponentiation becomes the inverse implementation of
the concrete field.

`div_2` is even more telling. The default `FieldNTT::div_2` could compute

`x * (1 + 1)^-1`,

but Goldilocks overrides it because halving appears inside inverse butterflies.
If the stored `u64` is even, the implementation just shifts right. If it is
odd, it adds `P` first and then shifts, because `x + P` is even while
representing the same field element modulo `P`.

That branch is small, but it is exactly the sort of field-specific detail the
engine room should absorb for everyone else.

### Goldilocks is also an NTT field, not just a prime field

The type `F` implements `FieldNTT`, which means it has more to provide than
ordinary inversion.

- `ROOT_OF_UNITY` is an element of order `2^32`.
- `root_of_unity(lg)` squares downward from that element until it reaches order
  `2^lg`.
- `NOT_ROOT_OF_UNITY` and `NOT_ROOT_OF_UNITY_INV` provide the coset shift used
  later during division in recovery code.

This modulus choice is what makes the later transform section possible. It
makes multiplication cheap and gives the crate a large power-of-two
root-of-unity tower. Without that, the later NTT and erasure machinery would
have nowhere to stand.

---

## 4. Polynomials: Semantic Objects, Not Coefficient Buckets

The next move in the chapter is
[`math/src/poly.rs`](../../../math/src/poly.rs). It turns the contract deck
into an object whose meaning has to survive several representations.

The crate is not manipulating coefficient vectors because vectors are nice. It
is manipulating polynomials whose semantic identity must survive storage shape,
evaluation strategy, and recovery path.

### `degree()` and `degree_exact()` are different on purpose

`Poly<K>` stores a non-empty coefficient list. That storage choice lets the
crate represent the zero polynomial as `[0]` and preserve explicit padding when
some caller wants it.

But that means raw length is not the same thing as semantic degree.

Take coefficients

`[3, 5, 0, 0]`.

Storage length says the polynomial has four coefficients, so `degree()` returns
`3`. Semantically, the polynomial is just

`3 + 5X`,

so `degree_exact()` should return `1`.

The crate therefore offers both answers:

- `degree()` is the cheap upper bound that does not inspect coefficients.
- `degree_exact()` walks backward and trims trailing zeros semantically.

The same semantic stance appears in `PartialEq`. Two polynomials compare equal
even if one of them has extra high zero coefficients. Without that behavior,
ordinary subtraction would create false distinctions between

`a_0 + a_1 X`

and

`a_0 + a_1 X + 0X^2 + 0X^3`.

### Evaluation has two routes because `Space<R>` made both legal

`Poly<K>::eval` uses Horner's method. Starting from the highest coefficient, it
repeatedly multiplies by `r` and adds the next coefficient. That is the direct,
low-allocation path.

`Poly<K>::eval_msm` computes the same value differently. It builds the powers

`1, r, r^2, ...`

and then asks `K::msm` to form the weighted sum of coefficients.

These are not two different semantics. They are two execution shapes for the
same request. The reason both exist without duplicating algebraic logic is that
the contract deck already established what it means for coefficients to live in
a `Space<R>`.

The same idea extends to `lin_comb_eval`, which fuses several weighted
evaluations into one combined MSM-style pass. Again, the chapter should treat
that as one algebraic act expressed in several mechanical forms.

### Interpolation is the inverse story, and the crate does real work up front

The most important under-covered part of `poly.rs` is the `Interpolator`.

Its purpose is narrow and practical: recover the constant term of a polynomial
from evaluations at known points. That is the secret-sharing use-case. Shares
are values of a polynomial. The secret sits in the constant coefficient. Enough
shares should reconstruct that constant without recomputing every weight from
scratch each time.

For points `w_0, ..., w_{n-1}`, the constant can be written as

`p(0) = sum_i y_i * L_i(0)`

where each `L_i` is the Lagrange basis polynomial for point `w_i`.

`Interpolator::new` precomputes exactly those weights.

The naive way would compute every denominator

`prod_{j != i} (w_i - w_j)`

and invert them one by one. The implementation does something better.

1. It computes
   `c_i = w_i * prod_{j != i} (w_j - w_i)`.
2. It computes the total product
   `W = prod_i w_i`.
3. It uses Montgomery's trick: invert the product of all `c_i` once, then use
   prefix products to recover all `1 / c_i`.
4. From those pieces it materializes the interpolation weights.

That turns many inversions into one inversion plus multiplications.

There is also an important edge case: if one evaluation point is `0`, then the
constant term is simply the value at that point. The implementation detects
that and returns a one-hot weight vector instead of going through the general
formula. That is a good example of the crate choosing the semantically obvious
answer once it recognizes the structure.

### Roots-of-unity interpolation has a separate fast path

`Interpolator::roots_of_unity` exists because the transform layer can do better
than the generic O(n²) point-based construction when evaluation points come
from an NTT domain.

That constructor delegates to
[`lagrange_coefficients` in `ntt.rs`](../../../math/src/ntt.rs), which computes
the coefficients for interpolation at `0` from a subset of domain points. The
key identity is:

`L_j(0) = P_Sbar(w^j) / (N * P_Sbar(0))`

where:

- `S` is the set of present indices,
- `Sbar` is the missing complement,
- `P_Sbar` is the vanishing polynomial over the missing points,
- `N` is the domain size.

This is exactly the kind of bridge the crate wants: polynomial semantics on one
side, transform-domain structure on the other.

### Commitments fit because polynomials are generic over coefficient type

One more quiet point matters. `Poly<G>::commit` maps a scalar polynomial into a
group polynomial by multiplying each scalar coefficient by `G::generator()`.
That works because the crate did not hard-code "coefficients are field
elements." The polynomial layer is generic over any additive type that behaves
correctly under the relevant scalar action.

So the third engine-room lesson is this: `poly.rs` is where the algebra layer
stops being a set of traits and becomes a semantic object other crates can
evaluate, interpolate, and commit to without changing what that object means.

---

## 5. NTT Changes the Route, Not the Meaning

The chapter can now enter
[`math/src/ntt.rs`](../../../math/src/ntt.rs), where the crate turns the same
polynomials into a form suitable for fast evaluation, vanishing-polynomial
construction, and erasure recovery.

Read this file as a layout decision, not just a fast algorithm:

> once the crate knows what a polynomial means, how does it lay out memory and
> choose a domain so that the same polynomial work factors into structured
> butterflies instead of naive quadratic arithmetic?

### The butterfly comes from splitting even and odd coefficients

For a polynomial `f(X)`, write

`f(X) = f_+(X^2) + X f_-(X^2)`

where `f_+` collects even coefficients and `f_-` collects odd ones.

If `w` is a `2^m` root of unity, then `w^2` is a `2^(m-1)` root of unity.
That means:

- evaluate `f_+` on powers of `w^2`,
- evaluate `f_-` on powers of `w^2`,
- combine them as
  `f_+(w^{2i}) + w^i f_-(w^{2i})`
  and
  `f_+(w^{2i}) - w^i f_-(w^{2i})`.

The in-place `ntt` routine turns that recursive idea into iterative stages. For
forward transforms it applies the standard butterfly:

- `(a, b) -> (a + w^j b, a - w^j b)`.

For inverse transforms it carefully undoes the same step:

- add and subtract the pair,
- multiply the second branch by the inverse twiddle,
- divide both results by `2` using `div_2`.

That is why `FieldNTT` had to promise more than ordinary field behavior.

### Bit reversal is pushed into storage, not left as an afterthought

`reverse_bits` and `reverse_slice` are not incidental. They show how the crate
makes recursive structure contiguous in memory.

This shows up most clearly in `PolynomialVector`.

Each column stores one polynomial, but the coefficient rows are kept in
reverse-bit order. For a four-term polynomial

`a_0 + a_1 X + a_2 X^2 + a_3 X^3`,

the stored rows are

`a_0, a_2, a_1, a_3`.

Why do that? Because then the even and odd halves become contiguous blocks.
That makes each butterfly stage line up with memory layout instead of requiring
constant reshuffling.

This is a real implementation decision. The crate spends representation
complexity so the transform stages can stay simple and fast.

### `Matrix`, `PolynomialVector`, and `EvaluationVector` are the real data plane

Do not jump from "there is an NTT" straight to "recovery uses it." `ntt.rs`
defines a concrete data plane.

`Matrix<F>`
- stores row-major data,
- provides codec support,
- can be multiplied naively when the code needs a reference implementation,
- and can reinterpret columns as polynomial vectors.

`PolynomialVector<F>`
- treats each column as one polynomial,
- pads row count to the next power of two,
- stores coefficients in reverse-bit order,
- and runs NTTs column-wise across the matrix.

`EvaluationVector<F>`
- stores evaluations of all those polynomials over the same domain,
- remembers which rows are actually present via `VanishingPoints`,
- and provides the `recover` path for missing rows.

This matters because the transform layer is not only about a single polynomial.
Coding and recovery operate on row and column families. The matrix/vector
structures make that batch shape explicit.

### `VanishingPoints` is bookkeeping with algebraic consequences

`VanishingPoints` tracks which roots in the domain should count as present.
Internally it uses a bitmap, but the important fact is that its indexing also
respects reverse-bit order.

That lets the code build vanishing polynomials recursively over domain chunks.
If a whole chunk vanishes everywhere, the implementation can treat it as a
special case. If a chunk vanishes nowhere, it can skip work. Only the mixed
case needs the full polynomial machinery.

This is one of the best examples in the crate of concept-first optimization.
The code is fast because it noticed algebraic structure in the input pattern,
not because it wrote a shorter loop.

---

## 6. Vanishing Polynomials and Real Erasure Recovery

This is the part the original chapter most needed to deepen.

The transform layer is not only there to evaluate dense polynomials quickly. It
also supports missing-row recovery, and that machinery is real, not decorative.

### `EvaluationColumn::vanishing` builds the polynomial the recovery path needs

Given a set of present or missing rows, the crate often needs a polynomial `V`
such that:

- `V(w^j) = 0` at the rows that should vanish,
- `V(w^j) != 0` at the rows that are present.

`EvaluationColumn::vanishing` constructs exactly that object, and it does more
than a naive product of `(X - w^j)` factors.

The routine:

1. splits the domain into chunks,
2. directly expands low-degree factors inside each chunk,
3. marks each chunk as vanishing nowhere, somewhere, or everywhere,
4. merges chunk polynomials upward,
5. and uses NTT-based multiplication in the cases where ordinary special-case
   logic is no longer enough.

That "somewhere/everywhere/nowhere" trichotomy is not an implementation quirk.
It is how the code keeps the common cases from paying for a full polynomial
multiplication every time.

### Recovery works by multiplying by a vanishing polynomial, then dividing back

Now take an `EvaluationVector` with some rows missing.

If every row is present, `interpolate()` is enough. If some rows are missing,
the recovery path uses a sharper idea.

Let `D(X)` be the original data polynomial for one column. Let `V(X)` vanish at
the missing rows.

At every present point `w^i`, we know `D(w^i)`. If we multiply those known
evaluations by `V(w^i)`, we obtain the evaluations of `D(X) V(X)` on all the
present rows. At missing rows, the value is also zero because `V` vanishes
there.

That means the partially filled evaluation table can be turned into a complete
evaluation table for `D(X) V(X)`. Once that is true, the crate can interpolate
to recover the coefficients of `D(X) V(X)`.

Then it only needs to divide by `V(X)` to recover `D(X)`.

That is exactly what `EvaluationVector::recover` does:

1. build the vanishing polynomial for the active-row pattern,
2. multiply each present evaluation row by the vanishing evaluation,
3. interpolate to obtain `D(X) V(X)`,
4. divide by the vanishing polynomial,
5. return the recovered polynomial vector.

### The division step uses a coset because direct division would hit zeros

The cleverest recovery detail lives in `PolynomialVector::divide`.

A direct divide in the ordinary root-of-unity domain would fail, because the
vanishing polynomial is zero exactly where the missing rows lie. Pointwise
division by zero is not a recoverable "maybe."

So the crate leaves the original domain. It multiplies the roots by
`coset_shift()`, an element guaranteed not to be a power of the domain root of
unity. In practice:

1. it divides the roots of both numerator and denominator by the coset factor,
2. evaluates both on that shifted domain,
3. performs pointwise division there,
4. inverse-transforms back to coefficients,
5. and then shifts the roots back with `coset_shift_inv()`.

This is where `FieldNTT::coset_shift()` stops looking abstract and starts
looking necessary. The trait existed because recovery really does need a safe
domain where the denominator stays away from zero.

### A small recovery picture

Suppose we encode four data rows with two parity rows, then pad to an
eight-point domain for the transform. If rows `1` and `4` disappear, the crate
builds a vanishing polynomial whose roots are `w^1` and `w^4` up to a harmless
scale factor.

Then it:

- multiplies each surviving row by that vanishing evaluation,
- interpolates the result into `D(X) V(X)`,
- moves into the coset domain `z w^i`,
- divides by `V(z w^i)`,
- and returns the coefficients of `D(X)`.

The missing rows are not guessed. They are forced by algebra.

### `lagrange_coefficients` exposes the same recovery idea in a lighter form

`lagrange_coefficients` gives another view of the same machinery. When the
caller only wants interpolation at `0`, it is cheaper to compute the relevant
Lagrange weights directly than to recover the full polynomial first.

The implementation builds the vanishing polynomial over the missing complement
and uses:

`L_j(0) = P_Sbar(w^j) / (N * P_Sbar(0))`.

That formula is the recovery story in miniature. Missing-point structure is not
an obstacle to interpolation. It is part of the computation.

So the fourth engine-room lesson is this: `ntt.rs` is not merely a fast
evaluator. It is the place where polynomial semantics, domain structure, and
erasure recovery become one operational system.

---

## 7. What Pressure This Design Absorbs

With the full machine in view, we can say more precisely what
`commonware-math` absorbs for the rest of Commonware.

It absorbs correctness pressure.

The contract deck, the property suites, canonical field decoding, and the toy
test field and group keep algebra from fragmenting into crate-local conventions.

It absorbs performance pressure.

Borrowed operators, the Goldilocks reduction strategy, bit-reversed storage,
batched interpolation weights, chunk-aware vanishing construction, and the NTT
all exist because higher layers need arithmetic they can actually afford to use.

It absorbs semantic pressure.

Higher crates should not care whether a polynomial is represented by raw
coefficients, by evaluations on a root-of-unity domain, or by a partially
present evaluation vector waiting for recovery. They should be able to ask for
evaluation, interpolation, commitment, or recovery and trust the engine room to
preserve the same polynomial meaning all the way through.

That is what makes this crate infrastructural instead of ornamental.

---

## 8. Limits and Reading Order

The fast path works only because the prerequisites are real.

Not every field can implement `FieldNTT`. Not every domain supports power-of-
two roots of unity. Not every polynomial representation can be divided safely
without a coset shift. The crate is powerful because it is strict about what it
promises.

The cleanest source-reading order follows the same lecture path:

1. [`math/src/algebra.rs`](../../../math/src/algebra.rs) for the contract deck
   and generic exponentiation engine.
2. [`math/src/test.rs`](../../../math/src/test.rs) for the tiny field and group
   that exercise the generic code paths.
3. [`math/src/fields/goldilocks.rs`](../../../math/src/fields/goldilocks.rs)
   for concrete reduction, inversion, roots of unity, and codec behavior.
4. [`math/src/poly.rs`](../../../math/src/poly.rs) for polynomial semantics,
   evaluation routes, and interpolation.
5. [`math/src/ntt.rs`](../../../math/src/ntt.rs) for matrix layout, butterflies,
   vanishing polynomials, and erasure recovery.

If you read in that order, the later machinery feels earned rather than magical.

---

## 9. Glossary

- **Additive** - a type with addition, subtraction, negation, and a zero.
- **Space** - an additive object that can be scaled by a ring-like scalar type.
- **MSM** - multi-scalar multiplication, a weighted sum of additive objects.
- **Ring** - an additive and multiplicative structure with `one()`.
- **Field** - a ring where every nonzero element has a multiplicative inverse.
- **FieldNTT** - a field with roots of unity, coset shifts, and efficient
  halving for transform work.
- **Goldilocks** - the concrete field `2^64 - 2^32 + 1` used here.
- **Bit-reversed order** - a storage order that makes recursive butterfly
  structure contiguous in memory.
- **Vanishing polynomial** - a polynomial chosen to be zero on a specific set of
  domain points.
- **Coset shift** - an element that moves transform work off the base domain so
  pointwise division avoids zeros.
- **NTT** - the number-theoretic transform, the fast path between coefficient
  and evaluation views of a polynomial.
