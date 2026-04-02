# commonware-reshare

*How a committee passes trust forward without pretending the world stood still.*

---

## Why Threshold Keys Need Succession

Threshold cryptography gives a group collective control over a secret. Instead
of one signer holding the whole key, a committee holds shares and can act only
when enough shares cooperate. That buys fault tolerance and rotation, but it
also creates a new problem: the committee itself changes over time.

The key vocabulary is threshold, share, dealer, player, DKG, and epoch. A
share is one piece of a larger secret. A dealer distributes share material. A
player receives and validates share material. A DKG run creates the initial
shared secret without trusting one founder to hold everything. An epoch is the
bounded time window in which one committee is responsible for the current
round.

The naive approach is to rerun DKG from scratch every time membership changes.
That is easy to explain, but expensive and disruptive. The other naive
approach is to keep the same committee forever. That avoids rekeying work, but
it ignores churn and eventually makes the system brittle as participants leave
or join. A more subtle failure is to copy share state by hand without a clear
handoff rule. That can leave the next committee with a story that is almost
right and impossible to replay after a crash.

The main tradeoff is continuity versus rebootstrap cost. Resharing preserves
the secret's continuity across changing membership, but it demands durable
state, deterministic replay, and careful boundary rules for when one epoch
stops and the next one inherits the output. `commonware-reshare` is about that
succession problem, not about making DKG itself feel magical.

## 1. Why Resharing Exists

Threshold cryptography is easy to imagine when membership never changes. Pick a
committee, split the secret, require enough shares, and you are done.

Real systems do not stay still. Validators rotate in and out. Some participants
only exist for a single epoch. Some rounds need a smaller dealer set than the
previous round. If the secret stays tied to one fixed membership, the chain may
continue producing blocks while silently losing the ability to sign the next
ones.

`commonware-reshare` is not a tutorial about rerunning DKG from scratch. It is
a lecture on succession. The problem is not whether a threshold secret exists.
The problem is whether a changing committee can inherit it without breaking
continuity.

The example treats the chain as an **epoched log**. Each epoch is a bounded
window in which one committee is responsible for moving trust forward. The
output of one epoch becomes the starting point of the next. The secret is not
rebuilt from nothing. It is handed on.

That is why the chapter should be read as a protocol story, not as a module
tour. The important question is not "what function ran?" The important question
is "what state had to survive so the next epoch could keep the story coherent?"

---

## 2. Mental Model

Picture a relay race staged on a notebook page.

Each lap is an epoch. The runner does not carry the whole race history in their
hands. They carry a baton. At the end of the lap, the baton is handed off, and
the notebook records who held it, what they said, and whether the handoff was
actually completed.

That is `commonware-reshare`.

- The **baton** is the threshold secret.
- The **notebook** is durable DKG storage.
- The **laps** are epochs.
- The **runners** are committees that overlap in time but do not remain the
  same forever.
- The **official** is the orchestrator that decides when one lap is really
  over.

The deeper point is that there are two clocks in the system:

1. the chain clock, which decides when an epoch boundary exists, and
2. the DKG clock, which decides what must be remembered across that boundary.

The chain says when trust may move. The DKG state says how the next committee
can continue without guessing.

---

## 3. The Core Ideas

### 3.1 The epoch boundary is a constitution

The example uses `BLOCKS_PER_EPOCH` to divide the chain into windows. That is
not just a scheduling knob. It is the rule that tells the protocol when a
committee's authority begins and ends.

While an epoch is open, the current committee distributes shares, records
acks, and accumulates the evidence needed to close the round. When the last
block arrives, the actor stops treating the round as an open conversation and
turns it into an outcome.

The chain does not merely carry the resharing protocol. It governs succession.

### 3.2 Dealer and player are state machines, not labels

Inside one epoch, a participant may act as both a **dealer** and a **player**.
That is the choreography this example is really teaching.

The dealer side starts from the epoch's output, share, and RNG seed. It tracks
which player messages are still unsent, replays stored acks after a restart,
and finalizes exactly once so it can produce a signed dealer log.

The player side resumes from the stored dealer messages and logs already seen
in the epoch. It keeps an acknowledgment cache so the same dealer message always
leads to the same ack after a crash.

The key invariant is simple: once the actor has committed to a dealer message or
an acknowledgment, it must make the same choice after a restart.

That is why the example treats message flow as a state machine. A dealer is not
just "someone who sends." A player is not just "someone who receives." Each role
has memory, replay, and a deterministic end state.

### 3.3 Persistent DKG storage is protocol memory

The storage layer is doing the unglamorous work that makes the whole system
survive reality.

It keeps epoch state in metadata keyed by epoch number, and it keeps dealer
messages, player acks, and finalized dealer logs in a journal. On restart, that
data is replayed back into in-memory caches so the actor can resume the same
cryptographic commitments instead of inventing new ones.

That replay matters because DKG work is not atomic. A share may be sent before
its ack is persisted. A log may be finalized before the node learns the epoch is
done. A crash in the middle of that process cannot be allowed to create a second
version of the same handoff.

The lesson is broader than this example:

**any change that alters a cryptographic commitment must be recoverable after a
restart.**

The storage layer also makes the security tradeoff explicit. It preserves share
material so the actor can recover, but that means old shares must be handled
carefully at the operational layer. Recovery and secure deletion are not the
same problem.

### 3.4 Engine, orchestrator, and marshal form one continuity pipeline

The system is not a single loop. It is a stack of responsibilities that turns
continuity into an explicit contract.

- The **engine** composes the DKG actor, buffered network plumbing, consensus,
  and the epoch-aware application into one validator process.
- The **orchestrator** starts a fresh consensus engine when an epoch begins and
  stops the old one only after boundary finalization is safe.
- The **marshal** layer is the evidence courier. It fetches missing boundary
  finalization when a peer appears to be ahead, so the system does not assume
  continuity from rumor.

That division is the important architectural lesson. Consensus orders blocks.
The DKG actor decides what the resharing evidence means. The orchestrator makes
epoch succession explicit. Marshal makes missing history retrievable.

The application stays intentionally thin. It asks the DKG actor for the current
outcome when proposing a block, and it lets the finalized block feed back into
the DKG actor later. Consensus sees a block. The resharing protocol sees a
boundary.

---

## 4. The Full Epoch Timeline

The easiest way to understand the example is to follow one epoch from start to
finish.

### 4.1 Setup chooses the starting story

The setup phase generates participants and then chooses one of two starts:

- a trusted threshold output, or
- a full DKG bootstrap ceremony.

That choice only affects how epoch 0 begins. Once the validator is running, the
important question is the same in both cases: can the next epoch inherit a valid
output from the previous one?

### 4.2 The validator composes the moving parts

The validator process wires together the network, marshal, engine, and DKG
actor. It is the place where the pieces become one continuity pipeline. The
point is not the wiring itself. The point is that the validator owns the whole
succession path, from network messages to epoch transitions.

### 4.3 The DKG actor restores durable state

At startup, the DKG actor loads the persisted epoch state. If the node has never
seen the epoch before, it seeds fresh round state with the current RNG seed,
output, and share.

It then determines the current dealer and player sets from the peer config and
the prior output. In resharing mode, the current dealers must come from the
previous output's players. That is how continuity is enforced instead of merely
assumed.

The actor also tells the orchestrator that a new epoch has started. This is the
first visible handoff in the timeline.

### 4.4 Early epoch work is share distribution and ack replay

During the early phase, dealers continuously distribute shares. Players accept
dealer messages, persist them, and generate a deterministic ack. If the node is
both dealer and player for the same epoch, it handles the self-dealing path in
both roles so it does not special-case itself out of the protocol.

This is where persistence matters most. The same dealer message must lead to the
same ack after a restart, and the dealer must remember which acks are already
safe to use.

### 4.5 Mid-epoch work is finalization discipline

At or after the midpoint, the dealer finalizes if it has not already done so.
That is deliberate. The protocol does not wait until the end of the epoch to
begin deciding what the outcome means. It simply waits until the boundary to
commit to the outcome.

If the actor is asked to propose a block during the epoch, it can include the
reshare outcome when one exists. But the example only treats that outcome as
authoritative after the block is finalized. That keeps verification fast and
pushes protocol meaning to the boundary where it belongs.

### 4.6 The last block closes the round

When the final block of the epoch is finalized, the actor performs the actual
handoff.

It reads the logs for the epoch and resolves the round:

- if the player state can finalize, it yields a new output and a new share;
- if the actor is only observing, it reconstructs the output from the dealer
  logs;
- if the round failed, it keeps the previous valid state and does not pretend a
  handoff succeeded.

The important ordering is this:

1. compute the result,
2. persist the next epoch state,
3. acknowledge the finalized block,
4. notify the callback,
5. tell the orchestrator to exit the epoch.

That ordering prevents a crash from creating a public success with private
amnesia. The next epoch is written down before the outside world is told the
story advanced.

### 4.7 The next epoch starts from the previous output

On the next epoch, the actor loads the new durable state again.

If the round succeeded, it starts from the new output and share. If the round
failed, it carries the previous valid state forward and tries again in the next
window. Either way, the system has a memory of continuity. It does not invent a
fresh secret and call that success.

---

## 5. Bootstrap Modes Compared

The example has three distinct starting stories, and it is important not to
blur them together.

### Trusted bootstrap

The setup procedure can produce an initial threshold output and per-participant
shares from a trusted dealer. That is the simplest operational start. The
validators begin with an already-established secret and immediately move into
resharing across epochs.

### DKG bootstrap

The system can also start by running a distributed ceremony for epoch 0. In that
case, the first output is produced by the participants themselves instead of by
a trusted dealer. Once that is done, later epochs are still resharing, not
another bootstrap.

### Resharing epoch

This is the recurring case the chapter is really about. The current epoch does
not invent a new committee from scratch. It inherits the previous output,
derives the current dealer set from the previous players, and carries the share
forward.

The comparison matters because each mode has a different trust story, but they
all feed the same epochal machine after startup.

---

## 6. What Pressure It Is Designed To Absorb

This example is built for the kinds of failure that make distributed systems
feel unfair.

It absorbs crashes by persisting the exact messages that matter. It absorbs
restarts by replaying those messages into dealer and player state. It absorbs
duplicate messages by making the handlers idempotent with respect to stored
commitments. It absorbs delayed peers by keeping share distribution and ack
handling open for the whole early part of the epoch.

It also absorbs committee churn. The set of dealers can change from one epoch
to the next, but the transition is not arbitrary. The new committee is drawn
from the previous output's players, so continuity is preserved instead of
invented.

That design makes two tradeoffs explicit:

- it assumes a meaningful synchrony window during each epoch,
- and it prefers durable replay over speculative optimism.

Those are good tradeoffs for a resharing protocol. Secret handoff is not a
place to be clever.

---

## 7. How to Read the Source

If you want to map the lecture back to the code, read the source as a chain of
responsibilities:

1. `examples/reshare/src/engine.rs` shows how the validator becomes one
   continuity pipeline.
2. `examples/reshare/src/dkg/state.rs` shows what must survive restart so the
   next epoch can continue the same commitment.
3. `examples/reshare/src/dkg/actor.rs` shows how dealer and player roles turn
   persistence into replayable protocol state.
4. `examples/reshare/src/orchestrator/actor.rs` shows how boundary finalization
   makes epoch entry and exit explicit.
5. `examples/reshare/src/application/core.rs` and
   `examples/reshare/src/application/scheme.rs` show how consensus stays
   separate from resharing while still consuming its outcome.
6. `examples/reshare/src/setup.rs` shows the two startup stories and why they
   lead to the same continuity problem.

If you keep that order, the example reads like one continuity story instead of
a bag of modules.

---

## 8. Glossary

- **Epoch** - one window of consensus and resharing activity.
- **Dealer** - a participant that sends share material for the current epoch.
- **Player** - a participant that receives dealer messages and acknowledges
  them.
- **Output** - the public result of a DKG round.
- **Share** - the private secret fragment held by a participant.
- **Dealer log** - the evidence that a dealer's round completed successfully.
- **Boundary finalization** - the finalized block that closes one epoch and
  allows the next one to begin.
- **Committee continuity** - the idea that a new epoch should inherit the
  secret from the previous epoch rather than recreate it.

---
