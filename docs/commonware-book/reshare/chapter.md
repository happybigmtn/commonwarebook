# commonware-reshare

*How a committee passes trust forward without pretending the world stood still.*

---

## The Succession Problem

Imagine you have a secret—say, the combination to a very important safe. Now, you don't want to trust just one guy with it, because he might lose it, or worse, turn rogue. So, you split the combination into pieces using threshold cryptography. You hand these pieces out to a committee. Now, the safe only opens if a certain number of them—a *threshold*—turn their keys at the same time.

That's wonderful. You’ve bought fault tolerance! But here comes the rub: the real world doesn't stand still. People get tired, validators crash, or they just want to leave the committee. New people want to join. If your secret is mathematically bolted to that original, exact group of people, eventually enough of them will leave, and your safe is locked forever.

Now, you have two naive ways to fix this.
1. **The "Start Over" approach:** Every time someone leaves or joins, you throw away the old secret and run a brand new Distributed Key Generation (DKG) ceremony from scratch. This is simple, but it is slow, expensive, and a huge pain in the neck.
2. **The "Never Change" approach:** You just keep the same committee forever. You stick your fingers in your ears and ignore the churn. Eventually, the system breaks.

There's a much more subtle, dangerous failure too: trying to hand-copy the secret shares to the new committee without a rigorous rulebook. If a computer crashes halfway through copying it over, the next committee wakes up with a story that's *almost* right, but mathematically broken. 

What we really want is **continuity**. We want to take the collective secret and gracefully "reshare" it to the new committee, without ever bringing the whole secret together in one place, and without making everyone start from scratch. 

That is exactly what `commonware-reshare` is about. It's not a tutorial on the math of DKG. It's a lecture on **succession**. How does a changing committee inherit a secret without dropping the baton?

---

## 1. The Relay Race: A Mental Model

To understand the protocol, picture a relay race taking place on the pages of an indestructible notebook.

Each lap of the race is an **epoch**. An epoch is just a window of time where one specific committee is in charge. 
- The **baton** is the threshold secret. 
- The **notebook** is our durable storage (`examples/reshare/src/dkg/state.rs`). 
- The **runners** are the committee members. Notice they overlap! The guys finishing the last lap pass the baton to the guys running the next one.
- The **official** with the stopwatch is the orchestrator, who blows the whistle and says, "Lap's over! Next lap begins!"

There are two distinct clocks ticking in this system:
1. **The Chain Clock:** This is consensus. It decides when an epoch officially begins and ends.
2. **The DKG Clock:** This decides what must be written in the notebook across that boundary, so the new runners know exactly what's going on.

The chain governs *when* trust moves. The DKG state governs *how* the next committee can continue without guessing.

---

## 2. The Core Ideas (and How the Code Actually Does It)

### 2.1 The Epoch Boundary is the Law

In our code, we use something called `BLOCKS_PER_EPOCH`. You might look at that and think, "Oh, that's just a scheduling knob." No! That is the ironclad rule that tells the protocol when a committee's authority begins and ends.

While the epoch is open, the committee is chattering. They're passing share fragments around, acknowledging them, gathering evidence. But it's just chatter. When the last block of the epoch arrives, the music stops. The actor stops treating the round as an open conversation, looks at the evidence gathered, and carves the outcome into stone.

### 2.2 Dealers and Players: It's a State Machine!

If you look in `examples/reshare/src/dkg/actor.rs`, you'll see we handle `Message::Dealer` and `Message::Ack`. 

Inside a single epoch, a node might be a **dealer** (someone sending out share material) and a **player** (someone receiving it). But don't just think of these as labels. Think of them as **state machines**.

The dealer starts with the secret from the last epoch. They figure out what pieces to send, and they wait for acks. If the power goes out and the node restarts, the dealer has to wake up, read the notebook, and resume exactly where they left off. 

The player listens for these dealer messages, verifies them, and sends back an acknowledgment (`PlayerAck`). 

Here is the grand, unbreakable rule of this state machine: **Once you have committed to a dealer message or an acknowledgment, you must make the exact same choice after a restart.** You cannot change your mind, because if you do, the math falls apart. 

### 2.3 Protocol Memory (The Unglamorous Hero)

Let's talk about `examples/reshare/src/dkg/state.rs`. This is the notebook. This is the unglamorous plumbing that lets the system survive reality.

A computer can crash at any millisecond. A dealer might send a share, but crash before writing down that the player acknowledged it. A player might acknowledge a share, but the network drops it. 

To fix this, the storage layer uses an append-only journal. It meticulously records:
- `Event::Dealing`: A message we received and committed to ack.
- `Event::Ack`: A player's ack that we (as a dealer) received.
- `Event::Log`: A finalized dealer log.

When a node restarts, it doesn't just guess what happened. It replays this entire journal back into its in-memory cache (`EpochCache`). It literally rebuilds the past so it can resume the cryptographic commitments without accidentally inventing new ones. 

The profound lesson here is: **any change that alters a cryptographic commitment must be recoverable after a restart.** 

### 2.4 The Continuity Pipeline

The system isn't just one big loop. It's a stack of responsibilities, clearly visible in `examples/reshare/src/engine.rs`:

1. **The DKG Actor** (`dkg::Actor`): Does the heavy cryptographic lifting. It decides what the resharing evidence means.
2. **The Consensus Engine** (`Application` in `application/core.rs`): It just orders blocks. Notice how thin it is! When it wants to propose a block, it just taps the DKG actor on the shoulder and asks, "Hey, got a result for me?" It doesn't do the math itself.
3. **The Orchestrator**: The referee. It starts a fresh consensus engine for the new epoch and strictly kills the old one only when the boundary is safe.
4. **The Marshal**: The courier. If a peer is ahead, the marshal fetches the missing history so nobody relies on rumors.

Consensus sees a block. The resharing protocol sees a boundary. They work together, but they mind their own business.

---

## 3. The Full Epoch Timeline: Start to Finish

Let's follow one complete lap of the race.

1. **Setup:** You start the validator. It wires up the network, the storage, and the DKG actor.
2. **Waking Up (`state.rs`):** The DKG actor reads the notebook. If it's a new epoch, it seeds the random number generator. It looks at the *previous* output and says, "Ah, the players from last time? You are the dealers this time." This is how continuity works! Trust is inherited.
3. **The Chatter (`actor.rs`):** Dealers deal (`DealerPubMsg`, `DealerPrivMsg`). Players ack (`PlayerAck`). The notebook (`Storage`) furiously scribbles everything down in the append-only journal.
4. **Finalizing Early:** If a dealer gets enough acks early, they finalize right then and there. We don't wait for the epoch to end to figure out our outcome; we just wait for the epoch to end to *commit* to it. 
5. **The Boundary Block:** The last block of the epoch arrives. The whistle blows!
   - We compute the final result.
   - We write the *next* epoch's starting state into the durable notebook.
   - We acknowledge the finalized block.
   - We tell the orchestrator, "Epoch complete!"
   
   *Notice the order!* We write down the future *before* we tell the outside world we succeeded. That prevents a crash from causing public success but private amnesia.

---

## 4. How the Race Begins (Bootstrap Modes)

How do you start Epoch 0? We have three ways:

- **Trusted Bootstrap:** A trusted dealer just hands out the initial shares. Simple. 
- **DKG Bootstrap:** The participants run a full ceremony from scratch just for Epoch 0. 
- **Resharing Epoch:** This is what happens forever after. Epoch $N$ takes the output of Epoch $N-1$ and hands it forward. 

No matter how you start, once the engine is running, the protocol is purely doing resharing. 

---

## 5. What Kind of Punishment Can This Take?

This code is built to survive the unfairness of distributed networks. 

- **Crashes?** Handled. The journal records the exact messages that matter, and replay rebuilds the state.
- **Duplicate messages?** Handled. The handlers in `actor.rs` are idempotent. If you tell them twice, they just shrug and give you the same answer.
- **Network Lag?** Handled. Share distribution stays open for the entire early part of the epoch.
- **Committee Churn?** Handled. The new committee is mathematically drawn from the old one.

The protocol makes a conscious trade-off: it prefers **durable replay** over speculative optimism. When you are handing off a secret key that controls the system, you do not try to be clever or overly optimistic. You write things down, and you verify them.

---

## 6. Your Reading Assignment (How to Read the Source)

If you want to see this in action, don't just open files at random. Read them as a story of responsibility:

1. `examples/reshare/src/engine.rs`: Start here. Watch how the validator becomes a single continuity pipeline.
2. `examples/reshare/src/dkg/state.rs`: Look at the notebook. See what survives a crash (`Event::Dealing`, `Event::Ack`).
3. `examples/reshare/src/dkg/actor.rs`: Watch the state machines. See how dealers and players turn the persisted notebook into live protocol action.
4. `examples/reshare/src/orchestrator/actor.rs`: See how the whistle is blown and epochs begin and end.
5. `examples/reshare/src/application/core.rs`: Look at how wonderfully thin consensus is kept. It just asks DKG for the outcome.
6. `examples/reshare/src/setup.rs`: Finally, see how the whole thing boots up.

Read it in that order, and you'll see a beautiful machine keeping a secret alive across time, without ever dropping the baton.

---

## Glossary

- **Epoch** - A bounded lap of time for consensus and resharing.
- **Dealer** - Someone handing out share material this round.
- **Player** - Someone catching share material and acknowledging it.
- **Output** - The public result of the DKG round.
- **Share** - The private piece of the secret. *Guard this with your life.*
- **Boundary finalization** - The whistle blow. The finalized block that ends one lap and starts the next.
- **Committee continuity** - The whole point of the chapter: inheriting a secret instead of inventing a new one.
