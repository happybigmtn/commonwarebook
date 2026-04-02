# Chapter Brief: commonware-coding

## 1. Module Purpose

`commonware-coding` should be taught as a chapter about **agreement under
partial information**.

The surface problem is familiar: a leader has a large payload, the network
needs to disseminate it, and plain replication makes the leader do nearly all
the work. Coding fixes that by spreading transmission load across the network.

The deeper problem is what honest nodes can safely believe while they still see
only fragments of the payload. If node A sees one subset of shards and node B
sees another, they must not form incompatible beliefs about what they are
helping disseminate. That is why the chapter should keep three ideas tied
together from the start:

- **recoverability**: enough shards can reconstruct the payload;
- **commitments**: checked shards are anchored to one encoded object;
- **agreement**: honest nodes should not diverge while operating on partial
  information.

The chapter should open with a compact apparatus:

- **promise**: coding lets the system recover a payload, bind shards to one
  object, and keep agreement while every node still sees only fragments;
- **crux**: partial information is the normal case, so fragments must become
  evidence instead of being mistaken for the whole payload;
- **primary invariant**: one checked shard must name one encoded object under
  one commitment, and honest nodes must not diverge about it;
- **naive failure**: "split the block, send pieces, and recover later" fails
  because raw fragments do not tell nodes whether they belong to the same
  valid encoding story;
- **reading map**: start with `coding/src/lib.rs`, then
  `coding/src/reed_solomon.rs`, then `coding/src/zoda/mod.rs`, then
  `coding/src/zoda/topology.rs`;
- **assumption ledger**: the network is adversarial, encoding is deterministic,
  and "checked" means the shard has already crossed the validation bar.

The enduring mental model is a **proof-carrying jigsaw**:

- the payload is the picture,
- the shards are the pieces,
- the commitment is the picture on the box,
- a checked shard is a piece that carries evidence about which box it belongs
  to.

The chapter should keep Reed-Solomon and ZODA inside that same picture, but
give them different jobs:

- **Reed-Solomon** is the answer to the recoverability question: if enough
  honest pieces survive, can we reconstruct the same payload later?
- **ZODA** is the answer to the early-agreement question: before full
  reconstruction, can a node already know that the dissemination corresponds to
  a valid encoding story?

That framing is stronger than a feature comparison. It teaches when a system
knows enough to act.

---

## 2. Source Files That Matter Most

### `coding/src/lib.rs`
**Why it matters:** Defines the lecture's real subject matter: `Config`,
`Scheme`, `PhasedScheme`, `ValidatingScheme`, and the guarantees around check
agreement, unique commitments, commitment binding, and the `PhasedAsScheme`
adapter that exposes what is gained and lost when a phased scheme is flattened
back into the ordinary `Scheme` contract.

### `coding/src/reed_solomon.rs`
**Why it matters:** Gives the cleanest recoverability-first story. Shows how a
payload becomes regular shards, how those shards are bound to a BMT
commitment, how canonical byte layout is enforced, and how decode re-encodes
the recovered object to audit commitment consistency rather than merely
returning bytes.

### `coding/src/zoda/mod.rs`
**Why it matters:** Gives the early-agreement story. Introduces `StrongShard`,
`WeakShard`, `CheckingData`, `weaken`, transcript-derived checking matrices and
checksums, shuffled row sampling, and the stronger meaning of a successful
check.

### `coding/src/zoda/topology.rs`
**Why it matters:** Shows that topology is part of the security argument, not
just implementation sizing. Rows, samples, and checksum columns determine how
much proof a shard carries.

### `docs/blogs/coding.html`
**Why it matters:** Supplies the systems pressure at the chapter opening:
leaders are bandwidth-bound, validators are idle, and coding changes who pays
the dissemination cost.

### `docs/blogs/zoda.md`
**Why it matters:** Supplies the conceptual pivot from plain recoverability to
immediate guarantees about valid encodings.

---

## 3. Chapter Outline

```text
0. Opening Apparatus
   - Promise, crux, primary invariant, naive failure, reading map, assumptions

1. What Problem Does This Solve?
   - Large payloads make leaders the bottleneck
   - Coding matters because nodes act before they have the full payload
   - Introduce recoverability, commitments, and agreement as one problem

2. Mental Model: A Proof-Carrying Jigsaw
   - Payload as picture, shards as pieces, commitment as picture on the box
   - Checked shards are trusted pieces, not raw fragments
   - Partial information is the normal case, not an edge case

3. Core Ideas
   - Config as threshold plus redundancy budget
   - Scheme as encode, check, decode
   - Check agreement, unique commitments, commitment binding
   - PhasedScheme and ValidatingScheme as stronger trust stories
   - `PhasedAsScheme` as a useful but revealing compromise

4. How the System Moves
   - Standard path: canonicalize -> encode -> check -> recover -> re-encode
   - Reed-Solomon decode as a canonicality audit, not just recovery
   - Phased path: strong shard -> weaken -> checking data -> weak shard -> check
   - ZODA transcript, checksum, and shuffled-row logic
   - Topology as part of the proof story

5. Two Systems Questions, Two Answers
   - Reed-Solomon answers the recoverability question
   - ZODA answers the early-agreement question
   - Compare what each scheme lets the rest of the system safely say at each stage
   - Explain why `PhasedAsScheme` preserves safety while hiding phased operational advantages

6. Pressure and Tradeoffs
   - Spreading network load
   - Naming intermediate trust states explicitly
   - Canonicality as part of the safety budget
   - Parallel strategy as policy, not algorithmic essence
   - Tests as executable proof obligations

7. Failure Modes and Limits
   - Missing shards
   - Wrong proofs, wrong indices, mixed commitments
   - Non-canonical shard families
   - Why plain recoverability does not imply early validity
   - Why stronger guarantees require more machinery
   - What higher layers still need to decide

8. How to Read the Source / Glossary
   - Start with trait guarantees
   - Then Reed-Solomon
   - Then ZODA
   - Then topology and supporting material
```

---

## 4. System Concepts to Explain at Graduate Depth

1. **Recoverability is a necessary but incomplete answer.** A distributed
   system needs more than "some threshold of shards reconstructs some payload."
   It needs a path from partial local evidence to shared global belief.

2. **Commitments turn fragments into protocol evidence.** Without a
   commitment, shards are just pieces of data. With a commitment and a check
   procedure, a shard becomes evidence about one encoded object.

3. **Check agreement is a protocol property.** If honest nodes can each accept
   their own shard but disagree about one another's shards, the wider protocol
   can fork while every node believes it acted correctly.

4. **Determinism makes the commitment meaningful.** If a payload admitted
   several successful commitments, the commitment would stop being a stable name
   for "the thing consensus referenced."

5. **`PhasedScheme` marks a change in when certainty appears.** The standard
   story reaches its strongest conclusion at reconstruction time. The phased
   story makes useful claims earlier, while the system still has only partial
   information.

6. **`ValidatingScheme` is the deep conceptual marker.** It says a successful
   check proves valid encoding, not merely shard membership.

7. **`PhasedAsScheme` teaches by flattening.** The adapter shows how a phased
   scheme can satisfy the plain `Scheme` contract while also showing what that
   contract cannot express about early certainty and forwarding.

8. **Topology is part of the proof, not background tuning.** In ZODA, rows,
   samples, and checksum columns determine how much evidence each shard carries
   about the encoding's validity.

9. **Reed-Solomon decode is an audit path.** The implementation reconstructs,
   re-encodes, and rebuilds the BMT root so that decode confirms canonical
   agreement rather than merely recovering parseable bytes.

10. **The tests are carrying theorem fragments.** Mixed commitments,
    duplicate indices, checksum malleability, and non-canonical encodings are
    all checked explicitly because higher layers rely on those facts.

---

## 5. Interactive Visualizations to Build Later

1. **Proof-carrying jigsaw walkthrough**  
   Show payload, shards, commitment, and checked shards as one running picture.

2. **Threshold vs redundancy slider**  
   Move `minimum_shards` and `extra_shards` and show how recoverability margin
   and dissemination cost change.

3. **Commitment-first shard explorer**  
   Show a payload, its shard family, the BMT commitment, and what `check`
   proves before decode begins.

4. **Recoverability vs early-agreement animation**  
   Use one scene for Reed-Solomon and one for ZODA, but frame them as two
   different moments when a node asks "do I know enough yet?"

5. **ZODA strong/weak shard pipeline**  
   Animate `encode -> weaken -> check -> decode`, emphasizing how knowledge
   changes at each phase.

6. **Topology visualizer**  
   Show how `Topology::reckon` chooses rows, samples, and checksum columns as
   security and payload size change.

---

## 6. Claims-to-Verify Checklist

- [ ] `Config::total_shards()` is exactly `minimum_shards + extra_shards`
- [ ] `Scheme::encode` is deterministic for the same config and input
- [ ] `Scheme::check` agreement holds across honest parties
- [ ] Mixing checked shards from different commitments fails at decode time
- [ ] Reed-Solomon decode succeeds from any `minimum_shards`-sized subset
- [ ] Reed-Solomon detects duplicate indices and insufficient shards
- [ ] Reed-Solomon rejects non-canonical shard families after re-encoding/root reconstruction
- [ ] `PhasedScheme::weaken` and `PhasedScheme::check` agree for honest shards
- [ ] ZODA marks itself as a `ValidatingScheme`
- [ ] `PhasedAsScheme` rejects inconsistent checking data across adapted checked shards
- [ ] `Topology::reckon` enforces enough samples/columns for the target security
- [ ] ZODA rejects duplicate-index / insufficient-unique-row and checksum-malleability attacks
