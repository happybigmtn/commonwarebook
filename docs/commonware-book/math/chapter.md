# commonware-math: The Engine Room

*Or: How to stop worrying and love the algebra.*

---

## 1. Why Do We Even Need This?

Let's start at the beginning. If you've ever written systems code, you know what numbers are. They're little buckets of bits inside the computer. You add two of them together, and if the bucket gets too full, it spills over. We call that an overflow. If you divide them, you lose the crumbs. We call that rounding.

Now, imagine you're building a system that cuts up a secret key into pieces, scatters them across a network, and later tries to put them back together even if some pieces got lost. If you try to do that with normal integer arithmetic, the overflows and the rounding will destroy you. The math just won't work! The pieces won't fit. You'll put the puzzle back together and the picture will be slightly wrong, but a cryptography system doesn't say "Oh, close enough!" It just fails. 

So, we can't just use "some numbers." We need an environment with strict rules. A place where addition always stays in bounds, where you can always divide without losing crumbs, and where you can move data around quickly without changing its meaning. 

That is what `commonware-math` is. It's the mathematical engine room for the rest of the system. 

It answers one simple question for every other crate in the project:
> "What are the rules of the game, what specific numbers are we playing with, and how do we do the math fast enough that the computer doesn't catch on fire?"

Let's walk through it, layer by layer.

---

## 2. The Contract Deck (Or, What Are the Rules?)

The first thing `commonware-math` does is lay down the law. And it does this using Rust traits in [`algebra.rs`](../../../math/src/algebra.rs). It doesn't pick a specific number system yet. It just says, "If you want to play here, you have to follow these contracts."

Here's the ladder of contracts:

- `Additive`: You can add (`+`), subtract (`-`), and negate (`-x`). You're like a commutable group.
- `Multiplicative`: You can multiply (`*`) and square things.
- `Space<R>`: You can take an additive thing, multiply it by a scalar (a number), and stretch it out.
- `Ring`: You have everything above, plus the number `1`, and you can do exponentiation. 
- `Field`: You are a Ring, but you also have a superpower—you can *divide* anything (except zero). Every number has an inverse.
- `FieldNTT`: You are a Field with a special bonus: you have "roots of unity" which let us do super-fast transforms, which we'll get to later.

These aren't just fancy math words for the sake of being fancy. They are promises to the machine. If a system knows something is `Additive`, it knows it can cancel things out. If it knows it's a `FieldNTT`, it knows it can leap into a transform domain and leap back safely. The laws *are* the interface.

### The "Don't Copy The Library" Rule

If you look closely at `algebra.rs`, you'll see a lot of borrowed operators. You don't see `T + T`. You see `T + &T`. 

Why? Because in systems code, these objects aren't always tiny 64-bit integers! Sometimes they are massive polynomials with thousands of coefficients. If you passed them by value, the computer would spend all its time copying memory around. It would be like trying to read a paragraph from a book in the library, and instead of walking over to the book, you photocopy the entire library, read the sentence, and throw the copy away. 

By enforcing borrowed right-hand sides (`&mut T += &T`), the crate protects you from accidentally doing something incredibly slow.

### Nature Uses the Same Trick Twice: `monoid_exp`

There's a beautiful piece of code in `algebra.rs` called `monoid_exp`. 

Suppose you want to compute `x^13`. 
The naive way is to say: `x * x * x * x...` thirteen times. That's slow!
The smart way is to look at the number 13 in binary: `1101₂`. 

You start with an accumulator. You look at the bits from right to left. 
1. The first bit is `1`, so you multiply the accumulator by `x`. Then you square `x` (now it's `x^2`).
2. The second bit is `0`, so you skip multiplying. You square `x` again (now it's `x^4`).
3. The third bit is `1`, so you multiply the accumulator by `x^4`. You square again (`x^8`).
4. The fourth bit is `1`, so you multiply the accumulator by `x^8`.
Result: `x^1 * x^4 * x^8 = x^13`. 

But wait! What if you wanted to compute `13 * x` using just addition?
You use the *exact same logic*, just with different operations. Instead of multiplying, you add. Instead of squaring, you double!
Result: `x + 4x + 8x = 13x`.

`commonware-math` realizes this is the exact same underlying idea. It writes one generic routine—`monoid_exp`—and feeds it either (multiply, square) or (add, double). One engine powers both. That's good engineering.

---

## 3. Goldilocks: Making the Rules Concrete

Abstract rules are great, but eventually the computer has to flip some actual bits. In `commonware-math`, the concrete numbers we use live in a specific Field called **Goldilocks**, found in [`math/src/fields/goldilocks.rs`](../../../math/src/fields/goldilocks.rs).

In this field, math wraps around a specific prime number (the modulus):
`P = 2^64 - 2^32 + 1`

Why this number? Is it just because it looks pretty? No! It's because of what it does to the computer's arithmetic.

When you multiply two 64-bit numbers, the result is a 128-bit number. To stay in the field, we have to divide that massive 128-bit number by `P` and find the remainder. Division on a CPU is *terribly* slow. We want to avoid it like the plague.

### The `reduce_128` Trick

Here is how the Goldilocks modulus saves the day. Let's do some chalkboard math.

Since `P = 2^64 - 2^32 + 1`, we know that inside this field:
`2^64 = 2^32 - 1` (We just moved the terms to the other side of the equation).

If we multiply both sides by `2^32`, we get another fun fact:
`2^96 = -1`

Now, take any big 128-bit number `x`. We can chop it into three parts: a low 64 bits (`a`), a middle 32 bits (`b`), and a high 32 bits (`c`).
`x = (c * 2^96) + (b * 2^64) + a`

Now substitute the fun facts we just figured out!
`x = (c * -1) + (b * (2^32 - 1)) + a`
`x = a - c + b * (2^32 - 1)`

Look at what just happened! We completely eliminated the 128-bit division! We replaced it with a couple of tiny subtractions, one small multiplication, and some bit-shifting. 

The code in `reduce_128` literally pulls `a`, `b`, and `c` out of the number and puts them back together using exactly this formula. It is an incredibly fast, gorgeous trick, and it only works because someone was very clever when they chose the modulus `P`.

---

## 4. Polynomials: Not Just Buckets of Coefficients

The next layer up is polynomials in [`math/src/poly.rs`](../../../math/src/poly.rs). 

Most people think of a polynomial as a bucket of numbers: `[3, 5, 0, 0]` meaning `3 + 5x + 0x^2 + 0x^3`.
But to `commonware-math`, a polynomial is a *semantic object*. It represents a mathematical truth that has to survive no matter how it's stored.

Take the degree, for example. The array `[3, 5, 0, 0]` has 4 elements. But mathematically, the `0x^2` and `0x^3` don't do anything! The real polynomial is just `3 + 5x`, which has a degree of 1.
That's why the crate has two functions: `degree()` (which just looks at the array size because it's cheap) and `degree_exact()` (which walks backward and ignores the trailing zeros to find the *true* mathematical degree).

### The Interpolation Miracle

If you have a polynomial of degree 2 (like a parabola), and I give you 3 points on it, you can figure out the entire equation. This is called interpolation. In our system, the "secret" we are trying to share is usually the constant term of the polynomial (the point where `x = 0`).

To find the secret from a bunch of scattered points, you use something called Lagrange weights. The naive way to calculate these weights requires calculating a ton of inverses (divisions). As we discussed, division is slow.

So, the `Interpolator` does something amazing: **Montgomery's Trick**.
Imagine you want to find `1/A`, `1/B`, and `1/C`. 
Instead of doing three expensive divisions, you multiply them all together: `A * B * C`. You do *one* expensive division to get `1 / (ABC)`. 
Then, you multiply by `BC` to get `1/A`. You multiply by `AC` to get `1/B`. 
You traded a bunch of divisions for one division and a handful of cheap multiplications. The crate uses this trick to batch-calculate all the Lagrange weights up front, making secret recovery lightning fast.

---

## 5. The NTT (The Number-Theoretic Transform)

Now we enter the real magic trick of the crate: [`math/src/ntt.rs`](../../../math/src/ntt.rs).

Sometimes you want to evaluate a polynomial at many different points. Doing it the normal way (`a + bx + cx^2...`) for every single point is painfully slow—it takes `O(N^2)` time. 

But what if you carefully choose the points? 
If you choose a special set of points called "roots of unity" (which the Goldilocks field provides), the math perfectly folds in on itself in a process called the Number-Theoretic Transform (NTT).

### The Butterfly

Here is the physical intuition. You have a polynomial `f(X)`. You can split it into the even-powered terms and the odd-powered terms:
`f(X) = f_even(X^2) + X * f_odd(X^2)`

If you evaluate this on the special "root of unity" points, something magical happens. Calculating the value at point `w` gives you the value at point `-w` almost for free! You just do:
- `a = f_even`
- `b = w * f_odd`
- The value at `w` is `a + b`.
- The value at `-w` is `a - b`.

This is called the "butterfly operation." It halves the amount of work you have to do. Then you apply the trick again. And again. Suddenly, evaluating a massive polynomial takes a fraction of the time (`O(N log N)`).

### Why Do We Store Things Backwards?

If you look at how the crate stores polynomial matrices for the NTT, you'll see it uses **bit-reversed order**. 
For a 4-term polynomial, instead of storing `0, 1, 2, 3`, it stores `0, 2, 1, 3`.

Why on earth would you scramble the data?
Because of the butterfly! The butterfly operation splits the even and odd coefficients apart over and over again. If you keep the data in normal order, the computer has to constantly jump around in memory to find the pairs it needs. Memory jumping is slow. 
By scrambling the data into bit-reversed order *first*, the elements the butterfly needs are sitting right next to each other exactly when it needs them. We spend a little complexity on the storage layout so the inner math loop can run at blazing speed.

---

## 6. Erasures and The Division Dance

Finally, what happens when things go wrong? We encoded some data, padded it out with parities, sent it over the network, and a few pieces were lost (erased). How do we get them back?

The math handles this elegantly using **Vanishing Polynomials**.

Let's say our data is a polynomial `D(X)`. We know its values at the points that arrived safely, but not at the points that went missing. 
We construct a new polynomial, `V(X)`, designed specifically so that it equals `0` (it "vanishes") at exactly the points we are missing. 

Now, we multiply them: `D(X) * V(X)`.
At the surviving points, we can compute this easily. At the missing points, well, we don't know `D(X)`, but we know `V(X) = 0`. And anything times zero is zero! So we know the entire combined polynomial `D(X) * V(X)` across the whole board.

We interpolate this combined polynomial to get its coefficients. Now we have `D(X) * V(X)`. To get our original data `D(X)` back, we just have to divide by `V(X)`.

### The Coset Shift (Stepping to the Side)

But wait! We have a problem. We need to divide by `V(X)`, but `V(X)` was specifically designed to be zero at our missing points. If we try to divide by zero, the universe explodes.

So `commonware-math` does a little dance called the **Coset Shift**. 
It takes the entire polynomial and physically shifts it off the domain points. It multiplies the evaluation points by a constant factor so that none of them land on the zeros. 

1. Shift the points to the side.
2. Do the division (safely, because no point is zero anymore).
3. Shift the points back.

The missing rows aren't guessed. They are forced back into existence by the inescapable laws of algebra.

---

## 7. The Takeaway

When you read `commonware-math`, don't get lost in the Greek letters. Ask yourself: what pressure is this design absorbing?

- **It absorbs correctness pressure.** The trait bounds and test suites mean the rest of the project doesn't have to wonder if `+` actually means `+`.
- **It absorbs performance pressure.** The Goldilocks modulus trick, the borrowed operators, and the bit-reversed NTT layout mean the math is fast enough to run in the real world.
- **It absorbs semantic pressure.** The rest of the codebase can ask to "interpolate this secret" or "recover these missing rows" without needing to know the complex dance of coset shifts happening underneath.

This crate isn't just a math library. It is the solid, unyielding floor that the rest of the protocol is built on. If you want to understand it, read the code in this order:

1. `algebra.rs` to see the laws.
2. `test.rs` to see the laws being enforced on toy examples.
3. `fields/goldilocks.rs` to see how the math gets fast.
4. `poly.rs` to see how numbers become objects with meaning.
5. `ntt.rs` to see how structure transforms those objects into a machine for erasure recovery.

It’s all just buckets and rules. But if you get the rules exactly right, the buckets can do magic.