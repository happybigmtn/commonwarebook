# commonware-collector

*A lesson in commitment-keyed coordination: asking many peers the same question, counting only the replies that belong, and making cancellation a clean act of forgetting.*

---

## 1. What Are We Actually Trying to Do?

If you want to build a distributed system, you quickly run into a very simple, very annoying problem. You need to ask a bunch of people a question, and you need to gather their answers. 

Sounds easy, right? But nature doesn't guarantee your message arrives. It doesn't guarantee the other guy's answer arrives. It might arrive twice. It might arrive late. It might arrive after you've already changed your mind and don't care about the answer anymore.

When you send a request to many peers, you have to answer a few basic questions:
- *Who did I actually ask?*
- *Which answers belong to which questions?*
- *Did this guy already answer me?*
- *What happens if I cancel the request, but answers are still in the mail?*

If every part of your system tries to solve this from scratch, you'll end up with a tangled mess of timeouts, counters, and boolean flags. `commonware-collector` solves this one specific problem. It takes a request, routes it to peers, and collects the replies—but *only* if they belong to that request, and *only* if they come from peers you actually asked.

The beauty here is the boundary. The collector doesn't look at the *meaning* of the answer. It just checks the envelope to see if it belongs in the right file folder.

---

## 2. The Mental Model: The Clerk and the Case File

To understand how the collector works, don't think about networks or packets. Picture a busy courtroom clerk. 

When you want to ask a network a question, you go to the clerk and open a "case". Every case has a unique ID—we call it a **commitment**. 

The clerk writes down this commitment in a ledger, along with two lists:
1. The people you sent the question to.
2. The people who have answered so far (initially empty).

That's it. That's the whole trick! Everything else follows from those two lists.

When an answer comes in, the clerk looks at the commitment on the envelope. 
- "Do I have an open case for this?" If no, throw it in the trash. 
- "Did we ask this person?" If no, throw it in the trash.
- "Has this person already answered?" If yes, throw it in the trash.

If it passes all three checks, the clerk files the answer and marks the person off the list. 

And what if you want to cancel the request? You just tell the clerk to close the case file. The clerk erases the entry from the ledger. Any answers that arrive late will just be thrown away, because the case no longer exists. *Cancellation is just an act of forgetting.*

---

## 3. The Core Ideas: Three Narrow Roles

If you look in `collector/src/lib.rs`, you'll see the system is split into three traits. We split it up so each piece has a very narrow, easy-to-understand job.

### The Originator (Starting Work)
The `Originator` is how you send requests and cancel them. 

```rust
pub trait Originator: Clone + Send + 'static {
    type Request: Committable + Digestible + Codec;
    
    // Send a request to a list of peers.
    fn send(&mut self, recipients: Recipients<Self::PublicKey>, request: Self::Request) -> ...;
    
    // Forget about a request.
    fn cancel(&mut self, commitment: <Self::Request as Committable>::Commitment) -> ...;
}
```
Notice that `Request` has to be `Committable` and `Codec`. It needs to be something we can send over a wire (`Codec`), and it needs to have a unique identifier—the "case number" (`Committable`).

### The Handler (Answering Work)
When someone asks *us* a question, it goes to the `Handler`.

```rust
pub trait Handler: Clone + Send + 'static {
    // Process a request and maybe send back a response!
    fn process(
        &mut self,
        origin: Self::PublicKey,
        request: Self::Request,
        response: oneshot::Sender<Self::Response>,
    ) -> ...;
}
```
The handler gets the request and a `oneshot::Sender`. It doesn't have to worry about the network. It just does its thinking and drops the answer into the sender. If it doesn't want to answer, it just drops the sender. Simple!

### The Monitor (Watching the Results)
When valid answers come back, they are handed to the `Monitor`.

```rust
pub trait Monitor: Clone + Send + 'static {
    // Called every time we get a valid response.
    fn collected(
        &mut self,
        handler: Self::PublicKey,
        response: Self::Response,
        count: usize,
    ) -> ...;
}
```
The monitor is the guy standing next to the clerk, looking at the valid answers as they get filed.

---

## 4. The Mailbox: Your Door to the System

So how do you actually talk to this clerk? Through the `Mailbox` (`collector/src/p2p/ingress.rs`).

The Mailbox implements `Originator`. It's just a channel sender that takes your intent and turns it into an internal `Message`:

```rust
pub enum Message<P: PublicKey, R: Committable + Digestible + Codec> {
    Send {
        request: R,
        recipients: Recipients<P>,
        responder: oneshot::Sender<Result<Vec<P>, Error>>,
    },
    Cancel {
        commitment: R::Commitment,
    },
}
```
When you call `send()`, the mailbox packages it up into `Message::Send` and drops it in the mail slot. The hard state—the ledger—stays entirely inside the engine. The mailbox is wonderfully dumb.

---

## 5. The Engine: Where the Ledger Lives

If you open `collector/src/p2p/engine.rs`, you find the `Engine`. This is the clerk. This is where the magic happens.

Look at the main piece of state in the `Engine`:

```rust
// tracked: HashMap<Commitment, (AskedPeers, RepliedPeers)>
tracked: HashMap<Rq::Commitment, (HashSet<P>, HashSet<P>)>,
```

This is it! This is the entire ledger. A map from the case number (`Commitment`) to a tuple of two sets: who we asked, and who has replied.

There is no "timeout" counter here. There is no "best response" logic. The collector keeps it perfectly minimal. It tracks what it needs to coordinate the network, and leaves the application logic to the application.

### How the Engine Moves

The engine runs a massive `select_loop!`. It sits there, juggling multiple things at once.

#### 1. Sending a Request
When a `Message::Send` comes from the Mailbox, the engine computes the commitment (the case number). It creates a new entry in the `tracked` map:

```rust
let entry = self.tracked.entry(commitment).or_insert_with(|| {
    self.outstanding.inc();
    (HashSet::new(), HashSet::new())
});
```
It then fires the request out to the network. Importantly, it records the peers it *actually managed to send to* in the first `HashSet`. It doesn't pretend the network is perfect.

#### 2. Handling Incoming Requests (and Not Blocking!)
When a peer asks *us* a question, the engine receives it from the network. But what if answering takes a long time? We can't stop the clerk from processing other things!

So, the engine passes the request to the `Handler`, gets a future back, and tosses that future into a `Pool` called `processed`:

```rust
let (tx, rx) = oneshot::channel();
self.handler.process(peer.clone(), msg, tx).await;
processed.push(async move { Ok((peer, rx.await?)) });
```
This is a brilliant trick. The engine keeps running its loop, and whenever a handler finishes its work, the pool pops out the result, and the engine sends the reply back to the peer. We never block the switchboard!

#### 3. Receiving a Response: The Admission Matrix
This is the most critical part of the code. When a response comes in from the network, the engine checks it against the ledger:

```rust
let commitment = msg.commitment();

// 1. Does this case exist?
let Some(responses) = self.tracked.get_mut(&commitment) else {
    debug!("response for unknown commitment");
    continue;
};

// 2. Did we ask this peer?
if !responses.0.contains(&peer) {
    debug!("never sent request");
    continue;
}

// 3. Have they already answered?
if !responses.1.insert(peer.clone()) {
    debug!("duplicate response");
    continue;
}

// All good! Give it to the monitor.
self.monitor.collected(peer, msg, responses.1.len()).await;
```

If it fails any of these checks, the message is dropped on the floor. It's safe, it's deterministic, and it prevents a whole class of nasty distributed systems bugs.

If the message is corrupted on the wire, the engine doesn't just log it—it uses a `Blocker` to isolate that peer. We don't tolerate bad actors messing with our ledger!

#### 4. Canceling a Request
What happens when you send a `Cancel` message? 

```rust
Message::Cancel { commitment } => {
    self.tracked.remove(&commitment);
}
```
That's it. It removes the entry from the `HashMap`. Because the case file is gone, any future responses for this commitment will fail step 1 of the admission matrix ("Does this case exist?") and be ignored. 

We don't try to "unsend" packets. We don't send cancellation messages over the network. We just close the case locally. It's profoundly simple and completely robust.

---

## 6. What Can We Learn From This?

The `commonware-collector` is a masterclass in drawing boundaries.

If you try to make the network understand your application, you build a tangled mess. But if you invent a concept like a **Commitment**—a shared case number—you can build a coordinator that handles fanout, duplicates, late arrivals, and cancellations, all without needing to know *what* it's actually coordinating.

The system relies on physics and local state. It knows that you can't control the network, so it controls the one thing it can: its own memory of who it asked, and who answered.

**Further Reading:**
- Want to see how the edge cases are proven? Read `collector/src/p2p/mod.rs` for the tests.
- Want to see it pushed to its limits with garbage data? Check out `collector/fuzz/fuzz_targets/collector.rs`.
- Ready for the next layer down? Read `commonware-p2p` to see how the underlying connections are maintained!
