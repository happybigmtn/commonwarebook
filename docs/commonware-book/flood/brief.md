# commonware-flood Interactive Book Chapter - Brief

## 1. Module Purpose

`commonware-flood` is a wind tunnel for authenticated p2p deployments. It is
not a benchmark harness in disguise. The crate asks a harder question than
"can two peers exchange bytes?": what happens when a whole mesh of peers all
try to talk at once, across real cloud machines, with real queue limits, real
network latency, and real failure modes?

The chapter should read like a lecture on pressure, fan-out, and what breaks
when a deployment is asked to carry too much traffic at once. The command line
is only the surface. The real lesson is the pressure model:

- one message becomes fan-out to every peer,
- every peer is both sender and receiver,
- the queues in p2p become observable pressure points,
- the deployment itself becomes part of the test.

The example has two halves:

- `setup` builds a distributed deployment plan, generates peer identities, and
  writes the per-instance configuration that turns a group of EC2 machines into
  one test network.
- `flood` boots the network, registers every peer as an allowed participant,
  and then continuously sends timestamped random messages to all peers at once
  while recording delivery latency.

`commonware-flood` composes most directly with:

- `commonware-p2p` for authenticated discovery and channel delivery
- `commonware-deployer` for building and managing the EC2 fleet
- `commonware-runtime` for task execution, telemetry, and metrics
- `commonware-cryptography` for peer identities and signing
- `commonware-utils` and `commonware-codec` for key handling and decoding

---

## 2. Key Source Files

### `examples/flood/src/lib.rs`

Defines `Config`, the shape of the workload. The fields are the pressure
surface: peer credentials, listening port, allowed peers, bootstrappers, worker
threads, message size, message backlog, mailbox size, and instrumentation
switches. This is the one type that explains what the example thinks matters.

### `examples/flood/src/bin/setup.rs`

Builds the deployment artifact. It generates peer keypairs, chooses
bootstrappers, spreads peers across regions, and writes both the per-peer YAML
configs and the root deployer config. This file is where the workload becomes a
topology.

### `examples/flood/src/bin/flood.rs`

Runs the actual stress loop. It loads hosts and config, constructs a discovery
network, registers all authorized peers, spawns one task that floods messages
and another that records latency, and then waits for any task to fail. This is
the file that turns "deployment" into "load".

---

## 3. Chapter Outline

1. **Why Flood Exists** - Why a mesh under load teaches more than a pair of
   nodes exchanging packets.
2. **Mental Model** - A pressure chamber or wind tunnel for the network.
3. **The Workload Shape** - How `Config` turns concurrency, queueing, and
   instrumentation into an experiment.
4. **How the Deployment Is Built** - How `setup` turns identities, regions, and
   bootstrappers into a real network.
5. **How the Flood Runs** - The sender loop, the receiver loop, and the meaning
   of `Recipients::All`.
6. **What Gets Measured** - Why the timestamp lives in the first 8 bytes and
   how the latency histogram turns delivery into evidence.
7. **What Pressure the Design Absorbs** - Fan-out, queue growth, slow peers,
   and cross-region latency.
8. **Failure Modes and Limits** - EC2 throttling, missing credentials, small
   message sizes, and why it is a stress case rather than a proof.
9. **How to Read the Source** - The shortest path from configuration to load.

---

## 4. Concepts to Explain in the Chapter

- **Fan-out as a stress multiplier** - A single send becomes traffic to every
  peer. The important effect is not linear growth in bytes; it is the way a
  broadcast turn can fill queues everywhere at once.
- **Deployment as part of the experiment** - The AWS layout, bootstrapper set,
  and allowed peers are not surrounding machinery. They define the shape of the
  test.
- **Timestamped payloads as probes** - The first 8 bytes are a time capsule.
  They do not carry protocol meaning. They exist so the receiver can measure how
  long a message spent in flight.
- **Backlog and mailbox as pressure valves** - These limits decide whether the
  network absorbs bursts or reveals them as blocking, delays, or errors.
- **Metrics as the observable output** - The example is not trying to be
  clever. It is trying to make the bottlenecks visible.

---

## 5. Claims to Verify

- [ ] `setup` refuses invalid topology inputs such as more bootstrappers than
      peers.
- [ ] `flood` enforces a minimum message size large enough to store the
      timestamp.
- [ ] `Recipients::All` really fans a message out to the full authorized peer
      set.
- [ ] The latency histogram records time between send and receive, not just
      time spent in the local process.
- [ ] Queue limits surface pressure instead of silently hiding it.
- [ ] EC2 throttling can explain some slowdowns, so the deployment must be part
      of the reading of the results.
