# commonware-log

## A Secret Log With a Public Commitment

Imagine you have a secret. You want to prove to everyone that you *had* this exact secret at a specific moment in time, but—and here is the trick—you absolutely refuse to tell them what the secret is! 

How in the world do you get a whole network of computers to agree on a secret they aren't allowed to see?

This example sits right at the fascinating intersection of two ideas that people often mix up: **secrecy** and **commitment**. 
- **Secrecy** is about *who* is allowed to know a value. 
- **Commitment** is about how everyone can agree that a value existed, in a specific order, without actually revealing it. 

To pull this off, we use a hash. A hash is one of the simplest, most beautiful commitment tools we have. It’s short, it’s stable, and it’s incredibly easy for anyone to verify.

There are three words we need to get straight before we go any further: **payload**, **digest**, and **transcript**.
1. The **payload** is your private message (the secret).
2. The **digest** is the public fingerprint of that message (the hash).
3. The **transcript** is the ordered, public record that the whole network agrees to preserve forever.

If you put the payload directly into the transcript, you're forcing the consensus protocol to carry around secret data it has no business knowing! But if you hide the payload *without* a commitment, nobody can agree on what happened. So, `commonware-log` takes the clever middle path: keep the secret local, and publish *only* the digest.

The tradeoff is simple but profound. Commitments give you public verifiability and a tiny, compact state, but they do *not* magically give you your secret back later. The application has to own the secret. Consensus just owns the order. And the persistence layer just makes sure the ordered commitment doesn't vanish if you turn the computer off.

---

## 1. What Problem Does This Actually Solve?

Now, you might think this chapter is just about hashing bytes. It’s not. It is really about figuring out **what belongs inside the protocol and what must stay outside of it**. 

`commonware-log` gives us a wonderfully clean answer: keep the payload private, publish only the commitment, and let the consensus algorithm order the commitments instead of the secrets themselves. Every turn, a participant cooks up a random 16-byte message, hashes it, and hands *only the digest* to consensus. The raw message never even touches the protocol!

Why does that matter? Well, if the application shoved the full, raw payload through consensus, the protocol would have to carry around secret data it doesn't need, it would have to know way too much about handling payloads, and the system would be exposed to a whole host of complexities. Here, the application is the boss of the secret. Consensus is just the boss of ordering the commitments.

---

## 2. The Mental Model: Envelopes and Receipts

Think of each proposal in the system as two separate objects.

The first object is a **sealed envelope**. That’s your private payload.
The second object is the **receipt**. That’s your public commitment (the hash).

You, the sender, keep the envelope. The network only ever sees the receipt. Everyone can perfectly agree on the receipt without ever opening your envelope. This is why we use a hash instead of the raw message! The hash is small, it never changes, and it’s a breeze to compare. Most importantly, it gives consensus exactly what it needs: a public fact that points to a private value without spilling the beans.

When the system boots up, it does something neat for the very first step (the genesis step). Before making any real proposals, the application hashes a fixed message—literally the string `b"commonware is neat"`—just to seed the protocol with a known starting point. After that, every single view is just another envelope, and another receipt.

If you want to remember how this example works, just remember this rule:
> **Consensus is the receipt book, not the post office.**

---

## 3. The Boundary (Where the Magic Happens)

The entire example balances on one incredibly important invariant:
**Consensus only needs the digest of the secret, never the secret itself.**

Let's look at how this is enforced in the code. The boundary between the application (which knows the secret) and consensus (which only knows the hash) is beautifully clear. The application owns the hasher, the random number generator, and the local log. It only exposes the digest to the consensus engine via a `Mailbox`.

There are three main pieces of code making this boundary work:

### `Application` (`examples/log/src/application/actor.rs`)
This is where the secrets are born. It runs an asynchronous loop, waiting for messages. When it's told to `Propose`, it generates a random 16-byte buffer, hashes it, logs the secret locally, and then sends *only* the digest back to consensus:

```rust
Message::Propose { response } => {
    // Generate a random message (secret to us)
    let mut msg = vec![0; 16];
    self.context.fill(&mut msg[..]);

    // Hash the message
    self.hasher.update(&msg);
    let digest = self.hasher.finalize();
    info!(msg = hex(&msg), payload = ?digest, "proposed");

    // Send digest to consensus
    let _ = response.send(digest);
}
```
Notice how `msg` stays right there in the application, and only `digest` goes through the channel!

### `Mailbox` (`examples/log/src/application/ingress.rs`)
This is the boundary guard. It implements the traits that consensus expects (like `Automaton` and `Relay`). When consensus says "Hey, it's your turn to propose," the Mailbox sends a message to the Application actor and waits for the digest. 

And here is the kicker—look at the `Relay` implementation:
```rust
impl<D: Digest> Re for Mailbox<D> {
    // ...
    async fn broadcast(&mut self, _: Self::Digest, _: Self::Plan) {
        // We don't broadcast our raw messages to other peers.
    }
}
```
The `broadcast` method is completely empty! It refuses to do it. The protocol cannot drift into transporting secrets because the application literally won't let it. We are agreeing on a public fact, not distributing private data.

### `Reporter` (`examples/log/src/application/reporter.rs`)
This file is the observer. It watches what consensus has decided and records it. It reports when a proposal is notarized (agreed upon by a quorum), finalized, or nullified. 

---

## 4. The Rhythm of the System

The system moves with a very simple rhythm, but the real lesson is in watching data cross that boundary.

If you look at `main.rs`, you'll see the system being wired together. It parses identities, configures the network, and sets up the storage directory. It’s not just a toy script; it’s a full distributed system!

Here is how the loop plays out:
1. Consensus asks the application for the genesis digest.
2. The application hashes `b"commonware is neat"` and hands back the result.
3. When it is a participant's turn, consensus asks for a new proposal.
4. The application generates 16 bytes of secret nonsense, hashes it, and gives consensus the digest.
5. Consensus runs its normal machinery—voting, ordering, and validating—on that digest.
6. The `Reporter` fires off events when the digest is notarized or finalized.
7. A GUI catches those events and renders them on your screen, letting you watch the heartbeat of the protocol.

There are two things you should slow down and appreciate here. First, the application doesn't hand consensus a message and ask, "Hey, figure out what to do with this." It hands consensus a *digest*. That keeps the protocol's surface area tiny and keeps the payload completely opaque. Second, the secret never crosses the boundary. A private value becomes a public fact by being hashed, not by being exposed.

---

## 5. Why the Example is So Small

You'll notice this example is deliberately narrow. That’s because its job is to teach you about boundaries, not to solve every problem in distributed systems.

- **Privacy:** It handles privacy by just... keeping the payload out of the protocol entirely!
- **Restarting:** It handles restarts cleanly because consensus state is dumped into `storage-dir`. If you kill the process and spin it back up, it picks up exactly where it left off instead of rewriting history.
- **Observability:** It separates the protocol from the presentation. The GUI and reporter are just lenses to look through; they don't change how the gears turn.

We also left out a lot of things on purpose. We aren't broadcasting raw messages. We aren't backfilling missing payloads if a node goes offline. We aren't dealing with multiple epochs. Those are complex problems that belong to other layers. By leaving them out, we keep the spotlight right where it belongs: on the commitment boundary.

---

## 6. Failure Modes and Limits

Let’s be honest about what this code *doesn’t* do.

It doesn't support multiple epochs. If you look at `Application::genesis`, it explicitly asserts that the epoch is zero. 

It doesn't verify parent links. In a real blockchain, you'd want to make sure block $N$ properly links back to block $N-1$. But here, we just want to prove we can agree on hashes, so we skip that complexity.

It doesn't try to be clever with the `verify` step. In `ingress.rs`, when consensus asks the application to verify a digest, the application just returns `true`. Why? Because consensus already did the cryptographic heavy lifting of verifying the signatures of the participants.

And finally, it makes absolutely zero promises about recovering your plaintext secret if your node forgets it. The digest is enough for the network to agree. It is *not* enough to reconstruct your secret! This is a commitment example, not a backup service.

---

## 7. How to Read the Source

If you want to read the code, read it like a map of a boundary. Start from the outside and work your way in.

1. **Start with `examples/log/src/main.rs`.**
   Look at the shape of the system. See how identities are parsed, how the network is wired, and where the application actually plugs into the simplex consensus engine.
2. **Next, check `examples/log/src/application/actor.rs`.**
   This is the core. This is where the application generates a secret, hashes it, and decides that the digest is the only thing worth sharing.
3. **Then read `examples/log/src/application/ingress.rs`.**
   This is the border crossing. Notice how consensus talks to the application, and pay special attention to the empty `broadcast` method. What the application refuses to do is just as important as what it does.
4. **After that, read `examples/log/src/application/reporter.rs`.**
   This will show you what the system considers worth observing (notarization, finalization).
5. **Finally, skim `examples/log/src/gui.rs`.**
   Treat it as a lens. It makes the protocol fun to watch, but it’s not the mechanism itself.

---

## 8. Glossary and Further Reading

- **Digest** - The public commitment (the hash) to the secret message.
- **Genesis** - The first agreed-upon digest that gets the whole story rolling.
- **Mailbox** - The boundary guard that translates consensus requests into messages the application actor understands.
- **Reporter** - The observer that takes internal consensus activity and turns it into readable logs.
- **Persistence** - The fact that our state is safely tucked away in `storage-dir` so we can resume after a crash.
- **Backfill** - Something we intentionally left out so you can focus on commitment instead of data retrieval!

**Further reading:**
- `examples/log/src/main.rs`
- `examples/log/src/application/actor.rs`
- `examples/log/src/application/ingress.rs`
- `examples/log/src/application/reporter.rs`
- `docs/commonware-book/consensus/chapter.md`