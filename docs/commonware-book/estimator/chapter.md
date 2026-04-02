# commonware-estimator

## A Wind Tunnel for Distributed Mechanisms

---

## Why Performance Needs a Shape

Distributed performance is not one number. A mechanism can look fast in one
region, slow in another, and completely different once the proposer changes or
a threshold is crossed. So the first lesson is to stop asking for a single
average and start asking for the contour of the cost.

The useful vocabulary is latency, jitter, bandwidth, backlog, threshold, and
placement. Latency is how long one message takes. Jitter is how much that
delay varies. Bandwidth is how much data can move. Backlog is how much work
can pile up before the system has to wait. A threshold is the point where
enough responses have arrived to move forward. Placement is where the peers
and leaders happen to live. A realistic experiment has to consider all of them
at once.

The naive approach is to run one benchmark on one machine, with one proposer,
and trust the result. That hides the hardest parts of the problem. It hides
geography by putting everyone on the same host. It hides leadership bias by
keeping the proposer fixed. It hides protocol cliffs by using tiny messages or
small loads that never cross the thresholds where real costs appear.

The better tradeoff is a wind tunnel, not a scoreboard. A wind tunnel keeps
the scenario controlled enough to repeat, but varied enough to show where the
drag appears. That means accepting some simplification, like modeled region
links instead of a full internet trace, in exchange for a measurement that can
be rerun, compared, and reasoned about. `commonware-estimator` is built
around that tradeoff: more structure than a benchmark, less fantasy than an
idealized proof.

## 1. What Problem Does This Solve?

When a new distributed mechanism looks good on a laptop, the result is often
less meaningful than it seems. A laptop gives the mechanism a gift that real
deployments never get: one machine, one clock, one network, and one proposer
that is usually sitting next to the rest of the system.

That makes the measurement look clean in exactly the wrong way.

The real mistake is to treat performance as a single number. In a distributed
system, performance has shape:

- some peers are close together and some are not,
- some regions have more bandwidth than others,
- one proposer can make the mechanism look fast while another makes it look
  sluggish,
- and one blocking step can hide the cost of everything that comes after it.

`commonware-estimator` exists to make that shape visible before the protocol
is deployed. It does not prove safety or liveness. It does something narrower
and more useful for design work: it turns a mechanism into a repeatable
measurement experiment.

That is why I think of it as a wind tunnel for distributed mechanisms. You
put the design in the tunnel, blow realistic network conditions across it, and
watch where the drag appears.

---

## 2. Measurement Shape

The point of the estimator is not to tell you whether a mechanism is "fast"
in the abstract. It is to show you the contour of its cost.

A good design may look flat in one region and steep in another. It may stay
smooth while traffic is small, then hit a cliff when a threshold step or a
larger message arrives. It may behave well when leadership starts in one
region and very differently when leadership moves somewhere else.

That is the kind of shape you want before deployment. A single number hides
the bends. A measurement shape makes them visible.

---

## 3. The Wind Tunnel

The easiest picture is a lab bench with two layers.

The bottom layer is the network model:

- a set of AWS regions,
- a peer count per region,
- optional ingress and egress limits for each region,
- and a latency matrix that says how expensive it is to talk from one region
  to another.

The top layer is the mechanism script:

- send a proposal,
- wait for replies,
- collect a quorum,
- broadcast the next phase,
- and keep going until the script is done.

The important point is that the script is not a toy example of the network.
It is the mechanism's actual control flow, expressed in a tiny DSL. That lets
the simulator ask a useful question:

**What happens to this logic when the environment becomes geographical?**

One more detail matters a lot: the simulator rotates the proposer. If a
mechanism only looks good when the proposer is in the fast region, that is not
a lucky result. It is a warning. By running the same task once per proposer,
the estimator exposes how leadership placement changes the observed latency.

So the mental model is not "a benchmark." It is "the same protocol story,
performed under every plausible lead actor, with a realistic stage."

---

## 4. The Instruments

### 4.1 Geography becomes friction

`examples/estimator/src/lib.rs` defines a `Distribution` as a map from region
name to `RegionConfig`. Each region carries:

- a peer count,
- an optional egress cap,
- and an optional ingress cap.

That design matters because the network is not treated as abstract background.
The placement of peers is part of the experiment itself. A mechanism that
spans `us-east-1` and `ap-southeast-2` is not just "more distributed" than one
that stays in a single region. It is operating under a different cost
structure.

### 4.2 CloudPing becomes latency and jitter

The simulator loads CloudPing matrices from `p50.json` and `p90.json`, or
downloads fresh values if the user asks for a reload. Those tables are not
used as a direct "ping = latency" copy.

Instead, the code turns them into a simpler model:

- one value for average latency,
- one value for jitter.

CloudPing reports round-trip timing, so the model splits each value into an
approximate one-way delay and uses the gap between p50 and p90 as a coarse
jitter band. That is not a physics experiment. It is a practical way to keep
the shape of real regional links without pretending to be more precise than
the data supports.

### 4.3 Message size bends the line

The simulator lets message commands carry a `size` parameter. That seems like
a small detail until bandwidth caps enter the picture.

A protocol with 4-byte messages and a protocol with 4 KB messages do not pay
the same cost on a limited link. Without message size, the model would miss an
entire class of delays. With it, the estimator can ask whether the mechanism
still looks good once proposals, votes, or certificates are large enough to
matter.

### 4.4 Thresholds create cliffs

The task file is where a protocol becomes measurable.

The DSL has a small set of commands:

- `propose` sends a message from the current proposer to everyone.
- `broadcast` sends a message to everyone.
- `reply` sends a message back to the proposer, or records the proposer's
  local receipt.
- `wait` blocks until enough messages of a given ID have arrived.
- `collect` does the same thing, but only matters for the proposer.

The command set is intentionally small because the point is not to build a new
language. The point is to model the moves that matter in consensus-like and
broadcast-like mechanisms: propose, respond, wait, and collect.

Compound expressions with `&&` and `||` let the script express control flow
that would otherwise require bespoke code. That is useful because protocols do
not just wait for one threshold. They often wait for a threshold and then one
more condition, or for either of two possible conditions to become true.

### 4.5 Statistics are the readout

The simulator does not stop at a run ending. It records when each tracked line
of the task first unblocks, then prints:

- proposer latency,
- per-region latency,
- overall latency across all regions,
- and finally aggregated results across every proposer run.

That gives the reader three different views of the same mechanism:

- where the proposer spends time,
- where each region spends time,
- and what the mechanism looks like in aggregate when leadership moves
  around.

The experiment is therefore not "did it finish?"
The experiment is "what did it cost, and where did the cost land?"

---

## 5. How the Tunnel Runs

The main flow in `examples/estimator/src/main.rs` is easier to understand as
one experiment loop than as a sequence of setup chores.

The CLI reads a task file and a region distribution. That is the experiment
definition: what behavior to simulate and under what placement.

The distribution parser accepts per-region peer counts and optional bandwidth
limits. That makes the network shape explicit instead of hidden in code.

The estimator loads cached CloudPing data unless `--reload` is set. From there
it builds a region-to-region latency table that every simulated link can use.

For each proposer index, the simulator starts a deterministic runtime seeded by
that proposer index. That choice is subtle but valuable. It means the same
proposer run can be reproduced, and different proposers do not share the same
random stream.

The simulator registers every peer, assigns it to a region, and applies the
region's bandwidth caps. It then connects every peer pair with a simulated
link whose latency and jitter come from the table built earlier.

Each peer steps through the DSL in lockstep with the others. Commands that
simply send messages advance immediately. Commands that wait for a threshold
block until enough matching messages have been received. Compound expressions
only advance when their subexpressions say they can.

The interesting part is that the simulator records the moment a blocking step
unblocks. That timestamp is what later becomes the latency output.

After one run finishes, the simulator repeats the same task with the next peer
as proposer.

That is the whole point of the estimator's reporting model:

- see one run,
- then see all runs,
- then compare them.

The aggregated output is the answer to the design question. If the same
mechanism looks very different depending on proposer placement, the design is
telling you something real.

---

## 6. What Pressure It Is Designed To Absorb

The first pressure is **regional skew**.

In a real deployment, a quorum is not just a quorum. It is a quorum across a
geography. The estimator makes that visible by forcing every peer to live in a
region and by charging every link the cost of that placement.

The second pressure is **bandwidth bottlenecks**.

A mechanism that only sends tiny messages may look fine on latency alone. As
soon as proposals, votes, or certificates grow, the time spent moving bytes
starts to matter. Region-specific egress and ingress caps let the simulator
show those delays.

The third pressure is **control-flow complexity**.

Protocols are rarely a straight line. They wait for this condition or that
condition, and sometimes they need both. The DSL's `&&` and `||` operators let
the mechanism express those branches without turning the example into a full
language implementation.

The fourth pressure is **repeatable comparison**.

Because the runtime is deterministic, the same proposer run can be reproduced
exactly. Because the proposer rotates, the experiment does not overfit to one
leadership placement. Those two properties together make the output useful for
design work.

---

## 7. Failure Modes and Limits

The estimator is intentionally not a correctness machine.

It does not prove that a protocol is safe.
It does not prove that a protocol is live.
It does not tell you whether the mechanism is good in the abstract.

It only tells you how the mechanism behaves under a particular network model.

That model has limits:

- CloudPing data is a snapshot-based approximation, not a live Internet probe.
- The DSL is expressive enough for the example's target class, but it is not a
  general-purpose programming language.
- The simulator assumes the interesting part of the mechanism can be captured
  as message flow plus threshold logic.
- The statistics are descriptive, not magical. They summarize a run; they do
  not explain away protocol design mistakes.

Those limits are not flaws. They are the boundary that makes the tool useful.
The crate is trying to answer a specific kind of design question, and it stops
where that question stops.

---

## 8. How to Read the Source

Read the source as the life cycle of one experiment, from task definition to
latency readout.

Start with `examples/estimator/src/main.rs`.

Read it as the experiment loop:

1. parse the CLI,
2. load the task,
3. build the network model,
4. run the simulation once per proposer,
5. print the observed latencies,
6. then print the aggregate view.

After that, move to `examples/estimator/src/lib.rs`.

That file explains the idea behind the experiment:

- how the DSL is parsed,
- how thresholds are converted into required counts,
- how CloudPing data becomes the latency table,
- and how the simulation decides whether a command can advance.

Finally, glance at `examples/estimator/src/p50.json` and
`examples/estimator/src/p90.json`.

Those files are not prose, but they are the data source that gives the whole
example its realism. If you want to understand why the simulated links feel
geographically specific, those matrices are the reason.

---

## 9. Glossary and Further Reading

- **Proposer rotation** - running the same mechanism once per peer so the
  effect of leadership placement is visible.
- **Threshold command** - a blocking step that waits for some count or percent
  of the network.
- **CloudPing** - the external latency source used to approximate region-to-
  region delay and jitter.
- **Jitter** - the variance around the baseline latency of a link.
- **Measurement shape** - the contour formed by latency, bandwidth, and
  leadership placement together.
- **Simulated network** - the all-to-all region graph built by the runtime
  before the task script starts moving messages.
