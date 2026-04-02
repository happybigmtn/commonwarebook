# commonware-broadcast Interactive Book Chapter - Brief

## 1. Module Purpose

`commonware-broadcast` is a dissemination-and-replay primitive for unreliable
wide-area networks. It is not consensus, not durable storage, and not a generic
pub/sub bus. Its job is narrower and more useful:

- inject a payload into circulation now,
- remember it by digest,
- let later readers ask for that digest directly,
- and forget it once no tracked peer history still justifies keeping it.

The revised chapter should read as a Commonware lecture, not as a code walk. The
main conceptual move is to treat the buffered engine as an event loop whose
state has to stay coherent under duplication, delay, churn, malformed input, and
shutdown.

## 2. Main Conceptual Additions

The expanded version should materially deepen the current draft in six places.

1. **The event loop becomes the main machine.** The chapter should explain the
   `select_loop!` structure in `engine.rs` and how mailbox requests, network
   messages, waiter cleanup, and peer-set updates interleave.
2. **Eviction is explained as a semantic rule, not a cache trick.** The
   relationship between `items`, `deques`, and `counts` should be explicit.
3. **Duplicate-refresh semantics are named clearly.** A duplicate from the same
   peer refreshes recency without creating new global ownership.
4. **Waiter-release edge cases become first-class.** Immediate hits,
   pre-arrival waiters, dropped responders, and shutdown behavior all belong in
   the main narrative.
5. **Malformed-input handling gets its own treatment.** Decode failure is a
   boundary event, not a weird message.
6. **Tests and fuzzing become executable invariants.** The chapter should quote
   behaviors from unit tests and the fuzz target as part of the contract.

## 3. Key Source Files

### `broadcast/src/lib.rs`

Defines the public `Broadcaster` trait. This is the narrow official promise:
best-effort dissemination with a response about which peers were reached.

### `broadcast/src/buffered/ingress.rs`

Defines the mailbox surface: `broadcast`, `subscribe`, `subscribe_prepared`, and
`get`. This is where the three application questions become concrete.

### `broadcast/src/buffered/config.rs`

Defines the policy surface:

- local identity,
- mailbox backlog,
- per-peer deque size,
- send priority,
- codec bounds,
- peer-set provider.

### `broadcast/src/buffered/engine.rs`

The main source for the chapter. This file contains:

- the event loop,
- the shared cache and per-peer deques,
- waiter cleanup,
- duplicate-refresh behavior,
- membership-driven forgetting,
- and the exact ordering of local insert versus network send.

### `broadcast/src/buffered/metrics.rs`

Small file, large meaning. This tells the reader what the engine thinks is worth
measuring: received traffic, waiter completions, one-shot gets, per-peer receipt
counts, and outstanding awaited digests.

### `broadcast/src/buffered/mod.rs`

The behavioral spec. The tests in this file should drive major parts of the
chapter:

- self-retrieval,
- packet loss,
- cache eviction,
- shared-message survival across peers,
- selective recipients,
- malformed input,
- dropped waiters,
- peer-set updates,
- shutdown.

### `broadcast/fuzz/fuzz_targets/broadcast_engine_operations.rs`

This is the best source for "mixed workload" coverage. It randomizes send,
subscribe, get, sleep, recipient patterns, cache sizes, and lossy links. It is
useful to mention as evidence that the engine is meant to survive arbitrary
interleavings.

## 4. Expanded Chapter Outline

0. **Opening ledger** - promise, crux, invariant, naive failure, reading map,
   assumptions.
1. **Problem statement** - dissemination and replay without pretending to do
   agreement or durability.
2. **Mental model** - town crier with a ledger, bounded peer histories, and
   digest-addressed waiting.
3. **Public contract and policy surface** - trait, mailbox questions, config.
4. **The engine's memory model** - `items`, `deques`, `counts`, `waiters`,
   metrics, and external authorities.
5. **The event loop as protocol** - cleanup, mailbox handling, network decode,
   peer-set updates, clean stop.
6. **Duplicate-refresh semantics** - same peer, different peer, shared payload,
   no double ownership.
7. **Replay and waiter discipline** - `get` versus `subscribe`, waiter release,
   dropped responders, shutdown.
8. **Forgetting on purpose** - deque overflow, peer-set eviction, shared-message
   survival, replay horizon.
9. **Malformed input and partial failure** - decode errors, send failures,
   packet loss, selective recipients.
10. **Executable invariants** - map each important test to a named systems
    guarantee.
11. **Observability and tuning** - metrics, backlog, priority, decode bounds,
    peer-set authority.
12. **Comparisons and limits** - versus consensus, storage, pub/sub, naive
    resend loops.
13. **How to read the source** - code order plus tests and fuzz target.

## 5. Executable Invariants To Emphasize

- A payload stays cached if and only if at least one tracked peer deque still
  references its digest.
- Local broadcast inserts before network send, so the sender can replay its own
  payload immediately.
- Waiters are keyed by digest and can be satisfied by any arrival path.
- A duplicate from the same peer refreshes peer-local recency but does not
  increment global ownership.
- Malformed bytes fail at the decode boundary and do not mutate the cache.
- Removing one peer from the tracked set can evict a payload, unless some other
  tracked peer still references the same digest.
- After shutdown, operations degrade to empty results or cancellation instead of
  panicking.

## 6. Visual and Apparatus Ideas

1. **Event-loop plate** - show one loop turn with cleanup, mailbox request,
   network input, and peer-set update.
2. **Ownership diagram** - one shared payload box with arrows from several
   peer-local deques and a visible refcount.
3. **Duplicate-refresh timeline** - same digest arriving twice from the same
   peer, moving to the front without changing global ownership.
4. **Forgetting diagram** - compare deque overflow versus peer-set eviction.
5. **Executable invariants table** - invariant, enforcing structure, proving
   test.

## 7. Claims To Keep Honest

- Do not imply eventual delivery. The packet-loss test shows caller retries are
  still necessary.
- Do not imply durability. Eviction is intentional and membership-driven.
- Do not imply deduplication at the network level. The engine only makes
  duplicates cheap in memory.
- Do not imply agreement. Broadcast is for circulation and replay, not for
  deciding what the group accepts.
