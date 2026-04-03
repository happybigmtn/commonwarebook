# commonware-flood

*A pressure chamber for p2p deployments, and a guide to reading the result.*

---

## Building a Wind Tunnel for Peer-to-Peer Networks

If you build an airplane, you don't just put it on the runway, notice the wheels roll, and conclude, "Well, it must fly perfectly!" No, you put it in a wind tunnel. You crank up the wind until things start shaking. You want to see *how* it shakes, *where* it bends, and *when* it breaks.

A peer-to-peer network is exactly the same. It is remarkably easy to write code where Alice sends a message to Bob, Bob says "Got it!", and everyone goes home happy with the false impression that their network is robust.

But what happens when you have a hundred nodes, and *everyone* is shouting at everyone else, all at the exact same time? Every single queue fills up, the scheduler starts sweating, and the network links are carrying far more than they do on a happy, sunny day. That’s not a link test anymore; that’s a traffic jam. 

`commonware-flood` exists to make that traffic jam visible. It’s a pressure chamber for your deployment. It creates a controlled, massive workload, runs it against a real deployment (like AWS EC2), and helps you interpret what exactly just happened. 

To understand this, we need a simple mental model of what we're actually building.

## 1. The Anatomy of the Experiment (The Config)

Before we turn on the pump, we need to decide the shape of the experiment. We do this in `Config` inside [`examples/flood/src/lib.rs`](/home/r/coding/monorepo/examples/flood/src/lib.rs). 

If you look at this struct, you'll see it's not just a collection of random tuning knobs. It describes the physical constraints of our queuing system:

```rust
pub struct Config {
    // ...
    pub worker_threads: usize,
    pub message_size: u32,
    pub message_backlog: usize,
    pub mailbox_size: usize,
    // ...
}
```

Think about what these mean physically:
- **`worker_threads`**: How many workers are actively carrying the packages around inside the machine?
- **`message_size`**: How heavy is the package we are throwing? A bigger message takes more time to move.
- **`message_backlog`**: If I want to send packages but the workers are busy, how many packages can I pile up on my desk before they start falling on the floor?
- **`mailbox_size`**: When packages arrive for me, how big is my inbox? 

Performance isn't just a number; it's the result of a specific workload smashing into these specific limits. 

## 2. Setting Up the Chamber

In any good experiment, the environment is just as important as the thing you're testing. If you want to know how your network behaves across the world, you can't run it all on your laptop.

[`examples/flood/src/bin/setup.rs`](/home/r/coding/monorepo/examples/flood/src/bin/setup.rs) sets the stage. It generates the private keys, figures out who is allowed to talk to whom, and spreads the peers across whatever AWS regions you tell it to (like `us-west-2` or `eu-west-1`). 

This isn't just scaffolding—it *is* the test. 
If you change the regions, you are literally changing the speed-of-light delay (the latency). If you change the AWS instance type, you are changing the size of the pipe the cloud provider gives you before they start throttling your traffic. You are setting up the physics of the world.

## 3. Turning on the Pump

Now, how do we actually create the pressure? Look at the heart of [`examples/flood/src/bin/flood.rs`](/home/r/coding/monorepo/examples/flood/src/bin/flood.rs).

In this test, a node isn't just a polite client or a quiet server. It is both, simultaneously. Every node is continuously shouting and continuously listening. 

### The Shouter (Sender)

Let's look at the sender loop. It's brilliantly simple:

```rust
let mut msg = vec![0u8; config.message_size as usize];
let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos() as u64;

// 1. Put the time in the first 8 bytes
msg[0..8].copy_from_slice(&now.to_le_bytes());

// 2. Fill the rest with random junk
rng.fill_bytes(&mut msg[8..]);

// 3. Throw it at everyone!
if let Err(e) = flood_sender.send(Recipients::All, msg, true).await {
    error!(?e, "could not send flood message");
}
```

You see what it's doing? It takes the current time, stamps it into the very front of the message, fills the rest of the package with random bytes to make it realistically heavy, and then hurls it at *every single peer* (`Recipients::All`). 

We call this **fan-out**. One action by one node creates traffic for everybody. It’s the fastest way to multiply the amount of work the network has to do.

### The Listener (Receiver)

On the other side, the receiver is grabbing these messages out of the air:

```rust
match flood_receiver.recv().await {
    Ok((_sender, mut msg)) => {
        // Read the timestamp out of the message
        let sent_ns = msg.get_u64_le();
        let sent_time = UNIX_EPOCH + Duration::from_nanos(sent_ns);
        
        // Measure how long it took to get here
        latency.observe_between(sent_time, SystemTime::now());
    }
    // ...
}
```

When a node receives a message, it ignores all the random junk. It just looks at those first 8 bytes—the timestamp—and compares it to the time *right now*. 
"Ah! You sent this 50 milliseconds ago." 

It records that latency in a histogram. That's our gauge! We don't need complicated distributed tracing for every packet. The packet itself is carrying the stopwatch. It's the simplest possible probe that still tells the truth.

## 4. Reading the Dials (Diagnosis)

When you run this thing, you watch the dials. What are you looking for?

If the number of messages climbs steadily, and the latency histogram stays tight and fast, your network is holding up beautifully. The plumbing is draining faster than you're pouring water in.

But what if the latency starts stretching out? Messages take longer and longer. Why? Here is where you have to think physically about the bottlenecks:

- **Queue Pressure (The Mailbox is Full):** If you see latency rising but no send errors, the messages aren't getting lost; they are just waiting in line. They are sitting in the `message_backlog` or the `mailbox_size` buffer. 
- **Cloud Throttling:** Sometimes your code is fine, but the physical environment says "No." AWS will look at your EC2 instance and decide you are sending too much data. If you log into the machine and check the network interface (`ethtool -S ens5 | grep "allowance"`), you might see `bw_out_allowance_exceeded`. The cloud itself put a cap on your pipe!
- **Geography:** If you put nodes in Tokyo and Virginia, you can't beat the speed of light. If the slow tail of your latency only shows up across regions, your bottleneck is just the physical distance.
- **Scheduler Pressure:** If the machine itself can't keep up because you didn't give it enough `worker_threads`, the latency histogram will tell you long before the network looks broken. The workers are just too busy to move the packages.

## 5. The Philosophy of the Pressure Chamber

The whole point of this chapter isn't just to give you a script that makes a lot of noise. It's to give you a mental model of *capacity*. 

A network is just a series of pipes, buckets, and pumps. Finite `message_backlog` and `mailbox_size` limits are intentional. They define the exact place where the system is forced to say, "Enough!" 

`commonware-flood` is honest. It doesn't magically remove queues, it exposes them. When a queue overflows, it doesn't quietly drop the packet and pretend everything is fine. It logs an error. A stress test *should* fail eventually. Your job as an engineer is to find out exactly where the system breaks, and whether that limit makes sense for what you're trying to build.

Silence is not success here. Success is understanding exactly why the graph looks the way it does.

---

## 6. Glossary and Further Reading

- **Fan-out:** One send becoming traffic to every peer. The multiplier effect.
- **Backlog:** Messages waiting on your desk to be sent.
- **Mailbox:** The limited inbox for an actor to receive messages.
- **Bootstrapper:** A seed peer that helps the network get started.
- **Oracle:** The handle returned by the p2p network for registering the active set of peers.
- **Pressure chamber:** The mindset for this tool. A place where the deployment is deliberately stressed so bottlenecks become visible.

**Further reading:**
- `examples/flood/README.md` for the operator workflow.
- `examples/flood/src/bin/setup.rs` to see exactly how the environment is generated.
- `examples/flood/src/bin/flood.rs` to read the sender and receiver loops.
- `docs/commonware-book/p2p/chapter.md` for the networking model this test depends on.
