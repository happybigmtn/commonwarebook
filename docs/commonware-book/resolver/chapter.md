# commonware-resolver

## The Missing-Piece Coordinator

Imagine you’re trying to find a very specific piece of a jigsaw puzzle, and the only way to find it is to ask a room full of people. Now, some of these people might have it, some might not, some might be incredibly slow to answer, and some might even hand you a piece from a completely different puzzle just to mess with you.

How do you organize this search without completely losing your mind?

That’s exactly the problem `commonware-resolver` solves. It is a persistent, coordinated search that stays alive until you—the consumer—look at the piece and say, "Yes, this is exactly what I needed."

---

## 0. Opening Apparatus

**The Promise.** By the end of this chapter, you’ll understand how `commonware-resolver` keeps a search for a missing piece alive without accidentally multiplying the work, and why it absolutely insists on separating *finding* a piece from *validating* it.

**The Crux.** The resolver is a coordinator. It keeps one search per key. It remembers who it has already asked so it doesn't do the same work twice. And most importantly, it never assumes a reply is the correct answer.

**The Primary Invariant.** A key never turns into two independent searches. A search only ends when one of three things happens: the consumer accepts the value, the caller cancels the search, or the caller decides to trim the search away.

**The Naive Failure.** If you just treat every reply as a success, you're in trouble. Every time someone doesn't have the piece, you spawn more searches. Every time someone hands you a piece of junk, you think you're done. You end up burning the network down just rediscovering the same absences.

**Reading Map:**
1. Start with `resolver/src/lib.rs` to see the boundary between the resolver and the rest of the world.
2. Look at `resolver/src/p2p/fetcher.rs` to see the "memory" of the search.
3. Check `resolver/src/p2p/engine.rs` to see the beating heart—the actor loop that drives everything forward.
4. Don't skip the tests in `resolver/src/p2p/mod.rs` and `resolver/src/p2p/fetcher.rs`. They are the real documentation of how the edge cases are handled.

---

## 1. Background: Why Missing Data Turns Into Coordination

Let’s think about distributed lookup. It sounds simple, right? It's just a request and a response. But it’s not! It's a search problem in a network that is fundamentally unreliable. The network can lie to you by omitting things, delaying things, duplicating things, or just flat-out disagreeing.

Let’s get our terms straight so we know what we're talking about:
- A **candidate** is a piece of data that *might* be the answer.
- A **consumer** is the judge. It looks at the candidate and decides if it’s actually right.
- A **producer** is someone who has pieces and serves them to others.
- A **targeted search** means you only want to ask a specific group of people. "Only ask the people in the front row."
- An **untargeted search** means you'll take the piece from anybody who has it.

The naive way to build this is to say, "Hey, if someone replies, we're done!" But think about what happens. If someone replies with garbage, you stop searching, and you still don't have your piece. Or, if three different parts of your program need the same piece, they might all send out separate searches, doing three times the work!

A smart design—which is what we have here—keeps *one* live search per key. It remembers who it asked. It only stops when the judge (the consumer) looks at the piece and gives the thumbs up.

---

## 2. What Problem Does This Solve?

At the edge of a distributed system, you frequently know *what* you need long before you know *who* has it. The resolver’s job is to carry that search across an unreliable network.

If you brute-force this, every timeout means you do the work again. Every invalid response looks like a success. `commonware-resolver` prevents this collapse by strictly dividing the labor into two separate steps:

1. **Fetch:** Find a candidate value.
2. **Validate:** Decide if that value is the truth.

This split isn't just a neat trick; it is the entire discipline of the crate. If the resolver tried to validate the data itself, it would blur the line between moving data around and deciding what is true. By keeping them separate, the edge stays sharp.

Look at the API:
- `Resolver` controls the searches (start, target, cancel).
- `Consumer` judges the bytes (`deliver`).
- `Producer` serves bytes to others (`produce`).

The crate doesn't own the truth. It just owns the *search* for the truth.

---

## 3. The Public Contract

Let's look at `resolver/src/lib.rs`. It's the smallest useful surface area you could ask for.

```rust
pub trait Consumer: Clone + Send + 'static {
    // ...
    fn deliver(&mut self, key: Self::Key, value: Self::Value) -> impl Future<Output = bool> + Send;
}
```

This is beautiful. The resolver never says, "Here is the good value." It says, "Here are some bytes I found." The `Consumer::deliver` method returns a `bool`. If it returns `true`, the consumer is happy, and the search stops. If it returns `false`, the consumer is saying, "This is garbage," and the resolver knows it has to keep looking (and block the guy who sent the garbage!).

Why does this matter? Because different applications have completely different ideas of what "truth" is. One app might just want anything that parses. Another might need a cryptographic signature. The resolver doesn't care. It leaves the thinking to the consumer.

The API also gives you control over *who* to ask:
- `fetch` says, "Ask anyone."
- `fetch_targeted` says, "Only ask these specific peers."

And a targeted search is a *hard promise*. The resolver won't suddenly decide to ask someone else just because your targets are being slow. It stays within the boundary you gave it.

---

## 4. The Fetcher as Memory

If you look in `resolver/src/p2p/fetcher.rs`, you'll find the `Fetcher` struct. This is the memory of the search.

At first glance, you might think, "Why is this so complicated? Just ask peers until one answers!" But let's look at what it actually has to remember:
- The next request ID to use.
- Which requests are actively waiting for a response.
- Which keys are pending a retry.
- Which peers are blocked for lying to us.
- The performance score of each peer, so we ask the fast ones first.
- Which keys have a strict target list.

Once you see this list, you realize the `Fetcher` isn't complicated; it's doing exactly the minimum amount of work necessary to keep a search alive in a hostile environment.

### 4.1 One Key, One Search

If you ask the resolver for the same key twice, it doesn't create two searches. It edits the existing one. If you spawn duplicate searches, you multiply the network traffic for no reason. The engine uses a map of `fetch_timers` to know if a search is already running. If it is, great! You just hitch a ride on the existing search.

### 4.2 Pending vs. Active Waiting

There are two ways a search can be "waiting":
- **Pending:** The request hasn't been sent yet, or we're waiting to try again.
- **Active:** We've actually fired the request over the network to a specific peer, and we are staring at the clock, waiting for them to reply.

The `Fetcher` exposes these two different deadlines: `get_pending_deadline()` and `get_active_deadline()`. This ensures we don't spam the network, but we also don't wait forever if a peer goes silent.

### 4.3 Request IDs: Tying the Answer to the Question

When you send a message over the wire, how do you know what question the answer belongs to? The network doesn't remember for you. 

```rust
pub type ID = u64;

struct ActiveRequest<P, Key> {
    key: Key,
    peer: P,
    start: SystemTime,
}
```

Every outbound request gets a unique `ID`. When the response comes back, it brings that `ID` with it. The resolver looks up the `ID` to figure out which `Key` we were asking for, and crucially, *which peer we asked*. If peer B answers a question we asked peer A, we throw it away!

The wire format itself is delightfully simple:
- `Request(key)`: "Do you have this?"
- `Response(bytes)`: "Yes, here it is."
- `Error`: "Nope, don't have it."

Notice that `Error` is its own thing. It's not a fake value. It's a clear signal that lets the resolver quickly retry somewhere else without confusing "I don't have it" with "Here is bad data."

---

## 5. Walk One Key Through the Engine

Let's trace a single key's journey to see how it all comes together.

**Step 1: You ask for a key.**
You call `Resolver::fetch(key)`. The engine records it. If it's a new key, it starts a timer and puts the key in the `Fetcher`'s pending queue. 

**Step 2: The Fetcher picks a peer.**
The `Fetcher` looks at the eligible peers, removes anyone who is blocked, removes *yourself* (because you shouldn't ask yourself for something you're trying to find on the network!), and sorts them by performance. It picks the best candidate.

**Step 3: The question goes out.**
The resolver fires off a `Request(key)` over the wire with a fresh `ID`. The key moves from "pending" to "active."

**Step 4: The network answers (or doesn't).**
- **If they send an `Error` (or timeout):** They didn't have it. The key goes back to the pending queue to try someone else. We don't block them; they just didn't have it.
- **If they send `Response(bytes)`:** The resolver hands the bytes to the `Consumer`.
  - If the consumer says `true` (it's good!): The search is over. The timer is canceled, the targets are cleared. Success!
  - If the consumer says `false` (it's garbage!): The resolver *blocks* that peer so they can't poison future searches, and puts the key back in the pending queue to try someone else.

Notice the profound difference there? An empty response means "keep looking." Bad data means "punish the peer, *then* keep looking."

---

## 6. The Engine Loop

If you open `resolver/src/p2p/engine.rs`, you'll see the heart of the beast. It's a single massive `select_loop!`.

Why one loop? Because it has to coordinate several different realities at the same time:
- Commands coming from the application (the mailbox).
- Updates to the list of connected peers.
- Deadlines for retries and timeouts.
- Network messages arriving from the outside world.

By putting it all in one loop, the engine avoids race conditions. It doesn't have to guess which state is the "real" one; it synchronizes them all in lockstep.

Here's the essence of how it handles an incoming network message:

```rust
match msg.payload {
    wire::Payload::Request(key) => self.handle_network_request(peer, msg.id, key),
    wire::Payload::Response(response) => {
        self.handle_network_response(peer, msg.id, response).await
    }
    wire::Payload::Error => self.handle_network_error_response(peer, msg.id),
};
```

It's incredibly clean. All the complexity of the distributed search is contained in the *state* (the `Fetcher`), not in deeply nested `if` statements.

---

## 7. What the Tests Prove

The tests aren't just there to make sure the code compiles; they are the executable proof of the resolver's promises. If you want to know what the resolver actually guarantees, read the test names in `resolver/src/p2p/mod.rs` and `resolver/src/p2p/fetcher.rs`:

- `test_peer_no_data`: Proves that if a peer says "I don't have it," we don't give up.
- `test_blocking_peer`: Proves that if a peer gives us bad data, they get blocked and we spill over to the next peer.
- `test_duplicate_fetch_request`: Proves we don't do double the network work if you ask for the same thing twice.
- `test_fetch_targeted_no_fallback`: Proves that a targeted search *really* means "only these targets," even if it means waiting forever.

If the documentation ever disagrees with these tests, the tests are right.

---

## 8. Failure Modes and Limits

Let's be honest about what the resolver *can't* do. It's not magic.

If nobody in the network has the data, the resolver can't invent it out of thin air. It will just keep trying (or waiting for targets) until you cancel it. 

It also can't tell if data is correct. That is solely the burden of the `Consumer`. If your consumer is lazy and accepts garbage, the resolver will happily stop searching and hand you garbage.

And if you use a targeted fetch, you have to know what you're doing. If you target a peer that is offline or just painfully slow, the resolver will patiently wait for them. It won't fall back to a broader search to save you. It does exactly what you told it to do.

---

## 9. Glossary

Let's review the vocabulary so you can read the code like a pro:

- **Fetch:** Asking the network to find a key.
- **Validate:** The consumer's job of looking at the bytes and deciding if they are the real deal.
- **Targeted fetch:** A strict constraint to only ask a specific set of peers. No fallbacks.
- **Pending request:** A key that is sitting around, waiting to be sent to a peer or retried.
- **Active request:** A key that has been shot over the wire, and we are staring at the clock waiting for a reply.
- **Blocked peer:** Someone who gave us bad data. They are dead to us.
- **Request ID:** The little tag we attach to a question so we know what the answer corresponds to.
- **Producer:** The local code that digs up data when someone else asks *us* for a key.
- **Consumer:** The local code that judges data when we fetch it.

Keep asking yourself this question as you read the source: *"What does the resolver know right now, what is it waiting to find out, and how is it making sure it doesn't do the same work twice?"* Keep that mental model, and the code will unfold for you perfectly.
