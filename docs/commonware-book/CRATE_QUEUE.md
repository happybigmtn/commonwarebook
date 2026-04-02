# Commonware Book Crate Queue

This file now serves as the editorial status record for the completed first
edition of the Commonware book. The rule that shaped the volume was simple:

- start from the systems question,
- build a clear mental model,
- use code to prove the idea,
- avoid falling into line-by-line source narration unless the line explains a
  genuinely important invariant.

## Current Chapter Pass

| Crate | Chapter Status | Lecture Pass |
|-------|----------------|--------------|
| `commonware-runtime` | Featured | Lecture pass complete |
| `commonware-p2p` | Featured | Lecture pass complete |
| `commonware-consensus` | Featured | Lecture pass complete |
| `commonware-broadcast` | Complete | Lecture pass complete |
| `commonware-cryptography` | Complete | Lecture pass complete |
| `commonware-stream` | Complete | Lecture pass complete |
| `commonware-storage` | Complete | Lecture pass complete |
| `commonware-resolver` | Complete | Lecture pass complete |
| `commonware-coding` | Complete | Lecture pass complete |
| `commonware-codec` | Complete | Lecture pass complete |
| `commonware-math` | Complete | Lecture pass complete |
| `commonware-conformance` | Complete | Lecture pass complete |
| `commonware-macros` | Complete | Lecture pass complete |
| `commonware-utils` | Complete | Lecture pass complete |
| `commonware-parallel` | Complete | Lecture pass complete |
| `commonware-invariants` | Complete | Lecture pass complete |
| `commonware-collector` | Complete | Lecture pass complete |
| `commonware-deployer` | Complete | Lecture pass complete |
| `commonware-sync` | Complete | Lecture pass complete |
| `commonware-bridge` | Complete | Lecture pass complete |
| `commonware-chat` | Complete | Lecture pass complete |
| `commonware-estimator` | Complete | Lecture pass complete |
| `commonware-log` | Complete | Lecture pass complete |
| `commonware-reshare` | Complete | Lecture pass complete |
| `commonware-flood` | Complete | Lecture pass complete |

The remaining sections are the historical build order and editorial planning
notes that produced this edition.

## Historical Core Primitive Queue

Original priority order for new or expanded chapters:

1. `commonware-cryptography`
2. `commonware-stream`
3. `commonware-storage`
4. `commonware-broadcast`
5. `commonware-resolver`
6. `commonware-coding`
7. `commonware-codec`
8. `commonware-math`
9. `commonware-conformance`
10. `commonware-macros`
11. `commonware-utils`
12. `commonware-parallel`
13. `commonware-invariants`
14. `commonware-collector`
15. `commonware-deployer`

## Next-Wave Research Notes

### Wave 1: Evidence, Channels, Durable State

1. `commonware-cryptography`
   - Systems question: how do distributed systems create evidence that other
     parties can trust?
   - Mental model: a trust foundry producing identities, commitments,
     certificates, and shared keys.
2. `commonware-stream`
   - Systems question: how do we turn an arbitrary transport into a secure,
     framed, ordered message channel?
   - Mental model: a secure envelope machine on top of any sink/stream pair.
3. `commonware-storage`
   - Systems question: how do we persist state so it is durable, recoverable,
     and often cryptographically provable?
   - Mental model: start with a log, derive a view, then prove facts about the
     view.

### Wave 2: Dissemination, Retrieval, Recovery

4. `commonware-broadcast`
   - Systems question: how do we disseminate data without assuming everyone
     sees it immediately and without replaying it forever?
   - Mental model: a town crier with a memory.
5. `commonware-resolver`
   - Systems question: how do we fetch data by key when we do not know who has
     it yet?
   - Mental model: a missing-piece coordinator.
6. `commonware-coding`
   - Systems question: how do we split data into recoverable pieces while still
     rejecting malformed pieces?
   - Mental model: a proof-carrying jigsaw.

### Wave 3: Shared Machinery and Appendix Candidates

7. `commonware-codec` — full chapter
8. `commonware-math` — full chapter
9. `commonware-conformance` — full chapter
10. `commonware-macros` — shorter appendix
11. `commonware-utils` — shorter appendix or survey chapter
12. `commonware-parallel` — shorter appendix
13. `commonware-invariants` — shorter appendix
14. `commonware-collector` — case-study / appendix
15. `commonware-deployer` — case-study

## Historical Example Crate Queue

These likely fit better as shorter case-study chapters or appendices:

1. `commonware-sync`
2. `commonware-bridge`
3. `commonware-chat`
4. `commonware-estimator`
5. `commonware-flood`
6. `commonware-log`
7. `commonware-reshare`

## Historical Scale Guidance

Likely full chapters:

- `commonware-cryptography`
- `commonware-stream`
- `commonware-storage`
- `commonware-broadcast`
- `commonware-resolver`
- `commonware-coding`
- `commonware-codec`
- `commonware-math`
- `commonware-conformance`

Likely shorter appendix or case-study chapters:

- `commonware-collector`
- `commonware-parallel`
- `commonware-invariants`
- `commonware-utils`
- `commonware-deployer`
- `commonware-macros`

## Editorial Checklist

Every crate chapter should answer, in order:

1. What systems problem does this crate actually solve?
2. What is the cleanest mental model for that problem?
3. Which invariants matter most?
4. Which types and actors exist because of those invariants?
5. How does the control flow preserve the invariants?
6. What breaks under adversarial or partial failure?
7. How should a reader approach the source without getting lost?
