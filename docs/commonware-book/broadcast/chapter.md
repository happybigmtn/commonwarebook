# commonware-broadcast

## A Town Crier With a Ledger, a Queue, and a Forgetting Rule

---

## Opening Ledger

This chapter explains how `commonware-broadcast` disseminates a payload, caches
it by digest, and serves later replay requests without claiming to solve
ordering, durability, or agreement.

**Crux.** The engine is not "a sender with a cache." It is an event loop that
keeps four facts in sync:

- which payloads are currently remembered,
- which peers still justify remembering them,
- which applications are waiting for which digests,
- and which peers are still socially relevant enough to keep in memory.

**Primary invariant.** A payload remains in shared memory if and only if at
least one tracked peer deque still contains its digest.

**Secondary invariant.** Waiters are keyed by digest, not by sender, path, or
recipient set. If the payload arrives from anywhere, every waiter for that
digest should become eligible to complete.

**Naive failure.** The easy mistake is to equate "I sent a payload" with
"everyone now has it" and then to keep resending full bytes until the network
feels quiet. That wastes bandwidth, makes duplicates expensive, and still gives
late readers no stable replay key.

**Reading map.**

- Section 1 explains the systems problem.
- Section 2 gives the mental model.
- Sections 3 and 4 name the public surface and internal state.
- Sections 5 through 9 follow the real machine: loop, duplicates, waiters,
  forgetting, and malformed input.
- Section 10 turns the tests into executable invariants.

**Assumption ledger.**

- The network is best-effort. Delay, duplication, and packet loss are normal.
- Peer membership is external. The broadcast engine consumes peer-set updates;
  it does not define the peer sets itself.
- Memory is bounded. Old digests will be forgotten on purpose.
- Replay is digest-addressed. Sender identity matters for retention accounting,
  not for lookup.
- This crate is BETA, so the behavioral contract matters.

---

## Background: Why Dissemination Needs Memory

Broadcast sounds like a simple act: send a payload to many peers. In practice,
the hard part is what happens after the first send.

The key vocabulary is broad but manageable:

- **dissemination** is getting a payload into circulation,
- **replay** is asking for that same payload again later,
- **digest** is the compact name that identifies the payload,
- **duplicate suppression** avoids storing or resending the same payload too
  many times,
- **retention** decides how long a recent payload should stay available.

The naive approach is to treat "I sent it" as the same thing as "the system has
it." That fails as soon as packets are duplicated, delayed, or received out of
order. It also fails for late readers, who need to ask for the payload by a
stable name rather than by the memory of which peer happened to say it first.

The tradeoff is between freshness and bounded memory. If you remember too
little, replay breaks. If you remember too much, the broadcast layer turns into
an unbounded cache. The interesting design problem is how to keep the recent
payloads that are still socially relevant while forgetting the ones that no
longer justify their cost.

That is the background for this chapter. The Commonware mechanism then makes
that tradeoff explicit with digest-based storage, peer histories, waiters, and
intentional forgetting.

---

## 1. What Problem Does This Solve?

In a wide-area distributed system, dissemination and agreement are different
jobs.

The first job is simple to state and hard to do well: get a payload into
circulation now, under ordinary network messiness, and make it possible for
late readers to ask for that same payload again. The second job is consensus:
decide whether the system should accept, order, or commit that payload. Those
jobs should not be collapsed into one abstraction.

`commonware-broadcast` owns the first job.

It gives the rest of the system a digest-addressed memory for recently seen
payloads. That sounds smaller than "reliable broadcast," and it is. The crate
does not promise total delivery, finality, or durable storage. It promises a
different kind of usefulness:

1. the sender can inject a payload into circulation,
2. the local node will remember that payload by digest,
3. later readers can ask for the digest directly,
4. if the payload is not present yet, they can wait on that digest,
5. memory will eventually be reclaimed according to bounded, explicit rules.

This is the right promise for higher-level protocols that already know the
digest they care about and need a live replay layer, not a permanent archive.

The simplest wrong design would resend full payloads until everyone "probably"
has them. That wastes bytes and still does not answer the late-reader question:
"Now that the broadcast wave has passed, how do I ask for the same object
again?" `commonware-broadcast` answers that by centering the digest, not the
transmission event.

---

## 2. Mental Model

Think of a town crier who does not merely shout. He also keeps a ledger.

When a proclamation arrives, he writes down its digest. If several couriers
repeat the same proclamation, he does not create several proclamations. He
keeps one shared text and records that several recent courier histories still
refer to it. If a citizen asks for the proclamation by digest, he checks the
ledger. If the text is already on hand, he answers immediately. If not, he
keeps the request open under that digest until the text appears.

Two facts make the metaphor useful.

First, the crier does not keep an infinite archive. He remembers a bounded
recent history per courier. When an old digest falls out of every relevant
courier history, the shared text is forgotten too.

Second, the crier does not care which courier eventually satisfies a waiting
citizen. The waiting citizen asked for a digest, not for "the copy from courier
A." Arrival from any path is good enough.

That is the buffered broadcast engine in one picture:

- one shared cache of payloads by digest,
- one bounded recent-digest deque per peer,
- one reference count per digest across all peer deques,
- one waiter list per digest for pending replay requests.

The rest of the chapter makes that invariant explicit.

---

## 3. Public Contract, Real Mechanism

The public trait is the promise boundary: it names the send path, but not the
storage, retention, or replay story behind it.

The buffered implementation carries the mechanism. The mailbox is the
application entry point, the engine owns the event loop and shared memory,
`Config` defines how much history the protocol is allowed to remember, and
`Metrics` exposes the result as a live system instead of a pile of state.

That split matters. The crate is not "just a trait" or "just a cache." The
mailbox names the interaction; the engine decides whether the protocol can
honor it.

### 3.1 The Three Questions the Mailbox Supports

The mailbox is small because the questions are precise.

`broadcast(recipients, message)` asks:

> Put this payload into circulation now. Also tell me which peers the network
> send path claims to have reached.

`get(digest)` asks:

> Do you have this payload now? Answer once.

`subscribe(digest)` asks:

> Wake me when this digest becomes available.

`subscribe_prepared(digest, responder)` asks the same question with externally
prepared plumbing. The point is not convenience. The point is that waiting is a
first-class protocol state, not a side effect of repeated polling.

### 3.2 What the Config Is Really Controlling

`Config` looks modest, but each field names a protocol commitment:

- `public_key` tells the engine which peer identity to use for local insertion.
  The local node participates in the replay story too.
- `mailbox_size` defines ingress backpressure. How many application requests can
  queue before sends become lossy.
- `deque_size` defines the retention window per peer.
- `priority` marks whether outgoing network sends should be prioritized over
  other traffic.
- `codec_config` defines the decoding bounds for incoming messages.
- `peer_provider` defines which peer histories remain relevant enough to keep.

These are not cosmetic knobs. They are the policy surface that decides how much
history the broadcast layer is allowed to preserve.

---

## 4. The Engine's Memory Model

If you open `broadcast/src/buffered/engine.rs`, read it as a state machine, not
as a module of helpers.

The engine maintains four linked memories:

- `items: Digest -> Message`
- `deques: Peer -> VecDeque<Digest>`
- `counts: Digest -> usize`
- `waiters: Digest -> Vec<oneshot::Sender<Message>>`

Each structure exists because the protocol needs a different kind of memory.

### 4.1 `items`: Shared Payload Memory

`items` is the actual replay cache. It stores each payload at most once, keyed
by digest.

This is the layer a `get()` call hits. It is also the layer that allows a
`subscribe()` call to resolve immediately when the digest is already known.

### 4.2 `deques`: Bounded Peer Histories

`deques` stores a bounded recent-digest history per peer. This is not merely an
LRU convenience. It is the proof that a payload is still live in the current
social world of the engine.

The same digest can appear in multiple peer deques. That is how the engine
models "several peers have recently carried the same message."

### 4.3 `counts`: Shared Ownership Across Peer Histories

`counts` tells the engine how many peer histories still justify keeping a
digest in `items`.

This map is what prevents two opposite mistakes:

- storing duplicate payload copies for the same digest,
- or evicting a shared payload too early when one peer forgets it but another
  peer still references it.

### 4.4 `waiters`: Deferred Replay

`waiters` stores pending subscriptions keyed by digest.

This is the part of the design that turns replay from a polling API into a
digest-addressed rendezvous. The waiter map says:

> "You do not have to ask repeatedly. If the digest shows up later, the engine
> will complete your request."

### 4.5 External Authorities

The engine also depends on two outside authorities:

- the wrapped sender/receiver pair, which defines what "sent" and "received"
  mean at the transport boundary,
- the peer-set provider, which tells the engine which peers are still tracked.

That boundary is deliberate. Broadcast owns live dissemination memory. It does
not own transport semantics or membership semantics.

---

## 5. The Event Loop Is the Main Character

The loop is the chapter's real subject.

The engine is not "a cache with helper methods." It is a `select_loop!`
reactor over four classes of events:

```text
loop {
    cleanup closed waiters
    publish waiter metric

    select {
        mailbox message        => handle application request
        network payload        => decode and insert or drop
        peer-set update        => evict untracked peer histories
        stop                   => shut down cleanly
    }
}
```

That picture is concept-first and code-faithful. It is the chapter's real
timeline.

### 5.1 A Loop Turn Starts by Cleaning Dead Waiters

At the top of each loop turn, the engine calls `cleanup_waiters()`. Closed
responders are removed before anything else happens.

This matters because waiting is lossy at the application boundary by design.
The application is allowed to drop a subscription. The engine should not keep
that dead promise forever. The test
`test_dropped_waiters_for_missing_digest_are_cleaned_up` in
`broadcast/src/buffered/mod.rs` makes this explicit.

This is a good example of Commonware style: small abstraction, complete
ownership of the edge case.

### 5.2 Local Broadcast Begins With Local Insertion

When the mailbox receives `Message::Broadcast`, `handle_broadcast()` does two
things in a deliberate order:

1. it inserts the message into the local cache as if it had been seen from the
   local peer,
2. only then does it send the message outward.

That ordering is the replay story.

If the sender broadcasts a payload and then immediately asks for the digest, the
local node should already be able to replay it. The engine is not waiting for
the network to echo the payload back before it becomes locally real.

The test `test_self_retrieval` proves exactly that: a pre-broadcast waiter can
be satisfied by the sender's own broadcast path, and a post-broadcast `get` is
effectively immediate.

### 5.3 Application Replay Hits the Shared Cache First

`handle_subscribe()` first checks `items`.

- If the payload is already present, the responder is completed immediately.
- If not, the responder is added to the waiter list for that digest.

`handle_get()` is stricter. It performs a one-shot cache lookup and returns
`Option<Message>`.

This distinction is small but architecturally clean:

- `get` asks for present state,
- `subscribe` asks for future state,
- `broadcast` changes the world.

### 5.4 Network Input Crosses a Decode Boundary

The network path in `run()` first receives bytes, then decodes them with the
configured codec bounds, then hands valid messages to `handle_network()`.

That decode boundary is the broadcast crate's first honesty check. Malformed
bytes are not "weird messages." They are invalid transport input. The engine
logs the failure, increments the invalid receive metric, and continues. It does
not poison the cache and it does not stop valid later traffic from being
processed.

The test `test_malformed_network_payload_does_not_break_valid_traffic` is worth
calling out because it captures a real adversarial pressure. The claim is not
"malformed bytes never happen." The claim is "malformed bytes do not corrupt the
engine's useful work."

### 5.5 Peer-Set Updates Trigger Structural Forgetting

The loop also listens to the peer-set subscription. When tracked membership
changes, the engine calls `evict_untracked_peers()`.

This is not a garbage collector in the generic sense. It is a social forgetting
rule:

> histories belonging to peers that no longer exist in any tracked set must no
> longer keep payloads alive.

This is one of the most important concept-first points in the crate. Memory is
driven by live membership, not by abstract object age alone.

---

## 6. Duplicate-Refresh Semantics

The most interesting function in the crate is `insert_message()`.

It does not merely "put the message in the cache." It enforces the precise
relationship between waiters, per-peer recency, shared ownership, and eviction.

### 6.1 First Arrival From a Peer

When a digest is new to that peer:

1. any waiters for the digest are removed and completed,
2. the digest is pushed to the front of that peer's deque,
3. the digest's global refcount is incremented,
4. the payload is inserted into `items` if the new refcount is 1,
5. if the deque is now too long, the oldest digest is popped and its refcount is
   decremented.

This is the full memory update, not just "cache insert."

### 6.2 Duplicate From the Same Peer

If the same peer delivers the same digest again, the engine does something more
subtle.

It looks for the digest inside that peer's deque. If found:

- the digest is moved to the front if it was not already there,
- `counts` is unchanged,
- `items` is unchanged,
- the function returns `false`, which the caller records as a dropped duplicate.

This is the crate's duplicate-refresh semantics.

The message is not globally new. The payload should not be stored again. But the
peer has refreshed evidence that this digest is still part of its recent
history, so the peer-local recency order should change.

That distinction is central to the chapter. The engine does not try to remove
duplicates from the network. It makes duplicates cheap and semantically clear:

- globally, no new payload,
- locally, recency refreshed.

### 6.3 Duplicate Across Different Peers

If two different peers send the same digest, the payload is still stored once in
`items`, but the refcount grows. This is what allows the message to survive the
forgetting of one peer history while another peer history still justifies it.

The tests `test_cache_eviction_multi_peer`,
`test_ref_count_across_peers`, and
`test_peer_set_update_preserves_shared_messages`
all exist to prove this multi-owner story.

### 6.4 Why This Matters

Without this split between shared payload storage and per-peer recent histories,
the engine would be forced into one of two bad designs:

- one payload copy per peer, which is wasteful,
- or one global recency queue with no memory of which peers still justify
  retention, which forgets the wrong things.

The current design is better because it remembers exactly the fact the crate
needs: which live peer histories still point at the digest.

---

## 7. Waiter Discipline and Replay Semantics

The waiter path deserves its own section because it is where replay becomes
digest-addressed rather than sender-addressed.

### 7.1 `get` and `subscribe` Are Different Contracts

`get(digest)` returns one answer now:

- `Some(payload)` if the shared cache already has it,
- `None` otherwise.

`subscribe(digest)` creates a deferred contract:

- immediate completion if already cached,
- otherwise storage in `waiters[digest]` until arrival,
- or cancellation if the receiver is dropped or the engine shuts down.

This is a better interface than "keep polling until maybe something happens."
It makes absence explicit and waiting explicit.

### 7.2 Waiters Are Released by Digest Before Duplicate Suppression

One subtle code fact matters here.

`insert_message()` releases waiters before it checks whether the digest is a
duplicate in the peer's deque. Conceptually, that is the right order. The
question for a waiter is:

> "Did the payload for this digest arrive?"

not:

> "Was this globally novel traffic?"

If the digest is now materialized for replay, the waiters should be eligible to
complete.

### 7.3 Dropped Waiters Are Ordinary, Not Exceptional

The application can drop a subscription at any time. The engine does not treat
that as corruption. It cleans dead responders on later loop turns and updates
metrics accordingly.

This detail matters because it keeps the crate from quietly accumulating dead
obligations. It is also part of the reason the chapter should speak in terms of
"promises that can be withdrawn" rather than "immutable subscriptions."

### 7.4 Shutdown Semantics Are Cleanly Bounded

After shutdown:

- `broadcast()` should fail or report an empty result,
- `subscribe()` should resolve to cancellation,
- `get()` should return `None`,
- and nothing should panic.

The shutdown tests in `broadcast/src/buffered/mod.rs` are important because they
show that the crate treats termination as part of the contract, not as
undefined behavior.

---

## 8. Forgetting On Purpose

Broadcast becomes useful only if forgetting is honest and predictable.

### 8.1 Deque Overflow

Each peer has a bounded `VecDeque` of recent digests. When a new digest pushes
the deque over `deque_size`, the oldest digest is popped from the back and its
global refcount is decremented.

If the count reaches zero, the shared payload is removed from `items`.

This means eviction is not purely age-based and not purely global. It is
age-within-peer-history plus cross-peer ownership accounting.

`test_cache_eviction_single_peer` is the simple case: one peer's history
forgets the oldest digest, so the payload disappears from replay.

### 8.2 Shared Payload Survival

`test_cache_eviction_multi_peer` and `test_ref_count_across_peers` show the
more interesting case: the same digest may survive one peer's forgetting
because another peer's history still points at it.

This is exactly what `counts` is for: shared ownership, not bookkeeping.

### 8.3 Membership-Driven Forgetting

Deque overflow is local forgetting. `evict_untracked_peers()` is structural
forgetting.

When a peer leaves every tracked peer set, the engine removes that peer's entire
deque and decrements all corresponding digest counts. If that peer was the last
live justification for a digest, the payload leaves the shared cache.

The tests `test_peer_set_update_evicts_disconnected_peer_buffers` and
`test_peer_set_update_preserves_shared_messages` are the clearest specification
of this rule.

### 8.4 What Replay Means After Forgetting

Once every tracked reference to a digest is gone, replay at this layer is over.

That is not a bug. It is the design. If an application needs replay across long
epochs, across restarts, or across membership turnover, it must persist the
payload somewhere else. This crate gives a live dissemination memory, not a
historical archive.

---

## 9. Malformed Input, Partial Failure, and Bounded Honesty

`commonware-broadcast` is careful about which failures belong to it.

### 9.1 Malformed Bytes Do Not Become Messages

Malformed transport payloads fail at decode time. The engine logs, increments an
invalid metric, and continues. No cache mutation, no waiter release, no replay
artifact.

That is the right boundary: broadcast is willing to ingest untrusted bytes, but
only decoded messages participate in the ledger.

### 9.2 Send Failure Still Leaves a Local Replay Record

`handle_broadcast()` inserts the local copy before trying the outward send. If
the send fails, the responder gets an empty list, but the local node still
remembers the payload by digest.

This is honest and useful.

- It does not pretend the network succeeded.
- It does not erase the fact that the local application emitted the payload.

### 9.3 Recipient Selection Is Exact, Not Aspirational

The mailbox supports arbitrary recipient sets through the underlying P2P
`Recipients` type. The test `test_selective_recipients` proves a simple but
important fact: recipient selection affects who receives the payload over the
network, but not whether the sender itself can replay the payload locally.

### 9.4 Packet Loss Is a Caller-Level Retry Story

The packet-loss test is also instructive. With unreliable links, a single
broadcast is not enough to reach everyone. The test retries from above the
crate until all peers have seen the digest.

That is exactly the right separation of responsibilities. This crate is a
best-effort dissemination primitive with replay memory, not an eventual
delivery theorem.

---

## 10. Executable Invariants

The invariants deserve to be named because the tests already enforce them.

1. **Local-first insertion.** A local broadcast must make the digest replayable
   on the sender even before any peer echoes it back.
   Proven by `test_self_retrieval`.

2. **Shared-cache liveness.** A payload exists in `items` if and only if at
   least one tracked peer deque still references its digest.
   Proven by `test_cache_eviction_single_peer`,
   `test_cache_eviction_multi_peer`,
   `test_ref_count_across_peers`,
   and the peer-set update tests.

3. **Duplicate refresh without double ownership.** A duplicate from the same
   peer refreshes that peer's recency order but does not increase the global
   refcount or create a second payload copy.
   Proven structurally by `insert_message()` and behaviorally by the eviction
   tests.

4. **Digest-addressed waiter release.** Waiters complete when the digest becomes
   available, regardless of which peer path supplied the payload.
   Proven by `test_get_nonexistent` and `test_self_retrieval`.

5. **Dead waiters do not accumulate.** Closed subscriptions are cleaned on later
   loop turns.
   Proven by `test_dropped_waiters_for_missing_digest_are_cleaned_up`.

6. **Malformed bytes do not poison later traffic.**
   Proven by `test_malformed_network_payload_does_not_break_valid_traffic`.

7. **Membership drives forgetting.** When a peer leaves all tracked sets, its
   remembered digests lose their ownership weight immediately.
   Proven by `test_peer_set_update_evicts_disconnected_peer_buffers`.

8. **Shared ownership survives partial membership churn.**
   Proven by `test_peer_set_update_preserves_shared_messages`.

9. **Shutdown is a bounded failure mode, not a panic surface.**
   Proven by `test_operations_after_shutdown_do_not_panic` and
   `test_clean_shutdown`.

These are not decorative tests. They are the executable form of the lecture.

---

## 11. Observability and Tuning

The metrics file is small, but it matters because it shows what the engine
treats as scarce.

- `peer` counts received broadcasts by peer.
- `receive` classifies inbound messages by status.
- `subscribe` counts waiter completions.
- `get` counts one-shot replay lookups.
- `waiters` tracks the number of digests currently awaited.

`waiters` is the clearest signal. It counts distinct missing digests that still
carry interest, not generic subscription handles.

The config fields and the metrics together define the operational surface:

- `mailbox_size` shapes ingress pressure,
- `deque_size` shapes replay horizon,
- `priority` shapes network scheduling,
- `codec_config` shapes the decode trust boundary,
- `peer_provider` shapes the meaning of liveness,
- metrics show whether the chosen settings actually fit the workload.

---

## 12. What Pressure This Design Absorbs

The crate is designed for five ordinary pressures.

### 12.1 Duplication

Wide-area traffic duplicates payloads. The engine keeps those duplicates cheap:
one shared payload, several peer-local recency references.

### 12.2 Delay

Readers can ask for a digest before it arrives and wait without polling.

### 12.3 Churn

Tracked membership changes do not leave orphaned retention state forever.

### 12.4 Boundedness

Memory growth is explicit and finite.

### 12.5 Malice and Corruption at the Transport Edge

Malformed input is rejected at the decode boundary and does not become a cache
event.

---

## 13. Comparisons and Limits

This crate sits in a narrow layer between transport and consensus.

Compared with consensus:

- broadcast disseminates and replays,
- consensus orders and commits.

Compared with durable storage:

- broadcast forgets on purpose,
- storage remembers on purpose.

Compared with a topic pub/sub system:

- broadcast subscriptions are digest-addressed and one-object-oriented,
- pub/sub subscriptions are stream-oriented.

Compared with naive gossip-resend loops:

- broadcast gives a stable replay key and bounded memory,
- gossip-resend alone gives neither.

What it does **not** guarantee:

- total order,
- eventual delivery to every peer,
- permanent retention,
- recovery after shutdown,
- or agreement about which payload the system should accept.

Those are not omissions. They are boundary lines.

---

## 14. How to Read the Source

Read the source in this order.

1. `broadcast/src/lib.rs`  
   Start with the public trait to see how little the transport layer promises.

2. `broadcast/src/buffered/ingress.rs`  
   Learn the three mailbox questions: send, check once, or wait.

3. `broadcast/src/buffered/config.rs`  
   Read the policy surface before the control flow.

4. `broadcast/src/buffered/engine.rs`  
   Treat this as the main lecture text. Focus on:
   `run`, `handle_broadcast`, `handle_subscribe`, `handle_get`,
   `handle_network`, `insert_message`, `evict_untracked_peers`,
   and `cleanup_waiters`.

5. `broadcast/src/buffered/metrics.rs`  
   Read this after the control flow so the counters line up with the state
   machine.

6. `broadcast/src/buffered/mod.rs`  
   Then read the tests. They are the clearest statement of the behavioral
   contract.

7. `broadcast/fuzz/fuzz_targets/broadcast_engine_operations.rs`  
   Finally, read the fuzz target. It stress-tests randomized interleavings of
   send, subscribe, get, sleep, cache size, recipient shape, and lossy network
   conditions. It is especially useful as evidence that the mailbox and engine
   should remain stable under mixed workloads.

One caveat is worth noting: the fuzz target is strongest on mailbox and network
interleavings. The peer-set eviction story is covered more directly by the unit
tests.

---

## 15. Glossary and Further Reading

- **Digest** - the stable identity of a payload.
- **Replay** - later retrieval of a payload by digest.
- **Waiter** - a pending subscription for a digest not yet present in cache.
- **Deque** - the bounded recent-digest history for one peer.
- **Refcount** - the number of peer histories still pointing at a digest.
- **Tracked peer set** - the live membership universe that still counts for
  retention.
- **Duplicate refresh** - the act of moving a digest to the front of one peer's
  deque without changing global ownership.
- **Membership-driven forgetting** - dropping payloads because the peers that
  justified retaining them are no longer tracked.

Further reading:

- `docs/blogs/commonware-broadcast.html`
- `broadcast/src/buffered/engine.rs`
- `broadcast/src/buffered/mod.rs`
- `broadcast/fuzz/fuzz_targets/broadcast_engine_operations.rs`
