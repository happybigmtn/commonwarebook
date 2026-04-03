# commonware-estimator

## A Wind Tunnel for Distributed Mechanisms

---

Have you ever noticed how a new distributed algorithm looks incredibly fast when you run it on your laptop?

Well, of course it does! Your laptop gives the protocol a magnificent gift that reality never will: one machine, one perfectly synchronized clock, one tiny internal network, and a leader that happens to live exactly zero millimeters away from everyone else. 

When you measure performance that way, you aren't really measuring the protocol. You're just measuring how fast your computer can talk to itself. It looks beautifully clean, but in exactly the wrong way.

In the real world, distributed performance is never just a single number. It has a shape. Some computers are close together; some are far apart. Some network pipes are fat, and some are thin. If you change who the leader is, the whole mechanism might suddenly look sluggish. Or it might cruise along fine until the messages get just a little bit too big, and then—*bam!*—it hits a cliff and stalls.

So, how do we see this shape *before* we put the protocol out into the wild? 

We don't need a simple scoreboard or a generic benchmark. We need a **wind tunnel**. We need a place where we can take our mechanism, blow realistic geographical weather across it, and watch carefully to see where the drag appears. That is exactly what `commonware-estimator` is built to do.

---

## 1. The Anatomy of Drag

To understand the shape of a protocol's performance, we need a vocabulary for the friction it encounters. 

- **Latency** is just how long a piece of information takes to get from A to B.
- **Jitter** is the wiggle room—how much that delay bounces around unpredictably.
- **Bandwidth** is the thickness of the pipe; how much data can we shove through at once?
- **Threshold** is the magic number of responses we need before we can stop waiting and move on.
- **Placement** is geography. Where do the peers live? Where does the leader live?

If you only test with small messages, you hide the bandwidth limits. If you only test in one region, you hide the latency. If you only use one leader, you hide the placement bias. The estimator brings all of these physical realities back into the picture.

---

## 2. Building the Wind Tunnel

Imagine setting up a laboratory bench. We need two things: a stage (the network) and a script (the protocol).

### The Stage: Geography as Friction
If you look inside `examples/estimator/src/lib.rs`, you'll see we define a `Distribution`. This isn't abstract math; it's a map of regions. We say, "Put 5 peers in `us-east-1` and 3 peers in `ap-southeast-2`." We can even pinch the pipes by setting `egress_cap` and `ingress_cap` to limit bandwidth.

To make the travel time realistic, the simulator loads real-world latency matrices (from CloudPing). But it doesn't just treat "ping" as a perfect number. It looks at the average time (P50) and the slow time (P90), and turns that gap into our **jitter**. It’s a practical, simple model of real regional links.

### The Script: A Tiny DSL and the Power of Rust Enums
We don't want to write a whole new programming language just to run a test. We just need to express the *moves* that actually matter in consensus protocols. We do this by defining a Domain Specific Language (DSL).

Let’s look at how beautifully Rust lets us define this inside `lib.rs`:

```rust
pub enum Command {
    Propose(u32, Option<usize>),
    Broadcast(u32, Option<usize>),
    Reply(u32, Option<usize>),
    Collect(u32, Threshold, Option<(Duration, Duration)>),
    Wait(u32, Threshold, Option<(Duration, Duration)>),
    Or(Box<Self>, Box<Self>),
    And(Box<Self>, Box<Self>),
}
```

Now, an `enum` in Rust isn't just a simple list of names like in some older languages; it's a way to say, "A command can be *exactly one* of these distinct shapes, and each shape can hold its own special cargo." A `Propose` command carries a message ID (a `u32`) and an optional size (because a 4-byte "yes" moves faster than a 4-megabyte "certificate"). 

But look at the branching logic: `Or(Box<Self>, Box<Self>)`. What's going on there? If we want a command to be "Wait for this OR Wait for that," we are defining a structure that contains itself! If Rust tried to put that directly in memory, the compiler would say, "Wait, how big is this? It could be infinitely recursive!" 

To fix that, we wrap the inner commands in a `Box`. A `Box` simply takes the data, puts it somewhere out on the heap, and leaves behind a fixed-size pointer. It’s Rust’s way of saying, "Don't worry about the size right now, just hold this tag that tells you where to find the rest of the logic." It makes building complex, branching protocol logic wonderfully elegant.

---

## 3. The Engine in Motion

So, how does the machine actually run? Let's trace the loop inside `examples/estimator/src/main.rs`.

When you fire it up, it reads the region distribution and your protocol script. It builds a virtual network of peers and wires them together with those CloudPing latencies. Then, it does something brilliant: **it runs a deterministic simulation**. 

Because we control the random seed, the whole universe ticks forward predictably. If a peer hits a `wait{id=1, threshold=67%}`, the peer drops down into the engine's `can_command_advance` logic. It simply checks its inbox. If it only has 50% of the messages, it stops and waits. When enough messages finally crawl across the simulated network to hit 67%, the peer writes down the exact timestamp: *"I unblocked right... NOW."*

### Asynchronous Mail Chutes
How do we actually run this simulation without it becoming a tangled mess of operating system threads? We use Rust's asynchronous tasks and channels. 

In `main.rs`, you'll see this setup:

```rust
let (tx, mut rx) = mpsc::channel(peers);
let jobs = spawn_peer_jobs(&context, proposer_idx, peers, identities, commands, tx);

// ... later on ...
for _ in 0..peers {
    responders.push(rx.recv().await.unwrap());
}
```

MPSC stands for "Multi-Producer, Single-Consumer." Think of it as a mail chute. We spawn a lightweight asynchronous task (`spawn_peer_jobs`) for each peer. They all live in the same deterministic runtime, ticking forward cooperatively. When a peer finishes its entire script, it drops a message down the chute using its "producer" transmitter (`tx`). 

The main engine, acting as the "consumer" (`rx`), just sits at the bottom of the chute and waits: `rx.recv().await.unwrap()`. Once it receives a completion message from every single peer, it knows the play is over, and it can shut the universe down. The `.await` syntax is the secret sauce here—it tells the runtime, "Hey, I'm stuck waiting for mail, go ahead and let another peer do some work." It keeps the simulation perfectly cooperative.

### Rotating the Proposer
This is the most important part of the experiment. Once the script finishes, the engine resets the universe, picks the *next* peer in the network to be the leader, and runs the exact same script again.

If a protocol looks blazing fast when the leader is in Virginia, but crawls to a halt when the leader is in Tokyo, you don't have a fast protocol—you have a lucky one. By systematically rotating the proposer and running the whole play again, the estimator exposes the true cost of leadership placement.

---

## 4. Reading the Instruments

When the dust settles, the simulator doesn't just say "Done." It gives you the timestamps it recorded. 

You get to see:
1. **The Proposer's View:** How long did the leader spend waiting?
2. **The Regional View:** How long did the peers in Europe wait compared to the peers in Asia?
3. **The Aggregate View:** What happens when we average the results across *every single proposer run*?

You can watch the lines bend. You can see the cliffs appear when messages get too big or thresholds get too high. You aren't just getting a single number; you are seeing the contour of the mechanism's cost.

---

## 5. What It Is, and What It Isn't

It's important to know the limits of your laboratory equipment.

`commonware-estimator` is **not** a correctness machine. It won't prove that your protocol is safe. It won't prove that it's live or free of deadlocks. The math and the logic proofs have to happen somewhere else.

What the estimator *does* is absorb the pressures of reality—regional skew, bandwidth bottlenecks, and leadership placement—so you can compare designs. It lets you ask, "If I change this wait condition to an OR, how much time do I save in the worst case?" and get a repeatable, geographical answer.

---

## 6. How to Explore the Source

If you want to poke around the machinery yourself, here is the best way to read the code:

1. **Start with `examples/estimator/src/main.rs`.** 
   Read `run_simulation_logic`. This is the beating heart of the wind tunnel. Watch how it sets up the virtual network, spawns a job for each peer, and passes messages around in virtual time using the `mpsc` channels. 
2. **Then look at `examples/estimator/src/lib.rs`.** 
   Look for `can_command_advance`. This function is the physics rule for when a peer is allowed to take its next step. It evaluates the exact thresholds and logic (`&&`, `||`) of your script against the peer's inbox.
3. **Finally, peek at `p50.json` and `p90.json`.**
   They aren't code, but they are the raw friction of the internet, captured as a matrix.

This tool exists because a distributed mechanism isn't just an abstract idea. It's a physical process that moves information across the Earth. And to design physical things well, you need to put them in the wind tunnel.