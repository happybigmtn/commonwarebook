# commonware-p2p

*Authenticated, Encrypted Peer-to-Peer Networking for Adversarial Environments*

---

## Backgrounder: What Peer-to-Peer Networking Is Actually Hard About

The naive picture of networking is simple enough to fit in one sentence: one computer opens a
socket, another computer accepts it, and bytes flow between them.

That picture is not wrong. It is just missing the parts that matter most once the network becomes
dynamic, hostile, or long-lived.

When people say "peer-to-peer," they often mean at least five different things at once:

- there is no permanently central server for all traffic,
- many machines may connect to many other machines,
- participants may join, leave, crash, or move,
- identities matter independently of IP addresses,
- and the network has to keep working even when some peers are slow or malicious.

If you carry only the naive socket picture into that setting, many design mistakes look reasonable
at first. This backgrounder is here to replace that first picture with a better one.

### Start with the basic layers

At the physical level, packets move between interfaces and routers. At the software level, the
application sees endpoints such as IP addresses and ports. That is already enough to make a small
client-server program work. But distributed systems care about another layer that is easy to miss:
the difference between **location** and **identity**.

An IP address tells you where traffic should be sent right now. It does not tell you who owns the
connection, whether the owner is the same machine you talked to yesterday, or whether the address
will still be valid ten minutes from now.

That distinction sounds abstract until you see how often the two come apart:

- a laptop changes networks and gets a new address,
- a node sits behind NAT and is dialed through a public address but emits packets from another
  visible source,
- DNS for one hostname resolves to several candidate addresses,
- a malicious party reuses an old address after a legitimate peer disappears,
- or a peer record stays cached after the machine it described has already moved.

So the first conceptual rule of serious p2p design is:

> A network address is a route hint, not a stable identity.

Once you accept that, many later choices stop looking fussy and start looking necessary.

### Vocabulary that pays for itself

Some terms are worth fixing early.

- A **peer** is another participant in the overlay network.
- An **overlay** is the logical network formed by peers, independent of the underlying Internet
  routing.
- A **socket address** is an IP address plus port.
- **Dialing** means initiating an outbound connection.
- **Listening** means accepting inbound connections.
- A **transport connection** is the live stream over which messages move.
- A **handshake** is the protocol that authenticates the parties and often negotiates encryption.
- **Discovery** is how peers learn where other peers might be reachable.
- **Backpressure** is the mechanism that tells a sender to slow down instead of buffering forever.
- **NAT** is the class of network devices that rewrite addresses, often hiding many machines behind
  one public address.
- A **channel** or **stream** is a logical lane of messages multiplexed over one underlying
  transport.

If you blur those terms together, it becomes hard to reason about which guarantees the system
actually has.

### Why "IP equals peer" breaks immediately

Imagine a network that stores peers as `HashMap<SocketAddr, Connection>`. That sounds convenient.
Incoming packets from `203.0.113.7:9000` must come from that peer, right?

Not necessarily.

Maybe the real peer restarted behind a load balancer. Maybe the remote machine is behind a NAT and
outbound packets appear from a different egress address than the one you dialed. Maybe the address
was learned through gossip and has already gone stale. Maybe an attacker wants you to bind network
authority to an address it can spoof or later inherit.

This is why mature systems authenticate **cryptographic identities**, not addresses. A public key
can act as the durable name of the peer. The address becomes the currently plausible path to that
name.

That one shift fixes several conceptual bugs at once:

- you can rotate addresses without rotating identity,
- you can verify you reached the intended peer after dialing,
- you can talk about "blocking peer P" without caring which address P currently uses,
- and you can validate signed peer records as statements made by an identity rather than as truths
  attached to one socket.

### Discovery is knowledge management, not just gossip

Another easy mistake is to think of peer discovery as a one-time bootstrap step. Get a list of IPs,
connect, done.

Real p2p systems do not get that luxury. Peer sets evolve. Addresses go stale. Some peers are only
temporarily reachable. Some information is second-hand. Different nodes may know different subsets
of the network at the same time.

So discovery is better understood as a **distributed knowledge problem**:

- What peers do I believe exist right now?
- Which of them do I have a usable route for?
- How fresh is that route information?
- Which facts are safe to re-share?
- When should failed knowledge be retried, downgraded, or discarded?

This is why good discovery protocols distinguish between:

- **membership** knowledge: who belongs in the set,
- **reachability** knowledge: who seems dialable,
- **attested address** knowledge: who signed what address and when,
- and **local experience**: which dial attempts have recently failed.

If you collapse all of those into one boolean such as "known peer," the system cannot represent the
difference between "this identity exists but I have no address," "I have a route but it may be
stale," and "I just tried that route and it failed three times."

### Why handshakes do more than start encryption

A handshake is often described as "the part where TLS starts." In p2p systems it usually carries a
heavier burden.

The handshake answers questions like:

- Which identity is on the other end?
- Did I reach the identity I intended to reach?
- Are we deriving session keys bound to this identity?
- Are both directions of the connection talking about the same overlay and namespace?

Without that step, the connection is just a pipe to some endpoint. The handshake turns the pipe
into a relationship with a named peer.

This matters even more in adversarial settings. A malicious node may happily accept a TCP
connection. That fact alone tells you almost nothing. The interesting guarantee is not "somebody
answered." It is "the holder of public key P proved possession of the matching private key inside
this transport session."

### Multiplexing and why one queue is not enough

Suppose you have one live encrypted connection to a peer and several message classes:

- heartbeats,
- discovery gossip,
- consensus votes,
- large data payloads,
- catch-up or backfill traffic.

If they all share one FIFO queue with no policy, a burst of bulky, low-importance traffic can delay
urgent control traffic. The network is still "working" in the narrow sense that bytes are moving,
but the system-level behavior may degrade sharply.

This is where channels, priorities, and backpressure enter the story.

The conceptual problem is not just bandwidth. It is **contention between message classes with
different urgency**. A good overlay therefore tends to separate:

- logical channels, so different consumers can reason locally,
- priority classes, so urgent control messages are not trapped behind routine traffic,
- and buffer policies, so overload becomes visible as backpressure or drops instead of silent
  unbounded memory growth.

There is no perfect policy. Unbounded high-priority lanes can protect liveness traffic, but they
must be used sparingly or everything becomes "urgent." Bounded low-priority lanes prevent runaway
memory use, but they force the application to accept drop or retry behavior.

### The special pain of NAT and asymmetric addressing

Students often learn networking in environments where every host has a stable, directly reachable
address. Many real deployments do not look like that.

NAT devices rewrite packet headers so many internal machines can share one public address. That
means:

- the address a peer advertises may not equal the address you see on inbound packets,
- two peers may both think they are reachable even though only one direction of dialing works,
- and "where to send traffic" may not be identical to "what source address is acceptable on
  receive."

This is why asymmetry matters. Some systems need one field for ingress, meaning what to dial, and
another for egress, meaning what source address to accept as legitimate for that identity.

That distinction feels like overengineering until the day you deploy across consumer networks or
cloud edges and discover that the world does not preserve your clean symmetry assumptions.

### Failure models shape the protocol

Networking code has to operate under many kinds of failure, and each kind suggests a different
response:

- **delay** means wait longer or retry later,
- **drop** means retransmit or accept loss,
- **reordering** means the receiver must not infer meaning from arrival order alone,
- **stale information** means address records need freshness rules,
- **malicious input** means every signed or framed message needs validation,
- **slow consumers** mean buffers need explicit policy,
- **disconnects** mean connection lifetime cannot equal peer lifetime.

One of the easiest mistakes in distributed systems is to treat all failures as "the connection
failed." That hides the real question: did the route fail, the peer fail, the handshake fail, the
queue fill, the address go stale, or the verification logic reject the record?

The more clearly a p2p design names those cases, the easier it becomes to recover from them without
inventing ambiguous state.

### The main tradeoffs in p2p design

Broadly, p2p overlays live between several tradeoffs:

- **Centralization vs autonomy**: a central directory simplifies discovery but becomes a trust and
  availability bottleneck.
- **Freshness vs bandwidth**: more frequent gossip improves convergence but increases overhead.
- **Persistence vs churn tolerance**: long-lived connections amortize handshake cost, but they can
  pin stale assumptions.
- **Strict reliability vs bounded memory**: if nothing may be dropped, buffers can grow without
  bound; if some traffic may be dropped, the application must know how to recover.
- **Identity richness vs wire simplicity**: richer signed metadata helps routing and verification,
  but every field raises questions about freshness, replay, and what exactly the signature covers.

There is no universal winner. Good systems pick one point on each tradeoff and then make the
resulting semantics explicit.

### The bridge into Commonware

That is the right backdrop for `commonware-p2p`.

The crate is not merely "TCP plus encryption." It is Commonware's answer to a more specific
question: how should a distributed system talk to named peers in an adversarial, changing network
without confusing route information for identity, without letting one traffic class dominate every
other, and without giving up deterministic testing?

So the rest of this chapter narrows from the broad problem class to the specific mechanism:

- identities are public keys,
- discovery is built from signed peer records and compact bitvectors,
- the transport handshake binds a connection to an expected identity,
- relay lanes separate urgent and ordinary traffic,
- and the actor structure turns all of that into a manageable control plane.

Once that conceptual map is in your head, the Commonware design reads less like a grab bag of
actors and more like a careful answer to the real p2p question: not "can bytes move?" but "can
peers learn, verify, and use routes to one another without losing the distinction between what is
known, what is fresh, and what is safe to trust?"

---

## 1. What Problem Does This Module Solve?

At first glance, peer-to-peer networking sounds like a solved problem. Open a socket, connect to a
remote address, and send bytes. But that picture leaves out almost everything a real adversarial
network needs:

- How do you know the thing on the other end is actually the peer you intended to reach?
- How do you route different classes of traffic without one slow consumer clogging the whole link?
- How do you discover addresses when the network membership changes?
- How do you handle NAT, stale peer records, or partially connected topologies?

`commonware-p2p` is the answer Commonware uses for those questions. It provides authenticated,
encrypted, multiplexed communication between peers identified by cryptographic public keys.

The crate operates in two modes:

**Discovery mode** (`discovery::Network`)  
Use this when you know *who* should be in the network but not yet *where* they are. Peers start
from a seed set, exchange signed address information, and gradually learn how to dial the rest of
the current peer set.

**Lookup mode** (`lookup::Network`)  
Use this when the application already knows both identity and address. The application supplies
`(PublicKey, Address)` pairs directly, so the network can skip discovery gossip and start dialing.

Both modes share the same transport machinery: the encrypted handshake, the relay, the mailbox
structure, the peer actors, and the channel model. The difference is only where addresses come
from.

The crate composes with the rest of Commonware like this:

- **Cryptography** (`commonware-cryptography`) — provides the `Signer` and `PublicKey` traits used for peer authentication and signed peer attestations.
- **Codec** (`commonware-codec`) — provides `Encode`/`Decode` for all wire messages (`Ingress`, `Address`, `Payload`).
- **Runtime** (`commonware-runtime`) — provides the abstract `ContextCell` that drives all async actors and I/O, enabling deterministic testing via `deterministic::Runner`.
- **Stream** (`commonware-stream`) — provides the encrypted stream protocol (`commonware_stream::encrypted`) that handles the actual connection establishment and framing.

---

## 2. Mental Model

The best mental model is **an encrypted postal service with named mail slots**.

- A peer's **public key** is its identity.
- An **address** is only a possible route to that identity.
- A **connection** is an authenticated encrypted tunnel between two identities.
- A **channel** is a named lane inside that tunnel.
- A **priority flag** decides whether a message enters the fast lane or the ordinary lane.

That distinction between *identity* and *address* is the first thing to keep straight. An address
is not who a peer is. It is only where you are trying to reach them. If you dial
`203.0.113.8:9000`, you have learned almost nothing yet. You still have to perform the handshake
and prove that the remote side owns the expected key.

Once that picture is in place, the rest of the chapter gets easier:

- The network keeps long-lived encrypted connections alive when it can.
- Messages are tagged with channel IDs so unrelated traffic does not get mixed together.
- Low-priority traffic can be dropped or backpressured without blocking urgent traffic.
- In discovery mode, peers gossip signed records describing how they can be reached.

One more invariant matters so much that it is worth stating twice:

> **Identity is never inferred from an address.**

If a packet arrives from `1.2.3.4:9000`, that tells you where it came from, not who sent it. The
handshake is what ties the connection to a cryptographic identity.

---

## 3. Core Abstractions and Important Types

### 3.1 Addressing — `Ingress` and `Address`

`p2p/src/types.rs`

Start with the addressing types, because they explain a design choice that appears everywhere else:
Commonware separates *what we dial* from *what we expect to receive from*.

`Ingress` is **what we dial** to reach a peer:

```rust
pub enum Ingress {
    Socket(SocketAddr),               // Direct IP address
    Dns { host: Hostname, port: u16 }, // DNS name (resolved at dial time)
}
```

`Address` is the **full address specification**:

```rust
pub enum Address {
    Symmetric(SocketAddr),                              // Same address for dial and filter
    Asymmetric { ingress: Ingress, egress: SocketAddr }, // Dial one thing, expect to receive from another
}
```

`Asymmetric` is the interesting case. It models the common NAT situation where the peer knows the
public address other nodes should dial, but inbound packets appear to come from a different egress
IP that must still be checked. If those two concepts were collapsed into one field, the runtime
would either reject valid peers behind NAT or accept spoofed sources too easily.

`allow_private_ips` applies to both direct socket addresses and DNS-resolved
addresses. When an `Ingress::Dns` name resolves to several IPs, the dialer
chooses among them randomly. The point is not discovery sophistication; it is
to avoid turning one DNS answer into a brittle permanent pin.

### 3.2 The Wire Protocol — `Payload`

`p2p/src/authenticated/discovery/types.rs`

Four `Payload` variants traverse the wire:

| Variant | Role | When Sent |
|---------|------|-----------|
| `Greeting(Info<C>)` | Introduces the peer | First message on every new connection |
| `BitVec(BitVec)` | Discovery + keepalive | Periodically (default: every 50s) |
| `Peers(Vec<Info<C>>)` | Gossip response | When BitVec reveals unknown peers |
| `Data(Data)` | Application payload | Whenever the app sends |

`BitVec` is deliberately compact and deliberately lossy. Bit `i` in position `index` means
"I believe I can dial peer `sorted_peers[i]`." A zero bit does **not** mean "this peer does not
exist." It means "I am not currently asserting reachability." That distinction matters because it
lets the system age out stale information without pretending it has strong negative knowledge.

### 3.3 Signed Peer Records - `Info` and `InfoVerifier`

`Info` is a signed attestation by peer P of its own `(ingress, timestamp)`:

```rust
pub struct Info<C: PublicKey> {
    pub ingress: Ingress,
    pub timestamp: u64,       // Epoch milliseconds
    pub public_key: C,
    pub signature: C::Signature,
}
```

Only `(ingress, timestamp)` is signed. The `public_key` field tells the verifier *which* key to
use, but it is not itself inside the signed payload. That sounds subtle, because it is. The point
is not that the type is unsafe; the point is that you should reason about exactly what the signature
proves:

- it proves that the holder of a private key signed an `(ingress, timestamp)` pair;
- it does **not** prove that every field in `Info` was covered by that signature.

Good protocol reading often comes down to noticing details like that.

`InfoVerifier::validate` applies three checks on every gossip message:

1. **Not-self**: reject if `info.public_key == me` — prevents self-announcement.
2. **Timestamp within `synchrony_bound`**: reject if `info.timestamp` is more than `synchrony_bound` milliseconds in the future — bounds how far into the future a forged timestamp can be.
3. **Valid signature**: verify against the gossip namespace. This prevents cross-namespace replay,
   and the signed payload is exactly `(ingress, timestamp)`.

The gossip namespace `_COMMONWARE_P2P_TRACKER` is distinct from the stream signing namespace `_COMMONWARE_P2P_STREAM`. This separation ensures that peer records gossiped through discovery cannot be replayed as stream messages.

### 3.4 Tracker Directory and Record State

`p2p/src/authenticated/discovery/actors/tracker/directory.rs`  
`p2p/src/authenticated/discovery/actors/tracker/record.rs`

The discovery tracker is the network's control-plane memory. It does more than
remember peers; it decides what the system can currently justify about
reachability, reservation, and block state.

- Which peers belong to any currently tracked peer set?
- What do we currently know about how to reach each one?
- Which connection attempts are allowed right now?
- Which facts are safe to re-share to somebody else?

`Directory` keeps three coupled data structures because those three claims
change one another's meaning:

- `peers: HashMap<PublicKey, Record>` — the per-peer source of truth
- `sets: BTreeMap<u64, Set<PublicKey>>` — the tracked peer sets, keyed by epoch-like index
- `blocked: PrioritySet<PublicKey, SystemTime>` — peers temporarily denied service

The important design choice is that **address knowledge and connection state live in the same
record**. A `Record` tracks both:

| Field | Meaning |
|-------|---------|
| `address` | `Unknown`, `Myself`, `Bootstrapper`, or `Discovered(Info, fails)` |
| `status` | `Inert`, `Reserved`, or `Active` |
| `sets` | How many tracked peer sets still reference this peer |
| `persistent` | Whether the record should survive set eviction (`Myself`, bootstrappers) |
| `next_reservable_at` | Earliest time another actor may reserve this peer |
| `next_dial_at` | Earliest time the dialer should try a new outbound attempt |

That is the state machine behind discovery:

- `Unknown` means "we know this identity matters, but not where it is."
- `Bootstrapper` means "we have a seed address, but not a signed fresh attestation yet."
- `Discovered(info, fails)` means "we have signed peer info plus a local failure counter."
- `Reserved` means exactly one actor currently owns the right to turn this peer into a live
  connection.
- `Active` means the peer actor exists and the record may now become sharable.

Two methods drive the directory's knowledge semantics:

- `update(info)` only accepts strictly newer timestamps. A stale replay does not overwrite fresher
  knowledge.
- `want(dial_fail_limit)` decides whether this peer should appear as "wanted" in the knowledge
  bitmap. Unknown and bootstrapper records are always wanted. Discovered records become wanted
  again after enough dial failures unless they are already active.

This is the subtle point the chapter should not skip: the discovery bitmap is **derived state**. It
is not a separate truth source. `Set::update(peer, !want(...))` projects each record into a single
bit that says whether we currently claim useful reachability information for that peer.

You can read the directory as a small admission controller:

- `reserve()` only succeeds if the peer is eligible, unblocked, and `Status::Inert`
- on success, it moves the record to `Reserved`, sets `next_reservable_at = now + cooldown`, and
  computes a jittered `next_dial_at`
- `connect()` upgrades `Reserved -> Active`
- `release()` downgrades `Reserved` or `Active -> Inert`

That cooldown-plus-jitter behavior is not cosmetic. It prevents many actors from hammering the same
peer in lockstep after an outage. The tracker turns "everybody retry now" into "one retry now, and
future retries spread out a bit."

Three invariants are worth carrying in your head while reading the code:

1. **At most one live reservation per peer.** `Reserved` is the gate that prevents concurrent dial
   and listen paths from both claiming the same identity.
2. **Only connected knowledge is sharable.** `Record::sharable()` returns discovered `Info` only
   when the peer is `Active`, so gossip reflects currently usable knowledge rather than stale rumor.
3. **Blocking outlives the record.** A block lives in `PrioritySet` even if the peer record is
   later deleted due to set eviction. Temporary punishment is tied to identity, not to whether the
   record still happens to exist in `peers`.

The set bookkeeping completes the picture. `add_set()` increments a reference count on every peer
in the new set, rejects non-monotonic indices, and evicts the oldest set once `max_sets` is
exceeded. A record can only disappear when `sets == 0`, `persistent == false`, and `status ==
Inert`. That rule is what lets old connections survive an epoch transition without leaking records
forever.

One more discovery-specific detail matters when a peer asks for gossip. `infos(bit_vec)` does not
blindly dump everything it knows. It first checks that the bitvector length matches the tracked set,
then only returns peers the requester marked as missing, and finally refuses to re-share `Info`
with timestamps later than the local clock. That last filter is a small but important anti-abuse
measure: future-dated but locally acceptable info should not be re-gossiped in a way that could
get another honest peer blocked.

### 3.5 Lookup Tracker State and Control Plane

`p2p/src/authenticated/lookup/actors/tracker/directory.rs`  
`p2p/src/authenticated/lookup/actors/tracker/record.rs`

Lookup mode is not "discovery with the gossip parts commented out." It has a different control
plane.

In discovery mode, the tracker learns addresses from signed peer records. In lookup mode, the
application tells the tracker what the addresses are and remains the authority on updates. That
changes the record model:

- there is no `Unknown` or `Discovered`
- a peer is either `Myself` or `Known(Address)`
- address changes come from `add_set()` or `overwrite()`, not from peer gossip

That simplification has consequences. `add_set()` returns two lists:

- `deleted_peers` — peers that fell out of all tracked sets after eviction
- `changed_peers` — existing peers whose addresses were replaced

That return value is the control-plane contract. If a peer's address changes, the caller should
tear down any existing connection, because that connection was established under the old routing
assumption. Discovery mode can grow into a new address by gossip. Lookup mode expects the
application to say, plainly, "this mapping changed; reconnect."

Inbound filtering is also more explicit in lookup mode. `acceptable(peer, source_ip)` checks:

- membership and non-blocked status
- that the record is `Inert`
- and, unless `bypass_ip_check` is enabled, that the connection's observed source IP matches the
  peer's configured egress IP

That egress check is the lookup-mode version of "identity is not inferred from address." The
application may supply a dial ingress and an expected egress, but the listener still treats them as
two separate facts. `listenable()` makes this concrete by precomputing the set of egress IPs worth
accepting from tracked, eligible peers.

So the shortest honest summary of lookup mode is:

> Discovery propagates knowledge about addresses. Lookup enforces addresses supplied by a higher
> layer.

Both modes still share reservation state, cooldowns, block timers, and peer-set retention. The
difference is who gets to mutate address knowledge.

### 3.6 Priority Relay - `Relay<T>`

`p2p/src/authenticated/relay.rs`

Every peer-to-peer channel is backed by a `Relay`:

```rust
pub struct Relay<T> {
    low: mpsc::Sender<T>,   // Bounded — fills up if app is slow
    high: mpsc::Sender<T>,  // Unbounded — priority messages skip queue
}
```

`send(message, priority=true)` routes to `high`. `send(message, priority=false)` routes to `low`.
The important behavior is what happens under pressure:

- if the low lane is full, a low-priority send fails immediately via `try_send`;
- if the high lane is live, a priority send still gets through.

This is how the runtime avoids a very ordinary failure mode: a backlog of unimportant traffic
quietly blocking the traffic that actually matters.

### 3.7 Mailbox Primitives - `Mailbox` and `UnboundedMailbox`

`p2p/src/authenticated/mailbox.rs`

This section only becomes interesting when you read it as a statement about
where backpressure belongs.

The networking stack has two different places where messages can wait, and they
should not be governed by the same rule.

At the router and spawner boundary, waiting is informative. If application
traffic or connection work is arriving faster than the actor can absorb it, the
system wants to feel that pressure immediately. A bounded `Mailbox<T>` turns the
actor's queue into a visible limit. It says:

> this actor is part of the data plane, so backpressure is a real signal, not
> an implementation inconvenience.

The tracker is different. It is part of the control plane that keeps the rest
of the network alive. If the tracker blocked on its own bookkeeping queue, the
system could deadlock on the very metadata it needs in order to recover. That is
why `UnboundedMailbox<T>` exists. It is not "the same mailbox but bigger." It is
the spelling for a different systems claim:

> control-plane bookkeeping should not stop because the bookkeeping channel
> itself became the bottleneck.

So the important distinction is not bounded versus unbounded in the abstract.
The distinction is whether queue growth is supposed to act like backpressure or
whether the actor must keep moving to preserve liveness of the larger network.

### 3.8 The Shared Trait Surface - `Manager`, `AddressableManager`, `Provider`

`p2p/src/authenticated/mod.rs` defines the shared surface, but the two modes
carry different assumptions about what the application already knows. In
discovery, the application names peer sets and lets gossip fill in addresses.
In lookup, it supplies concrete address mappings up front.

```rust
pub trait Manager: Provider {
    fn track(&mut self, id: u64, peers: Set<PublicKey>) -> impl Future<Output = ()>;
}

pub trait AddressableManager: Provider {
    fn track(&mut self, id: u64, peers: Map<PublicKey, Address>);
    fn overwrite(&mut self, peers: Map<PublicKey, Address>); // In-place address updates
}
```

The `Oracle` returned by `Network::new` implements `Manager` in discovery mode and `AddressableManager` in lookup mode. The application uses the oracle to register peer sets and (in lookup mode) push address updates.

---

## 4. Execution Flow and Lifecycle

This section is easier to follow if you picture five long-running actors handing work to one
another:

- the **tracker** knows which peers matter right now,
- the **dialer** tries to establish outbound connections,
- the **listener** accepts inbound ones,
- the **spawner** turns a fresh connection into a peer actor,
- and the **router** knows how to send application traffic over live peers.

No single actor does everything. That separation keeps each loop understandable.

### 4.1 Startup Sequence

```
Application
    |
    | 1. Creates Config (recommended() / local() / test())
    |
    v
Network::new(context, cfg)   // Returns (Network, Oracle)
    | Creates five actors: tracker, router, spawner, listener, dialer
    | Creates the channels registry (Channels)
    | Generates self-signed Info for this node
    v
oracle.track(epoch, peers)  // Registers peer set at epoch index
    |
    | 2. Registers application channels via network.register()
    |    Each channel gets a Sender and Receiver handle
    v
network.start()              // Spawns all five actors
    |
    v
  Five actors now run concurrently:
  - tracker: owns peer set state, directory, connection reservations
  - router: owns per-peer Relay map, routes app messages to connections
  - spawner: owns per-connection peer actors (one per established connection)
  - listener: accepts inbound TCP, runs encrypted handshake
  - dialer: drives outbound connection loop, respects dial_frequency
```

### 4.2 Outbound Connection Flow (Dialer → Spawner → Peer)

Read this flow as a chain of increasingly strong claims.

At first the system has only a candidate peer identity. Then it has a reservation saying nobody
else should race the same dial. Then it has a socket. Then it has an authenticated encrypted
stream. Only after all of that does it have a usable peer connection.

```
dialer.tick (every dial_frequency)
    |
    | Asks tracker for dialable peers
    | tracker.dialable() returns shuffled peers not recently connected
    v
For peer P:
    tracker.dial(P) -> Reservation (or None if cooldown not expired)
        |
        | Reservation holds Metadata::Dialer(P, ingress) + Releaser
        v
    dial_peer(reservation)
        |
        | Resolve ingress (DNS if needed, filter private IPs)
        | Pick one resolved address randomly
        | context.dial(address) -> (sink, stream)
        | commonware_stream::encrypted::dial() — encrypted handshake
        |   - Sends auth challenge, receives signature proof
        |   - Validates peer public key against tracker
        |   - Returns authenticated stream
        v
    supervisor.spawn(instance, reservation)  // → spawner
        |
        | spawner allocates a peer actor
        | tracker.connect(P, is_dialer=true) -> greeting Info
        | router.ready(P, messenger) -> channels registry
        | peer_actor.run() — the per-connection message loop
        |   - Sends Greeting (self Info)
        |   - Receives peer's Greeting, validates via InfoVerifier
        |   - Enters Data/BitVec/Peers loop
        |   - On exit: router.release(P), tracker disconnects
        v
    Connection active — router now has Relay<P> for peer P
```

### 4.3 Inbound Connection Flow (Listener → Spawner → Peer)

Inbound flow is the same story from the other side. The listener first decides whether the
connection should even be entertained. Only then does the handshake prove the peer's identity, and
only then does the rest of the system allocate long-lived state for it.

```
listener.accept() -> (address, sink, stream)
    |
    | Check private IP policy, IP/subnet rate limits, concurrent handshake limit
    | If any check fails: close connection, continue
    v
handshake() — commonware_stream::encrypted::listen()
    | Runs the server-side encrypted handshake
    | Validates dialer's public key against tracker via acceptable()
    v
tracker.listen(peer) -> Reservation (or None if peer not in any tracked set)
    |
    | Reservation holds Metadata::Listener(peer, observed_egress)
    | The egress IP is checked against Address::Asymmetric { egress } if present
    v
supervisor.spawn((send, recv), reservation)  // → spawner
    | Continues as in outbound flow from peer_actor.run()
    v
Connection active
```

### 4.4 The Peer Actor Loop Is the Protocol Core

`p2p/src/authenticated/discovery/actors/peer/actor.rs`

The peer actor is where an authenticated connection turns into a real protocol session. The
handshake has already proven identity by the time the actor starts, but the actor still enforces
all the connection-local rules: greeting order, per-message validation, gossip cadence, and the
boundary between network traffic and the application.

`Actor::run` immediately splits into two long-lived tasks:

- a **sender half** that owns the stream writer and the periodic gossip timer
- a **receiver half** that owns the stream reader and protocol validation

The whole peer shuts down when either half exits. That is a strong invariant: Commonware treats a
peer connection as one bidirectional session, not two semi-independent streams.

The sender half does four jobs:

1. Send our `Greeting` first, before any other payload.
2. Periodically ask the tracker to `construct(peer, mailbox)` a fresh bitvector. This acts as both
   keepalive and discovery request.
3. Forward control-plane messages from the tracker mailbox: `BitVec`, `Peers`, or `Kill`.
4. Forward pre-encoded application payloads from the relay's `high` and `low` queues straight onto
   the encrypted stream.

Notice what it does **not** do: it does not re-encode application messages on every hop. The
router and channel machinery pre-encode `Data`, and the peer actor just writes those frames.

The receiver half is where the protocol invariants become explicit:

- The first received message must be `Greeting`. Anything else is `MissingGreeting`.
- A second greeting is a hard error (`DuplicateGreeting`).
- The greeting's `public_key` must match the expected peer key from the handshake.
- The greeting `Info` is revalidated with `InfoVerifier` before it is handed to the tracker.

Only after that first step does the actor process ordinary traffic. From there, it handles each
payload class differently:

- `Data(channel, message)`:
  validates that the channel exists, then `try_send`s to the application receiver
- `BitVec(bit_vec)`:
  asks the tracker to compute useful peer info for this requester
- `Peers(peers)`:
  revalidates every `Info` in the batch, then forwards them to the tracker

The receive loop contains several easy-to-miss defensive details:

- It validates the channel **before** creating any channel-labeled metrics. That avoids unbounded
  metric-cardinality from attacker-chosen channel numbers.
- It rate limits `BitVec` and `Peers` after the first instance of each. The first pair is expected
  immediately after the greeting exchange, so penalizing it would punish normal startup.
- It drops application `Data` when the application-side mailbox is full instead of blocking the
  loop.

That last choice is especially important. A slow application receiver is not allowed to stall peer
discovery. By using `try_send` for application data, the actor keeps processing `BitVec` and
`Peers` even under backpressure. In other words:

> The application data plane is allowed to lose messages under pressure. The discovery control
> plane is not allowed to deadlock behind it.

### 4.5 Application Send Flow

```
sender.send(Recipients::All, message, priority=false)
    |
    | Rate check per recipient (quota)
    | Encode Data { channel: 0, message }
    | Encode into pooled buffer
    v
router Mailbox <- Message::Content { recipients: All, encoded, priority, success }
    |
    | router iterates connections, calls relay.send(encoded, priority)
    | If low-priority and relay.low is full: drop and increment dropped metric
    | If high-priority: goes through relay.high (unbounded) — never drops
    v
Encoded frames written to each peer's encrypted stream
    |
    | commonware_stream::encrypted frames and signs each message
    | Underlying TCP/TLS write
    v
Remote peer's stream receives and decrypts
    | Routes to peer's per-channel receive buffer
    | Application receiver.recv() returns (sender_pk, message)
```

---

## 5. Concurrency, Protocol, and Systems Semantics

The earlier sections described the pieces. This section is about the pressures those pieces are
designed to absorb: fan-out, stale knowledge, uneven traffic, retries, and slow peers. Read it less
as "what knobs exist?" and more as "what kinds of bad network behavior is this system trying to
turn into something survivable?"

### 5.1 Actor Topology and Mailbox Sizing

The five actors communicate via message passing with fixed mailbox sizes:

| Actor | Mailbox | Bound/Unbounded | Backpressure |
|-------|---------|-----------------|--------------|
| `tracker` | `UnboundedMailbox` | Unbounded | Never blocks sender |
| `router` | `Mailbox` | Bounded (`mailbox_size`) | Blocks sender when full |
| `spawner` | `Mailbox` | Bounded (`mailbox_size`) | Blocks dialer/listener |
| `listener` | N/A (event loop) | — | Rate limits via `KeyedRateLimiter` |
| `dialer` | N/A (event loop) | — | `select_loop!` on sleep tick |

The bounded mailboxes on router and spawner provide **backpressure**: if the router's event loop falls behind, `sender.send()` blocks at the `mailbox_size` threshold rather than growing memory indefinitely. This is the correct behavior for a system designed for adversarial environments — slow consumers should be visible, not hidden.

### 5.2 Gossip Convergence

Discovery gossip uses an **epidemic broadcast** with compact bitvectors:

- Peer set at index `i` is sorted by `PublicKey`. Position `i` in the bitvector corresponds to peer `sorted_peers[i]`.
- A `1` bit means "I have a currently valid address for this peer."
- A `0` bit means "I don't know, or my last `dial_fail_limit` dials failed."
- On receiving a `BitVec`, a peer responds with a `Peers` message containing up to `peer_gossip_max_count` `Info` records for bits where the sender has `0` and the receiver has `1`.

With `N` fully-connected honest peers and zero failures, all bits converge to `1` within
`⌈log₂(N)⌉` gossip rounds. That bound is useful because it captures the clean case where knowledge
roughly doubles each round. Real networks are noisier. Loss, stale addresses, and retry limits push
the system away from that ideal, which is exactly why the gossip protocol is careful about how it
represents uncertainty.

### 5.3 Peer Set Epochs and Tracked Sets

Peer sets are keyed by a monotonically increasing `u64` (typically an epoch number). The application calls `oracle.track(epoch, peers)` to register a new peer set. All honest peers must track the same IDs at the same values for gossip to be coherent — the bitvector index `i` means "peer at position `i` in the set at epoch `N`." If peers disagree on the set composition at a given epoch, the bitvector becomes misaligned.

`tracked_peer_sets` (default: 4) controls how many historical sets are retained simultaneously. This is critical during epoch transitions: a peer may have an outbound connection to a peer in the *previous* epoch's set. The connection is preserved (not forcibly closed) as long as that peer is in any tracked set. This allows gossip about the old set to complete even after the new set is registered.

### 5.4 Per-Channel Rate Limiting

Each registered channel has a `Quota` (messages per second) that limits send rates per recipient. The rate limiter uses a **token bucket** algorithm. If a recipient is over their quota, they are silently skipped — the message is sent to all other recipients. The sender receives back a vector of `PublicKey`s that successfully received the message, so the application can retry for the others.

### 5.5 Utility Layer: `Muxer` and `LimitedSender`

`p2p/src/utils/mux.rs`  
`p2p/src/utils/limited.rs`

These two utilities are easy to miss because they are not discovery-specific, but they explain a
lot of the application-facing behavior.

`Muxer` turns one p2p channel into many lightweight subchannels. It does that
by prefixing each message with a varint-encoded subchannel ID and maintaining a
routing table from `Channel` to a local queue. That is not an abstraction for
its own sake. It is how the crate keeps unrelated streams from sharing the same
head-of-line failure mode:

- registrations are dynamic, even after the muxer has already started
- control messages are preferred over network messages in the main loop
- delivery to each subchannel uses `try_send`, not blocking `send`
- a full or abandoned subchannel is isolated; it does not stall unrelated subchannels

So the muxer is deliberately biased toward avoiding head-of-line blocking. If subchannel 7 stops
draining, subchannel 3 still moves. If a message arrives for an unregistered subchannel, it can go
to a backup channel or be dropped, but it does not poison the whole receiver.

`LimitedSender` sits on the send side for the same reason: quota has to apply
to a concrete recipient set, not to an abstract broadcast wish. The sender
subscribes lazily to the current connected-peer set and resolves
`Recipients::All` against a **snapshot of known peers**, so rate limiting stays
tied to real capacity instead of a mythical global broadcast primitive.

That has two practical consequences:

- rate limiting is applied recipient by recipient
- when every intended recipient is over quota, `check()` returns the earliest retry time instead of
  silently dropping the whole send

The returned `CheckedSender` is intentionally narrow. It represents "these recipients passed the
limit check right now." Sending through the raw inner sender would bypass that decision, which is
why the code treats `into_inner()` as an escape hatch rather than the normal path.

### 5.6 Connection Cooldown and Retry Budget

`peer_connection_cooldown` is a per-peer rate limit on connection *attempts*. Even after a successful connection, the dialer will not attempt to reconnect to the same peer within this window. This prevents thrashing during volatile network conditions.

The code-level nuance is that reservation and dialing are not the same moment. `Record::reserve()`
sets `next_reservable_at = now + peer_connection_cooldown`, then computes a jittered
`next_dial_at` from that point. So the tracker is enforcing two related ideas:

- nobody gets to reserve this peer again too soon
- and even once the cooldown opens, future dials spread out instead of synchronizing exactly

`dial_fail_limit` (default: 2) is the number of consecutive failed dial attempts before a peer
marks a bit as `0` in its bitvector. The peer continues to accept inbound connections from that
peer, since the problem may be asymmetric routing rather than identity loss.

The failure accounting is careful. On `release()`, a dialer-owned reservation only increments the
failure counter if the failed ingress still matches the record's current discovered ingress. That
avoids blaming a new address record for an older in-flight dial attempt.

### 5.7 Block Duration and Byzantine Peers

When `block_peer()` is called via the `Blocker` trait, the peer's connection is severed and a `block_duration` timer starts. While blocked, any inbound connection from that peer is immediately rejected. After `block_duration` expires, the peer can reconnect. This is the byzantine fault tolerance mechanism: a peer that sends invalid messages is blocked, not banned forever (which would be a denial-of-service vector against honest peers).

### 5.8 Simulated Network - `Oracle` as Test Harness

`p2p/src/simulated/mod.rs`
`p2p/src/simulated/bandwidth.rs`

The simulated network implements `Manager` and `AddressableManager` so tests can swap real and simulated networks with zero API changes. The `Oracle` is the controller handle:

```rust
oracle.add_link(sender, receiver, Link {
    latency: Duration::from_millis(50),
    jitter: Duration::from_millis(10),
    success_rate: 0.95, // 5% packet loss
})
```

The surface API is intentionally simple, but the simulator's delivery model is not toy code.

Each in-flight transmission is modeled as a `Flow { id, origin, recipient, delivered }`. The
important field there is `delivered`. If a packet is going to be dropped, the planner still charges
sender egress bandwidth but does not charge receiver ingress bandwidth. That matches the physical
story: bytes that never arrive can still consume sending capacity.

When bandwidth limits exist, the simulator runs a scheduling tick whenever the active flow set
changes:

1. Build the set of active flows.
2. Register every constrained sender egress and receiver ingress resource.
3. Run progressive filling: raise every unfrozen flow at the same rate until some resource
   saturates.
4. Freeze the flows that touch the bottleneck, subtract their share from the remaining resources,
   and repeat.

That is a max-min fair allocation, not a FIFO queue with sleeps sprinkled on top. A flow gets more
bandwidth only when doing so would not make another active flow with less bandwidth strictly worse
off.

The helper functions in `bandwidth.rs` keep the time model honest by carrying
fractional progress forward instead of pretending every scheduling decision is
byte-aligned:

- `allocate()` computes the current bytes-per-second rate for each flow
- `duration(rate, remaining)` computes the next completion time, rounding up so completions are not
  scheduled early
- `transfer(rate, elapsed, remaining)` preserves fractional progress across ticks

That last point is important for fairness. The simulator does not throw away sub-byte progress every
time the schedule changes. It carries rational-valued remainder forward so repeated replanning does
not bias against slower flows.

**Latency model**: `Normal(latency_ms, jitter_ms)` sampled per message delivery. This produces realistic burst-delay patterns unlike uniform random.

**Loss model**: independent `success_rate` draw per message. A link with `success_rate: 0.5` drops half the messages — not in bursts, but randomly as if each packet had an independent coin flip.

**Determinism**: `commonware_utils::test_rng_seeded(seed)` drives all randomness. Two test runs with the same seed produce identical delivery order, which is critical for reproducing distributed bugs.

**Bandwidth limiting**: `oracle.limit_bandwidth(pk, egress_cap, ingress_cap)` sets bytes-per-second limits per peer.

**Ordering and queueing**: messages between the same ordered pair of peers remain in order. The
simulator allows the next message on that link to begin transmitting early enough that its first
byte arrives immediately after the prior message is fully received, which models pipelining without
violating per-link ordering.

**Fast path when unconstrained**: if no peer has ingress or egress caps, the simulator skips the
progressive-filling machinery entirely. That matters because many CI tests want topology and loss,
not expensive bandwidth accounting.

**Partition simulation**: `remove_link()` removes a unidirectional link. Removing both directions creates a network partition. The `oracle.blocked()` call reveals which `(P, P)` pairs are currently blocked.

That matters because the simulator is used as an assertion surface, not just as a packet shuffler.
Common tests start it under `context.with_label("network")`, drive link changes through the oracle,
and compare `context.auditor().state()` across seeded runs to confirm the same scenario really
replayed. `oracle.blocked()` is the human-readable companion to that digest: a direct check that
the paths the protocol meant to quarantine were actually blocked.

---

## 6. Failure Modes, Cancellation, and Correctness Concerns

Networking code is where vague explanations stop being harmless. A peer may be malicious, merely
slow, or just reachable from an address you were not expecting. The point of these failure sections
is to separate what the protocol forbids from what it merely mitigates. That distinction matters
more than any individual timeout value.

### 6.1 What a Byzantine Peer Cannot Do

Given valid `Info` signatures and a correct `InfoVerifier`:

- **Cannot forge address announcements**: Any `Info` with an invalid signature or wrong namespace is rejected.
- **Cannot announce a future timestamp**: Timestamps beyond `current + synchrony_bound` are rejected.
- **Cannot announce self as another peer**: Self-announcements are rejected.
- **Cannot trigger unbounded memory growth**: Bounded mailboxes + drop semantics prevent this.
- **Cannot block honest peers indefinitely**: `block_duration` is finite; honest peers can reconnect.

### 6.2 Abuse and Attack Scenarios

The crate is designed for adversarial settings, so it helps to name the concrete abuse stories the
implementation is defending against.

| Scenario | Defensive mechanism | What still happens |
|---------|---------------------|--------------------|
| **Stale or replayed peer info** | `Record::update()` only accepts strictly newer timestamps | Old info can still circulate, but it cannot overwrite fresher local state |
| **Future-dated peer info** | `InfoVerifier` rejects timestamps beyond `synchrony_bound`; `infos()` refuses to re-share info from the future relative to the local clock | A peer may still send junk and get blocked |
| **Self-announcement / identity confusion** | `InfoVerifier` rejects `public_key == me`; greeting key must equal the peer identity from the stream handshake | The connection attempt fails fast |
| **Cross-namespace replay** | Tracker gossip and stream authentication use separate namespaces | Replaying one proof in the other context does not validate |
| **Connection thrash** | Reservation state plus cooldown and jitter serialize repeated attempts | Honest recovery may take slightly longer, but the network avoids synchronized hammering |
| **IP poisoning / shared-IP crowding** | Listener-side IP/subnet rate limits and shuffled dialing reduce "everyone dials the same bad IP first" behavior | A popular IP can still cause delay; lookup mode avoids this class entirely |
| **Slow application receiver** | Peer actor drops `Data` via `try_send` when the app buffer is full | The application loses low-level payloads, but gossip and keepalives keep moving |
| **Invalid or attacker-chosen channel IDs** | The peer actor validates the channel before emitting channel-labeled metrics or delivering to the app | The peer is disconnected instead of expanding metric cardinality |

### 6.3 Failure Modes

| Failure | Symptom | Recovery |
|---------|---------|----------|
| DNS resolution failure | Peer shows as `0` in bitvector after `dial_fail_limit` attempts | Inbound connections still accepted; gossip eventually learns working address |
| TCP connection refused | Dial fails; `dial_fail_limit` decrements; bitvector clears bit | Re-dial after cooldown; peer may still be reachable inbound |
| Encrypted handshake timeout | `handshake_timeout` fires; connection dropped | Dialer retries on next tick |
| Peer crashes and restarts with new IP | Old connection closed; `Info` with new IP gossiped | Bitvectors converge to new address within `log₂(N)` rounds |
| Byzantine peer sends invalid `Info` | `InfoVerifier` rejects; peer is `block!`-ed | Block duration expires; peer can reconnect with valid `Info` |
| Application receive buffer full | `Data` dropped; discovery protocol unaffected | Application must drain buffer faster |
| Context shutdown | All actors receive `on_stopped`; connections close gracefully | Application calls `context.stop(epoch, None)` |

### 6.4 Cancellation

All async operations in the runtime are cancellable via `select!`. When `context.stop()` is called:

1. The runtime signals all actors to stop via `on_stopped`.
2. The `select_loop!` in each actor exits.
3. Connections are closed by dropping the stream/sink.
4. The `spawner` releases each peer's `Relay` from the router's map.
5. The `tracker` marks all connections as closed.

There is no explicit graceful shutdown message sent to peers — the TCP FIN serves as the signal.

### 6.5 Scheduler/Runtime Tradeoffs

`commonware-p2p` is designed to work with the abstract `ContextCell` from `commonware-runtime`. All five actors run as `spawn_cell!` tasks within this context. The scheduler is cooperative: actors yield at `select_loop!` boundaries and at `.await` points.

The critical implication for performance: **slow actors create head-of-line blocking**. The router's event loop processes `Message::Content` in order. If a high-priority message arrives while the router is processing a large `Recipients::All` fan-out, priority messages wait. This is a deliberate trade-off — simplicity of implementation over strict priority scheduling.

---

## 7. How to Read the Source Code

Do not read the p2p crate as one giant actor graph all at once. That is the fastest way to lose
the plot.

Read it in layers:

1. understand identity and addressing,
2. understand what moves over the wire,
3. understand which actor owns which responsibility,
4. only then read the live event loops.

That order turns the code from "many files with mailboxes" into one coherent transport design.

### Reading Order

1. **`p2p/src/types.rs`** — Start here. All addressing semantics (Ingress, Address, DNS resolution, private IP filtering, wire encoding) are defined here. Every subsequent file assumes familiarity with these types.

2. **`p2p/src/authenticated/mod.rs`** — The trait surface (`Manager`, `AddressableManager`, `Sender`, `Receiver`, `Blocker`). Understanding what the `Oracle` actually implements clarifies the two modes.

3. **`p2p/src/authenticated/discovery/types.rs`** — `Payload`, `Info`, `InfoVerifier`, `BitVec`. This is where the security model is enforced. Read the `InfoVerifier::validate` checks carefully.

4. **`p2p/src/authenticated/discovery/network.rs`** — The `Network::new` constructor shows how all five actors are wired together. This is the assembly diagram.

5. **`p2p/src/authenticated/discovery/actors/tracker/actor.rs`** — The tracker is the stateful core. It owns `Directory`, `Record`s, `Reservation`s, and processes `Message`s. Understanding the tracker message types reveals the full capability of the oracle.

6. **`p2p/src/authenticated/discovery/actors/router/actor.rs`** — The router is the message routing switch. It holds `BTreeMap<P, Relay<EncodedData>>` and processes `Ready`, `Release`, `Content`, and `SubscribePeers` messages.

7. **`p2p/src/authenticated/discovery/actors/spawner/actor.rs`** — The spawner is a supervisor that bridges connection establishment (from listener/dialer) to peer actors. It calls `tracker.connect()` and `router.ready()` to hand off an authenticated connection.

8. **`p2p/src/authenticated/discovery/actors/listener.rs`** — The listener is the inbound connection handler. It applies IP/subnet rate limits, private IP filtering, and concurrent handshake limits before handing off to `handshake()`.

9. **`p2p/src/authenticated/discovery/actors/dialer.rs`** — The dialer is a timed loop that asks the tracker for dialable peers and attempts one connection per tick. It resolves DNS, picks a random resolved address, and calls `encrypted::dial()`.

10. **`p2p/src/authenticated/relay.rs`** — The priority relay is a simple but critical component. `try_send` semantics mean priority senders never block, but low-priority senders can be dropped.

11. **`p2p/src/simulated/mod.rs`** — Read this last to understand the test infrastructure. `Oracle`, `Manager`, `SocketManager`, `Link`, `Control` — these form a complete in-process network that implements the same traits as the real system.

### Key Patterns

**`select_loop!` macro**: Used in all five actors. It combines a `stopped` handler, timed sleeps, and mailbox receives in one construct. This is not `tokio::select!` — it is `commonware_macros::select!` which works with the abstract runtime.

**`Metadata` enum** in tracker: `Metadata::Dialer(P, Ingress)` vs `Metadata::Listener(P, SocketAddr)` carries who initiated the connection and (for listener) the observed egress IP. The spawner passes `is_dialer` to `tracker.connect()` to route correctly.

**`Reservation` and `Releaser`**: `Reservation` holds a `Releaser` which sends a `Message::Release` on drop. This means any early return in the dialer or listener automatically releases the tracker reservation, preventing leaks.

**`Channels<P>` registry**: Created in `Network::new`, passed to `router.start()`. Each registered channel gets a separate `Sender/Receiver` pair. The channels registry is cloned and sent to each peer actor so they can check rate limits.

---

## 8. Glossary and Further Reading

### Glossary

**Bitvector (BitVec)**: A compact representation of which peers a node knows how to dial, encoded as a bitmap over a sorted peer list at a given epoch index.

**Bootstrapper**: A `(PublicKey, Ingress)` pair used to seed discovery. Peers attempt to dial bootstrappers first, then learn about the rest of the network via gossip.

**Egress IP**: The source IP address observed on an inbound connection. Used in `Address::Asymmetric` for NAT traversal and spoofing prevention.

**Gossip namespace**: The `_COMMONWARE_P2P_TRACKER` namespace used to sign `Info` records. Distinct from the `_COMMONWARE_P2P_STREAM` namespace used for stream messages.

**Ingress**: The address a peer advertises as dialable — either a direct `SocketAddr` or a DNS name to be resolved at dial time.

**Info**: A signed attestation `(ingress, timestamp, public_key)` used in gossip. Prevents address forgery.

**InfoVerifier**: The validation logic that rejects self-announcements, future timestamps, and invalid signatures in gossip.

**Oracle**: The handle returned by `Network::new`. Implements `Manager` (discovery) or `AddressableManager` (lookup). Used by the application to register peer sets and (in lookup) push address updates.

**Payload**: The four-variant enum (`Data`, `Greeting`, `BitVec`, `Peers`) that forms the entire wire protocol.

**Peer set**: A `(u64 index, Set<PublicKey>)` pair. The `u64` is typically an epoch number. All honest peers must track the same peer sets at the same indices.

**Priority relay**: A two-lane mpsc facade where `priority=true` messages go through an unbounded high lane and `priority=false` messages go through a bounded low lane.

**Reservation**: A tracker-issued permit to dial or accept a connection. Carried from dialer/listener to spawner to tracker to release.

**Synchrony bound**: A `Duration` that bounds how far into the future a gossip timestamp can be. Protects against clock skew and replay.

---

### Further Reading

- **`p2p/src/authenticated/discovery/mod.rs`** — The module doc comment is the authoritative statement of how peer discovery works. It is more complete than this chapter in some respects.
- **`commonware-stream`** (`stream/src/encrypted/`) — The encrypted stream protocol that handles the actual connection establishment and authenticated framing.
- **`commonware-codec`** — The `Encode`/`Decode` traits used for all wire format serialization.
- **`commonware-runtime`** (`runtime/src/deterministic.rs`) — The deterministic runtime that enables in-process multi-peer testing without real I/O.
- **`docs/blogs/commonware-broadcast.html`** — The broadcast protocol built on top of p2p, demonstrating how p2p is composed in a real system.
- **Alto** (`https://github.com/commonwarexyz/alto`) — A full blockchain built on Commonware, showing p2p in a production consensus context.

---

## Open Questions For Interactive UI

The following are the most valuable interactive visualizations to build for the Commonware interactive book:

### 1. Discovery Bitvector Exchange Animator

**What it shows**: A small-world network of N nodes arranged in a ring or mesh. Each node holds a bitvector initially all zeros except self. An animated tick: nodes exchange bitvectors with their neighbors, update their own bits for successful knowledge, converge to full connectivity.

**Interactive controls**:
- N (number of nodes)
- Failure rate per dial attempt (clears bits)
- `dial_fail_limit` (how many failures before a bit is cleared)
- `dial_frequency` (animation speed)
- Pause/step/play

**What to highlight**: The `log₂(N)` convergence property. Show that with N=16 and 0% failure, all bits are set by round 4. With 20% failure, convergence slows but still reaches full connectivity eventually. With 60% failure, some bits may never converge — leading to unreachable peers.

### 2. Actor Mailbox Topology Diagram

**What it shows**: An interactive schematic of the five discovery actors (tracker, router, spawner, listener, dialer) with animated message flow arrows. Click an actor to expand its mailbox size, message types handled, and which downstream actors it communicates with.

**Interactive controls**:
- Toggle between discovery and lookup topologies
- Highlight the path of an outbound vs inbound connection
- Show backpressure: slow the router's event loop and watch low-priority senders block when mailbox fills

**What to highlight**: The `Relay` dual-lane semantics. Show that priority=true jumps the queue via the unbounded `high` lane, while priority=false goes through bounded `low` and can be dropped.

### 3. Simulated Network Link Control Panel

**What it shows**: A canvas with N labeled nodes (peers) and directed edges (links). Each edge shows `(latency, jitter, loss%)`. Color-coded by delivery rate: green > 95%, yellow 80-95%, red < 80%.

**Interactive controls**:
- Drag edge weight sliders to adjust latency/jitter/loss in real time
- Click "partition" to remove all edges crossing a chosen cut
- Watch messages pile up (queue growth) on slow links or drop on lossy links
- Hit "reconnect" and watch re-convergence

**What to highlight**: How Normal-distributed jitter produces burst delays. How independent `success_rate` per message produces random loss (not burst loss). How partition detection works via missing `BitVec` keepalives.

### 4. Payload Wire Format Explorer

**What it shows**: A hex dump view of a multi-frame connection establishment:

```
Frame 1 (Greeting):
  [01]                    — prefix = Greeting variant
  [41 bytes]             — Info { ingress, timestamp, public_key, signature }

Frame 2 (BitVec):
  [02]                   — prefix = BitVec variant
  [08 00 00 00 00 00 00] — index = 8 (varint)
  [1F]                   — bits = 00011111 (5 bits set for first 5 peers)

Frame 3 (Data):
  [00]                   — prefix = Data variant
  [00 00 00 00]          — channel = 0 (varint)
  [0D 00 00 00]          — message length = 13 (varint)
  [68 65 6c 6c 6f ...]  — "hello, world"
```

**Interactive controls**:
- Click any field to see its meaning and valid range
- Corrupt a byte and show what happens: `InvalidEnum`, `InvalidLength`, `UnexpectedEof`
- Toggle between `Ingress::Socket` and `Ingress::Dns` encoding to see the prefix difference

**What to highlight**: The `MAX_PAYLOAD_DATA_OVERHEAD = 1 + 10 + 5 = 16` bytes of fixed overhead per data frame. How the prefix byte determines which variant is being decoded. Why the codec uses varint encoding for length fields.

### 5. Asymmetric Address NAT Traversal Demo

**What it shows**: Two nodes, each behind a distinct NAT. Node A has `Ingress::Dns { host: "node-a.example.com" }` but its egress is `1.2.3.4`. Node B has `Ingress::Dns { host: "node-b.example.com" }` but its egress is `5.6.7.8`.

**Interactive step-through**:
1. A connects to B's DNS name → B sees connection from egress `1.2.3.4`
2. B's `InfoVerifier` checks: is this in B's `tracked` set? Yes (A is in B's peer set).
3. B responds with `Info { ingress: Dns("node-b.example.com"), egress: 5.6.7.8 }`
4. A receives B's Info, updates directory to `Asymmetric { ingress: Dns("node-b.example.com"), egress: 5.6.7.8 }`
5. Subsequent connections from B to A: A's listener checks `egress` matches `Address::Asymmetric { egress: 5.6.7.8 }` — if not, reject.

**What to highlight**: Why `Symmetric` is insufficient for NAT. How `egress` filtering prevents address spoofing. How gossip propagates the egress IP before the first outbound connection succeeds.

### 6. Priority Relay Backpressure Demo

**What it shows**: A single peer's `Relay` with a `low` lane of size 3 and `high` lane unbounded. Fill the low lane with low-priority messages, then send a high-priority message.

**Interactive controls**:
- Toggle priority flag on each send
- Observe: low-priority sends block when low lane is full
- Observe: high-priority sends always succeed
- See the metrics (`messages_dropped_total`, `messages_rate_limited_total`) update

**What to highlight**: The design invariant: priority=true never blocks and never drops. Low-priority senders absorb backpressure from slow consumers. This is the correct trade-off for adversarial environments: important messages are never delayed by unimportant ones.
