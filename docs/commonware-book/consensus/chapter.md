# commonware-consensus

## The Fundamental Problem: Agreeing in a Noisy Room

Imagine you have a bunch of people—let's call them machines—and they all have to agree on what happens next. If they are all in the same room, honest, and listening perfectly, it's easy. But what if they aren't? What if some of them are deaf, some are incredibly slow, and a few are actively trying to trick the others by whispering different things to different people? 

In computer science, we call this the Byzantine fault-tolerant consensus problem. It asks one very uncomfortable question:
> When several machines disagree about what should happen next, who gets to decide?

If you want to build a reliable distributed system, you can't just hope for the best. You need a strict protocol. `commonware-consensus` is exactly that protocol. It takes a chaotic, adversarial network and forces out a single, undeniable sequence of events. 

And here is the beautiful part: it does this with **opaque** messages. Consensus doesn't care if your payload is a financial transaction, a smart contract state, or a recipe for pancakes. You decide what the bytes mean. Consensus just decides what order they go in.

---

## Why Is Consensus So Hard?

When students first hear about consensus, they often think, "Why don't they just all vote, and whatever gets the majority wins?"

It sounds simple, right? But think about it. A majority of *what*? Observed by *whom*? At *what time*?

Imagine I'm a malicious leader. I propose "History A" to half the room, and "History B" to the other half. The network is slow, so people don't realize I've lied until they've already locked their votes in. Now we have a split brain. Or worse, what if some machines just crash and wake up later with amnesia? "Just vote" isn't a protocol; it's a disaster waiting to happen.

### The Geometry of Quorums

To solve this, we don't just use simple majorities. We use **quorums**. 
The idea behind a quorum is pure, elegant geometry. We require enough participants to endorse a decision so that *any two valid quorums must overlap*. 

In a benign system, a simple majority (over 50%) guarantees overlap. But in a Byzantine system where up to `f` machines out of `N` can lie, we need a stronger threshold. This is why you constantly see the magic rule: `> 2N/3`. 
If fewer than 1/3 of the network is malicious, then any two groups of size `> 2N/3` *must* share at least one honest machine. That single honest machine is the linchpin. Because it obeys the rules, it won't sign two conflicting histories. The geometry of the quorum physically prevents the system from splitting.

### Crash vs. Byzantine

We have to separate two worlds. If a machine just unplugs, that's a **crash fault**. It's annoying, but it's not evil. A crashed node won't forge signatures or tell lies. 
A **Byzantine fault** is malicious. A Byzantine node will strategically omit messages, forge what it can, and send conflicting data to split the network. Once you admit Byzantine behavior, you can't trust anything without cryptographic proof. Signatures, namespaces, and explicit evidence are no longer just paperwork—they are the load-bearing walls of the system.

---

## The Commonware Approach: Simplex

The `commonware-consensus` crate is built on a primitive called **Simplex**. 

Simplex takes the classical consensus dance and distills it down to three phases. You can think of Simplex as a voting machine with memory. Each round (called a **view**) has a designated leader who proposes a block. The validators then move through three types of votes: **Notarize**, **Nullify**, and **Finalize**.

Here is the mental model to keep in your head:
> **Finalization requires Notarization, and Notarization requires Proposal Validity.**

Let's break down exactly what these votes mean.

### 1. Notarize: "Is this valid?"
When a leader proposes a block, validators check if it makes sense. If it does, they sign a **Notarize** vote. Once `> 2N/3` validators notarize it, we get a *Notarization Certificate*. This doesn't mean the block is etched in stone forever, but it crosses a critical threshold: any safe future history *must* account for it.

### 2. Nullify: "Should we move on?"
What if the leader is dead? Or evil? We can't wait forever. If progress stalls, validators vote to **Nullify** the view. Nullify votes carry no payload, just the round number. But they are crucial! You can't just skip a view willy-nilly; you need proof that the network agreed to skip it, ensuring no one got left behind on a valid chain.

### 3. Finalize: "Lock it in!"
Once a block is notarized, the system can ask, "Are we ready to commit this to the permanent ledger?" If yes, validators cast a **Finalize** vote. A Finalization Certificate is the ultimate proof: this block is history.

---

## Code Explainer: The Machinery Underneath

Let's look at how the Rust code actually enforces this. The brilliance of the implementation is how it organizes time, data, and actors.

### What Time Is It?
In the code (`types.rs`), we don't just use UNIX timestamps. We have precise, logical clocks:
* **`Epoch`**: The validator-set boundary. If the people in the room change, the epoch changes.
* **`View`**: The leader-attempt counter. If a leader fails, the view goes up.
* **`Round`**: The combination of `(Epoch, View)`. This is our absolute coordinate.
* **`Height`**: The position of a finalized block in the chain.

### The Boundary: The `Automaton` Trait
How does consensus talk to your application? Through the `Automaton` trait. 
Notice that the consensus engine only passes around *digests* (hashes), not the massive blocks themselves. 

```rust
pub trait Automaton: Clone + Send + 'static {
    type Context;
    type Digest: Digest;

    fn genesis(&mut self, epoch: Epoch) -> impl Future<Output = Self::Digest> + Send;
    fn propose(&mut self, context: Self::Context) -> impl Future<Output = oneshot::Receiver<Self::Digest>> + Send;
    fn verify(&mut self, context: Self::Context, payload: Self::Digest) -> impl Future<Output = oneshot::Receiver<bool>> + Send;
}
```
The `verify` function is fascinating. It returns a one-shot channel. Why? Because your application might need to go look up a database or wait for a network request to decide if a transaction is valid. But notice: once it says `false`, consensus drops it forever. It's a single-shot decision.

### The Cryptographic Hygiene: Domain Separation
How do we ensure a malicious leader doesn't take a validator's signature from a `Notarize` vote and copy-paste it to pretend it was a `Finalize` vote? 

We use **Domain Separation**. In `scheme/mod.rs`, you'll see:
```rust
const NOTARIZE_SUFFIX: &[u8] = b"_NOTARIZE";
const NULLIFY_SUFFIX: &[u8] = b"_NULLIFY";
const FINALIZE_SUFFIX: &[u8] = b"_FINALIZE";
```
Every time a validator signs something, these bytes are mixed into the cryptographic hash. A signature for `_NOTARIZE` mathematically cannot be validated as a `_FINALIZE`. This simple trick blocks an entire class of replay attacks.

---

## The Three Actors: Voter, Batcher, Resolver

If you look at the source code, you won't find one giant monolithic "Consensus" struct. That would be a nightmare to test. Instead, Simplex is split into three cooperating actors communicating over channels.

1. **The Voter** (`voter/actor.rs`): This is the heart. It owns the temporal truth. It knows what view we are in, handles timeouts, and talks to the `Automaton`. If you want to know *why* the node is refusing to vote, look here.
2. **The Batcher** (`batcher/round.rs`): This actor handles the heavy cryptographic lifting. It collects untrusted votes from the network, verifies signatures in batches, and squashes them into Quorum Certificates. It catches the liars who try to double-vote.
3. **The Resolver** (`resolver/actor.rs`): What if we missed a message? The resolver tracks gaps. It knows our "floor" (the last thing we safely knew) and reaches out to peers to fetch missing certificates and nullifications so the Voter can catch up.

### The Trickiest Invariant: Parent Nullification

Here is a brilliant piece of logic in the Voter actor you need to understand. 
Look at the `Context` struct inside `simplex/types.rs`:
```rust
pub struct Context<D: Digest, P: PublicKey> {
    pub round: Round,
    pub leader: P,
    pub parent: (View, D),
}
```
Why do we carry the `parent` view around? 
Imagine an honest leader proposes Block A at View 5. You are a bit slow and haven't notarized it yet. A malicious leader takes over at View 6 and proposes Block B, but they maliciously point Block B's parent all the way back to View 4, trying to orphan the honest Block A!

If you just blindly voted for View 6, you'd be helping the attacker fork the chain. 
The code prevents this with **Parent Nullification**: Before you are allowed to vote on View 6, you *must* possess a Nullification Certificate for View 5. If you don't have proof that View 5 was legally skipped, you stay silent. This rule enforces an unbroken chain of cryptographic justification.

---

## The Surrounding Layers

Simplex doesn't work alone. It's sandwiched between other highly specialized primitives:

* **Ordered Broadcast**: Before Simplex can even agree on digests, the actual block data has to reach the nodes. Ordered Broadcast handles reliable delivery from sequencers to validators. It chains chunks together so that if a sequencer equivocates (sends two different things), the network generates cryptographic proof of the lie.
* **Aggregation**: Sometimes you just need to staple a quorum of signatures over an already-ordered sequence of items. Aggregation handles this efficiently using a "safe tip" heuristic to ignore malicious stragglers.
* **Marshal**: The final boss. Marshal takes the chaotic, out-of-order stream of certificates from Simplex and irons them flat. It ensures the application *only* receives finalized blocks in a strict, monotonic, gap-free sequence. It holds things in a pipeline (`PendingAcks`) until every condition is perfect.

## Conclusion: Making it Real

Consensus design isn't just about reading whitepapers; it's about turning theoretical guarantees into rust code that survives crashes, network partitions, and active adversaries. 

`commonware-consensus` makes these guarantees executable. The N3f1 thresholds, the domain-separated signatures, the single-shot verifications, and the strict parent nullifications—they aren't arbitrary rules. They are the physical constraints that force a room full of chaotic, noisy machines to inevitably and securely agree on exactly one history.