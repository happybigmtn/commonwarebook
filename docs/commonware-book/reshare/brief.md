# Chapter Brief: commonware-reshare

## 1. Module Purpose

`commonware-reshare` teaches a hard distributed-systems lesson: trust can be
handed off, but it cannot be assumed to stay still. How do you keep a threshold
secret alive while the committee that carries it keeps changing?

The naive version of the problem is to treat a committee as permanent. That
works only if the same participants stay online forever, never crash, and never
need to hand the secret to a new set of signers. Real systems do not get that
luxury. Membership changes. Some validators only participate for a while. Some
epochs need a different dealer set. And if the secret is not moved carefully,
the chain keeps producing blocks while losing the ability to sign them.

This example shows the smaller, more durable pattern:

- consensus runs over an **epoched log**,
- each epoch choreographs dealer and player state machines,
- DKG persistence replays exact messages after restart,
- the engine, orchestrator, and marshal cooperate to make epoch boundaries
  explicit,
- and the next epoch starts from the previous output, not from scratch.

The important thing is continuity. The chapter should read like a lecture on
committee succession: the secret is the baton, each epoch is a handoff, and the
committee is only trustworthy if it can inherit rather than reinvent.

---

## 2. Source Files That Matter Most

### `examples/reshare/src/dkg/state.rs`
The persistence layer for the secret-moving problem. This file explains how the
example remembers epoch state, dealer messages, player acks, and finalized logs
so a crash does not erase the protocol's memory of trust.

### `examples/reshare/src/dkg/actor.rs`
The heart of the example. It keeps per-epoch DKG state, replays acks and logs
from storage, drives dealer and player behavior, watches finalized blocks, and
advances the resharing state when an epoch closes.

### `examples/reshare/src/engine.rs`
The composition root for validators. It wires together buffered transport,
consensus, the DKG actor, the orchestrator, and the epoch-aware application.

### `examples/reshare/src/orchestrator/actor.rs`
The epoch transition manager. It starts and stops consensus engines as epochs
enter and exit, and it asks marshal to fetch missing boundary finalization when
it sees evidence that another peer is already ahead.

### `examples/reshare/src/application/core.rs`
The consensus-facing application. It shows how a block can carry the DKG
outcome without letting consensus learn the protocol details.

### `examples/reshare/src/application/scheme.rs`
The epoch-aware signing scheme provider. This file is where the chapter can
explain why the initial DKG, the trusted bootstrap case, and later epochs use
different verification stories.

### `examples/reshare/src/setup.rs`
The initial participant generation story. Important mainly for explaining the
bootstrap distinction between trusted setup and initial DKG.

---

## 3. Chapter Outline

1. **Why resharing exists** - why trust must move when the committee moves.
2. **Mental model** - a relay race over a notebook, where each checkpoint is an
   epoch and each handoff is a transfer of authority.
3. **The core ideas** - epoch boundaries, dealer/player state machines,
   persistent replay, and engine/orchestrator/marshal composition.
4. **The full epoch timeline** - bootstrap, enter, distribute, finalize,
   persist, exit, and inherit.
5. **Bootstrap modes compared** - trusted bootstrap, DKG bootstrap, and
   resharing as separate trust stories.
6. **What pressure it absorbs** - crashes, duplicate messages, delayed peers,
   and rotating committee sizes.
7. **How to read the source** - which file reveals which part of the story
   first.

## 4. System Concepts To Explain

- **Committee continuity** - the next committee should not invent a fresh
  secret; it should inherit the last valid one and prove it can carry trust
  forward.
- **Epoched log** - the chain is the timeline that decides when a resharing
  round closes and the next one starts.
- **Dealer and player replay** - persisted messages let the actor resume the
  same cryptographic commitments after a restart.
- **Boundary finalization** - the orchestrator only advances once the current
  epoch is really over, not when some task happens to be ready.
- **Dual roles** - a participant can be both dealer and player in the same
  epoch, which is why the example treats message flow as a state machine rather
  than a one-shot exchange.
- **Bootstrap split** - the first epoch can begin from either a trusted dealer
  output or a full DKG, but later epochs are resharing, not initial setup.
- **Continuity pipeline** - engine, orchestrator, and marshal each own a
  different part of the handoff so no layer has to guess about the others.

## 5. Visuals To Build Later

1. **Committee relay plate** - show one committee passing a secret baton to the
   next committee across epoch boundaries.
2. **Epoch log plate** - show blocks at the end of an epoch triggering final
   resharing state, then starting the next committee with the new output.
3. **Persistence plate** - show dealer messages, acks, and logs flowing into
   storage and back out again after a restart.
4. **Transition plate** - show the orchestrator starting a new consensus engine
   for each epoch and stopping the old one only after boundary finalization.

## 6. Claims-To-Verify Checklist

- [ ] The chapter explains why committee continuity is the actual problem, not
      just threshold signing.
- [ ] The epoched log is framed as the timeline that advances the secret.
- [ ] The reader understands how persisted DKG state supports crash recovery.
- [ ] The chapter makes clear that a participant can act as both dealer and
      player in the same epoch.
- [ ] The chapter distinguishes bootstrap, DKG, and resharing without turning
      into a CLI tour.
- [ ] The chapter explains the handoff ordering: compute, persist, acknowledge,
      callback, exit.
- [ ] The chapter stays focused on the protocol story rather than the command
      surface.
