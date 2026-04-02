# commonware-sync

## Chasing a Moving Proof-Backed Target

---

## Opening Apparatus

**Promise.** This chapter shows how a client stays aligned with a remote
database that keeps changing, without mistaking "the server said so" for a
proof-backed state transition.

**Crux.** Synchronization is not copying. It is a repeated act of naming a
target root, fetching just enough history to justify it, verifying the proof,
and then starting over when the target has already moved again.

**Primary invariant.** The client should only advance by operations and proofs
that match one concrete target. A root is only worth chasing if the transition
to it is still legible.

**Naive failure.** The easy story is "dial the server, download what it has,
and call that sync." That fails the moment the server keeps writing, the wire
reorders responses, or the database flavor changes what "current state" means.

**Reading map.**

- `examples/sync/src/databases/mod.rs` names the shared `Syncable` contract.
- `examples/sync/src/net/wire.rs` names the two actual questions on the wire.
- `examples/sync/src/net/resolver.rs` and `io.rs` show how the client keeps
  requests and responses straight.
- `examples/sync/src/bin/server.rs` shows how targets and proofs are served.
- `examples/sync/src/bin/client.rs` shows the repeated reconciliation loop.

**Assumption ledger.**

- The reader is comfortable with request/response protocols and asynchronous
  tasks.
- The target root is assumed to be cryptographically meaningful, even though
  the example lets the server announce it directly for simplicity.
- The chapter is about the mechanism of proof-backed synchronization, not the
  CLI flags.

---

## Synchronization Before the Code

Synchronization sounds like copying, but copying is only the last mile. The
real problem is that the thing you are copying keeps moving while you are
trying to copy it. So the system has to answer three questions in order: what
target do I want, what evidence gets me there, and how do I know the target
has not changed underneath me?

A useful vocabulary helps. A root is a compact name for a state. An operation
is one step in the history that led there. A proof explains why a batch of
operations is enough to justify the root. Reconciliation is the act of
comparing the local view with the remote view and deciding what to do next.
The target is not just "the latest thing". It is a concrete state named by a
root and supported by proof.

The naive approach is to fetch everything, verify it once, and call the result
synchronized. That fails if the source keeps appending data, if the network
reorders messages, or if the database flavor changes the meaning of "current".
Another naive approach is to poll the server until it stops changing. That can
livelock forever in a live system, and it still does not tell you which
transitions were justified.

The better tradeoff is to sync in bounded pieces. You name one target, fetch
only the proof-backed history needed for that target, verify it, and then
repeat. That gives you a narrow protocol surface, predictable work per step,
and a clean place to detect cancellation, retries, and stale responses. The
cost is that the client must tolerate churn, because the target may move again
before the next round begins.

## 1. What Problem Does This Solve?

This chapter is not about wiring two binaries together. It is about what it
means to keep a local database aligned with a remote database that does not
stop moving.

That distinction matters. If the client copied the server once and treated the
result as permanent, it would be stale almost immediately. If it accepted
whatever the server sent without proof, it would be fast but untrustworthy.
`commonware-sync` shows the middle path: chase a target root, verify the proof
that justifies it, and repeat when the target moves.

That gives the chapter its real sentence:

> synchronization is not a copy operation. It is a reconciliation loop with
> evidence.

The important roles are:

- the **server**, which keeps extending the log and serving evidence,
- the **wire protocol**, which names the exact questions the client is allowed
  to ask,
- the **resolver**, which turns those replies into typed sync results,
- the **sync engine**, which applies batches and verifies proofs,
- and the **database flavor**, which decides what the same operations mean once
  they land.

The example keeps those roles separate on purpose. That is what lets the reader
see the moving target, the proof that supports it, and the reconciliation work
that bridges them.

---

## 2. Mental Model

The cleanest image is a surveyor following a boundary that keeps being redrawn.

- The **server** moves the boundary by appending new operations.
- The **target root** is the current line the client is trying to reach.
- The **historical proof** is the record that shows how the old line connects
  to the new one.
- The **client** is the surveyor, checking each segment before stepping
  forward.
- The **resolver** is the messenger that carries the questions and answers
  across the network.

The surveyor does not trust a new line because it looks convenient. The
surveyor wants the evidence that makes the line legible. That is why the
server serves both the current target and the operations needed to reach it.
The client only advances after the proof and the target agree.

The database flavor is the terrain:

- `any` shows a direct operations log and a direct root.
- `current` shows the same operations, but rebuilds a current-state view after
  sync.
- `immutable` shows a log-oriented database whose retained operations stay
  active.

Different terrain, same lecture. The reader keeps learning the same lesson:
follow the target, verify the proof, reconcile the state.

---

## 3. The Core Ideas

### 3.1 `Syncable` Is the Shared Contract

`examples/sync/src/databases/mod.rs` defines `Syncable`, and that trait is the
center of the example.

It requires a database to:

- create deterministic test operations,
- accept operations in batches,
- report its root,
- report its current size,
- report its inactivity floor,
- produce historical proofs,
- and provide pinned nodes for the sync engine.

That is enough to compare three storage shapes without pretending they are the
same thing internally. The contract stays fixed while the semantics vary.

This is the most important abstraction boundary in the example. It says the
sync loop does not care how the database stores bytes internally. It cares
about a smaller, sharper question:

> Can this database name a target, justify the path to it, and apply the
> operations needed to get there?

### 3.2 The Wire Protocol Only Asks Two Real Questions

Once the client connects, the protocol in `examples/sync/src/net/wire.rs` does
not expose a sprawling RPC surface. It exposes two main questions.

The first is:

> What target should I be chasing right now?

That is `GetSyncTargetRequest` and `GetSyncTargetResponse`. The answer is a
`Target<D>`: a root plus a non-empty range.

The second is:

> Starting from this operation location, give me the next proof-backed segment
> toward that target.

That is `GetOperationsRequest` and `GetOperationsResponse`. The request carries:

- `request_id`, so the response can be matched later,
- `op_count`, the operation boundary the client believes it is syncing toward,
- `start_loc`, the location from which it wants more history,
- `max_ops`, the requested batch size,
- `include_pinned_nodes`, which asks the server to include extra MMR anchors
  when the sync engine needs them.

The response carries exactly the material the client needs to keep going:

- the same `request_id`,
- a historical `Proof<D>`,
- a batch of operations,
- and optionally `pinned_nodes`.

That compactness matters. The protocol is not "send me your database." It is
"name the line, then give me the next justified segment."

### 3.3 Request IDs Are the Memory of the Conversation

The whole protocol would become slippery without `request_id`.

`examples/sync/src/net/request_id.rs` uses an atomic counter to generate
monotonically increasing `u64` request IDs. That seems almost too small to be a
chapter point, but it is one of the example's real discipline moves.

The client has multiple requests in flight over time. A response can arrive
late. A target update can race with an operations reply. The wrong response
type can arrive for the right channel. The resolver therefore never asks "did I
receive a response?" It asks "did I receive the response for *this* request?"

That is why both success and error messages carry `request_id`, and why the
resolver treats any mismatched response shape as `UnexpectedResponse {
request_id }`. In a live sync loop, request correlation is not bookkeeping. It
is what prevents the transport from becoming a source of semantic confusion.

### 3.4 The Resolver Is a Narrow Trust Boundary

`examples/sync/src/net/resolver.rs` is deliberately boring in the best way.
It does not verify storage proofs. It does not interpret operations. It does
not decide whether the server is morally trustworthy.

It does something smaller and more reliable:

- allocate a fresh request ID,
- send one typed wire message,
- wait for one typed reply,
- convert server-side errors into local `Error`,
- reject wrong response types,
- and hand the result to the sync engine.

That narrowness is the right design. The resolver should not become a second
algorithm with its own opinion about synchronization. It is the transport edge
for a proof-driven system.

### 3.5 The I/O Loop Is Split to Stay Cancellation-Safe

One of the most instructive parts of the example is `examples/sync/src/net/io.rs`.

At first glance, it looks like ordinary plumbing: a request channel, a response
channel, and a network loop. But the split is there to defend a real invariant.

`recv_frame` is not cancellation-safe. If an async select dropped it halfway
through reading a frame, the stream could be left in a corrupted state. The
code therefore spawns a dedicated `recv_loop` task whose only job is:

1. read complete frames from the stream,
2. forward them over an internal channel,
3. never be canceled in the middle of a frame.

The main `run_loop` then uses `select_loop!` only on cancellation-safe channel
operations:

- incoming outbound requests from the resolver,
- and complete inbound frames from the recv task.

This is a classic Commonware move. The example is small, but it still teaches
that async control flow has transport semantics. Cancellation is not free.

### 3.6 The Three Database Flavors Do Not Mean the Same Thing

The example is much better once you stop treating `any`, `current`, and
`immutable` as three skins on the same state machine.

`any` is the straightest case. The synced root is the direct database root, and
the historical proof is the obvious operations proof.

`current` is subtler. Its canonical state includes more than the raw operations
log. It rebuilds current-state machinery after sync, so the example deliberately
targets the **ops root**, not the canonical root. That keeps the sync proof
surface aligned with the operations the engine can verify directly. The client
then reconstructs the bitmap and grafted structure deterministically afterward.

`immutable` changes the meaning of the inactivity floor. In that flavor, all
retained operations stay active, so the inactivity floor collapses to the
pruning boundary. The proof story is still historical, but the state semantics
are different.

That is why the chapter should never say "the three databases are equivalent."
They are comparable because `Syncable` names the same reconciliation surface,
not because their internal meaning is the same.

---

## 4. How the System Moves

### 4.1 The Server Keeps Manufacturing New Targets

`examples/sync/src/bin/server.rs` begins by initializing one of the three
database flavors with deterministic test operations. Then it does something
that turns the example from a one-shot transfer into a real sync study: it
keeps adding new operations on a timer.

`maybe_add_operations` checks whether `op_interval` has elapsed since the last
write. If so, it generates more deterministic operations, appends them, and
logs the new root. That means the source of truth is intentionally unstable.

The server is therefore always serving from a moving frontier. That is not
noise. It is the condition the client must learn to survive.

### 4.2 Naming a Target Means Naming Both Root and Range

When the client asks for the current target, the server does not return only a
root. `handle_get_sync_target` reads three facts from the database:

- `root`,
- `inactivity_floor`,
- `size`.

It then constructs `Target { root, range: non_empty_range!(inactivity_floor, size) }`.

That range matters. Synchronization is not just "head hash equals head hash."
The range says where the live window of relevant operations currently begins and
ends. For `current`, that lower bound is especially important because it marks
which operations are still active in the rebuilt state view.

So the target is not merely a digest to admire. It is a digest plus an interval
that tells the client how much history is still relevant to the present claim.

### 4.3 The Operations Path Is a Bounded Proof Ladder

The more interesting server path is `handle_get_operations`.

The request is validated first. `GetOperationsRequest::validate()` rejects the
obvious nonsense case where `start_loc >= op_count`. The handler then checks
the live database size and clamps the request by two ceilings:

- the client's requested `max_ops`,
- and the server's own `MAX_BATCH_SIZE`.

This means batching is jointly owned. The client asks for a batch size, but the
server still enforces a hard upper bound. That keeps the protocol readable under
pressure and prevents a single request from turning into an unbounded proof
response.

After that, the server calls `historical_proof(op_count, start_loc, max_ops)`.
If the request asked for them, it also fetches `pinned_nodes_at(start_loc)`.

This is a nice systems detail. The client is not always asking for the same
proof payload. Sometimes it needs the extra pinned nodes that anchor the proof
at a specific boundary. The wire protocol makes that explicit with
`include_pinned_nodes`.

### 4.4 The Client Runs a Two-Loop Reconciliation System

`examples/sync/src/bin/client.rs` is easiest to understand as two loops.

The first is the **target update loop** in `target_update_task`.

It sleeps for `target_update_interval`, asks the server for the latest target,
and compares only the root against the current target. If the root changed, it
tries to send the new target over a bounded channel to the sync engine.

That bounded channel is important. The example does not want an infinite queue
of stale targets piling up behind the engine. It wants the newest meaningful
change, or a clear failure if the update consumer is gone.

The second is the **sync iteration loop** in `run_any`, `run_current`, and
`run_immutable`.

Each iteration:

1. opens a fresh resolver connection,
2. asks for the current target,
3. spawns the background target-update task,
4. runs `sync::sync` with explicit batching and outstanding-request limits,
5. logs the resulting root,
6. aborts the updater,
7. sleeps for `sync_interval`,
8. starts over.

That repeated restart is not waste. It teaches that recovery from a previous
run is part of synchronization. A client should be able to reopen state, ask
for the new boundary, and continue.

### 4.5 The Client's Network Edge Is Also Cancellation-Safe

The resolver itself does not touch sockets directly. It hands requests to the
I/O task in `net/io.rs`.

That task keeps a `pending_requests: HashMap<RequestId, oneshot::Sender<_>>`.
When a request arrives:

- the request ID is inserted into the pending map,
- the message is encoded and framed,
- `send_frame` writes it to the sink.

When a complete response frame arrives from the dedicated recv task:

- the message is decoded,
- its request ID is extracted,
- the matching oneshot sender is removed from the pending map,
- the typed response is delivered.

This is the wire-level version of the same discipline the chapter has been
teaching all along: keep the current frontier explicit. Here the frontier is
not a root. It is the set of requests that still have a live reply path.

### 4.6 Re-Anchoring Is the Real Point of the Example

The most instructive moment is not the first successful sync. It is the moment
the target update task observes that the server root changed while the client is
still working.

At that point the client does not throw everything away. It sends the new
target into the sync engine and lets the engine reconcile against the fresher
boundary. The work already done still matters, but the interpretation of "done"
has changed.

That is the habit the example is teaching:

> in a live system, "up to date" is only a temporary name for the current
> proof-backed boundary.

---

## 5. Database Semantics and Why They Matter

### 5.1 `any` Is the Clean Baseline

`any` is the simplest lecture version.

- the root being chased is the direct database root,
- `historical_proof` is the direct proof path,
- replayed operations land exactly where the proof surface says they should.

This is the best flavor for first understanding the sync loop because the
storage semantics do not add a second layer of interpretation.

### 5.2 `current` Teaches Why a Canonical Root Is Not Always the Sync Root

`current` is the most pedagogically useful flavor because it forces a subtle
distinction.

Its full canonical state includes more than the operations log. The bitmap and
grafted structure express which operations are currently active. But the sync
engine does not directly chase that canonical root. It chases `ops_root()`.

That is not a shortcut. It is the correct separation of concerns.

The server serves proof material about the operations history. The client syncs
that operations history first. Then, because the reconstruction of the bitmap
and grafted view is deterministic from the operations, the richer canonical
state can be rebuilt locally.

This is exactly the kind of design lesson the example should teach: the most
natural application root is not always the right network proof root.

### 5.3 `immutable` Changes the Meaning of Activity

`immutable` is different again.

Its operations are not updates to a mutable current-state view in the same way.
Retained operations stay active, so `inactivity_floor()` is effectively the
pruning boundary. That changes the interpretation of the target range even
though the sync engine still sees a root, a proof, and operations.

This is why the example is stronger than a single storage demo. It shows that a
shared sync mechanism can survive a change in state semantics as long as the
proof surface stays explicit.

---

## 6. What Pressure It Is Designed To Absorb

### 6.1 Continuous Writes

The server keeps appending operations while the client is still working. The
design assumes the target may change between the first fetch and the last.

### 6.2 Verification Pressure

The client does not accept a root by reputation. It fetches proofs and
operations, then relies on the sync engine to verify the transition.

### 6.3 Reconnection Pressure

The example creates a fresh sync iteration each time through the loop. That
shows the protocol can recover from a previous run and pick up again without
having to restart the whole system by hand.

### 6.4 Bounded Work

Batch size, update cadence, and `max_outstanding_requests` keep the system from
turning into an uncontrolled flood of fetches. The example stays readable
because the pressure is bounded.

### 6.5 Transport Disorder

Request IDs, typed replies, and the pending-request map keep the protocol sane
even if responses are late, unexpected, or arrive after the logical moment that
caused them.

### 6.6 Async Cancellation Hazards

The dedicated recv tasks on both client and server exist because frame reads are
not cancellation-safe. The example is therefore also teaching a more general
lesson: not every async operation belongs directly inside a select loop.

---

## 7. Failure Modes and Limits

The example is honest about what it does not solve.

It does not authenticate the server. The client dials the address and trusts
the responses enough to demonstrate the sync mechanism. In production, that
trust boundary should be explicit.

It also does not source the target from a stronger authority. The example asks
the server for the current target, which is convenient for a tutorial but not
the same as getting a target from consensus or another trusted source.

There is no rate limiting for target updates, either. That is fine for a case
study, but a real deployment needs to protect the server from unnecessary
polling.

And like any sync system, this one depends on the server having the data it
claims to have. Proofs can verify a transition only if the target you are
chasing is itself trustworthy.

The limit to keep in mind is simple:

> this example shows how to follow a moving target, not how to decide what the
> target should be in the first place.

---

## 8. How To Read The Source

Read the example as a sequence of boundaries, from storage contract to client
loop.

1. `examples/sync/src/databases/mod.rs`  
   Start with the shared sync contract. `Syncable` names the surface all three
   storage shapes must satisfy.

2. `examples/sync/src/net/wire.rs` and `examples/sync/src/net/request_id.rs`  
   Read these together to see the wire questions and the correlation rule that
   keeps replies attached to the right request.

3. `examples/sync/src/net/io.rs` and `examples/sync/src/net/resolver.rs`  
   Read these as the transport boundary. The recv task, pending-request map,
   and typed responses keep the sync loop from confusing transport with state.

4. `examples/sync/src/databases/any.rs`, `current.rs`, and `immutable.rs`  
   Compare how each database turns the same proof surface into a different
   notion of root, inactivity floor, and retained history.

5. `examples/sync/src/bin/server.rs`  
   See how the moving source of truth names targets and serves proof-backed
   segments.

6. `examples/sync/src/bin/client.rs`  
   Finish with the reconciliation loop once the wire and storage boundaries
   already make sense.

If you read the files in that order, the example stops looking like two
binaries and starts looking like one proof-backed reconciliation system with
two roles.

---

## 9. Glossary And Further Reading

- **Target** - the root and range the client is currently trying to reach.
- **Proof** - the evidence that connects the current target to the operations
  that justify it.
- **Reconciliation** - the work of fetching, verifying, and re-anchoring until
  local state matches the proof-backed target.
- **Inactivity floor** - the boundary below which operations are no longer
  considered active for that database flavor.
- **Pinned nodes** - extra MMR anchors the sync engine may need to verify a
  historical segment at a specific boundary.
- **Resolver** - the client-side bridge from typed wire messages to sync
  requests.
- **Request ID** - the unique token that keeps one wire reply attached to one
  logical question.
- **Syncable** - the shared contract that makes the three database flavors
  comparable.

Further reading:

- `commonware-storage` for the sync engine the example is exercising.
- `commonware-resolver` for the wider fetch-and-validate pattern this example
  borrows from.
- `examples/sync/README.md` for the operational shortcuts the example takes on
  purpose.
