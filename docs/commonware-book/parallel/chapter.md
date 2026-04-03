# commonware-parallel

## One Algorithm, Two Ways to Run

Have you ever noticed what happens when people want to make their program run faster using multiple cores? They look at a perfectly beautiful, simple loop they've written, and they say, "I need to parallelize this!"

So what do they do? They write a *second* version of the exact same algorithm. Only this time, it's covered in mutexes, thread spawns, and shared state. They twist the logic around just to make the scheduler happy.

And then what happens? A month goes by. Somebody finds a bug in the first loop and fixes it. But they completely forget to update the second, parallel loop! Now the codebase has two different pieces of code that are *supposed* to do the same thing, but they drift apart. They don't even compute the same answer anymore! It's a mess.

This chapter is about `commonware-parallel`. The whole point of this crate is to solve this exact problem with a very simple promise: **You write what your algorithm means exactly once. How it gets scheduled—whether on one thread or many—is a separate choice that you make later, without changing the logic.**

## The Core Idea: Meaning vs. Scheduling

Think about it like this. Your algorithm is a recipe, and the computer is a kitchen.

- The **`Sequential`** strategy is like having exactly one cook. He takes the recipe, starts at step one, and works his way to the end, all by himself.
- The **`Rayon`** strategy is like a kitchen full of cooks. They chop up the ingredients into separate piles. Each cook prepares a part of the meal independently, and then they bring all their plates together at the very end.

The beautiful thing here is: **the recipe doesn't change**. The policy of *who* does the work changes, but *what* they are cooking remains exactly the same!

We achieve this in Rust by defining a boundary called a `Strategy`. Instead of writing `for` loops directly, you describe your work as a "reduction" or a "fold", and you let the `Strategy` trait decide how to physically run it on the machine.

## The Workhorse: `fold_init`

To understand how this works, we have to look at the most important tool in this crate. It's a method called `fold_init`.

If you know what a regular `fold` is, you know it takes a long list of things and squashes them down into one final result—like adding a list of numbers to get a sum. But `fold_init` gives you a little something extra, something absolutely essential for real-world programming: **local scratch space**.

Imagine you're processing a huge list of items, and to figure out each item, you need to use a temporary buffer. If you try to share *one* buffer across many threads, they will all step on each other's toes! You'd have to use a lock, and then they'd all just end up waiting in line. You've ruined the parallelism!

Instead, `fold_init` lets you give *each individual worker* its own private scratch space. Let's look at the Rust syntax. I've simplified the signature so we can see what the machinery is actually doing:

```rust
fn fold_init<I, INIT, T, R, ID, F, RD>(
    &self,
    iter: I,          // The list of things we want to process
    init: INIT,       // 1. How to create private scratch space (makes type `T`)
    identity: ID,     // 2. How to create a starting accumulator (makes type `R`)
    fold_op: F,       // 3. The local work: (accumulator, scratch space, item) -> accumulator
    reduce_op: RD,    // 4. The merge work: (accumulator, accumulator) -> accumulator
) -> R
```

Let's walk through exactly what the cooks are doing here:
1. **`init`**: Each cook gets their own private scratch pad (of type `T`). They don't share this with anyone. No locks, no waiting!
2. **`identity`**: Each cook gets a fresh plate to put their intermediate results on (of type `R`).
3. **`fold_op`**: This is the actual chopping and cooking. A cook takes an item from their pile, maybe uses their scratch pad to help process it, and adds the result to their plate.
4. **`reduce_op`**: When all the cooks are done, we have a bunch of plates. This operation takes two plates and combines them into one. We keep doing this until only one giant plate is left!

Let's look at a real, physical example. Let's say we want to format some numbers into a list of strings. We want to use a reusable `String` buffer so we aren't constantly asking the operating system for new memory allocations:

```rust
use commonware_parallel::{Strategy, Sequential};

let strategy = Sequential;
let data = vec![1u32, 2, 3, 4, 5];

let result: Vec<String> = strategy.fold_init(
    &data,
    || String::with_capacity(16),  // 1. Each worker gets a fresh, private string buffer
    Vec::new,                      // 2. Each worker starts with an empty list
    |mut acc, buf, &n| {           // 3. The local work!
        buf.clear();               // Clean our private scratch pad
        use std::fmt::Write;
        write!(buf, "num:{}", n).unwrap(); // Write into the scratch pad
        acc.push(buf.clone());     // Put the result on our plate
        acc
    },
    |mut a, b| {                   // 4. The merge step! Combine two cooks' plates.
        a.extend(b);
        a
    },
);
```

If we run this with `Sequential`, it's just one cook doing everything. But if we run it with `Rayon`, the work is partitioned automatically, the cooks are spawned, they each get their own buffers, and the results are safely glued together at the end. The brilliant part? **The code didn't change at all!**

## The Magic Rule: Associativity

Now, I have to let you in on a secret. This whole trick only works if your algorithm obeys a fundamental law of nature: **Associativity**.

In simple math, associativity means `(a + b) + c` gives you the exact same answer as `a + (b + c)`.

When you let `Rayon` chop up the work, you are giving up control over the exact order in which the plates are combined. Maybe cook A and cook B combine their plates first, and then cook C adds his. Or maybe B and C combine theirs, and A adds his later.

If your `reduce_op` cares about the grouping—if combining B and C first gives a fundamentally different answer than doing it left-to-right—then you simply cannot run it in parallel like this. You've written an algorithm that is inherently order-sensitive!

A great example is merging overlapping ranges. If you have `[1, 4]` and `[3, 5]`, they should merge together to become `[1, 5]`. If you just naively glue lists of ranges together in a parallel reduce without checking the edges, you might end up with `[[1, 4], [3, 5]]`, which is wrong!

To make an algorithm associative, your `fold_op` needs to keep things neat and tidy *locally*, so that your `reduce_op` only has to worry about the edges where two chunks meet. If you can make each chunk a canonical, perfect summary, the merge step is just snapping the edges together. That is the real trick to parallel programming.

## Sequential is Not a "Fallback"

You might look at the `Sequential` strategy and think, "Oh, that's just a dumb fallback for when I don't have threads." No!

`Sequential` is the **reference semantics**. It is the absolute truth of what your algorithm means. It's wonderfully boring. It creates exactly one scratch space, walks the items in order, folds them up, and completely ignores the merge step—because there is only one worker, there's nothing to merge!

When you write a new algorithm, you should always test it with `Sequential`. Because it's perfectly deterministic, if it works there, you know your fundamental logic is sound. And because `Sequential` works without the Rust standard library (`no_std`), you can take your exact same algorithm and run it in tiny embedded systems or smart contracts where threads don't even exist.

## Rayon and the Cost of Partitioning

When you *do* use `Rayon`, how does it actually divide up the physical work?

It doesn't just hand out items one by one to threads as they arrive. That would cause chaos and terrible performance! Instead, it collects the input into a `Vec` first.

Why allocate a vector? Because it gives us **contiguous partitions**. We chop the vector into solid, continuous blocks. A worker gets a solid block of items that are right next to each other in the original order. They can do their local fold cleanly, and produce exactly one summary for that entire block.

If we just streamed items randomly, we'd have to merge millions of tiny, individual results. By blocking them up, we do a bunch of fast local work, and only merge a few large results at the very end. That vector allocation is a deliberate, calculated price we pay for cleaner, much faster reductions.

## Convenience Methods

You don't always need the full, heavy machinery of `fold_init`. `Strategy` gives you some handy shortcuts that are built right on top of it:

- **`fold`**: Just like `fold_init`, but without the private scratch space. Great for simple sums or counting where you don't need a buffer.
- **`map_collect_vec`**: Transform each item one-by-one and collect them all into a vector.
- **`map_init_collect_vec`**: Transform items, but you get a private scratch space for the transformation.
- **`map_partition_collect_vec`**: Transform items, and keep the successful ones in one pile (vector) and the failures or filtered ones in another pile.
- **`join`**: Run two completely different closures at the exact same time and get both results back!

## Summary

The `commonware-parallel` crate absorbs a very specific, very annoying pressure: the temptation to write your code twice.

It forces you to write the *meaning* of your algorithm—the fold, the reduction, the scratch space—against the `Strategy` trait. Once you do that, the environment gets to decide the policy. `Sequential` gives you fixed order, zero overhead, and `no_std` support. `Rayon` gives you raw speed on multicore CPUs.

So don't write two loops. Write one reduction, and let the kitchen handle the rest!
