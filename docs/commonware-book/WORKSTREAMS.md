# Commonware Book Workstreams

This file now records the workstreams that produced the completed first edition
of the Commonware book.

## Editorial Standard

Each chapter should read like a lecture, not a generated code tour.

The intended pattern is:

1. Start from the systems problem.
2. Give the reader a clean mental model.
3. Introduce the invariants that matter.
4. Use code only where it sharpens the conceptual picture.
5. Treat implementation detail as evidence, not as the main story.

Depth target:

- central crate chapters should grow well beyond first-draft length,
- they should cover the small set of files that carry most of the crate's
  substance,
- and they should use textbook-style background to make the dense code easier
  to understand instead of replacing that depth with summary.

## Completed Workstreams

### Featured Chapter Rewrites

- `runtime/`
  - Goal: second-pass rewrite of the full chapter in a more concept-first
    lecture style.
- `p2p/`
  - Goal: second-pass rewrite with clearer networking intuition and less
    implementation-inventory prose.
- `consensus/`
  - Goal: second-pass rewrite that keeps the core safety/liveness invariants in
    view throughout.

### Crate Research and Draft Seeding

- `cryptography`, `stream`, `storage`
  - Goal: identify chapter arcs, mental models, invariants, and source anchors.
- `broadcast`, `resolver`, `coding`
  - Goal: identify chapter arcs, mental models, invariants, and source anchors.
- `codec`, `collector`, `conformance`, `math`, `parallel`, `invariants`,
  `utils`, `deployer`, `macros`
  - Goal: triage into full chapter vs appendix/case-study and define first-read
    source files.

### Editorial Waves

- Foundational second pass:
  - `cryptography`, `stream`, `storage`, `broadcast`, `resolver`, `coding`
  - Goal: convert strong first drafts into more continuous lecture-style
    chapters.
- Support second pass:
  - `macros`, `utils`, `parallel`, `invariants`, `collector`, `deployer`
  - Goal: make appendix and case-study chapters feel more like short lectures
    than tidy reference notes.
- Example second pass:
  - `bridge`, `sync`, `chat`, `estimator`, `log`, `reshare`, `flood`
  - Goal: make composition chapters teach the system they exemplify rather than
    the CLI they happen to expose.

## Future Work

1. Add bespoke visuals and interactive plates to the highest-value generated chapters.
2. Continue tightening chapter parity so support and example chapters feel as finished as the featured trio.
3. Treat the current renderer, index, and editorial docs as the baseline for later editions rather than as an active drafting queue.
