# Commonware P2P: Talking to Strangers Without Getting Fooled

*Or, Authenticated, Encrypted Peer-to-Peer Networking for Adversarial Environments.*

---

## 1. The Naive Picture vs. The Real World

When you first learn about computers talking to each other, the picture you get is beautifully simple. One computer opens a socket, another computer listens for it, and—*whoosh*—bytes start flowing back and forth like water through a pipe. 

It’s a nice picture. It’s not exactly *wrong*. But it leaves out all the things that make the real world interesting—and dangerous.

When people say "peer-to-peer" (p2p), they're really bundling a whole bunch of hard problems together:
- Nobody is permanently in charge (no central server).
- Anyone can connect to anyone else.
- People join, leave, unplug their machines, or move around.
- **Identity** matters completely independently of **location**.
- The whole thing has to keep working even when some people are lying, broken, or actively trying to mess with you.

If you bring that naive "water pipe" picture into this messy world, you're going to make mistakes that look perfectly reasonable at first, but break the moment things get real. 

My goal here is to replace that naive picture with a better one.

### The Grand Illusion: IP = Identity

Suppose you build a system that remembers peers by their IP address: `HashMap<SocketAddr, Connection>`. Seems sensible, right? If a packet comes from `203.0.113.7:9000`, it must be your friend Alice. 

Not so fast! 
What if Alice took her laptop to a coffee shop and got a new IP? What if Alice is behind a NAT (a router that hides a bunch of computers behind one address), and her outward-facing address isn't the one she listens on? What if an attacker swoops in and steals that IP after Alice logs off?

Here is the first and most important rule of peer-to-peer networking:
> **A network address is a route hint, not a stable identity.**

An IP address just tells you *where* to send a packet right now. It tells you absolutely nothing about *who* is sitting at that location. 

Because of this, mature systems authenticate **cryptographic identities** (like public keys), not addresses. A public key is the durable name of the peer. The IP address is just a plausible rumor about where that key might be hanging out today.

Once you realize that, a lot of things suddenly make sense:
- You can change your IP without losing who you are.
- You can verify you reached the right person *after* you knock on their door.
- You can talk about blocking a malicious person without caring what IP they use tomorrow.

### Vocabulary That Pays For Itself

Before we look at the machinery, let's get our words straight so we don't trip over ourselves:
- **Peer**: Another participant in the network.
- **Overlay**: The logical network we build on top of the messy physical Internet.
- **Socket Address**: An IP address plus a port. (The "where").
- **Dialing**: Reaching out to start a connection.
- **Listening**: Waiting for someone else to reach out.
- **Handshake**: The secret knock. It authenticates who is there and sets up encryption.
- **Discovery**: How we figure out where people are right now (the rumor mill).
- **Backpressure**: Telling the guy sending you data to *slow down* because your bucket is full.

---

## 2. The Mental Model: An Encrypted Postal Service

So, what does `commonware-p2p` actually do? It provides authenticated, encrypted, multiplexed communication between peers who are identified by their public keys. 

To understand how it works, imagine an **encrypted postal service with named mail slots**.

- A peer's **public key** is their permanent name.
- An **address** is just a route hint to find them.
- A **connection** is an armored, guarded tunnel between two names.
- A **channel** is a specific lane inside that tunnel (like a mail slot).
- A **priority flag** tells the post office whether this letter needs to go on the fast truck or if it can wait in the slow lane.

If you remember that *identity is never inferred from an address*, everything else is just mechanics.

### Two Modes of Operation

The crate operates in two distinct modes, depending on how much you already know:

1. **Discovery Mode**: You know *who* you want to talk to, but not *where* they are. You start with a few seed peers, and everyone gossips about signed addresses until you learn how to dial the rest of the network.
2. **Lookup Mode**: You already know exactly who everyone is and where they live. You just tell the network the `(PublicKey, Address)` pairs directly, and it skips the gossip and gets straight to dialing.

Both use the exact same underlying mechanics. The only difference is where the address rumors come from.

---

## 3. Let's Look at the Code: Addressing & Gossip

Let's look at how this is written in Rust. In `p2p/src/types.rs`, you'll notice we split up "what we dial" from "what we expect to receive".

```rust
pub enum Ingress {
    Socket(SocketAddr),               // A direct IP
    Dns { host: Hostname, port: u16 }, // A DNS name, resolved when we dial
}
```
`Ingress` is what we dial. But the full `Address` is more subtle:

```rust
pub enum Address {
    Symmetric(SocketAddr),                              
    Asymmetric { ingress: Ingress, egress: SocketAddr }, 
}
```
Why `Asymmetric`? Because of NAT! When you dial a friend, they might have told you to dial their public router (`ingress`), but when they dial *you*, their packets might look like they come from a different internal address (`egress`). If we didn't separate these, we'd end up rejecting perfectly good peers or accepting spoofed traffic. Nature is asymmetric, so our code must be too.

### The Gossip (Signed Peer Records)

When peers gossip about where they are, they use an `Info` struct:

```rust
pub struct Info<C: PublicKey> {
    pub ingress: Ingress,
    pub timestamp: u64,       // When this rumor was created
    pub public_key: C,
    pub signature: C::Signature,
}
```
Notice something tricky here? Only the `(ingress, timestamp)` are actually signed. The `public_key` tells us *which* key to check, meaning it tells us *who* is making the claim. It proves that the holder of the private key signed this location at this time. It doesn't prove anything else! And we strictly check that the timestamp isn't from the future, and that people aren't gossiping about themselves in weird ways.

---

## 4. The Five Workers (Actor Topology)

`commonware-p2p` is built using five asynchronous "workers" (actors) that run concurrently. Imagine a busy factory floor:

1. **The Tracker (The Brains):** Keeps track of who we care about, where we think they are, and who gets to dial who. It hands out "Reservations" so two workers don't accidentally dial the same person at the same time.
2. **The Dialer (The Outbound Guy):** Constantly asks the Tracker, "Who should I call?" If it gets a Reservation, it resolves the IP, dials, and does the encrypted handshake.
3. **The Listener (The Bouncer):** Sits at the door accepting incoming connections. It checks IP rate limits, filters bad IPs, and does the receiving half of the handshake.
4. **The Spawner (The Foreman):** When the Dialer or Listener successfully completes a handshake, they hand the new connection to the Spawner. The Spawner creates a dedicated `Peer` actor for that specific connection.
5. **The Router (The Switchboard):** Knows how to route your application's messages to the right `Peer` actor based on who you're trying to talk to.

### The Encrypted Handshake: The Secret Knock

When a connection happens, what goes over the wire? It's not just TLS. It's an encrypted handshake that proves possession of the private key matching the expected identity. 

A malicious node might gladly accept your TCP connection. That proves nothing! The interesting guarantee is: *"The holder of public key P proved possession of the matching private key inside this transport session."*

---

## 5. Traffic Control: The Priority Relay

Imagine you have one pipe to a peer, and you're sending heartbeats, gossip, and massive 50MB files all at the same time. If they all sit in the same queue, that massive file will delay your urgent heartbeat, and your peer might think you died!

To fix this, we use a `Relay`:

```rust
pub struct Relay<T> {
    low: mpsc::Sender<T>,   // Bounded: fills up if app is slow
    high: mpsc::Sender<T>,  // Unbounded: fast lane, skips the queue!
}
```
When you send a message, you say if it's high priority. 
- If it's normal (low priority) and the pipe is full, it fails immediately (backpressure!). We drop the message rather than letting memory grow forever.
- If it's high priority (like control traffic), it goes straight through the unbounded lane. 

This is brilliant because it forces you to feel the pain of a slow network immediately on the low-priority stuff, while keeping the critical life-support systems (high priority) running without getting blocked.

---

## 6. How We Deal With Failure

Networking code has to survive a brutal environment. Here's how the Commonware design translates failure into manageable rules:

- **Delay?** We wait or retry (cooldowns and jitter prevent us from hammering a node that just woke up).
- **Drop?** The Router's bounded mailbox applies backpressure. If the bucket is full, we drop low-priority stuff.
- **Stale info?** We use timestamps. If a rumor is older than what we already know, we ignore it.
- **Malicious input?** We verify the signature on every gossip message. If a peer lies, we block them for a `block_duration`. (We don't ban them forever, because IPs change and we don't want to permanently ban an honest person who gets that IP later!).

---

## 7. The Simulator: Testing Nature

You can't test a p2p network by just hoping it works. In Commonware, we built a **Simulated Network** that perfectly mimics the traits of the real one. 

We can write tests that say: *"Give me 5 nodes. Make the link between Node A and B drop 5% of packets. Add 50ms of latency."* 

Because the runtime is deterministic (driven by a fixed random seed), if the network breaks on Tuesday, it will break the exact same way on Wednesday when you try to debug it. You can see exactly when a message queued up, when a packet dropped, and how the Tracker recovered. We aren't just testing that "messages got through"—we are testing the *physics* of our network under exact, reproducible conditions.

---

## Summary

So, there you have it. `commonware-p2p` isn't just about moving bytes from A to B. It's a careful orchestration of cryptographic identity, gossip validation, priority queues, and autonomous actors working together to maintain a stable illusion of a network over an unstable, adversarial reality. 

Keep the "encrypted post office" in your head. Remember that identity is not location. And respect the backpressure. If you do that, the code will make perfect sense.