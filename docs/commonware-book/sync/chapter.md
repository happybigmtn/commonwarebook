# commonware-sync

## Chasing a Moving Proof-Backed Target

---

## Opening Apparatus

**Promise.** In this chapter, we're going to figure out how a client machine stays perfectly aligned with a remote database that just won't sit still. And we're not just going to blindly trust the server when it says "here's the new data." We want *proof*. We want evidence that the transition is correct.

**Crux.** You might think synchronization is just copying. Copying is easy! Synchronization is not copying. It is a repeated act of picking a target root, fetching just enough history to justify reaching it, verifying the proof, and then starting all over again because—guess what?—the target moved while you were doing all that!

**Primary invariant.** The client should only advance its state by operations and proofs that match one concrete, well-defined target. A root is only worth chasing if the path to get there is perfectly legible.

**Naive failure.** The easy story everyone tells themselves is: "I'll just dial the server, download what it has, and call it synced." That fails the exact moment the server keeps writing new data, or the network decides to reorder your messages, or the database changes what "current state" even means. 

**Reading map.**

- `examples/sync/src/databases/mod.rs` gives us the `Syncable` contract. It's the shared language.
- `examples/sync/src/net/wire.rs` boils down the network chatter to just two actual questions.
- `examples/sync/src/net/resolver.rs` and `io.rs` show how the client keeps its requests and responses straight.
- `examples/sync/src/bin/server.rs` shows how targets and proofs are served by a server that never stops moving.
- `examples/sync/src/bin/client.rs` shows the repeated, stubborn reconciliation loop.

**Assumption ledger.**

- You're comfortable with request/response protocols and asynchronous tasks. 
- You understand that a target root is cryptographically meaningful, even though our example lets the server announce it directly for simplicity.
- We're focusing on the *mechanism* of proof-backed synchronization here, not the plumbing of CLI flags.

---

## 1. Synchronization Before the Code

Let me explain something about synchronization. It sounds like copying, doesn't it? But copying is only the very last mile of the problem. The *real* problem is that the thing you are trying to copy keeps moving while you're trying to copy it. Imagine trying to paint a portrait of a dog that keeps running around the yard!

So, to solve this, the system has to answer three questions in order: 
1. What target do I want to reach? 
2. What evidence (or proof) gets me there? 
3. How do I know the target hasn't changed underneath me?

Let's get our vocabulary straight. A **root** is just a compact, cryptographic name for a specific state. An **operation** is one single step in the history that led to that state. A **proof** explains why a batch of operations is enough to justify the root. And **reconciliation** is the act of looking at your local view, looking at the remote view, and deciding what on earth to do next. 

The target isn't just "whatever is latest." "Latest" is a sloppy word. A target is a *concrete state* named by a root and supported by a proof.

The naive approach? Fetch everything, verify it once, and declare victory. But what if the source keeps appending data? What if the network scrambles the order? Another naive idea: just poll the server until it stops changing. But in a live system, it *never* stops changing! You'd be stuck in a loop forever, and you still wouldn't know which transitions were justified.

Here's the trick, the better trade-off: you sync in bounded pieces. You name one specific target, fetch only the proof-backed history you need to reach *that* target, verify it, and then repeat. It gives you a narrow protocol, predictable work, and a clean way to handle retries. The cost? Your client has to tolerate churn. You have to accept that the target will probably move again before your next round even begins.

---

## 2. The Mental Model: The Surveyor

The cleanest image I can give you is a surveyor trying to follow a boundary line that someone else keeps redrawing.

- The **server** is the person moving the boundary by appending new operations.
- The **target root** is the current line the client is desperately trying to reach.
- The **historical proof** is the mathematical record showing exactly how the old line connects to the new one.
- The **client** is our surveyor. The surveyor doesn't just run to the new line; they check every single segment before stepping forward.
- The **resolver** is the messenger running back and forth with questions and answers.

The surveyor doesn't trust a new line just because it looks convenient. The surveyor demands *evidence* that the line makes sense. That's why the server doesn't just serve the target; it serves the operations needed to reach it, along with the proof. The client only takes a step forward when the proof and the target perfectly agree.

Now, the "database flavor" is just the terrain the surveyor is walking on:
- `any` is flat ground: a direct operations log and a direct root.
- `current` is trickier: it shows the same operations, but rebuilds a view of the "current state" after the sync.
- `immutable` is a log-oriented database where retained operations stay active.

Different terrain, same exact lesson: follow the target, verify the proof, reconcile the state.

---

## 3. The Core Ideas in the Code

### 3.1 `Syncable` Is the Shared Contract

If you open up `examples/sync/src/databases/mod.rs`, you'll find a trait called `Syncable`. This is the absolute center of the example.

It requires any database to be able to do a few specific things:
- create deterministic test operations,
- accept operations in batches,
- report its root,
- report its current size and inactivity floor,
- produce historical proofs,
- and provide pinned nodes for the sync engine.

Why is this beautiful? Because it's the ultimate abstraction boundary. It says the sync loop doesn't care at all how the database stores bytes internally. It only cares about one sharp question: 

> *Can this database name a target, justify the path to it, and apply the operations needed to get there?*

As long as it can do that, the sync loop is happy.

### 3.2 The Wire Protocol Only Asks Two Real Questions

When the client connects, you might expect a sprawling, complicated API. But if you look at `examples/sync/src/net/wire.rs`, you'll see the protocol only really exposes two main questions.

Question One:
> "What target should I be chasing right now?"

That's the `GetSyncTargetRequest` and its response. The server answers with a `Target<D>`, which is a root plus a non-empty range of valid history.

Question Two:
> "Starting from where I am right now, give me the next proof-backed segment toward that target."

That's `GetOperationsRequest`. The request carries exactly what it needs: a `request_id`, the boundary it's syncing toward (`op_count`), where it wants to start (`start_loc`), how many operations it can handle (`max_ops`), and whether it needs `pinned_nodes`.

The response gives the client exactly the material needed to keep going: the `request_id`, a historical `Proof<D>`, the batch of operations, and any requested pinned nodes. 

It's not "send me your entire database." It's "name the line, and give me the next justified segment." It's elegant.

### 3.3 Request IDs Are the Memory of the Conversation

You look at `request_id` in `examples/sync/src/net/wire.rs` and you might think, "Oh, that's just a sequence number, standard bookkeeping." No! It's the memory of the conversation!

Over a network, things get chaotic. The client might have multiple requests flying around. A response arrives late. A target update races past an operations reply. The resolver never asks, "Did I receive a response?" It asks, "Did I receive the response for *this specific question*?"

That is why both success and error messages carry the `request_id`. It prevents the chaotic network transport from completely scrambling the logical meaning of the conversation. 

### 3.4 The Narrow Trust Boundary of the Resolver

Look at `examples/sync/src/net/resolver.rs`. It's deliberately boring. It doesn't verify storage proofs, it doesn't interpret operations, and it doesn't philosophize about whether the server is a good person.

It does a very narrow, reliable job:
- allocate a fresh request ID,
- send one typed wire message,
- wait for one typed reply,
- reject anything that doesn't match,
- and hand the clean result to the sync engine.

This is exactly how you want it. The transport layer shouldn't have opinions about synchronization. It just moves the evidence.

### 3.5 The I/O Loop Stays Cancellation-Safe

There's a subtle but wonderful lesson in `examples/sync/src/net/io.rs`. 

At first, it just looks like plumbing. But look closer. The `recv_frame` function is not cancellation-safe. If an asynchronous `select!` macro dropped it halfway through reading a frame from the network, your stream would be corrupted with half-read garbage.

So, what do they do? They spawn a dedicated `recv_loop` task whose *only* job is to read complete frames and forward them over an internal channel. It is never cancelled in the middle of a frame. The main loop then safely uses `select!` on the internal channels. 

Cancellation in async Rust isn't free. You have to respect the transport semantics!

---

## 4. How the System Moves

### 4.1 The Server Manufactures Moving Targets

In `examples/sync/src/bin/server.rs`, the server initializes a database and then does something crucial: it keeps adding new operations on a timer. 

`maybe_add_operations` checks if enough time has passed, generates new deterministic operations, appends them, and changes the root. 

The server is intentionally unstable! It's always serving from a moving frontier. This isn't a bug; this is the exact condition the client is being designed to survive.

### 4.2 Naming a Target Means Root + Range

When the client asks for the target, `handle_get_sync_target` doesn't just hand over a root hash. It reads the `root`, the `inactivity_floor`, and the `size`, and hands back a `Target` that includes the root *and* the range of history.

Why? Because synchronization isn't just matching a hash. The range tells the client how much history is actually relevant to this new claim. If the target was just a digest, you could be staring at it all day without knowing where to start digging.

### 4.3 The Bounded Proof Ladder

The most interesting path on the server is `handle_get_operations`. 

The server validates the request, but then it does something smart: it clamps the requested `max_ops` by its own `MAX_BATCH_SIZE`. The client can ask for a million operations, but the server says, "No, we're doing this in manageable chunks."

This means batching is jointly owned. It keeps the protocol readable under pressure and prevents a single massive request from blowing up the server's memory. Then it grabs the `historical_proof` and sends it back. 

### 4.4 The Client's Two-Loop Dance

If you want to understand the client in `examples/sync/src/bin/client.rs`, look at the two loops.

The first is the **target update loop** (`target_update_task`). It wakes up, asks the server for the latest target, and checks if the root changed. If it did, it shoves the new target down a bounded channel to the sync engine.

The second is the **sync iteration loop** (like `run_any`). Every iteration:
1. Opens a fresh connection.
2. Gets the current target.
3. Spawns that target update loop in the background.
4. Runs the sync engine (`sync::sync`), pulling batches and verifying proofs.
5. Logs the new root when it catches up.
6. Kills the update task, sleeps, and does it all over again.

Why restart? Because recovering from a previous state is a fundamental part of synchronization! A robust client should always be able to wake up, figure out the new boundary, and pick up right where it left off.

### 4.5 Re-Anchoring: The Real Lesson

The real magic happens when the target update task notices the server's root has changed *while the client is still downloading*. 

The client doesn't throw its hands up and throw away all its work. It feeds the new target into the sync engine, and the engine seamlessly reconciles against the fresher boundary. The work you just did still matters, but the definition of "done" just shifted.

That is the absolute core of the lesson here: 

> In a live system, "up to date" is only a temporary, fleeting name for the current proof-backed boundary.

---

## 5. Database Semantics: Different Terrains

We have three flavors, and you shouldn't think of them as the same thing under the hood.

**`any`** is the clean baseline. The synced root is the direct database root, and the proof is the direct operations proof. It's the easiest to understand.

**`current`** is incredibly clever. The canonical state of a "current" database includes bitmaps and grafted structures to track what is active. But the sync engine doesn't chase that canonical root! It chases the `ops_root()`. Why? Because the network provides proofs about the *operations history*. The client syncs the raw operations first, verifies the proof, and *then* locally rebuilds the complex canonical state deterministically. It teaches you that the application root isn't always the right network proof root.

**`immutable`** changes what "activity" means. Retained operations just stay active, so the inactivity floor is essentially just the pruning boundary. The proof story is the same, but the state semantics are different. 

The shared `Syncable` trait makes them all work through the exact same sync machinery!

---

## 6. What Pressure It Is Designed To Absorb

You don't build a system like this for sunny days. You build it for pressure:

- **Continuous Writes:** The server appends operations while the client is working. The target is *expected* to move.
- **Verification Pressure:** The client trusts nothing. It fetches proofs and forces the sync engine to verify the math before advancing.
- **Reconnection Pressure:** The loop intentionally restarts, proving that picking up from an old state is natural and safe.
- **Bounded Work:** `MAX_BATCH_SIZE` and `max_outstanding_requests` ensure the system doesn't drown in a flood of bytes.
- **Transport Disorder:** Request IDs and strict typing keep the conversation sane even when the network starts shuffling messages like a deck of cards.

---

## 7. Failure Modes and Limits

Let's be honest about what this example does *not* do. 

It doesn't authenticate the server. In a real production system, you'd want a secure, authenticated channel. It also doesn't source the target from a decentralized consensus mechanism; it just asks the server "what's the target?", which is great for a tutorial but requires more trust than a true trustless network.

And there is no rate limiting for target updates. If you deploy this exactly as-is to the open internet, someone will probably spam your server.

But remember the scope of the lesson: 

> This example shows you how to follow a moving target with mathematical proof, not how to decide what the target should be in the first place.

---

## 8. How To Read The Source

If you want to read the code, don't just jump in randomly. Read it as a sequence of boundaries:

1. **`examples/sync/src/databases/mod.rs`**: Start with the `Syncable` trait. Understand the contract.
2. **`examples/sync/src/net/wire.rs` & `request_id.rs`**: See the two narrow questions and the memory of the conversation.
3. **`examples/sync/src/net/io.rs` & `resolver.rs`**: Look at the transport boundary and how it handles cancellation safely.
4. **`examples/sync/src/databases/any.rs`, `current.rs`, & `immutable.rs`**: Compare the three terrains.
5. **`examples/sync/src/bin/server.rs`**: Watch the server manufacture its moving targets.
6. **`examples/sync/src/bin/client.rs`**: Finally, watch the client stubbornly chase the target down.

Read it that way, and it won't look like two separate programs. It will look like one beautiful, proof-backed reconciliation system.

---

## 9. Glossary

- **Target**: The root and the range of history the client is currently trying to reach.
- **Proof**: The mathematical evidence connecting the current state to the operations that justify it.
- **Reconciliation**: The stubborn work of fetching, verifying, and re-anchoring until local state matches the remote proof.
- **Inactivity floor**: The boundary below which operations are considered dead for a specific database flavor.
- **Pinned nodes**: Extra MMR anchors needed to verify a historical segment at a specific point.
- **Resolver**: The client's transport bridge. It turns typed wire messages into clean sync requests.
- **Request ID**: The memory token that attaches a chaotic wire reply to a specific logical question.
- **Syncable**: The shared contract that makes `any`, `current`, and `immutable` all speak the same language.
