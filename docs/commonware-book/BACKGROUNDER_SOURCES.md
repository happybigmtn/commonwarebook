# Commonware Book Backgrounder Sources

This file maps broad chapter families to canonical external references that are
useful when deepening the book's backgrounder sections.

The goal is not to imitate these sources mechanically. The goal is to borrow
their strongest teaching moves, vocabulary, and conceptual framing while
keeping the Commonware book grounded in its own codebase.

## Core Teaching References

- **The Feynman Lectures on Physics**
  - https://www.feynmanlectures.caltech.edu/
  - Use for: first-principles explanation, energy at the opening, concrete
    thought experiments, and the habit of making difficult ideas feel
    physically inevitable.

- **Operating Systems: Three Easy Pieces**
  - https://research.cs.wisc.edu/wind/OSTEP/
  - Use for: runtimes, storage, deployer, and systems chapters that benefit
    from compact timelines, explicit mechanics, and clean section rhythm.

- **Designing Data-Intensive Applications**
  - https://dataintensive.net/
  - Use for: storage, sync, broadcast, resolver, deployer, and any chapter
    where the main job is to orient the reader in a design space before
    narrowing to one implementation.

## Trust, Evidence, and Transport

- **Noise Protocol Framework**
  - https://noiseprotocol.org/noise.html
  - Use for: stream, p2p, handshake, and cryptography backgrounders around
    authenticated channels, transcript binding, and why encryption alone is not
    enough.

- **Real-World Cryptography**
  - Official book page: https://www.manning.com/books/real-world-cryptography
  - Use for: cryptography, stream, and reshare backgrounders on practical
    cryptographic goals, misuse resistance, and what protocols are really
    proving.

## Consensus and Distributed Coordination

- **Practical Byzantine Fault Tolerance (Castro and Liskov, OSDI 1999)**
  - https://pdos.csail.mit.edu/6.824/papers/castro-practicalbft.pdf
  - Use for: consensus backgrounders on quorum intersection, view change,
    safety versus liveness, and why Byzantine agreement is harder than simple
    majority voting.

- **HotStuff: BFT Consensus in the Lens of Blockchain**
  - https://arxiv.org/abs/1803.05069
  - Use for: consensus and marshal backgrounders on chained certificates,
    leader-based partial synchrony, and the happy-path simplification story.

## Storage and Data Structure Internals

- **Database Internals**
  - https://www.databass.dev/book
  - Use for: storage, sync, and deployer backgrounders about logs, pages,
    indexes, crash recovery, and why read, write, and proof paths should be
    treated as different mechanisms.

## How to Use This File

- Start with one or two references, not all of them.
- Use the references to improve the broad topic explanation near the front of a
  chapter.
- Then return to the Commonware code and re-anchor the prose in the crate's own
  invariant and control flow.
- Avoid turning a backgrounder into a literature survey. The chapter still has
  to narrow from broad field knowledge to one concrete Commonware mechanism.
