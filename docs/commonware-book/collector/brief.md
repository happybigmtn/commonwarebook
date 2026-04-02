# commonware-collector Interactive Book Chapter - Brief

## 1. Module Purpose

`commonware-collector` answers a very practical systems question: how do you
coordinate a committable request across many peers, keep the replies tied to
the same commitment, and cancel the whole thing safely without teaching every
protocol to reinvent its own ledger?

The naive approach is to let each protocol invent its own little ledger:

- one map for pending requests,
- one set for peers that were asked,
- another set for peers that already answered,
- and a pile of special cases for retries, duplicates, and shutdown.

That works until it is copied a few times and each copy drifts in a different
direction. `commonware-collector` turns that pattern into one reusable
mechanism. The request's commitment becomes the shared key, the engine becomes
the switchboard, and the monitor becomes the place where collected replies are
reported with the right count for the right case.

The crate is not trying to decide what a "correct" application response means.
It only enforces the plumbing:

- the request and response share the same commitment,
- only peers that were actually sent the request can answer,
- each peer counts once per commitment,
- and cancellation makes later replies harmless.

That is enough to let higher-level protocols ask many peers the same question
without rewriting the machinery of matching, counting, and cancellation.

---

## 2. Key Source Files

### `collector/src/lib.rs`
Defines the public traits. This is where the chapter should start because it
states the three roles explicitly: `Originator`, `Handler`, and `Monitor`.

### `collector/src/p2p/mod.rs`
Defines the `Config` for the p2p-backed collector and contains the behavioral
tests. This is the best place to see the crate as a system, not just as a set
of traits.

### `collector/src/p2p/engine.rs`
The switchboard itself. It tracks commitments, routes outgoing requests, owns
the per-commitment sent/received sets, and decides whether an incoming
response counts.

### `collector/src/p2p/ingress.rs`
The application-facing mailbox. This is the thin layer that turns
`send` and `cancel` into concrete messages for the engine.

## 3. Chapter Outline

1. **Why collector exists** - the cost of repeating request/response glue in
   every protocol.
2. **Mental model** - why a commitment is the right key for shared
   coordination.
3. **The core roles** - originator, handler, monitor, mailbox, and engine.
4. **How a request moves** - send, track, receive, validate, and report.
5. **How cancellation works** - why forgetting the ledger is enough to make
   late replies harmless.
6. **What pressure it absorbs** - fanout, duplicate replies, concurrency,
   shutdown, and malformed wire input.
7. **Failure modes and limits** - what the crate does not promise.
8. **How to read the source** - which file answers which question first.

## 4. System Concepts To Explain

- **Commitment as identity** - the request's commitment is the stable key that
  ties sends, responses, and cancellation together.
- **Sent and seen sets** - the engine remembers which peers were asked and
  which peers already answered.
- **One response per peer** - the same peer cannot count twice for the same
  commitment.
- **Monitor as the sink for collected replies** - collected responses are
  reported with a running count for that commitment.
- **Cancellation as safe forgetting** - removing a commitment means later
  responses are ignored instead of causing special cleanup logic.
- **Priority lanes** - request and response traffic can be marked as priority
  without changing the collector's core shape.

## 5. Visuals To Build Later

1. **Switchboard plate** - one commitment in the center, outgoing lines to
   peers, and checked boxes for peers that already answered.
2. **Request lifecycle plate** - send, handler, response, monitor, with the
   commitment stamped on every stage.
3. **Cancel plate** - show the ledger being removed and a late response
   becoming a no-op.
4. **Duplicate-response guard plate** - show the same peer answering twice and
   only the first reply reaching the monitor.

## 6. Claims-To-Verify Checklist

- [ ] The chapter explains why request/response glue should live in one
  reusable collector instead of being rebuilt in each protocol.
- [ ] The commitment-keyed switchboard mental model is consistent throughout.
- [ ] The three public roles - originator, handler, and monitor - are clear.
- [ ] The reader understands that the engine tracks both who was sent the
  request and who already answered.
- [ ] Cancellation is explained as safe forgetting, not as a special retry
  path.
- [ ] The chapter reads like a lecture about commitment-keyed coordination,
  not a compact implementation note.
