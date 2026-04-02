# commonware-resolver Interactive Book Chapter Brief

## 0. Opening Apparatus

Promise: `commonware-resolver` keeps one keyed search alive until the consumer
accepts the bytes, without mistaking a reply for a solution.

Crux: the resolver coordinates missing pieces. It preserves one search per
key, retries without duplicating work, and keeps validation separate from
retrieval.

Primary invariant: a key never becomes two searches, and a search ends only
when the consumer accepts the value, the caller cancels it, or the key is
retained away.

Naive failure: if every reply counts as success, every miss becomes fan-out,
every invalid response looks useful, and the network burns time rediscovering
the same absence.

Reading map:

- `resolver/src/lib.rs` for the public contract.
- `resolver/src/p2p/fetcher.rs` for the search state machine.
- `resolver/src/p2p/engine.rs` for the actor loop.
- `resolver/src/p2p/wire.rs` for the request IDs and payload grammar.
- `resolver/src/p2p/mod.rs` and `resolver/src/p2p/fetcher.rs` for the tests
  that pin the behavior down.

Assumption ledger:

- The reader is comfortable with asynchronous message passing.
- The reader wants the resolver as a distributed-systems primitive, not a
  storage API.
- The chapter reads the code as BETA behavior: stable wire and API, not a
  sketch.

## 1. Module Purpose

`commonware-resolver` solves a specific distributed-systems problem: you know
the key of some data, but not which peer has it yet. The crate coordinates the
search at the edge. It keeps one search alive per key, sends requests over the
P2P network, remembers what has already been tried, and stops only when the
consumer accepts the value.

That sounds simple until you ask what happens in a real network:

- several peers may answer at once,
- some peers may return empty responses,
- some peers may return invalid bytes,
- a target peer may be temporarily unavailable,
- and the application still needs one clean answer, not a pile of duplicate
  work.

The resolver owns that middle layer. It does not invent truth. It manages the
search for truth and keeps validation separate from retrieval. The application
supplies two judgments:

- `Producer` decides what bytes to serve when other peers ask for a key.
- `Consumer` decides whether a fetched value is valid when it comes back.

The P2P engine then acts like a coordinator between those two roles. On the
outbound side, it chooses peers, persists requests, retries sanely, and blocks
peers that deliver invalid data. On the inbound side, it serves requests by
handing them to the producer and sending the result back with the original
request ID.

Stability: `commonware-resolver` is **BETA**. Its public API and wire behavior
are intended to be stable.

## 2. What Must Be Explained

This chapter should explain the resolver at three levels at once:

- the public contract,
- the fetcher state machine,
- and the engine loop that keeps the two sides synchronized.

The key ideas to make concrete are:

- one key becomes one durable search,
- targeted search is a hard boundary, not a hint,
- request IDs match answers to questions,
- self-exclusion prevents local shortcuts from hiding distributed behavior,
- blocked peers are evidence-driven,
- and serving is the mirror image of fetching.

## 3. Source Files To Drive the Expansion

### `resolver/src/lib.rs`
Defines the public contract. `Consumer` is the validation boundary: it receives
`(key, value)` and returns `true` only when the application accepts the value.
`Resolver` is the control surface: fetch, fetch-all, targeted fetch, cancel,
clear, and retain. The docs on `fetch_targeted()` and `fetch_all_targeted()`
define the targeting rules precisely.

### `resolver/src/p2p/mod.rs`
The module-level explanation of the P2P resolver. This is the conceptual
bridge between the public traits and the actor implementation. It explains the
dual role of the peer actor: it fetches data for local consumers and serves
data to remote peers through the same network path.

### `resolver/src/p2p/engine.rs`
The actor loop. This file shows how mailbox commands, network responses,
timeouts, peer-set changes, and producer completions fit together. It is where
the chapter should explain the control flow of the whole crate, not just the
fetch path.

### `resolver/src/p2p/fetcher.rs`
The heart of the retrieval state machine. It tracks pending requests, active
requests, per-key targets, blocked peers, per-peer performance, retry
deadlines, and request IDs. If the chapter has to teach one file deeply, it is
this one.

### `resolver/src/p2p/wire.rs`
The wire format. `Message { id, payload }` and `Payload::{Request, Response,
Error}` are enough to tell the whole story: every request and response is
keyed, and every response can say "I do not have it" without pretending to be
a value.

### `resolver/src/p2p/config.rs`
The configuration surface for the peer actor. It controls mailbox depth,
retry timing, request and response priority, and the initial performance score
given to new peers.

## 4. Expanded Chapter Outline

1. Start from the edge.
2. Public contract: `Resolver`, `Consumer`, `Producer`.
3. The fetcher as memory: pending, active, targets, blocked peers, request
   IDs.
4. Unrestricted vs targeted search.
5. Request IDs and `(peer, id)` matching.
6. The engine loop: mailbox, deadlines, peer-set reconciliation, responses.
7. Serving as the mirror image of fetching.
8. Pressure and failure: timeouts, empty responses, invalid bytes,
   cancellations, retention, and clear.
9. What the tests prove.

## 5. Claims To Verify

- A duplicate fetch for the same key does not create duplicate in-flight
  work.
- A valid response clears the fetch and removes its targets.
- An invalid response blocks only the peer that misbehaved.
- A "no data" response does not clear the target set.
- A targeted fetch only tries the listed peers.
- Clearing targets allows the fetch to fall back to any eligible peer again.
- Pending requests wait for retry deadlines instead of spinning.
- Active requests time out and re-enter the retry path.
- Request IDs prevent stale responses from completing the wrong key.
- The peer actor can both serve remote requests and fetch local ones in the
  same loop.

