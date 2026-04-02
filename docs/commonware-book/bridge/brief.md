# Chapter Brief: commonware-bridge

## 1. Module Purpose

`commonware-bridge` should be taught as a chapter about moving evidence across
trust boundaries without moving trust with it.

The example is intentionally narrower than a full cross-chain protocol. It
shows a practical composition pattern:

- one network finalizes locally,
- the indexer keeps the latest evidence discoverable,
- the other network fetches that evidence later,
- and the local validator re-verifies everything before it influences local
  consensus.

The chapter should keep four ideas in view from the beginning:

- **finality is portable evidence**, not a local belief,
- **the indexer is a storage boundary**, not an oracle,
- **the validator is the policy host**, not the storage layer,
- **the bridge moves proof, not trust**.

The most important teaching move is to compare two loops:

- the **local-consensus loop**, where simplex asks for genesis, proposal,
  verification, and report,
- and the **cross-network evidence loop**, where the application pulls foreign
  finality from the indexer, verifies it locally, wraps it into a block, and
  publishes that block before handing the digest back to consensus.

The chapter should open with a compact apparatus:

- **promise**: move finality certificates between two networks without
  collapsing trust boundaries;
- **crux**: a bridge carries evidence across a boundary, but local validators
  still decide whether the evidence counts;
- **primary invariant**: foreign finality is verified locally, and a digest is
  not proposed until the indexer has stored the underlying block;
- **naive failure**: copying bytes across the boundary and hoping the other
  network believes them;
- **reading map**: start with `examples/bridge/src/lib.rs`, then
  `examples/bridge/src/types/block.rs`, then the ingress and actor files, then
  `examples/bridge/src/bin/indexer.rs`, then `examples/bridge/src/bin/validator.rs`;
- **assumption ledger**: the reader knows threshold signatures, digests, local
  consensus, and the difference between storage and authority.

---

## 2. Source Files That Matter Most

### `examples/bridge/src/lib.rs`
**Why it matters:** Names the bridge namespace, the scheme alias, and the core
example claim. This file is the top-level lecture note for the whole example.

### `examples/bridge/src/types/block.rs`
**Why it matters:** Defines the fork in the road. A block is either random
local data or a bridged finalization certificate.

### `examples/bridge/src/types/inbound.rs` and `examples/bridge/src/types/outbound.rs`
**Why they matter:** These are the customs forms. They define how validators
ask the indexer to store and fetch blocks and finalizations, and how the
indexer answers.

### `examples/bridge/src/application/ingress.rs`
**Why it matters:** Shows the consensus-facing mailbox. Simplex asks for
genesis, proposal, verification, and reporting without knowing bridge policy.

### `examples/bridge/src/application/actor.rs`
**Why it matters:** This is the policy engine. It chooses random data or
foreign evidence, verifies foreign certificates, publishes blocks before
proposing them, and posts finalizations back to the indexer.

### `examples/bridge/src/bin/indexer.rs`
**Why it matters:** The storage boundary made concrete. It stores blocks by
digest, stores the latest finalization per network, verifies incoming foreign
finality, and serves evidence back over encrypted streams.

### `examples/bridge/src/bin/validator.rs`
**Why it matters:** The composition root. It wires authenticated p2p, encrypted
indexer streams, local consensus, storage, and the application actor together.

---

## 3. Chapter Outline

```text
1. Why bridge exists
   - Moving proofs is harder than copying bytes
   - The bridge moves evidence, not trust

2. Mental model
   - Customs desk and receipts
   - Two loops: local consensus and cross-network evidence

3. Composition stack
   - Validator as composition root
   - Application as policy layer
   - Namespaces as boundary markers
   - BlockFormat as the fork between local noise and foreign evidence

4. The indexer as boundary
   - Block shelf by digest
   - Finalization shelf by network and view
   - Verify on store, fetch later on demand

5. Two loops, one timeline
   - Genesis, propose, verify, report
   - Fetch foreign finality, verify, wrap, publish, propose
   - Local finalization posted back out

6. Publish before you propose
   - Why the digest must not escape before the block is stored
   - Why finalization posting happens after report

7. Pressure and limits
   - Partial availability, restart, verification pressure
   - Shared service by design, not trustless relay

8. How to read the source
   - Source order and what each file teaches
```

---

## 4. System Concepts To Explain At Graduate Depth

1. **Evidence is a different object from trust.** The example should teach
   that a foreign finalization is portable because it is verifiable, not
   because the receiving side trusts the sender.

2. **The indexer is a shelf.** It makes evidence discoverable later. It does
   not decide whether the local chain should use that evidence.

3. **The validator is the policy host.** It chooses whether a proposal is
   random data or bridged evidence, but consensus stays generic.

4. **Publish-before-propose is the safety rule.** A digest should not enter
   local consensus until the underlying block is already stored by the indexer.

5. **The local loop and the evidence loop are distinct.** One drives consensus
   progress. The other moves proofs across the boundary.

6. **Namespaces protect the boundary.** Application, consensus, p2p, and
   indexer traffic live in different domains so the example does not blur
   protocols together.

7. **Persistence is recovery, not authority.** The validator can restart from
   storage, but foreign evidence still has to be re-verified locally.

---

## 5. Visuals To Build Later

1. **Two-loop timeline** - show the local-consensus loop and the
   cross-network evidence loop side by side.
2. **Block fork plate** - show `Random(u128)` on one side and
   `Bridge(Finalization)` on the other.
3. **Indexer shelf plate** - show block-by-digest storage and
   latest-finalization-by-network storage as two different shelves.
4. **Publish-before-propose plate** - show the block being stored before the
   digest is returned to consensus.

---

## 6. Claims To Verify

- [ ] The chapter explains why the bridge moves evidence rather than trust.
- [ ] The indexer is framed as shared evidence storage, not as authority.
- [ ] The reader understands why a block can be random data or foreign
      evidence.
- [ ] The chapter makes clear that foreign finalizations are verified locally
      before they influence consensus.
- [ ] The publish-before-propose rule is explicit and motivated.
- [ ] The chapter shows both the local consensus loop and the cross-network
      evidence loop.
- [ ] The chapter stays like a lecture, not a protocol manual.
