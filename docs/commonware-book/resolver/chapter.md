# commonware-resolver

## The Missing-Piece Coordinator

A persistent search that stays alive until the consumer accepts the answer.

---

## 0. Opening Apparatus

**Promise.** This chapter shows how `commonware-resolver` keeps one keyed
search alive until the consumer accepts the bytes, without mistaking a reply
for a solution.

**Crux.** The resolver is a coordinator for missing pieces. It preserves one
search per key, retries without duplicating work, and keeps validation separate
from retrieval.

**Primary invariant.** A key never becomes two searches. A search ends only
when the consumer accepts the value, the caller cancels it, or the key is
retained away.

**Naive failure.** If every reply counts as success, every miss becomes
fan-out, every invalid response looks useful, and the network burns time
rediscovering the same absence.

**Reading map.** Start with `resolver/src/lib.rs` for the public contract,
then `resolver/src/p2p/fetcher.rs` for the search state machine, then
`resolver/src/p2p/engine.rs` for the actor loop, then `resolver/src/p2p/wire.rs`
for the request IDs and payload grammar. Finish with the tests in
`resolver/src/p2p/mod.rs` and `resolver/src/p2p/fetcher.rs`, because they
document the cases the prose must not gloss over.

**Assumption ledger.**

- The reader is comfortable with asynchronous message passing.
- The reader wants the resolver as a distributed-systems primitive, not a
  storage API.
- The chapter reads the code as BETA behavior: stable wire and API, not a
  sketch.

---

## 1. Background: Why Missing Data Turns Into Coordination

Distributed lookup is not just a request-response loop. It is a search problem
in a network that can lie by omission, delay, duplication, or disagreement.

The first useful terms are straightforward:

- a candidate is a value that might solve the lookup,
- a consumer decides whether that candidate is actually acceptable,
- a producer serves values to other peers,
- a targeted search restricts which peers may answer,
- an untargeted search asks the system to try any eligible peer.

The naive approach is to treat any reply as success. That collapses search and
validation into one step, which means invalid values can look useful and the
same missing piece can be searched for repeatedly by different callers. A more
careful design keeps one live search per key, remembers which peers have
already been tried, and only stops when the returned value passes the caller's
own test.

The tradeoff is familiar: a broader search is often faster, but a narrower one
can express stronger trust. Parallel retries reduce latency, but they also
increase duplicate work. Timeouts keep the system honest, but they also make it
possible to give up before the network has truly failed. The resolver's job is
to manage those tensions without confusing a reply with an answer.

---

## 2. What Problem Does This Solve?

At the edge of a distributed system, you often know what you need before you
know who has it. That is the resolver's job: carry a search across an
unreliable network without confusing "someone replied" with "the answer is
valid."

If you try to solve that with brute force, every miss becomes fan-out, every
timeout becomes duplicate work, and every invalid response looks too much like
success. `commonware-resolver` exists to prevent that collapse. It keeps one
search alive per key, remembers what has already been tried, and keeps the
network from spending the same effort twice.

The crate divides the work into two separate judgments:

- fetch finds a candidate value,
- validate decides whether that value is fit to keep.

That split is not an implementation detail. It is the discipline. A resolver
that validates while it fetches would blur the edge between transport and
truth. This resolver keeps that edge sharp.

The public API reflects the split directly:

- `Resolver` starts, targets, cancels, and trims searches.
- `Consumer` judges the returned bytes.
- `Producer` serves bytes to other peers when they search here.

So the crate does not own truth. It owns the persistent search for truth.

---

## 3. The Public Contract

`resolver/src/lib.rs` gives the smallest useful surface:

- `Resolver` is the control plane for searches.
- `Consumer::deliver(key, value)` is the validation boundary.
- `Producer::produce(key)` is the mirror image on the serving side.

That split is easy to state and easy to underestimate. The resolver never
claims a value is good. It only delivers candidates. The consumer decides
whether the bytes are acceptable and whether the search can stop.

That matters because different applications need different kinds of truth.
One application might accept any syntactically valid value. Another might
require a cryptographic proof. Another might reject a value that is valid in
the abstract but stale for the application. The resolver is intentionally not
the place where those judgments live.

The API also distinguishes between ordinary and targeted searches:

- `fetch` and `fetch_all` say "try any eligible peer."
- `fetch_targeted` and `fetch_all_targeted` say "stay inside this boundary."

That boundary is not a hint. It is part of the request. A targeted search is a
promise to the caller that the resolver will not silently widen the search to
save itself work.

---

## 4. The Fetcher as Memory

`resolver/src/p2p/fetcher.rs` is the memory of the search.

The fetcher has to remember a surprising amount of state for something that
looks, at first glance, like "ask peers until one answers."

It tracks:

- the next request ID,
- which requests are active,
- which keys are pending retries,
- which peers are blocked,
- which peers are allowed for a given key,
- which peer performed well enough to try first next time,
- and which keys are being searched freely versus under a hard target set.

Once those facts are visible, the fetcher stops looking ornamental. It is the
minimum memory required to keep a search alive in an adversarial network.

### 4.1 One Key, One Search

The resolver does not create a fresh search every time the application asks
for the same key.

That sounds obvious until you think through the alternative. If duplicate
fetches spawned duplicate searches, then a retry, a re-target, or a caller
repetition would multiply network work and produce confusing late responses.
Instead, the resolver treats a key as one durable story.

The engine uses `fetch_timers` to make that story visible. If a key already has
a timer, it is already in flight. If it does not, the key is new and should be
inserted into the fetcher. Duplicate calls therefore edit the same search
instead of creating new work.

### 4.2 Pending and Active Are Different Kinds of Waiting

The fetcher has two live states:

- `pending` means the key is waiting to be tried or retried.
- `active` means the request has already been sent and is waiting on a peer.

That distinction is not cosmetic. Pending requests are still choosing where to
go. Active requests have already committed to one peer and are waiting for the
network to answer. The engine drives both states with different deadlines.

The fetcher exposes that split through two deadlines:

- `get_pending_deadline()` tells the engine when the next retry attempt can
  happen.
- `get_active_deadline()` tells the engine when an in-flight request should be
  treated as timed out.

The state machine is doing exactly the minimum useful thing: it keeps the key
alive, but it does not let the same attempt run forever.

### 4.3 Targeted Search Is a Hard Constraint

Targets are not a scoring signal. They are a search boundary.

If a key has targets, only those peers may answer it. The fetcher does not
silently widen the search to the rest of the network when the targets are
slow. That is deliberate. It allows the caller to express a stronger claim:
"this key should come from these peers, and not from anywhere else."

That is why the fetcher preserves targets through empty responses, send
failures, and timeouts. Those events tell us that the current attempt failed.
They do not tell us the target set was wrong. The target set is removed only
when the search ends successfully, when the caller cancels it, or when a peer
is blocked for sending invalid data.

### 4.4 Request IDs Match Responses to Questions

The wire does not carry memory by itself, so the fetcher and engine create it.

Every outbound request gets an ID. That ID is copied into the response.
`wire::Message` therefore ties the response back to the question that caused
it. The engine uses that ID together with the peer identity, because a response
that came from the wrong peer is still not the right answer.

That matching rule is what lets the system tolerate reordered or stale
traffic. A late response can arrive after a cancel, after a timeout, or after
the resolver has already moved on. The response is only meaningful if the
request still exists and the peer matches the active request record.

The wire format stays small on purpose:

- `Payload::Request(key)` asks for a value,
- `Payload::Response(bytes)` returns the bytes,
- `Payload::Error` says "I do not have it" without pretending to be a value.

That last case matters because it lets the requester retry quickly without
conflating "no data" with "bad data."

### 4.5 Self-Exclusion Is Not Optional

The resolver never sends a fetch to itself.

That sounds trivial until you consider that the local node can absolutely have
the data. The fetcher still excludes `me` from the eligible set. This keeps the
network path honest and avoids turning the resolver into a local shortcut that
never exercised the distributed path.

The `test_self_exclusion` case exists because this edge is easy to miss and
hard to recover later. If a resolver can satisfy itself, it can accidentally
hide topology mistakes and make the system look healthier than it is.

### 4.6 Peer Reputation Is Simple on Purpose

The fetcher keeps a performance score per peer and uses it to bias the next
choice.

The score is not a proof of goodness. It is just memory about whether a peer
has been fast, slow, or useless recently. Peers that respond quickly drift
toward the front. Peers that time out or fail drift backward. That is enough to
stop the resolver from repeatedly starting with the worst available option.

The code deliberately keeps the model simple. A more elaborate ranking system
would take more state and more explanation, and it would not change the
fundamental contract: prefer the peers that have been working lately, but keep
trying if they stop working.

---

## 5. Walk One Key Through the Engine

It is easier to understand the resolver if you follow one key all the way
through the loop.

### Step 1: The application asks for a key

The application calls `Resolver::fetch(key)` or one of the targeted variants.
The mailbox records the request. If the key is new, the engine starts a timer
for the whole search and moves the key into the fetcher. If the key is already
in flight, the engine updates the existing search instead of creating another
one.

That timer exists for the whole key, not for one specific peer attempt. If the
search completes, the timer is canceled. If the search is removed by cancel,
retain, or clear, the timer is canceled too. That is why the engine keeps
`fetch_timers` in lockstep with the fetcher.

### Step 2: The fetcher chooses a peer

The fetcher looks at the current peer set, removes blocked peers, removes
self, and applies any target restriction for that key.

From there it tries peers in performance order. Good peers stay near the front.
Poorly performing peers drift backward. Retries can shuffle the order so the
search does not keep hitting the same peer first.

This is where the search becomes a real distributed-system choice rather than a
queue of random retries. The resolver is not asking "who exists?" It is asking
"who should I try next, given what I have already learned?"

### Step 3: The resolver sends a keyed request

Every outbound message carries a request ID and the key being requested.

That request ID matters because the network is not a single clean line. A
response can arrive late, after a cancel, or after a retry started a fresh
request elsewhere. The resolver must know which question a response answers.
The ID is how it keeps those questions apart.

The wire is deliberately small:

- `Request(key)` asks for a value,
- `Response(bytes)` returns the bytes,
- `Error` says "I do not have it" or "I am not ready," without pretending to
  be a value.

The difference between `Response` and `Error` matters. The resolver can make a
fast retry decision on `Error`, but it must still pass `Response(bytes)` to the
consumer for validation.

### Step 4: The peer responds

There are three useful responses:

- the peer returns bytes,
- the peer returns an explicit error,
- or the peer never responds at all.

The first case is not automatically success. The bytes go to the consumer.
Only the consumer can say whether the value is valid.

If the consumer accepts the data, the resolver cancels the timer, clears the
targets for that key, and stops.

If the consumer rejects the data, the resolver blocks that peer and retries
the key elsewhere.

If the peer returns an error or the request times out, the resolver keeps the
search alive and tries again later.

That retry behavior is selective. An empty response does not prove malice, so
it does not trigger blocking. Invalid data does. This distinction is visible in
the tests: the "no data" cases keep trying, while the invalid-data case removes
the peer from future searches.

### Step 5: Work stops when the answer is good

That is the point. A resolver should not keep searching after it already has
the right answer. The crate prevents that in two ways:

- the successful key is removed from the fetcher,
- and the consumer timer is canceled so no stale timeout can wake up later and
  do useless work.

The search ends when the application accepts the value, not when the first
peer replies.

### Step 6: Serving mirrors fetching

The inbound path is the mirror image.

When another peer asks this node for a key, the peer actor forwards the key to
the `Producer`. The producer returns bytes or fails. The actor then sends a
response with the original request ID so the remote side can match the answer
to the question.

That symmetry matters. The same actor is both a client and a server. It asks
questions for local consumers and answers them for remote peers. The protocol
is easiest to understand when you realize both directions use the same
request/response grammar and the same timing discipline.

---

## 6. The Engine as a Single Loop

`resolver/src/p2p/engine.rs` is where the system becomes concrete.

The engine is one loop with several sources of truth:

- mailbox commands from the application,
- peer-set updates from the provider,
- deadlines from the fetcher,
- completed producer futures,
- and network messages from remote peers.

The loop does not privilege one of those sources as "the real one." It keeps
them synchronized.

### 6.1 Mailbox commands change the shape of the search

`fetch`, `fetch_all`, `fetch_targeted`, and `fetch_all_targeted` all enter
through the mailbox.

The engine distinguishes between a new search and an update to an existing
search. If the key is new, it starts the timer and adds the key to the ready
queue. If the key already exists, it adjusts targets instead of duplicating
work. That is why the tests around duplicate fetches and target clearing are so
important. They prove that the mailbox is editing an existing search, not
creating one per call.

`cancel`, `retain`, and `clear` all follow the same pattern:

- update the fetcher,
- remove the matching timer or timers,
- notify the consumer that the search ended without success.

The engine keeps the fetcher and timer map aligned so that no key survives in
one structure after it has been removed from the other.

### 6.2 Peer-set changes are not the same as application updates

The peer provider can change over time.

When that happens, the engine reconciles the fetcher's participant set with the
current tracked peers. This is how the resolver learns that a peer has become
eligible or ineligible for future searches.

The fetcher therefore uses the current peer set as a living constraint, not a
static list. That is why the tests around changing peer sets matter: they show
that the resolver adapts without losing the searches that are already in
flight.

### 6.3 Timeouts keep the loop honest

The engine uses two timer classes.

One timer belongs to the whole search and is tracked in `fetch_timers`. That
timer ends when the consumer accepts the value or when the search is canceled
or trimmed away.

The other timer belongs to the fetcher and controls when a key should be tried
again or when an in-flight request should be considered overdue.

Those timers are deliberately separate. The first one says "how long has this
search existed?" The second says "when should this attempt move again?"

That separation is the easiest way to understand why the engine needs both the
fetcher and the timer map. One tracks the search's existence. The other tracks
its current attempt.

### 6.4 The inbound response path is a proof obligation

When a response arrives, the engine does not trust it blindly.

It matches the request ID and peer against the fetcher. If that key no longer
exists, the message is stale and is ignored. If the peer does not match, the
message is also ignored. Only a live request from the correct peer can advance
the search.

If the response contains bytes, those bytes are handed to the consumer. If the
consumer accepts them, the timer is removed and the search ends. If the
consumer rejects them, the peer is blocked and the key is retried.

If the response is `Error`, the peer simply did not have the data. The search
continues, but the peer is not blocked.

The key code path is short enough to describe almost as pseudocode:

```rust
match msg.payload {
    Request(key) => handle_network_request(peer, id, key),
    Response(bytes) => handle_network_response(peer, id, bytes).await,
    Error => handle_network_error_response(peer, id),
}
```

That compactness is the point. Most of the complexity lives in the state the
engine is preserving, not in the branch structure itself.

---

## 7. What the Tests Prove

The tests in `resolver/src/p2p/mod.rs` and `resolver/src/p2p/fetcher.rs` are
the closest thing the crate has to a behavioral proof.

The important cases are easy to name because the tests already do the naming:

- `test_fetch_success` shows the ordinary happy path.
- `test_peer_no_data` shows that empty responses do not end the search.
- `test_blocking_peer` shows that invalid data causes blocking and future
  spillover.
- `test_duplicate_fetch_request` shows that duplicate calls do not create
  duplicate work.
- `test_fetch_targeted` shows that targets stay in force through invalid
  responses until a valid target answers.
- `test_fetch_targeted_no_fallback` shows that a hard target set really means
  "do not fall back."
- `test_fetch_all_targeted` shows that batching can mix targeted and
  unrestricted searches without confusing them.
- `test_fetch_clears_targets` shows that a later unrestricted fetch can widen
  an existing targeted search again.
- `test_self_exclusion` shows that the local node never becomes its own fetch
  target.
- `test_rate_limit_spillover` shows that rate limits create peer spillover
  instead of serializing the whole system behind one peer.
- `test_rate_limit_retry_after_reset` shows that the search resumes once rate
  limits lift.
- `test_retain` and `test_clear` show that trimming and clearing searches also
  clean up timers and notifications.

The fetcher unit tests carry the same weight at a lower level. They prove the
state machine itself:

- `add_ready` and `add_retry` put keys into the right queue,
- `get_pending_deadline` and `get_active_deadline` return the right next
  action,
- `pop_by_id` only succeeds for the right `(peer, id)` pair,
- `reconcile` updates the eligible peer set,
- `block` removes a peer from future target sets,
- `add_targets` and `clear_targets` edit hard constraints correctly,
- and the waiter logic prevents the engine from spinning when no peer can be
  used yet.

That is the real value of the tests: they describe the promises in executable
form. If the prose and the tests ever disagree, the tests win.

---

## 8. Failure Modes and Limits

The resolver is strong, but it does not do magic.

It cannot invent data that no peer has. If every eligible peer is empty, the
search can only wait, retry, or be canceled. The resolver can reduce waste,
but it cannot create a value from nothing.

It also cannot validate the data on its own. The consumer must do that work.
That is a feature, not a gap. Different applications need different notions of
correctness, so the resolver leaves the judgment at the boundary.

Targeted fetches have a hard edge. If you restrict a search to a specific set
of peers, the resolver will stay inside that set. It will not fall back to a
broader search just because the targets are slow. That is exactly what the API
promises, but it also means the caller must choose targets carefully.

Blocked peers are removed for a reason. Once a peer has been caught sending
invalid data, keeping it in future search paths would only add noise. By
contrast, empty responses and send failures are not proof of malice. The
resolver treats them as retry conditions, not as evidence.

The crate also depends on the rest of the system being honest about time and
peer sets. If the peer set changes, the fetcher must reconcile with the current
set. If the runtime is not driving timers correctly, retries can happen too
early or too late. The resolver handles the state, but it relies on the runtime
to move the world forward.

---

## 9. How to Read the Source

Read the source in this order:

1. Start with `resolver/src/lib.rs` to see the public split between
   `Resolver`, `Consumer`, and `Producer`.
2. Move to `resolver/src/p2p/mod.rs` for the peer actor as both fetcher and
   server.
3. Read `resolver/src/p2p/fetcher.rs` next. This is the search memory, and it
   explains how requests persist, retry, and stop.
4. Then read `resolver/src/p2p/engine.rs` to see how mailbox commands,
   peer-set changes, network responses, and producer completions keep that
   memory coherent.
5. Finish with `resolver/src/p2p/wire.rs` and the tests in
   `resolver/src/p2p/mod.rs` and `resolver/src/p2p/fetcher.rs` so the wire
   format, invariants, and edge cases line up.

If you keep the fetcher state machine in your head while reading, the rest of
the crate becomes much easier to follow. If you start from the mailbox and
work inward, the search logic can feel larger than it is.

---

## 10. Glossary

- Fetch - Ask the network for a key.
- Validate - Let the consumer decide whether the bytes are good.
- Targeted fetch - Restrict the search to a known set of candidate peers.
- Pending request - A key waiting to be sent or retried.
- Active request - A key already sent and waiting for a response.
- Blocked peer - A peer removed from search paths after sending invalid data.
- Request ID - The token that matches a response to the question that caused
  it.
- Producer - The local role that serves data to remote peers.
- Consumer - The local role that judges fetched data.

If you want the sharpest reading of the crate, keep asking the same question
while you read every file: "At this point, what does the resolver know, what is
it still unsure about, and what is it doing to avoid wasting work?"
