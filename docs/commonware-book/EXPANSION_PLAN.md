# Commonware Book Expansion Plan

This file will capture the crate-by-crate plan for substantially expanding the
book chapters.

The working target is:

- central crate chapters should become roughly 3x longer than the current
  drafts,
- the expansion should cover the small set of files, types, and flows that
  carry most of each crate's substance,
- and the extra length should come from code-substantive explanation plus
  textbook-style background, not from paraphrasing syntax.

## To Be Filled In

For each crate:

- under-covered code regions
- missing systems background
- missing invariants / proof sketches / timelines / comparisons
- proposed expanded chapter outline
- source files to drive the expansion

## Planned Priority

1. runtime / p2p / consensus
2. cryptography / stream / storage
3. broadcast / resolver / coding
4. codec / math / conformance
5. support appendices
6. example case studies

## Audit Findings: Broadcast / Resolver / Coding

### commonware-broadcast

Current gap:

- The chapter explains the digest cache well, but it still under-covers the
  real engine loop, duplicate-refresh behavior, malformed-input handling,
  waiter release edge cases, and membership-driven eviction logic.

Code regions to expand around:

- `broadcast/src/buffered/engine.rs`
- `broadcast/src/buffered/ingress.rs`
- `broadcast/src/buffered/config.rs`
- `broadcast/src/buffered/metrics.rs`
- tests in `broadcast/src/buffered/mod.rs`
- fuzz target `broadcast/fuzz/fuzz_targets/broadcast_engine_operations.rs`

Additions needed:

- one real event-loop timeline
- one live dissemination vs replay vs consensus comparison
- explicit invariants for `items`, `deques`, `counts`, and waiter release
- shutdown / malformed-input / duplicate-refresh / tracked-peer-eviction cases

### commonware-resolver

Current gap:

- The chapter gets the fetch/validate split right, but it still under-covers the
  fetcher as the real memory of the system: active/pending maps, peer
  prioritization, rate-limit spillover, targets as hard constraints, timers, and
  serve-side symmetry.

Code regions to expand around:

- `resolver/src/p2p/fetcher.rs`
- `resolver/src/p2p/engine.rs`
- `resolver/src/p2p/ingress.rs`
- `resolver/src/p2p/wire.rs`
- tests in `resolver/src/p2p/mod.rs`

Additions needed:

- a real fetcher state machine
- unrestricted vs targeted fetch comparison
- request-ID / `(peer,id)` response matching story
- explicit invariants for one-key-one-search, target persistence, self-exclusion,
  and timer bookkeeping

### commonware-coding

Current gap:

- The chapter now has a strong conceptual spine, but it still leaves out too
  much of the concrete proof machinery: adapters, checking-data consistency,
  Reed-Solomon canonicalization and re-encoding, and the full ZODA transcript /
  topology / checksum story.

Code regions to expand around:

- `coding/src/lib.rs`
- `coding/src/reed_solomon.rs`
- `coding/src/zoda/mod.rs`
- `coding/src/zoda/topology.rs`
- `coding/src/benches/bench.rs`

Additions needed:

- guarantee ladder across `Scheme`, `PhasedScheme`, `ValidatingScheme`, and
  `PhasedAsScheme`
- one Reed-Solomon timeline and one ZODA timeline
- stronger Reed-Solomon vs ZODA table
- explicit invariants for canonical encoding, commitment binding,
  checking-data consistency, and enough-unique-rows logic

## Audit Findings: Runtime / P2P / Consensus

### commonware-runtime

Current gap:

- The chapter explains the executor/context/clock well at a first-pass level,
  but it still leaves too much of the real implementation mass untouched:
  buffer ownership, paged crash-safe blobs, backend selection, liveness/fault
  semantics, and the production runtime details.

Code regions to expand around:

- `runtime/src/iobuf/mod.rs`
- `runtime/src/iobuf/pool.rs`
- `runtime/src/utils/buffer/paged/append.rs`
- `runtime/src/tokio/runtime.rs`
- `runtime/src/iouring/mod.rs`
- `runtime/src/storage/faulty.rs`
- `runtime/src/utils/supervision.rs`

Additions needed:

- zero-copy ownership model and `try_into_mut`
- buffer pools and sizing tradeoffs
- paged append / CRC / crash recovery timeline
- production runtime architecture vs deterministic runtime
- `io_uring` event loop, wake path, and liveness caveats

### commonware-p2p

Current gap:

- The chapter has the top-level actor story, but not enough of the actual
  tracker/peer/simulator machinery that gives the design its real shape.

Code regions to expand around:

- `p2p/src/authenticated/discovery/actors/tracker/directory.rs`
- `p2p/src/authenticated/discovery/actors/tracker/record.rs`
- `p2p/src/authenticated/lookup/actors/tracker/directory.rs`
- `p2p/src/authenticated/discovery/actors/peer/actor.rs`
- `p2p/src/utils/mux.rs`
- `p2p/src/utils/limited.rs`
- `p2p/src/simulated/mod.rs`
- `p2p/src/simulated/bandwidth.rs`

Additions needed:

- discovery as knowledge propagation over synchronized peer sets
- reservation/cooldown as distributed admission control
- lookup as a distinct control plane, not “discovery minus gossip”
- abuse / attack table
- simulator internals: fairness, queueing, bandwidth, ordering

### commonware-consensus

Current gap:

- The chapter is still too simplex-heavy relative to the full crate. The actual
  implementation substance also lives in ordered broadcast, aggregation,
  marshal, persistence, and fuzz invariants.

Code regions to expand around:

- `consensus/src/simplex/actors/voter/mod.rs`
- `consensus/src/simplex/actors/batcher/mod.rs`
- `consensus/src/ordered_broadcast/types.rs`
- `consensus/src/aggregation/engine.rs`
- `consensus/src/aggregation/safe_tip.rs`
- `consensus/src/marshal/core/actor.rs`
- `consensus/src/marshal/coding/mod.rs`
- `consensus/fuzz/src/invariants.rs`

Additions needed:

- formal assumptions section near the front
- quorum / notarize-before-finalize / parent-nullification proof sketches
- layer split rationale: simplex vs ordered broadcast vs aggregation vs marshal
- standard marshal vs coding marshal
- fuzz invariants as executable proof obligations

## Audit Findings: Cryptography / Stream / Storage

### commonware-cryptography

Current gap:

- The lecture spine is strong, but the chapter still under-covers secret
  handling, concrete scheme dialects, recoverable signatures, timelock
  encryption, and non-certificate public modules like BloomFilter and LtHash.

Code regions to expand around:

- `cryptography/src/certificate.rs`
- `cryptography/src/secret.rs`
- `cryptography/src/bls12381/tle.rs`
- `cryptography/src/ed25519/scheme.rs`
- `cryptography/src/secp256r1/recoverable.rs`
- `cryptography/src/bloomfilter/mod.rs`
- `cryptography/src/lthash/mod.rs`

Additions needed:

- full scheme matrix
- attributable vs threshold evidence table
- attack / misuse matrix
- secret handling and zeroization caveats
- TLE as delayed evidence release
- DKG reveal bounds and synchrony caveats

### commonware-stream

Current gap:

- The chapter gets the concept right but still under-describes the actual data
  path, framing machinery, and handshake/cipher/key-exchange internals.

Code regions to expand around:

- `stream/src/encrypted.rs`
- `stream/src/utils/codec.rs`
- `cryptography/src/handshake.rs`
- `cryptography/src/handshake/cipher.rs`
- `cryptography/src/handshake/key_exchange.rs`

Additions needed:

- handshake message table
- threat/guarantee table
- sender/receiver data path walkthrough
- metadata leakage / what is still visible
- nonce/counter failure model

### commonware-storage

Current gap:

- The chapter has the right log -> view -> proof spine, but it still leaves too
  much of the authenticated-state machinery out.

Code regions to expand around:

- `storage/src/journal/authenticated.rs`
- `storage/src/qmdb/any/mod.rs`
- `storage/src/qmdb/current/mod.rs`
- `storage/src/qmdb/current/proof.rs`
- `storage/src/qmdb/current/sync/mod.rs`
- `storage/src/translator.rs`
- `storage/src/cache/mod.rs`
- `storage/src/queue/mod.rs`
- `storage/src/bmt/mod.rs`
- `storage/src/bitmap/authenticated.rs`

Additions needed:

- write / recovery / read / proof path separation
- authenticated journals as the bridge from durable bytes to proofs
- proof-expressiveness ladder across `keyless`, `immutable`, `any`, `current`
- translator collision-hardening and grafting rationale
- cost tables for memory / rewrite / proof size / recovery cost

## Audit Findings: Codec / Math / Conformance

### commonware-codec

Current gap:

- The chapter still under-teaches `RangeCfg`, varint grammar, `Lazy<T>`,
  canonical collection logic, and the error/conformance layer.

Code regions to expand around:

- `codec/src/config.rs`
- `codec/src/varint.rs`
- `codec/src/types/lazy.rs`
- `codec/src/types/mod.rs`
- `codec/src/types/hash_map.rs`
- `codec/src/types/hash_set.rs`
- `codec/src/error.rs`
- `codec/src/extensions.rs`
- `codec/src/conformance.rs`

Additions needed:

- varint grammar derivation
- accepted vs rejected collection encodings
- `Lazy<T>` worked example
- error-to-invariant table
- conformance as proof of stability

### commonware-math

Current gap:

- The engine-room lecture works, but it still under-covers the law-checking
  engine, Goldilocks reduction mechanics, interpolation details, and the real
  NTT/erasure-recovery substance.

Code regions to expand around:

- `math/src/algebra.rs`
- `math/src/fields/goldilocks.rs`
- `math/src/poly.rs`
- `math/src/ntt.rs`
- `math/src/test.rs`

Additions needed:

- double-and-add / square-and-multiply derivations
- Goldilocks reduction walkthrough
- degree vs exact-degree example
- interpolation worked example
- small NTT / erasure-recovery walkthrough

### commonware-conformance

Current gap:

- The chapter has the right ledger framing, but it still underplays digest
  construction, verification vs regeneration workflow, macro hygiene, and the
  breadth of actual consumers.

Code regions to expand around:

- `conformance/src/lib.rs`
- `conformance/macros/src/lib.rs`
- `codec/src/conformance.rs`
- `cryptography/src/handshake/conformance.rs`
- `storage/src/journal/conformance.rs`
- `storage/src/merkle/mmr/conformance.rs`

Additions needed:

- step-by-step digest construction
- operational outcomes table
- macro expansion example
- wrapper-style vs bespoke conformance comparison
- ledger coverage table from real `conformance.toml` files

## Audit Findings: Support and Appendix Crates

### commonware-macros

Current gap:

- The appendix explains why macro syntax matters, but it still leaves too much
  of the proc-macro internals, hygiene rules, error design, and nextest naming
  machinery outside the story.

Focus areas:

- `macros/impl/src/lib.rs`
- `macros/impl/src/nextest.rs`
- `macros/tests/select.rs`
- `macros/tests/stability.rs`

High-value additions:

- `tokio::select!` vs `commonware_macros::select!`
- manual actor loop vs `select_loop!`
- plain `#[test]` vs the Commonware test macros
- why `commonware_stability_RESERVED` exists

### commonware-utils

Current gap:

- The survey chapter currently covers only a minority of the crate. It still
  leaves out ordered collections, acknowledgements, futures pools, concurrency
  limiters, sync primitives, network/time helpers, `NonEmptyVec`, and the
  historical bitmap machinery.

Focus areas:

- `utils/src/ordered.rs`
- `utils/src/acknowledgement.rs`
- `utils/src/futures.rs`
- `utils/src/concurrency.rs`
- `utils/src/sync/mod.rs`
- `utils/src/net.rs`
- `utils/src/time.rs`
- `utils/src/bitmap/historical/`

High-value additions:

- ordered collections vs ad hoc `Vec` / `HashMap`
- acknowledgement and future-pool examples
- historical bitmap commit/abort/prune walkthrough
- the utils fuzz surface as maintenance evidence

### commonware-parallel

Current gap:

- The appendix has the thesis, but still not enough of the concrete partition /
  reduce mechanics, `fold_init`, `parallelism_hint`, and equivalence tests.

Focus areas:

- `parallel/src/lib.rs`
- `parallel/README.md`

High-value additions:

- one algorithm under `Sequential` and `Rayon`
- `fold` vs `fold_init`
- contiguous partitioning vs hypothetical alternatives
- "when parallelism loses" discussion

### commonware-invariants

Current gap:

- The appendix still under-covers mutation strategy, byte-growth heuristics,
  replay tokens, result classification, and search budgets in `minifuzz`.

Focus areas:

- `invariants/src/minifuzz.rs`
- `invariants/README.md`

High-value additions:

- example test vs `minifuzz` vs libFuzzer comparison
- `MINIFUZZ_BRANCH` replay walkthrough
- one full search iteration timeline

### commonware-collector

Current gap:

- The chapter gets the commitment-keyed coordination idea, but still underplays
  the engine state machine, processed future pool, invalid-wire blocking,
  shutdown behavior, and the test/fuzz matrix.

Focus areas:

- `collector/src/p2p/engine.rs`
- `collector/src/p2p/mod.rs`
- `collector/fuzz/fuzz_targets/collector.rs`

High-value additions:

- mailbox request lifecycle
- cancel-then-late-reply timeline
- response admission matrix
- collector vs handwritten request ledger comparison

### commonware-deployer

Current gap:

- The case study currently leans on the `create` path too heavily and leaves the
  operator commands, cache model, failure recovery, and generated artifact story
  under-taught.

Focus areas:

- `deployer/src/aws/mod.rs`
- `deployer/src/aws/s3.rs`
- `deployer/src/aws/ec2.rs`
- `deployer/src/aws/services.rs`
- `deployer/src/aws/update.rs`
- `deployer/src/aws/destroy.rs`
- `deployer/src/aws/profile.rs`

High-value additions:

- annotated YAML-to-topology lowering
- create / update / clean / destroy comparison
- rollback and partial-failure timeline
- manual EC2 / SSH / Terraform-plus-scripts comparison

## Audit Findings: Example and Case-Study Chapters

### Highest-leverage examples

The strongest expansion opportunities, in order:

1. `reshare`
2. `sync`
3. `bridge`

These are the example chapters where one more layer of real mechanism would add
the most conceptual value.

### commonware-bridge

Add:

- indexer protocol/storage boundary
- validator stream + p2p + simplex composition
- payload-publish-before-digest-propose rule
- local-consensus loop vs cross-network evidence loop timeline

### commonware-sync

Add:

- request/response wire protocol
- cancellation-safe I/O loop
- request-ID discipline
- pinned-node handling
- stronger distinction between `any`, `current`, and `immutable`

### commonware-chat

Add:

- `oracle.track(...)` as the real membership boundary
- quota/backlog configuration of the chat channel
- UI/event loop as observability surface
- aligned vs misaligned friend-set diagram

### commonware-estimator

Add:

- parser / expression engine
- peer execution loop and proposer rotation
- layered view: DSL -> peer state -> network -> statistics
- realism vs tractability tradeoff section

### commonware-log

Add:

- actual simplex composition root
- reporter / UI split
- persistence and restart implications
- explicit privacy-vs-retrievability tradeoff

### commonware-reshare

Add:

- persistent DKG storage / replay
- dealer / player state machines
- engine + orchestrator + marshal composition
- full epoch timeline and bootstrap-mode comparison

### commonware-flood

Add:

- topology from setup artifacts to EC2 + monitoring
- pressure path timeline: send -> backlog -> network -> receiver -> dashboard
- instrumentation overhead and throttling tradeoffs
