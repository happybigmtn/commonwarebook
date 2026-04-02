# commonware-flood

*A pressure chamber for p2p deployments, and a guide to reading the result.*

---

## Why Networks Need a Wind Tunnel

A p2p network is not healthy just because two peers can exchange a packet.
The interesting failures show up when many peers talk at once, queues begin to
fill, and the scheduler has to decide what can move now and what has to wait.
That is the difference between a link test and a deployment test.

`commonware-flood` exists to make that difference visible. It creates a
controlled broadcast workload, runs it against a real EC2 deployment, and then
helps you interpret what happened. The example is not only about pressure
creation. It is about diagnosing where the pressure landed.

The useful vocabulary is fan-out, backlog, mailbox, latency, throughput, and
observability. Fan-out is how many recipients one send becomes. Backlog is the
work waiting to be handled. A mailbox is the bounded place where inbound work
lands. Latency tells you how long the message spent in the system. Throughput
tells you how much traffic survived the path. Observability tells you which of
those limits you actually hit.

## 1. What Problem Does This Solve?

It is easy to make a p2p deployment look fine if you only test one connection
at a time. Two nodes can shake hands, exchange a few packets, and leave you
with the false impression that the network is healthy.

That does not tell you what happens when the whole deployment behaves like a
single loud participant:

- every peer is sending,
- every peer is receiving,
- every queue is under pressure,
- every link is carrying more than the happy path.

The example turns that situation on purpose. It is a stress exercise for
Commonware p2p deployments, but it is also a measurement exercise. The point is
to see whether the mesh slows down, where the slowdown begins, and whether the
cloud itself is part of the bottleneck.

## 2. Mental Model

Think of the example as a pressure chamber.

- `setup` builds the chamber.
- `flood` turns on the pump.
- the p2p network is the surface being stressed.
- the histogram and counters are the gauges.

Each message is a probe. The first 8 bytes carry the send timestamp, and the
rest is random data. The payload is intentionally uninteresting. The timestamp
is what matters. By the time the receiver reads it back, the message has
already explained how long it spent in transit.

The crucial detail is fan-out. One send becomes traffic to all peers. That
means the interesting question is not whether a packet can move. It is what
happens when many packets are trying to move through the same mesh at once.

## 3. The Core Ideas

### 3.1 The config describes the experiment

[`examples/flood/src/lib.rs`](/home/r/coding/monorepo/examples/flood/src/lib.rs)
defines `Config`, and its fields are workload shape, not just tuning knobs:

- `worker_threads` controls how much concurrency the runtime can drive.
- `message_size` controls how much data each probe carries.
- `message_backlog` controls how many sends can pile up.
- `mailbox_size` controls how much inbound pressure each actor can absorb.
- `instrument` controls whether the evidence is exported.

This matters because the example is teaching a systems lesson, not a benchmark
number. Performance is the result of a workload shape meeting a queueing
system.

### 3.2 `setup` turns topology into part of the test

[`examples/flood/src/bin/setup.rs`](/home/r/coding/monorepo/examples/flood/src/bin/setup.rs)
generates one private key per peer, derives the allowed peer list, chooses a
subset of bootstrappers, and spreads the peers across the requested regions.
Then it writes the deployer config, one host file per peer, and the dashboard
artifact.

That is not scaffolding around the test. It is the test. If you change the
regions, you change the latency profile. If you change the bootstrappers, you
change discovery. If you change the instance type, you change where throttling
appears.

### 3.3 `flood` makes every peer both source and sink

[`examples/flood/src/bin/flood.rs`](/home/r/coding/monorepo/examples/flood/src/bin/flood.rs)
loads the generated deployment, constructs an authenticated discovery network,
registers a flood channel, and starts the runtime loop.

The important shape is:

- all peer keys are tracked as authorized participants,
- the sender broadcasts to `Recipients::All`,
- the receiver measures end-to-end delay,
- every node emits traffic and absorbs traffic at the same time.

That symmetry is what creates the pressure. A node is not just a client or just
a server. In this example it is both.

### 3.4 The first 8 bytes are the measurement

The sender loop does three things:

1. write the current time into the first 8 bytes,
2. fill the rest with random bytes,
3. send the message to all peers.

The receiver decodes that timestamp and records latency in a histogram. The
payload itself is only there to keep the traffic realistic and nontrivial.
The timestamp is the actual instrument.

This is the simplest possible probe that still tells the truth.

### 3.5 Pressure valves matter as much as message creation

Flood does not remove queues. It exposes them.

The p2p network is configured with `message_backlog` and `mailbox_size`.
Those limits decide how much burst pressure can be absorbed before something
has to give. The send loop logs failures instead of hiding them, because a
stress tool should make saturation visible.

## 4. How to Read a Run

The best flood runs are the ones you can interpret.

If the `messages` counter climbs steadily and the latency histogram stays
tight, the deployment is keeping up. If the histogram widens before send
errors appear, queueing is starting to dominate. If send errors show up first,
the sender side or the network path is hitting a limit before the receiver
path does.

Some common patterns are worth reading directly:

- Rising latency with no send errors usually means buffering, not failure.
- Send failures plus `bw_out_allowance_exceeded` or similar EC2 counters point
  at cloud throttling.
- One region lagging behind the others usually points to topology or
  cross-region distance.
- A stalled receiver with a busy sender usually means the mailbox or worker
  budget is too small for the workload.
- A flat histogram with very few samples often means the workload never really
  left the sender, or the deployment never formed correctly.

The example is only useful if you read the metrics and logs together. Silence
is not success here.

## 5. Bottleneck Diagnosis

The chapter is trying to teach diagnosis, not just pressure generation.

### Fan-out pressure

Broadcasting to all peers multiplies the work per send. Even a small message
creates coordination cost because every peer has to receive, queue, and
process traffic.

### Queue pressure

Finite `message_backlog` and `mailbox_size` are intentional. They define the
place where the system starts to say "enough." If the queue never fills, the
workload is too small. If it fills immediately, the workload is too large.

### Cross-region pressure

Because `setup` can distribute peers across regions, the workload can expose
the difference between local success and distributed reality. If the slow
tail only appears cross-region, the problem is likely distance or routing, not
the protocol itself.

### Scheduler pressure

`worker_threads` matters because the runtime has to keep the sender, receiver,
network actors, and telemetry active together. If the machine cannot keep up,
the histogram will tell you long before the deployment looks obviously broken.

### Observability pressure

The counters and histogram are the evidence. Without them, flood is just a
noisy script. With them, it becomes a way to locate the bottleneck.

## 6. Failure Modes and Limits

The example is honest about what it can and cannot tell you.

- It does not prove correctness. For that you need protocol tests and
  invariants.
- It depends on the cloud being part of the test. If EC2 throttles traffic, the
  measurements should reflect that.
- It assumes the deployment was generated correctly. Bad credentials, a wrong
  host map, or an inconsistent peer set should fail early.
- It does not hide queue pressure. Send failures are logged, not papered over.
- It has hard size and topology rules. `message_size` is forced to at least 8
  bytes so the timestamp fits, and the bootstrapper and region counts must be
  consistent with the requested deployment.

## 7. How to Read the Source

1. Read [`examples/flood/src/lib.rs`](/home/r/coding/monorepo/examples/flood/src/lib.rs)
   first. It names the workload shape.
2. Read [`examples/flood/src/bin/setup.rs`](/home/r/coding/monorepo/examples/flood/src/bin/setup.rs)
   next. It turns the workload into a real deployment.
3. Read [`examples/flood/src/bin/flood.rs`](/home/r/coding/monorepo/examples/flood/src/bin/flood.rs)
   last. It shows how load, fan-out, and measurement meet.
4. Use the p2p discovery docs to understand how `oracle.track(...)` defines the
   active set.
5. Use the deployer docs to see how the cloud becomes part of the experiment.

Read that way, the example is not a CLI reference. It is a method for turning
a deployment into a readable pressure test.

## 8. Glossary and Further Reading

- **Fan-out** - One send becoming traffic to every peer.
- **Backlog** - Messages waiting to be sent.
- **Mailbox** - The bounded queue for an actor or channel.
- **Bootstrapper** - A seed peer that helps the network get started.
- **Oracle** - The handle returned by the p2p network for registering the
  peer set.
- **Pressure chamber** - A useful mental model for this example: a place
  where the deployment is deliberately stressed so bottlenecks become visible.

Further reading:

- `examples/flood/README.md` for the operator workflow
- `examples/flood/src/bin/setup.rs` for deployment generation
- `examples/flood/src/bin/flood.rs` for the runtime pressure loop
- `docs/commonware-book/p2p/chapter.md` for the networking model this example
  depends on
