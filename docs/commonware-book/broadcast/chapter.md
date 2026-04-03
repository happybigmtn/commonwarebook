# commonware-broadcast

## A Town Crier With a Ledger, a Queue, and a Forgetting Rule

*Edited by Richard Feynman*

Let me tell you a story about a town crier. 

When people build distributed systems, they often think broadcasting is just about shouting as loud as you can. You have a message, you send it to everyone on the network, and you hope they hear it. But what happens when the network is noisy? What if some people are deaf for a second? What if someone arrives late and asks, "Hey, what did I miss?"

If you just shout, the late arrivals get nothing. So, you might think, "Okay, I'll write down everything I ever shout." But very quickly, your notebook fills up, and your node crashes because it ran out of memory. 

You need something in between. You need a way to remember things for a *little while*, but you also need a smart, rigorous way to **forget them**. 

That is exactly what `commonware-broadcast` does. It doesn't solve consensus. It doesn't agree on the absolute order of events in the universe. It just gives you a Town Crier who keeps a very specific set of books, remembers recent payloads by a unique fingerprint (a "digest"), and forgets them the moment they are no longer socially relevant.

---

## 1. The Town Crier's Mental Model

Imagine a town crier standing in the square. He doesn't just shout; he has four tools on his desk. This is the heart of our engine:

1. **The Shared Ledger (`items`)**: When a new proclamation arrives, he doesn't write down the sender's name on the front. He writes down the *content* and labels it with a unique, mathematical fingerprint (the digest). He only ever keeps one copy of the text, no matter how many people bring it to him.
2. **The Courier Logs (`deques`)**: Every courier (peer) who brings news gets a small clipboard. The crier writes down the fingerprints of the most recent messages that courier brought. But the clipboard only holds so many lines! When it's full, the oldest fingerprint gets pushed off the bottom.
3. **The Tally Marks (`counts`)**: For every fingerprint in the ledger, the crier keeps a tally of how many couriers still have that fingerprint on their clipboards. 
4. **The Waiting List (`waiters`)**: Sometimes a citizen walks up and says, "I'm looking for a message with the fingerprint `XYZ`. Do you have it?" If the crier has it, he hands it over. If he doesn't, he writes the citizen's name on a waiting list. The moment `XYZ` arrives, he delivers it to them.

**The Golden Rule of Forgetting:** The crier only keeps a shared text in his ledger as long as its tally mark is greater than zero. The moment a fingerprint falls off the bottom of *all* the couriers' clipboards, the tally hits zero, and the crier tears that page out of the ledger and burns it. 

---

## 2. Under the Hood: The Rust Engine

Let's look at how this physical model translates into Rust. If you open `broadcast/src/buffered/engine.rs`, you'll see a struct called `Engine`. 

```rust
pub struct Engine<E, P, M, D> {
    // ... config and setup ...

    /// All cached messages by digest.
    items: BTreeMap<M::Digest, M>,

    /// A bounded list of the latest received digests from each peer.
    deques: BTreeMap<P, VecDeque<M::Digest>>,

    /// How many peer logs still contain this digest.
    counts: BTreeMap<M::Digest, usize>,

    /// People waiting for a digest to arrive.
    waiters: BTreeMap<M::Digest, Vec<Waiter<M>>>,
}
```

Let's break down this Rust syntax so you can see exactly what the machine is doing:
- `BTreeMap`: In Rust, a `BTreeMap` is just a very fast, organized dictionary. We use it to map a key (like a `Digest` or a `Peer PublicKey`) to a value. 
- `VecDeque`: Think of this as a tube of tennis balls. You can shove a ball in one end, and if the tube is full, a ball pops out the other end. It's a "double-ended queue". We use it to keep exactly `deque_size` recent digests for each peer.
- `Waiter<M>`: This holds a `oneshot::Sender`. In Rust's asynchronous world, a `oneshot` channel is like a pager you hand to a customer at a restaurant. It can only buzz exactly once. When the message arrives, we buzz the pager, and the citizen gets their data instantly!

### The Event Loop: The Crier's Busy Day

The Engine doesn't just sit there. It runs continuously in an infinite loop, waiting for the universe to poke it. In Rust, we use a macro called `select_loop!` to handle this. It looks a bit like this conceptually:

```rust
loop {
    // 1. Throw away sticky notes for citizens who left the square.
    cleanup_waiters(); 

    select! {
        // Someone locally wants to broadcast a new message!
        msg = mailbox.recv() => handle_broadcast(msg),
        
        // A packet just arrived over the network from a peer!
        payload = network.recv() => handle_network(payload),
        
        // The network topology changed (someone joined or left)!
        update = peer_provider.update() => evict_untracked_peers(update),
    }
}
```

The beauty of the `select!` block is that it waits for *any* of these events to happen, handles it immediately, and goes right back to waiting. It never gets stuck.

---

## 3. The Magic of Duplicates

What happens when two different peers shout the exact same message? This is where the design shines.

If Peer A sends a message with digest `XYZ`, we store the heavy payload in `items`, put `XYZ` on Peer A's `VecDeque`, and set the `counts` tally for `XYZ` to 1.

A second later, Peer B sends the exact same message.
Do we allocate more memory for the payload? No! The engine looks at `items` and says, "Ah, I already have the bytes for `XYZ`." 
Instead, it simply adds `XYZ` to Peer B's `VecDeque` and bumps the tally in `counts` to 2. 

**What if Peer A sends the same message twice?**
If a peer repeats themselves, we don't increase the global tally. We just take that digest in their `VecDeque` and move it back to the very front of the line. We are refreshing their "recency" without duplicating global memory. 

By keeping the heavy payload separate from the lightweight lists of "who said what recently," we save massive amounts of RAM while keeping perfect track of who still cares about the message.

---

## 4. How the Waiters Work (No Polling Allowed!)

If you want a message that hasn't arrived yet, you call `subscribe(digest)`. 

In a lazy system, you might write a loop that checks the cache every 10 milliseconds. "Is it there yet? No. Is it there yet? No." This burns CPU and slows down the whole computer. We don't do that.

Instead, the `Engine` takes your `oneshot::Sender` pager and puts it in the `waiters` map under the digest you want. You go to sleep. 

The very microsecond the network thread receives that digest and validates it, the Engine pulls your pager out of the `waiters` list, shoves the message into it, and wakes you up. This is **digest-addressed rendezvous**. It's physically the most efficient way to wait for data.

What if you get tired of waiting and drop your end of the pager? The Engine notices! At the top of every loop cycle, `cleanup_waiters()` goes through the list and throws away the pagers of anyone who walked away. We never leak memory holding onto dead promises.

---

## 5. Forgetting on Purpose

Broadcast only works if you are willing to forget. The `Engine` forgets things in two ways:

### 1. The Tube gets full (Deque Overflow)
If `deque_size` is 100, and Peer A sends their 101st message, the oldest digest falls out of their `VecDeque`. The Engine looks at that dropped digest and decrements its tally in `counts`. If the tally hits zero, the payload is removed from `items`. Poof. Gone.

### 2. The Peer disappears (Membership-Driven Forgetting)
Imagine a peer disconnects or is kicked out of our routing table. `peer_provider` fires an event. The Engine immediately takes that peer's entire `VecDeque` and throws it in the trash. It goes through every digest that was on that clipboard and drops their tallies. If a message was *only* kept alive by that dead peer, it is instantly purged from memory. 

We don't keep data around "just in case." Memory is driven by live, physical membership.

---

## 6. Real-World Pressures: Malformed Data

Out in the wild, the network is full of garbage. People will send you corrupted bytes, half-finished packets, or malicious nonsense. 

Before a network byte ever touches the `Engine`'s pristine internal state, it has to pass through a `Codec`. The codec boundary is our immune system. 
If the bytes are garbage, the codec spits out an error. The Engine simply logs a warning, increments a "bad packet" metric, and moves on to the next packet. It never writes garbage into the cache. It never crashes. It just ignores the noise.

---

## 7. The Three Mailbox Questions

As a user of this crate, you don't talk to the `Engine` directly. You talk to a `Mailbox`. The mailbox lets you ask three simple questions:

1. `broadcast(recipients, message)`: 
   *"Put this payload into circulation. Also, insert it into my local cache immediately, so if I try to read it a microsecond from now, it's already there."*
2. `get(digest)`: 
   *"Check the ledger. Do you have this payload right now? Just answer Yes (with the data) or No."*
3. `subscribe(digest)`: 
   *"Hand me a pager. Wake me up the exact moment this digest arrives from anywhere."*

---

## 8. Experiments (Executable Invariants)

In physics, you don't just write down a theory; you test it with an experiment. Our tests in `mod.rs` are executable physics experiments that prove the Engine behaves:

- **Experiment 1: Self-Retrieval (`test_self_retrieval`)**
  If I broadcast a message, can I instantly get it back? Yes. The engine stores it locally before even touching the network.
- **Experiment 2: Shared Liveness (`test_ref_count_across_peers`)**
  If two peers send the same message, and one peer disconnects, does the message survive? Yes! The tally drops from 2 to 1, but the message stays.
- **Experiment 3: The Drop Test (`test_dropped_waiters_for_missing_digest_are_cleaned_up`)**
  If a citizen asks for a message and then leaves the town square, does the crier keep their sticky note forever? No. The cleanup routine catches it.

---

## Summary

`commonware-broadcast` is not a magic wand that guarantees every node sees every message in perfect order. It is a highly engineered, memory-safe shock absorber.

It absorbs network delays by letting you wait efficiently. It absorbs duplication by deduplicating payloads and tracking peer recency. It absorbs malicious garbage by strict decoding. And most importantly, it prevents your computer from exploding by knowing exactly when to throw old news away. 

That is how you build a robust broadcast system. You don't try to remember everything forever. You just keep track of what matters, right now.
