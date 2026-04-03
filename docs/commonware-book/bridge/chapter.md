# commonware-bridge

*A customs desk for finality certificates: moving evidence across trust boundaries without moving trust.*

---

## What are we actually doing here?

I want to show you how `commonware-bridge` moves a finality certificate from one network into another. Now, the trick here is that we have to do this *without* pretending that the second network suddenly trusts the first one.

You hear the word "bridge" in crypto all the time, and you might think it's a pipe. It sounds like a pipe, right? Information flows from A to B. But **a bridge is not a pipe**. If you just build a pipe, you're going to have a bad time. Instead, a bridge is a *policy* for moving evidence across a boundary while keeping verification strictly local at every step that matters.

**The big rule:** A foreign certificate is *never* used until the local validator has re-verified it against the foreign network's public identity. And here's the other part of the rule—a block digest is *never* handed over to local consensus before the indexer has securely stored the block it names. 

**The naive mistake:** The easiest mistake to make is to just copy bytes across the boundary, throw them into the receiving chain, and hope the receiving side treats them as truth. But if you do that, you've just collapsed trust, storage, and consensus into one big, messy blob. Our bridge keeps them completely separate.

Here's how we're going to break it down:
1. We'll name the actual problem.
2. We'll set up a mental model so you can see it in your mind's eye.
3. We'll look at how the pieces fit together—the validator, the application, the indexer, and the consensus engine.
4. We'll look at the indexer, and why it's a storage boundary, not an oracle.
5. We'll walk through the two loops: local consensus and cross-network evidence.
6. We'll talk about the golden rule: publish *before* you propose.
7. We'll look at what pressures this design absorbs.
8. We'll be honest about its limits.
9. And finally, I'll tell you how to read the source code in the right order.

---

## 1. What Problem Does This Actually Solve?

Imagine two networks that need to exchange information. But they don't share trust. That's the whole problem right there.

If Network A says, "Hey, I finalized this block," Network B can't just say, "Oh, okay, I believe you" just because some peer delivered a message. Network B needs *proof*. It needs proof that can be checked against Network A's public identity, and it needs a way to fetch that proof later when its own consensus engine is ready to make a proposal.

That is why this example is not a gossip bus or a dumb pipe. It is a bridge in the strict sense: a system for carrying evidence across a boundary and then mathematically re-checking that evidence on the other side.

In our code, the payload we choose is a succinct finality certificate. Why? Because it's small enough to move cheaply, and strong enough to act as real, portable evidence. 

Once you decide to just move certificates, the rest of the design naturally falls out:
- The producing network finalizes locally.
- An "indexer" remembers the latest evidence for each network.
- The receiving network fetches that evidence when it wants to bridge.
- Local validators reject foreign evidence until it mathematically verifies under the foreign network's identity.

By doing this, we keep three very important jobs distinct: producing finality, storing evidence so it can be found again, and deciding whether the local chain should actually care about it.

---

## 2. The Customs Desk Mental Model

To see what's going on, picture a customs desk sitting on the border between two cities.

Each city has its own internal processes. When they finish a process, they stamp a receipt. Now, the customs desk doesn't invent receipts, and it doesn't decide what the receipts mean. It just files them, labels them by city, and hands them back later when someone asks, "Hey, what's the latest receipt from City A?"

Now imagine a traveler from City A walks into City B carrying City A's receipt. City B doesn't look at the receipt and say, "Well, a receipt arrived, so it must be true!" No, City B takes out its ledger, checks the stamp against City A's known public identity, and *only then* lets the receipt influence its own local business.

That is the bridge in one sentence:

> **Move proof, not belief.**

If we map our metaphor to the code:
- The **receipt** is the finalization certificate.
- The **customs desk** is the Indexer.
- The **traveler** is the application logic inside the validator.

This mental model shows you that there are really *two separate loops* running at the same time: a local consensus loop for the validator's own chain, and a cross-network evidence loop moving certificates through the indexer. 

---

## 3. The Composition Stack: How the Pieces Fit

If you look at `examples/bridge/src/lib.rs`, you'll see we define some namespaces right up front: `APPLICATION_NAMESPACE`, `P2P_SUFFIX`, `CONSENSUS_SUFFIX`, and `INDEXER_NAMESPACE`. These aren't just decorative labels. They are physical boundary markers on the wire. A bridge only works if the local network, the peer-to-peer fabric, the consensus engine, and the indexer all operate in their own sliced-up spaces.

### 3.1 The Validator is the Boss

Open up `examples/bridge/src/bin/validator.rs`. This is where the magic comes together. 

The validator process isn't just "consensus plus some IO." It is the policy host. It wires together:
- Authenticated peer-to-peer networking.
- Encrypted stream transport to talk to the indexer.
- The simplex consensus engine.
- Durable storage.
- And the *application actor* that makes the bridging decisions.

We keep these separate for a very good reason. If you jammed the bridge logic inside the consensus engine, you wouldn't be teaching composition anymore—you'd be teaching hidden coupling!

### 3.2 The Application is the Brains

Look in `examples/bridge/src/application/actor.rs`. This is where the bridge policy lives. The actor decides:
1. Do I propose local random data, or do I propose foreign evidence?
2. Is this foreign certificate actually valid?
3. When should I post my own local finality back to the indexer?

Notice what the actor *doesn't* do: it doesn't run consensus. It just sits at a mailbox (defined in `ingress.rs`) and answers questions when consensus asks for a `genesis`, a `propose`, a `verify`, or a `report`. Consensus is totally blind to *why* the application chose a payload. It just asks and receives.

### 3.3 The Block Type: A Clean Fork in the Road

One of my favorite parts is in `examples/bridge/src/types/block.rs`. We define the payload shape like this:

```rust
pub enum BlockFormat<D: Digest> {
    Random(u128),
    Bridge(Finalization<Scheme, D>),
}
```

This is beautiful! A block is exactly one of two things: it is either local noise (`Random`) to keep the consensus loop moving, or it is a piece of foreign evidence (`Bridge`) that has already survived verification somewhere else. We didn't have to write a special consensus engine for this. We just gave consensus a type that makes the distinction physically explicit. The `enum` in Rust guarantees that we handle both cases everywhere we process a block.

---

## 4. The Indexer is a Boundary, Not an Oracle

Let's look at `examples/bridge/src/bin/indexer.rs`. The indexer is not an oracle of truth. It's just a storage boundary with a tiny bit of verification logic.

It understands four basic messages (`inbound.rs` and `outbound.rs`):
- `PutBlock` and `GetBlock`
- `PutFinalization` and `GetFinalization`

Why this split? Because we're storing two very different kinds of things on two different shelves:
- **Blocks** are keyed by their digest. Validators might want to fetch a specific block again.
- **Finalizations** are a moving frontier. We only care about the *latest* one for a given network, so they are keyed by view.

When the indexer receives a finality certificate, it checks it against the public identity of the network it claims to be from. So the indexer's shelf only holds evidence that passed a basic verification bar. 

But—and this is crucial—the shelf is *still not authority*. It's just an archive. It remembers what was posted and serves the latest evidence. If the indexer vanished, the validators would just lose discoverability. If the indexer was compromised and lied, the validators would still mathematically reject the lie locally. The indexer doesn't tell the validator what to believe.

---

## 5. Two Loops, One Timeline

To really understand the physical execution, you have to look at the two loops running side by side.

### The Local Consensus Loop
This is the loop making the validator a validator.
1. Consensus asks the application for a proposal.
2. The application picks a payload and hashes it.
3. The application publishes the block payload to the indexer.
4. **Only after** the indexer says "I got it", does the application hand the digest back to consensus.
5. Consensus verifies the block by asking the indexer for the payload.
6. Consensus reports a finalization.
7. The application takes that finalization and posts it *back* to the indexer so the other network can see it.

### The Cross-Network Evidence Loop
This is the bridge loop. It happens when a validator wants to pull foreign proof into its chain.
1. The application asks the indexer, "What's the latest finalization from the other network?"
2. The indexer hands over the certificate.
3. The application verifies it against the foreign network's identity. If it fails, the loop stops.
4. If it succeeds, the application wraps it up as a `BlockFormat::Bridge`.
5. The application publishes this block to the indexer.
6. The digest goes to consensus.

The lesson here is that the two loops touch—they read and write to the same indexer—but they *never merge*. The local chain stays local. The foreign proof stays foreign until it's mathematically proven and wrapped up as a local payload.

---

## 6. The Golden Rule: Publish Before You Propose

There is a subtlety in `examples/bridge/src/application/actor.rs` that is the most important rule in the whole design:

> **Publish the block to the indexer BEFORE you give its digest to consensus.**

Why? Think about what happens if you don't do this. If you give consensus the digest first, the local chain might commit to a payload that isn't actually discoverable anywhere! You'd have a stable handle pointing to a ghost.

So, the application hashes the block, sends it to the indexer, waits for the indexer to say `Outbound::Success(true)`, and *only then* returns the digest to consensus. 

The reverse direction has the exact same shape: when the local chain finalizes, the application waits for the `Report` message from consensus, and *then* posts the finality to the indexer. It's consistent: evidence has to physically exist on the shelf before you can point to it, and finality has to be real before you advertise it.

---

## 7. Pressures the Design Absorbs

This design is robust because it anticipates the messy realities of operating a network.

- **Partial Availability:** What if the indexer doesn't have any foreign finalizations yet? No problem! The application just keeps proposing `BlockFormat::Random`. The bridge doesn't freeze the local consensus loop waiting for evidence that isn't there.
- **Verification Pressure:** The receiving network never relies on the indexer's word. The foreign certificates are checked locally, cryptographically, before they ever touch the local chain.
- **Separation Pressure:** The namespaces and the component isolation (`application`, `consensus`, `indexer`) mean that traffic doesn't bleed across protocols. The two networks stay entirely distinct. 

---

## 8. Failure Modes and Limits Let's Be Honest

We shouldn't overclaim what this example does. Let's be honest about its limits:
- If the indexer is totally unreachable, validators can't fetch or publish evidence. The bridge halts, though local consensus might spin on random blocks.
- If the foreign network hasn't finalized anything, there's nothing to bridge.
- The indexer only stores the *latest* finalization per network. It's not a complete archival node. It only answers the question: "What is the most recent proof I can use right now?"
- This is an *example*. If you want a completely trustless, decentralized cross-chain routing protocol, you'll need more than a simple shared indexer. But this example gives you the clean composition pattern that sits at the core of that larger problem.

---

## 9. How to Read the Source Code

If you want to read the code and see it clearly, follow this chain of responsibilities:

1. Start with `examples/bridge/src/lib.rs`. Look at the namespaces. See how we slice up the wire.
2. Next, look at `examples/bridge/src/types/block.rs`. This is the fork in the road. A block is either local data or bridged evidence. It's that simple.
3. Check out `examples/bridge/src/types/inbound.rs` and `outbound.rs`. This is the contract with the indexer. This is what you're allowed to ask it to do.
4. Glance at `examples/bridge/src/application/ingress.rs`. This is the mailbox. It's the narrow seam that keeps the consensus engine totally blind to the bridge logic.
5. Then, dive into `examples/bridge/src/application/actor.rs`. This is the brain! Look at the `Propose` arm. See how it chooses between random data and a bridge payload. See how it verifies the certificate. Notice the "publish before propose" ordering!
6. Read `examples/bridge/src/bin/indexer.rs` to see the storage boundary made real. It holds evidence without becoming an authority.
7. Finally, end with `examples/bridge/src/bin/validator.rs`. This is the composition root. It wires up the network, the storage, the consensus, and the actor into a single running process.

If you read the files in that order, the whole picture snaps into focus: evidence is discovered out in the world, verified locally, and only *then* turned into payload.
