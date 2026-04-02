# Chapter Brief: commonware-estimator

## 1. Module Purpose

`commonware-estimator` answers a question that matters any time someone says
"the mechanism is fast enough" before the mechanism has seen a real network:
what shape does that performance take when geography, bandwidth, and
leadership start pushing back?

The naive approach is to benchmark on one machine, in one region, with one
happy-path proposer. That gives you a number, but not a contour. It hides the
forces that usually decide whether a mechanism feels fast in practice:

- geography, which changes the cost of every message,
- skew, which changes who pays that cost first,
- and bandwidth, which changes when the design starts to bend instead of
  merely slow down.

This example turns that guesswork into a repeatable wind tunnel. It builds a
network from AWS region pairs, applies realistic latency and jitter from
CloudPing data, optionally limits egress and ingress bandwidth, and then runs
a task script that describes the mechanism's message flow. The output is not a
proof of correctness. It is a measurement shape: latencies by line, by region,
by proposer, and across all runs.

The crate's job is to make a mechanism measurable before it is deployed.
That is why the chapter should feel like a lecture about pressure, drag, and
contour, not a tidy simulation walkthrough.

---

## 2. Source Files That Matter Most

### `examples/estimator/src/main.rs`
Why it matters: this is the orchestration layer. It parses the CLI, builds the
simulated network, runs each proposer through the same task script, collects
per-line timings, and prints both single-run and aggregated statistics.

### `examples/estimator/src/lib.rs`
Why it matters: this is the model layer. It defines the DSL, the threshold and
region types, the latency table loader, the statistics helpers, and the
validation logic that tells you whether a task file can actually advance.

### `examples/estimator/src/p50.json` and `examples/estimator/src/p90.json`
Why they matter: these are the cached CloudPing matrices. They are the
real-world latency samples that the simulator turns into average latency and
jitter for each region pair.

### `examples/estimator/README.md`
Why it matters: it shows the user-facing DSL and output format, but the
chapter should treat it as a reference, not the main story.

---

## 3. Chapter Outline

1. Why performance is a contour, not a scalar
   - a single-region benchmark hides the real shape of a mechanism
   - proposer placement changes the contour
   - bandwidth turns delay into drag

2. Mental model: a wind tunnel for mechanisms
   - region pairs become the airflow around the design
   - the task script is the flight plan through the tunnel
   - the point is to see where the mechanism bends, stalls, or compounds delay

3. Core ideas
   - the region distribution and bandwidth caps
   - CloudPing p50/p90 data turned into latency and jitter
   - the DSL commands: `propose`, `broadcast`, `reply`, `wait`, `collect`
   - compound logic with `&&` and `||`
   - per-line statistics and proposer-rotation aggregation

4. How the tunnel is built
   - parse the task file
   - load or refresh latency data
   - build a deterministic simulated network
   - run one simulation per proposer
   - record completions when commands unblock
   - print regional and aggregate statistics

5. What pressure it is designed to absorb
   - realistic region skew
   - bandwidth bottlenecks
   - threshold-based blocking
   - compound conditions that model real protocol control flow
   - reproducible runs across proposers

6. Failure modes and limits
   - it estimates performance; it does not prove liveness or safety
   - the DSL is intentionally small
   - latency is a sampled approximation, not live Internet measurement
   - the model assumes the mechanism can be expressed as message flow plus
     threshold checks

7. How to read the source
   - start with `main.rs` to see the experiment loop
   - then read `lib.rs` for the DSL and measurement primitives
   - finally inspect the cached CloudPing matrices and the README examples

8. Glossary and further reading
   - proposer rotation
   - threshold command
   - CloudPing
   - jitter
   - measurement shape
   - simulated network

---

## 4. System Concepts To Explain

- **A mechanism is a script, not just code.** The DSL turns a protocol idea
  into a sequence of message operations and blocking conditions that can be
  replayed under different region placements.
- **Performance has contour.** The estimator is looking for bends, cliffs, and
  plateaus, not a single best-case number.
- **Performance depends on who starts where.** The simulator rotates the
  proposer through every peer so the reader can see how a mechanism behaves
  when leadership moves across regions.
- **Latency is geography plus variance.** CloudPing's p50 and p90 matrices are
  transformed into a per-link latency and jitter model, which is good enough
  to expose the cost of long-haul communication.
- **Bandwidth changes the story.** Message size and per-region caps matter
  because a mechanism that looks fine on an empty network can stall once
  larger messages or asymmetric links enter the picture.
- **Statistics are the final product.** The crate is not trying to narrate
  each packet. It is trying to answer "what happened, where, and how often?"
  with mean, median, and standard deviation.

---

## 5. Visuals To Build Later

1. **Wind-tunnel plate** - a protocol sketch in a tunnel of region-to-region
   latency bands, showing where delay thickens around the design.
2. **Script-to-run plate** - one `.lazy` file on the left, one proposer run on
   the right, with each command lighting up when it unblocks.
3. **Proposer rotation plate** - a table that shows how the same mechanism
   changes when leadership moves across regions.
4. **Bandwidth choke plate** - a pair of links with different caps and message
   sizes to show why latency alone is not enough.
5. **Statistics plate** - per-line mean/median/stddev grouped by region and
   then rolled up across all proposers.

---

## 6. Claims-To-Verify Checklist

- [ ] The chapter explains why a single-region benchmark is not a good proxy
      for a distributed mechanism.
- [ ] The wind-tunnel mental model stays consistent from start to finish.
- [ ] The reader understands that CloudPing data becomes a latency and jitter
      matrix.
- [ ] The DSL is explained as a way to express message flow and blocking
      conditions, not as the point of the crate.
- [ ] The prose makes clear that rotating the proposer is part of the
      experiment design.
- [ ] The chapter stays short enough to read like a case study.
