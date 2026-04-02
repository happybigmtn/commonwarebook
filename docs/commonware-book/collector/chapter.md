# commonware-collector

*A lesson in commitment-keyed coordination: ask many peers the same question,
count only the replies that belong, and make cancellation a clean act of
forgetting.*

---

## Background

Distributed systems are hard for a simple reason: messages do not arrive as a
single clean conversation. They arrive late, out of order, twice, or not at
all. Once a request fans out to many peers, the protocol has to answer a few
basic questions before it can answer the application question.

- Which peers were asked?
- Which replies belong to this request?
- Has this peer already answered?
- What should happen if the request is canceled while replies are still in
  flight?

Those questions are about **coordination**, not application meaning. A reply
can be timely and still belong to the wrong request. A request can be canceled
and still have packets arrive later. A duplicate reply can be real network
traffic and still not count twice.

The naive response is to use a single boolean or a simple counter and hope the
rest sorts itself out. That works only until the network misbehaves. Then the
protocol needs to distinguish identity from order, and membership from content.
That is why distributed systems often key work by a request ID, a digest, or a
commitment: the identifier says which case the packet belongs to.

The other naive response is to make cancellation mean rollback. That is usually
too expensive and too fragile. In-flight messages cannot be taken back. The
cleaner pattern is to close the case file and ignore late arrivals. That keeps
the protocol honest about what it can and cannot control.

The main tradeoff in this chapter is narrowness versus reuse. If the layer tries
to understand the application's meaning, it becomes too specialized. If it only
tracks commitment and sender identity, it can serve many protocols while
leaving the actual decision to the application.

---

## 1. What Problem Does This Solve?

Distributed protocols keep running into the same coordination problem. A
leader, a client, or a replica needs to ask the same question of several
peers, collect the replies that actually matter, and then stop the whole
conversation when the request is no longer worth pursuing.

That sounds ordinary until you try to make it safe.

Once the request fans out, you need a ledger for who was asked, a rule for who
is allowed to answer, a way to suppress duplicates, and a clean way to retire
the request when the application changes its mind. If every protocol invents
its own version of that machinery, the same mistakes get rewritten over and
over.

`commonware-collector` exists to keep that machinery in one place. It takes a
request with a commitment, routes it to a set of peers, and accepts replies
only when they belong to that same commitment and come from peers that were
actually contacted.

The boundary is deliberate. The collector does not decide whether a reply is
correct for the application. It decides whether the reply belongs to the
current case file. The application owns meaning; the collector owns the
coordination discipline.

---

## 2. Mental Model

Picture a switchboard, but think of it as a courtroom clerk rather than a
network gadget. Each outstanding request gets a case file, and the case file
is keyed by commitment.

When `send` runs, the collector opens that case file and records two facts:

- which peers were asked to weigh in,
- which peers have already filed a reply.

That is the whole trick. Everything else follows from those two lists.

- A request is not just a payload. It is a coordinated case.
- A response is not just a packet. It is an answer that must point back to the
  same case.
- Cancellation is not a rollback algorithm. It is the decision to close the
  case file so later answers have no place to land.

The commitment is the stable anchor because it names the case, not the route.
Peers can answer in different orders, the network can duplicate traffic, and
the application can decide to walk away. The commitment keeps all of those
events attached to one shared point of reference.

That is why the collector feels more like a clerk than a router:

- stamp the request with the commitment,
- stamp the ledger with the peers that were contacted,
- stamp each valid response once,
- and file the case away when the request is canceled.

The implementation is small because the idea is small. The power comes from
using the same commitment everywhere the coordination needs a name.

---

## 3. The Core Ideas

### 3.1 Three roles keep the conversation narrow

`collector/src/lib.rs` splits the coordination contract into three obligations:
starting and canceling work, answering work, and observing gathered replies.
That division matters because the crate is not trying to be a full messaging
framework. It is trying to keep each actor's responsibility narrow so the
commitment boundary stays visible.

### 3.2 The mailbox is the application-facing door

`collector/src/p2p/ingress.rs` exposes a `Mailbox`.

The mailbox does not interpret the protocol. It only translates application
intent into engine messages:

- `send(recipients, request)` becomes work for the switchboard,
- `cancel(commitment)` becomes a request to retire the case file.

That keeps the surface area small. The hard state stays inside the engine.

### 3.3 The engine owns the ledger

`collector/src/p2p/engine.rs` is where the metaphor becomes state.

Its central structure is a map from commitment to two peer sets:

- peers that were asked,
- peers that have already replied.

Those two sets are enough to enforce the collector's main invariant:

**a reply counts only if the request was sent to that peer, and each peer
counts once per commitment.**

Around that ledger the engine keeps the machinery needed to make the contract
operational: application commands, incoming requests, collected responses,
blockers for invalid traffic, and counters that expose the amount of work still
in flight. The metrics are secondary, but they make the pressure on the
switchboard visible.

One implementation detail deserves more weight than the old chapter gave it:
the tracked map stores exactly what this layer is allowed to know.

```text
tracked[commitment] = (asked_peers, replied_peers)
```

That is intentionally narrow. There is no application verdict in the ledger, no
"best response so far," and no embedded timeout machine. The collector is not
trying to become a protocol-specific state manager. It is proving a smaller
claim: whether a response belongs to a case file and whether it should count
exactly once.

### 3.4 The processed future pool keeps request handling from pinning the loop

The engine also has to solve a second problem: incoming requests may take time
to answer, but the coordination loop still needs to keep moving.

That is why `run()` creates a `commonware_utils::futures::Pool` called
`processed`. When a request arrives, the engine hands it to the `Handler`
together with a oneshot response channel, then pushes a future into the pool
that will later resolve to `(peer, response)`.

So the collector is maintaining two conversations at once:

- the main event loop that owns the commitment ledger,
- and an unordered completion pool for request handlers that may finish later.

That split is what lets the collector stay responsive to cancel commands and
incoming responses even while handlers are still doing work.

### 3.5 Commitment is the shared identity

The request and response types are tied together by commitment and digest. The
collector does not match replies by guessing or by inventing a new request ID.
It matches them by the same identity the protocol already carries forward.

That is what makes the crate reusable. It can sit underneath a vote, a query,
a fragment exchange, or a challenge response, because it cares only that the
request and response belong to the same committed case.

---

## 4. How the System Moves

### 4.1 Sending a request

The sequence begins when the application calls `send` on the mailbox.

The mailbox creates an internal one-shot response channel, places the request
into `Message::Send`, and hands it to the engine. The engine then does the
coordination work:

1. it computes the request commitment,
2. it creates a tracking entry if this is the first time it has seen that
   commitment,
3. it marks the commitment as outstanding,
4. it sends the request to the chosen recipients through the p2p transport,
5. and it returns the peers that were actually reached.

That last step is important. Sending is not a promise that the network will
obey. It is an attempt. The collector records the result of the attempt rather
than pretending every peer was reached.

### 4.2 Handling an incoming request

When a request arrives from the network, the engine does not answer it
directly. It hands the request to the `Handler` together with the origin peer
and a one-shot response channel.

That gives the handler a simple choice: reply or stay silent. The engine can
keep several handler futures in flight at once, so a slow peer does not pin the
entire switchboard.

This is another place where the coordination story matters. The collector does
not force a response. It gives the handler a structured way to contribute one.

### 4.3 Receiving a response

When a response arrives, the engine checks the response against the case file
before the monitor hears about it:

1. Does this commitment still exist?
2. Was the request ever sent to this peer?
3. Has this peer already answered for this commitment?

Only when all three answers are yes does the response count.

That is the duplicate-suppression rule in its simplest form. The engine does
not need a larger protocol for this part because the commitment and the peer
identity already give it enough information to know whether a reply belongs.

If the response is valid, the engine forwards it to the monitor with the
current count for that commitment.

It helps to state the response admission matrix directly:

| Condition | Engine behavior |
| --- | --- |
| Commitment unknown | ignore as late or orphaned |
| Peer was never asked | ignore as unsolicited |
| Peer already replied | ignore as duplicate |
| Response decode fails | block peer |
| All checks pass | count once and forward to monitor |

That table is the real personality of the crate. The collector does not know
whether the answer is semantically correct for the application. It knows whether
the answer belongs to this coordinated case.

### 4.4 Canceling a request

Cancellation is the moment the chapter's thesis becomes practical.

The application sends a commitment. The engine removes the matching tracking
entry. From that point forward, late responses for that commitment are just
orphans. They may still arrive, but they no longer have a case file to attach
to.

That is the right tradeoff for this layer. The collector does not try to
unsend packets or unwind work already done elsewhere. It ends the coordination
by forgetting the ledger.

### 4.5 Cancel-then-late-reply is the important edge case

The key edge case in this crate is not just duplicate replies. It is
successful late replies after the application has already moved on.

The tests in `collector/src/p2p/mod.rs` model this directly:

- a request is sent,
- its commitment is canceled immediately,
- the remote side may still process and answer,
- but the local engine no longer has a ledger entry for that commitment,
- so the late response is ignored.

This is a deep design choice hiding in a small amount of code. The collector is
refusing to pretend that cancellation can rewind the network. It can only close
the case file locally.

### 4.6 Invalid-wire handling is part of the protocol

Both inbound requests and inbound responses travel through wrapped codec
channels. If either fails to decode, the collector does not merely log the
error. It uses the blocker to isolate the peer.

That matters because malformed wire data is not just transport noise here. It
is an attempt to inject a message into a commitment-tracking protocol without
satisfying the grammar that makes the protocol safe to reason about.

---

## 5. What Pressure It Is Designed To Absorb

The collector is built for the pressures that show up in protocol code rather
than in toy examples:

- **Fanout pressure** - one request can go to many peers at once.
- **Response skew** - some peers answer quickly, some answer late, and some
  answer twice.
- **Concurrency pressure** - many commitments can be outstanding at the same
  time.
- **Shutdown pressure** - requests can be canceled when the application moves
  on or the engine is stopping.
- **Wire pressure** - malformed request or response frames should be rejected
  rather than half-interpreted.
- **Operational pressure** - request and response traffic can be marked as
  priority without changing the collector's basic shape.

The design answers all of that with the same move: keep the state local,
minimal, and keyed by commitment.

That is why the engine uses one map with two peer sets instead of a more
elaborate graph of request states. The problem is coordination. The collector
keeps the coordination visible and leaves the rest alone.

### 5.1 Tests and fuzzing are part of the mechanism story

This chapter gets much stronger once you read the tests and fuzz target as
evidence rather than appendix material.

The tests in `collector/src/p2p/mod.rs` cover the cases the prose most needs:

- ordinary send-and-collect,
- cancel before reply,
- broadcast to several peers,
- duplicate response suppression,
- invalid request and response handling,
- and shutdown behavior.

The fuzz target in `collector/fuzz/fuzz_targets/collector.rs` broadens that
surface by varying recipient shapes, request/response encodings, handler
behavior, and local timing inside the deterministic runtime.

That is exactly the kind of evidence this chapter needed to stop sounding like
an outside-in overview.

---

## 6. Failure Modes and Limits

The collector is not a consensus protocol, and it is not a durability layer.
It does not guarantee that every peer will answer, that responses will arrive
in any global order, or that a canceled request can be revived later.

Its job ends at the switchboard.

That means the main failure modes are easy to name:

- If a peer never receives the request, its reply will never count.
- If a peer sends invalid wire data, the blocker can isolate it.
- If a peer answers more than once, only the first response counts.
- If the request was canceled, later responses are ignored.
- If the engine shuts down, the mailbox stops being a reliable place to send
  new work.

There is a deeper limit worth stating plainly: the collector knows commitment
and sender identity, but it does not know whether a response is correct in the
application sense. The application still owns that meaning.

That is not a weakness. It is why the crate can serve many protocols without
turning into one more protocol with its own opinions.

---

## 7. How to Read the Source

Start in `collector/src/lib.rs` to understand the three roles that split the
coordination boundary.

Then read `collector/src/p2p/ingress.rs` for the application-facing edge and
`collector/src/p2p/engine.rs` for the actual ledger mechanics:

- how commitments enter `tracked`,
- how the processed future pool keeps handlers from pinning the loop,
- and how responses are admitted or discarded.

After that, read `collector/src/p2p/mod.rs` for the tests that prove the
collector still behaves when replies are duplicated, canceled, delayed, or sent
by the wrong peer.

Finish with `collector/fuzz/fuzz_targets/collector.rs` if you want to see the
broader search surface around malformed encodings and mixed workloads.

---

## 8. Glossary and Further Reading

- **Commitment** - the stable key that identifies one request case.
- **Mailbox** - the application-facing entry point for sending and canceling.
- **Engine** - the switchboard that tracks outstanding commitments and counts
  replies.
- **Handler** - the actor that processes incoming requests and may respond.
- **Monitor** - the observer that receives collected responses and counts.
- **Blocker** - the guard that can isolate peers sending invalid data.
- **Outstanding commitments** - the requests the engine is still tracking.

For a close sibling chapter, read `commonware-p2p` next. Collector sits on top
of that transport and turns raw peer links into a reusable request/response
workhorse.
