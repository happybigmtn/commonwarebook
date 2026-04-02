# Commonware Book Research Summary

This file captures the first crate-cluster research pass used to seed new
chapters.

## Cryptography → Stream → Storage

Recommended order:

1. `commonware-cryptography`
2. `commonware-stream`
3. `commonware-storage`

Why this order:

- cryptography introduces identity, evidence, transcripts, certificates, and
  shared-key machinery;
- stream turns those ideas into a live secure channel;
- storage reuses the same trust vocabulary to explain durability, replay, and
  proof-bearing state.

### commonware-cryptography

- Core question: How do we create trustable evidence for distributed systems,
  from single-party signatures up through committee certificates and threshold
  keys?
- Mental model: a trust foundry with four products: identities, commitments,
  certificates, and shared keys.

### commonware-stream

- Core question: How do we turn an arbitrary transport into a secure, framed,
  ordered message channel with minimal assumptions?
- Mental model: a secure envelope machine built on top of any sink/stream pair.

### commonware-storage

- Core question: How do we persist state so that it is durable, recoverable,
  and often cryptographically provable?
- Mental model: start with a log, derive a view, then prove facts about that
  view.

## Broadcast → Resolver → Coding

Recommended order:

1. `commonware-broadcast`
2. `commonware-resolver`
3. `commonware-coding`

Why this order:

- broadcast teaches dissemination, caching, and digest identity;
- resolver answers the next question: how do you recover data once you missed
  the broadcast?;
- coding is the most specialized and reads best after the reader already
  understands dissemination and recovery.

### commonware-broadcast

- Core question: How do we disseminate data across an unreliable wide-area
  network without assuming every peer sees it immediately, and without
  re-sending the same payload forever?
- Mental model: a town crier with a memory.

### commonware-resolver

- Core question: If I know the key of some data but not which peer currently
  has it, how do I fetch it robustly, validate it, retry sanely, and stop
  wasting work once I have the right answer?
- Mental model: a missing-piece coordinator.

### commonware-coding

- Core question: How do we split data into pieces so that a subset is enough to
  recover the original while still letting participants reject malformed or
  inconsistent pieces?
- Mental model: a proof-carrying jigsaw.

## Support and Appendix Candidates

Recommended writing priority:

1. `commonware-codec`
2. `commonware-math`
3. `commonware-conformance`
4. `commonware-macros`
5. `commonware-utils`
6. `commonware-parallel`
7. `commonware-invariants`
8. `commonware-collector`
9. `commonware-deployer`

Scale guidance:

- Full chapter:
  - `commonware-codec`
  - `commonware-math`
  - `commonware-conformance`
- Shorter appendix or case-study:
  - `commonware-macros`
  - `commonware-utils`
  - `commonware-parallel`
  - `commonware-invariants`
  - `commonware-collector`
  - `commonware-deployer`
