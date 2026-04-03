# commonware-coding

*A Lecture on Recoverability, Commitments, and Agreement Under Partial Information*

---

## Opening Apparatus: The Jigsaw Puzzle Problem

I want you to imagine a very simple, very annoying problem. You have a giant, beautiful picture—say, a 4 Megabyte block of data—and fifty friends who all need to see it. 

The naive way to do this is to just hand the whole 4 Megabytes to every single friend. But look what happens! You're suddenly pushing 200 Megabytes out of your single computer while everyone else just sits around waiting. Your connection is completely clogged, and you are the bottleneck.

So, some clever folks came up with a better idea: **erasure coding**. You chop the picture up into a bunch of puzzle pieces. You hand a different piece to each friend and say, "Here, you guys share these with each other!" Suddenly, everyone is helping. You only send out a little bit of data to each person, and if they gather enough pieces from one another, they can reconstruct the whole picture.

But here is where the real world ruins the elegant math: your friends might be liars, or the network might be full of adversaries. 

What if a malicious friend slips in a puzzle piece from a completely different picture? Or what if the person who made the puzzle pieces just handed out random cardboard shapes that don't fit together at all? 

In a distributed system, nobody has the whole picture at first. Everyone only sees fragments. And you don't want to spend precious time collecting pieces, voting on them, and forwarding them, only to discover at the very end that the puzzle is garbage.

This brings us to the crux of `commonware-coding`. We need **redundancy** (so we can lose some pieces and still build the picture) and we need **evidence** (so we know a piece actually belongs to the picture we care about). 

We need a **proof-carrying jigsaw puzzle**.

---

## 1. The Mental Model: Proof-Carrying Jigsaws

When you buy a jigsaw puzzle, there's a picture on the front of the box. Let's call that the **commitment**. It's the stable, cryptographic name for the thing we're all trying to build.

The puzzle pieces themselves are the **shards**. 

In our system, a piece isn't allowed to just be a cardboard shape. It has to carry a little cryptographic proof that says, "I belong to *this* specific box, at *this* specific position." When a node checks that proof and is satisfied, we call it a **checked shard**. 

Now, depending on *what* that proof tells us, we have two different stories to tell, and they answer two fundamentally different questions about our system:

1. **The Recoverability Question (Reed-Solomon):** "If enough pieces survive, can I reconstruct the picture?"
2. **The Early-Agreement Question (ZODA):** "Before I even try to reconstruct it, the second I look at *my* piece, can I know for sure that the guy who made the puzzle didn't just put random cardboard in the box?"

Let's dive into the code to see exactly how these two ideas are built.

---

## 2. The Configuration: The Contract of Recoverability

If you look in `coding/src/lib.rs`, you'll see a tiny, incredibly important struct:

```rust
pub struct Config {
    pub minimum_shards: NonZeroU16,
    pub extra_shards: NonZeroU16,
}
```

This is the dial you turn to trade efficiency for safety. 
- `minimum_shards` is your threshold. How many puzzle pieces do we absolutely need to finish the picture?
- `extra_shards` is your redundancy budget. How many extra pieces are we willing to create and send so that if some get lost or maliciously withheld, we don't care?

Notice we don't just ask for `total_shards`. We purposefully separate the threshold from the slack. This forces the system to be explicit about how much information must survive versus how much leeway we are buying.

---

## 3. The Standard Story: Reed-Solomon

Let's look at the basic `Scheme` trait. This is our baseline distributed-systems contract.

```rust
pub trait Scheme {
    type Commitment: Digest;
    type Shard;
    type CheckedShard;

    fn encode(...) -> Result<(Self::Commitment, Vec<Self::Shard>), Self::Error>;
    fn check(...) -> Result<Self::CheckedShard, Self::Error>;
    fn decode(...) -> Result<Vec<u8>, Self::Error>;
}
```

The flow of time here is beautiful:
1. `encode` takes the data, chops it up, and gives us the picture on the box (`Commitment`) and the raw pieces (`Vec<Shard>`).
2. `check` takes a raw piece from the network and turns it into a `CheckedShard`. It says, "Yes, the math checks out; this piece belongs to this box."
3. `decode` takes a pile of `CheckedShard`s and rebuilds the data.

### The Secret Life of `decode`

If you open `coding/src/reed_solomon.rs`, you'll notice something shocking. When we `decode`, we don't just run the math, get the bytes, and go home. Oh no! We do a **canonicality audit**.

What happens if an evil leader creates pieces that *can* be put together, but they decode into a weird padded layout that means something different to the application? An adversarial system cannot afford ambiguity.

Here is what our Reed-Solomon `decode` actually does:
1. Reconstructs the missing puzzle pieces.
2. *Re-encodes* those pieces from scratch.
3. Rebuilds a massive Merkle Tree over all the pieces.
4. Checks if the root of that new tree *exactly* matches the `Commitment` we started with!

It's completely paranoid, and for good reason! We aren't just asking "Did we recover something?" We are asking "Did we recover the *one, unique object* that consensus thought it was agreeing on?" We even check that all the padding bytes at the end are exactly zero. If they aren't, we throw it out. Canonicality isn't polish; it's a core safety requirement.

---

## 4. The Phased Story: ZODA and Early Validity

Reed-Solomon is fantastic, but it has a limitation. You check your piece, and you know it belongs to the box. But what if the box is full of pieces from five different puzzles? You won't find out until you collect `minimum_shards` and run `decode`. 

By then, you've wasted network bandwidth and precious consensus time. 

What if we want to know earlier? What if we want to know, just from looking at *our* piece, that the whole puzzle is mathematically guaranteed to be solvable?

Enter `PhasedScheme` and the magic of ZODA (`coding/src/zoda/mod.rs`).

```rust
pub trait PhasedScheme {
    type StrongShard;
    type WeakShard;
    type CheckingData;
    type CheckedShard;

    fn encode(...) -> Result<(Commitment, Vec<StrongShard>), Error>;
    fn weaken(...) -> Result<(CheckingData, CheckedShard, WeakShard), Error>;
    fn check(...) -> Result<CheckedShard, Error>;
    fn decode(...) -> Result<Vec<u8>, Error>;
}
```

Notice the new vocabulary! We have **Strong Shards** and **Weak Shards**. Why? 

Because the first person to receive a shard (let's say, from the leader) gets a `StrongShard`. It's packed with extra mathematical goodies. But they don't want to forward all that extra bulk to everyone else over the network! 

So, they call `weaken`. 
- `weaken` looks at the `StrongShard` and extracts `CheckingData` (the local proof rules).
- It immediately checks the piece itself against these rules, giving us a `CheckedShard`.
- And it spits out a stripped-down `WeakShard` that we can forward to our friends.

When our friends receive that `WeakShard`, they use the `CheckingData` to run `check()`. 

### How ZODA Works (Without the Painful Math)

How does ZODA actually prove the whole puzzle is valid from just one piece? With a brilliant trick involving matrix multiplication.

Imagine arranging our data into a grid (a matrix). 
1. We encode the rows of this grid so we have lots of extra rows (redundancy).
2. We commit to these rows using a Merkle tree.
3. Then, using the commitment as a source of randomness, we generate a magic **checking matrix**.
4. We multiply our data grid by this checking matrix to create a **checksum**. We commit to this checksum too!

When you get a `StrongShard`, you get some rows of the data, the Merkle proof, *and the checksum*.

When you `check` a piece, you aren't just verifying a Merkle proof. You are multiplying your rows by the checking matrix and verifying that they perfectly match the checksum! 

Because the checking matrix was generated randomly *after* the data was committed (thanks to the Fiat-Shamir transform), it is statistically impossible for an evil leader to forge a checksum that works for invalid data. If your piece passes the checksum test, you have mathematical certainty that a valid puzzle exists.

This gives ZODA the `ValidatingScheme` marker trait. It's the highest tier of trust! A successful check doesn't just mean "I belong to this commitment." It means "This commitment represents a valid encoding story."

### The Art of Topology

If you peek into `coding/src/zoda/topology.rs`, you'll see we spend a lot of effort deciding exactly how many rows, columns, and samples we need. This isn't just to make the arrays fit in memory. **The shape of the matrix is part of the security proof.**

`Topology::reckon` decides how to shape the grid to guarantee exactly 126 bits of security. We try to maximize the number of columns because ZODA is faster with wider matrices. But we must ensure that every shard gets enough random rows to catch a cheating leader. It calculates fractional logarithms to ensure the math holds. It's a beautiful balancing act between performance and cryptographic armor. Matrix shape is not a sizing detail; it is a security statement.

---

## 5. Summary: Which One Do I Choose?

The difference isn't just "simple vs. advanced." It's about *when* your system needs to be certain.

| Feature | Reed-Solomon | ZODA |
| :--- | :--- | :--- |
| **What does a check prove?** | "This piece belongs in this box." | "This piece belongs in this box, AND the box contains a valid puzzle." |
| **Who forwards what?** | Everyone forwards chunks. | First receiver gets a Strong Shard, extracts checking rules, and forwards a Weak Shard. |
| **When are we sure?** | When we collect enough pieces to decode. | The moment we successfully check our first piece! |

If your system can afford to wait until `decode` to find out if the leader was lying, **Reed-Solomon** is incredibly fast, simple, and robust. It's the right answer for straightforward recoverability.

If your system is moving fast and you cannot afford to waste time voting on or forwarding pieces of a broken puzzle, **ZODA** stops the lie immediately. It buys you early agreement.

### A Final Thought

Whether you are using Reed-Solomon or ZODA, `commonware-coding` absorbs a massive amount of pressure for your distributed system. It prevents the leader from being a bandwidth bottleneck. It gives you precise vocabulary (`Raw`, `Checked`, `Strong`, `Weak`) so you never accidentally trust a piece of data too early. 

And most importantly, it defends **agreement**. It guarantees that if two honest nodes accept their puzzle pieces, they will absolutely, mathematically end up looking at the exact same picture.

Now, go read `coding/src/lib.rs` and see the promises for yourself!