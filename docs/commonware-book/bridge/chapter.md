# commonware-bridge

*A customs desk for finality certificates: move evidence across trust
boundaries without moving trust.*

---

## Opening Ledger

This chapter shows how `commonware-bridge` moves a finality certificate from
one network into another without pretending that the second network should
trust the first one.

**Crux.** A bridge is not a pipe. It is a policy for moving evidence across a
boundary while keeping verification local at every step that matters.

**Primary invariant.** A foreign certificate is never used until the local
validator has re-verified it against the foreign network's public identity,
and a block digest is never handed to local consensus before the indexer has
stored the block it names.

**Naive failure.** The easy mistake is to copy bytes across the boundary and
hope the receiving side treats them as truth. That collapses trust, storage,
and consensus into one blob. The bridge keeps them separate.

**Reading map.**

- Section 1 names the problem and the trust boundary.
- Section 2 gives the mental model.
- Section 3 explains the composition stack: validator, application, indexer,
  and consensus.
- Section 4 treats the indexer as a storage boundary, not an oracle.
- Section 5 walks the local-consensus loop and the cross-network evidence loop
  side by side.
- Section 6 explains why the example publishes before it proposes.
- Section 7 names the pressures the design absorbs.
- Section 8 lists the limits honestly.
- Section 9 shows how to read the source in the right order.

**Assumption ledger.**

- The reader is comfortable with threshold signatures, digests, and local
  consensus loops.
- The bridge is an example, not a trustless general-purpose cross-chain
  protocol.
- The indexer is a shared service in this example, so evidence discovery is
  centralized on purpose.
- The local validator still performs the last verification step itself.

---

## What a Bridge Really Is

Before we talk about this example, it helps to define a bridge in the general
sense. A bridge is not a promise that two systems now trust each other. It is
a method for carrying evidence across a boundary where trust does not
naturally extend. The important words are evidence, boundary, and
verification.

A blockchain or consensus network is local by design. Its validators agree on
facts inside one domain, under one identity set, with one finality rule. A
different domain may observe the same event, but observation is not
acceptance. If the second domain wants to act on the first domain's finality,
it needs a proof that can be checked against the first domain's public
identity. That proof is usually small, portable, and expensive to fake.

The naive approach is to forward messages and call them truth. That works only
until a relay lies, the network forks, or the source chain reorganizes.
Another naive approach is to ask the destination chain to consult the source
chain live every time it needs an answer. That makes the destination chain
depend on remote availability and turns every decision into a cross-network
conversation. Both approaches blur the line between "I saw something" and "I
can justify using it."

A useful bridge therefore separates three jobs: producing finality on the
source side, remembering where the proof can be found, and rechecking the
proof on the destination side. That separation creates a familiar tradeoff.
The tighter the verification, the less you can trust the middle layer. The
more aggressively you cache or index evidence, the easier it is to serve, but
the more careful you must be about freshness and retention.

## 1. What Problem Does This Solve?

Two networks may need to exchange information, but they do not share trust.
That is the whole problem.

If Network A says, "I finalized this block," Network B cannot simply believe
it because some peer delivered a message. B needs a proof that is checkable
under A's public identity, and it needs a way to recover that proof later when
its own consensus engine asks for a proposal.

That is why this example is not a pipe and not a gossip bus. It is a bridge in
the strict sense: a system for carrying evidence across a boundary and then
re-checking that evidence on the other side.

The example chooses a very specific payload: a succinct finality certificate
from one network. The certificate is small enough to move cheaply and strong
enough to act as portable evidence.

The rest of the design follows from that one fact:

- the producing network finalizes locally,
- the indexer remembers the latest evidence per network,
- the receiving network fetches that evidence when it wants to bridge,
- and local validators reject foreign evidence until it verifies under the
  foreign network's identity.

That is the right abstraction because it separates three jobs that should
never be blurred together:

- producing finality,
- storing evidence so it can be found again,
- and deciding whether the local chain should use it.

The bridge only works when those jobs stay distinct.

---

## 2. Mental Model

Picture a customs desk between two cities.

Each city stamps a receipt when it has finished its own internal process. The
desk does not invent receipts and does not decide what they mean. It files
them, labels them by city, and hands them back later when someone asks for the
latest one.

Now imagine a traveler from City A walks into City B carrying City A's
receipt. City B does not say, "a receipt arrived, therefore the claim is
true." City B checks the stamp against City A's public identity and only then
lets the receipt influence its own local process.

That is the bridge in one sentence:

> move proof, not belief.

The metaphor is useful because it keeps the three moving parts separate.

- The receipt is the finalization certificate.
- The desk is the indexer.
- The traveler is the application logic inside the validator.

That separation matters because the bridge is really two loops:

- a local consensus loop that decides what the validator does on its own
  chain,
- and a cross-network evidence loop that moves finalization certificates
  between networks through the indexer.

Once you see those as separate loops, the rest of the example becomes much
easier to read.

---

## 3. The Composition Stack

`examples/bridge/src/lib.rs` names the moving parts up front:

- `APPLICATION_NAMESPACE` keeps the application protocol separate from the
  rest of the workspace.
- `P2P_SUFFIX` and `CONSENSUS_SUFFIX` keep the local network protocols from
  colliding with one another.
- `INDEXER_NAMESPACE` keeps the shared evidence shelf separate from local
  consensus traffic.

Those namespaces are not decorative. They are boundary markers. A bridge only
works if the local network, the p2p fabric, the consensus engine, and the
indexer each own a different slice of the wire space.

### 3.1 The Validator Is the Composition Root

`examples/bridge/src/bin/validator.rs` is the best place to understand the
whole system.

The validator wires together:

- authenticated p2p for the local validator set,
- encrypted stream transport for the indexer,
- simplex consensus for local block production,
- durable storage for restart,
- and the application actor that decides when to bridge.

That composition is the real story. The validator is not "consensus plus some
IO." It is a policy host that connects three independent machines:

1. local consensus,
2. remote evidence discovery,
3. and durable restart.

The example keeps these pieces separate for a reason. If the bridge logic were
embedded inside the consensus engine or the p2p stack, the chapter would stop
teaching composition and start teaching hidden coupling.

### 3.2 The Application Is the Policy Layer

`examples/bridge/src/application/actor.rs` is where the bridge policy lives.

The actor owns three decisions:

- whether to propose local random data or foreign evidence,
- whether a foreign certificate is valid enough to carry forward,
- and when to post local finality back to the indexer.

The actor does not own consensus itself. It answers the questions that
consensus asks through `examples/bridge/src/application/ingress.rs`:

- `genesis`
- `propose`
- `verify`
- `report`

That ingress layer is the narrow seam that keeps simplex generic. Consensus
only knows that it can ask for a digest, a proposal, a verification result, or
a report. It never learns why the application chose one payload over another.

### 3.3 The Block Type Makes the Fork Visible

`examples/bridge/src/types/block.rs` defines the payload shape:

- `BlockFormat::Random(u128)` for ordinary local data,
- `BlockFormat::Bridge(Finalization<...>)` for a foreign finality
  certificate.

That type is the chapter's cleanest fork in the road.

A block is either:

- local noise that keeps the consensus loop moving, or
- foreign evidence that has already survived verification on another network.

The bridge does not special-case the consensus engine for this. It just gives
consensus a block type that makes the difference explicit.

---

## 4. The Indexer Is the Boundary

The indexer is not a truth oracle. It is a storage boundary with a small amount
of verification logic.

`examples/bridge/src/types/inbound.rs` and
`examples/bridge/src/types/outbound.rs` define the protocol:

- `PutBlock`
- `GetBlock`
- `PutFinalization`
- `GetFinalization`

That split is useful because it mirrors the two things the example needs to
store:

- blocks by digest,
- and the latest finalization per network.

### 4.1 Blocks and Finalizations Are Not the Same Shelf

`examples/bridge/src/bin/indexer.rs` stores blocks in a digest-keyed map and
finalizations in a view-keyed map.

That distinction matters.

- A block is something a validator may want to fetch again by digest.
- A finalization is a moving frontier, so the example keeps the latest one per
  network.

The indexer is therefore two shelves in one room:

- one shelf keyed by digest for block retrieval,
- one shelf keyed by view for latest finality retrieval.

The indexer verifies incoming finality certificates against the network
verifier derived from the declared public identity before it stores them. That
means the shelf only holds evidence that already passed the example's local
verification bar.

But the shelf is still not authority. It is just a place where verified
evidence can stay reachable.

### 4.2 The Indexer Accepts Requests, Not Trust

The encrypted stream listener in `indexer.rs` accepts requests only from known
participants. Once a connection is upgraded, the indexer decodes the inbound
message, dispatches it to a small handler loop, and returns one of three
answers:

- success or failure for store operations,
- a block when a block lookup succeeds,
- or the latest finalization when a finalization lookup succeeds.

That makes the indexer behave like a customs archive:

- it remembers what was posted,
- it exposes the latest relevant evidence,
- but it never decides what the local chain should accept.

### 4.3 Why The Boundary Matters

The chapter should be explicit about this.

If the indexer vanished, the bridge would lose discoverability.
If the indexer lied, validators would still reject the lie locally.
If the indexer was honest but slow, the bridge would become a liveness
problem, not a correctness problem.

That is exactly the right tradeoff for an example like this. The bridge is
teaching a composition pattern, not claiming to solve decentralized storage.

---

## 5. Two Loops, One Timeline

The cleanest way to understand the example is to compare the local consensus
loop and the cross-network evidence loop.

| Loop | Trigger | Main actor | Output |
| --- | --- | --- | --- |
| Local consensus loop | Consensus asks for genesis, proposal, verification, or report | `application::Actor` | A digest, a verification result, or a finality report |
| Cross-network evidence loop | A finality exists on one network and might be useful on the other | Indexer plus application actor | A bridged block carrying foreign evidence |

### 5.1 The Local Consensus Loop

The local loop is what makes the validator a validator.

1. Consensus asks for genesis and gets a digest.
2. Consensus asks for a proposal.
3. The application chooses a payload.
4. The application hashes the payload.
5. The application publishes the block to the indexer.
6. Only after the indexer confirms the block exists does the application hand
   the digest back to consensus.
7. Consensus verifies the block by fetching it back from the indexer.
8. Consensus reports notarization, finalization, or nullification.
9. Finalization gets posted back to the indexer so the other network can use it
   later.

That is a local loop because the validator is still running its own chain.
The bridge only decides what kind of evidence that chain carries.

### 5.2 The Cross-Network Evidence Loop

The cross-network loop begins when a validator wants to carry foreign proof
into its own chain.

1. The application asks the indexer for the latest finalization from the other
   network.
2. The indexer returns the newest one it knows about.
3. The application verifies it against the foreign network identity.
4. If verification fails, the proposal stops there.
5. If verification succeeds, the application turns the certificate into
   `BlockFormat::Bridge`.
6. The application publishes that block to the indexer.
7. Consensus receives the digest only after publication succeeds.

This loop is the bridge itself. It is the path by which evidence from one trust
domain becomes payload inside another trust domain's history.

### 5.3 The Two Loops Touch But Do Not Merge

The loops touch in three places:

- the indexer stores and serves evidence,
- the application reads from and writes to the indexer,
- and consensus treats the resulting digest as local payload.

But they do not merge.

That is the lesson.

The local chain never stops being local. The foreign proof never stops being
foreign. The indexer keeps them discoverable, and the application decides when
to bind them together.

---

## 6. Publish Before You Propose

The most important rule in the example is easy to miss:

> publish the block to the indexer before you give its digest to consensus.

You can see that ordering in `examples/bridge/src/application/actor.rs`.

The actor hashes the block, posts the block to the indexer, waits for success,
and only then returns the digest to consensus.

That order prevents a subtle failure:

- if consensus sees the digest first, it can commit to a payload that is not
  yet discoverable,
- if the indexer sees the payload first, the digest becomes a stable handle for
  later verification.

The rule matters even more for foreign evidence.

If a validator fetches a finalization from the other network and turns it into
a local block, that block should not become part of local consensus until the
indexer has the block itself. The block digest is the local chain's handle on
the evidence. The evidence has to exist before the chain can safely point to
it.

The reverse direction has the same shape.

When the local chain finalizes, the application reports the finalization back
to the indexer after the report arrives. That makes the latest proof
discoverable by the other network later. The example is therefore consistent in
both directions:

- publish evidence before proposing it,
- and post finality after it is real.

That is a small rule, but it does a lot of work. It keeps the bridge from
becoming a loose reference to something the shelf does not yet contain.

---

## 7. What Pressure It Is Designed To Absorb

The example is meant to survive ordinary operational pressure without
collapsing its trust story.

### Partial Availability

If the indexer has no finalization yet, the application can keep proposing
random payloads. The bridge does not block consensus waiting for a foreign
certificate that does not exist.

### Restart Pressure

The validator stores consensus state on disk. If the node restarts, it can
resume from the same local history. That persistence is about recovery, not
trust. It does not replace proof verification.

### Verification Pressure

Foreign finalizations are checked locally before they influence the local
chain. The receiving network never relies on the indexer alone.

### Concurrency Pressure

The example keeps the application, consensus, p2p, and indexer as separate
moving parts. That makes the control flow easier to reason about and keeps the
boundaries visible.

### Separation Pressure

The two networks are intentionally distinct. The bridge keeps their identities
separate instead of pretending they are one mesh with two names.

### Naming Pressure

The namespaces in `examples/bridge/src/lib.rs` are part of this pressure
management. They keep application, consensus, p2p, and indexer traffic in
different domains so messages do not blur across protocols.

---

## 8. Failure Modes and Limits

The example is careful not to overclaim.

- If the indexer is unreachable, validators cannot fetch or publish evidence
  there.
- If the other network has not finalized anything yet, there is nothing to
  bridge.
- If a foreign finalization does not verify against the foreign network's
  public identity, the application rejects it.
- If the local network cannot finalize, there is no local certificate to post
  back out.
- If you need a trustless cross-chain protocol, this example is not the final
  answer. It is a clean composition pattern inside that larger problem.

The indexer also stores only the latest finalization per network. That is a
deliberate limit. The example is teaching discoverability of the current proof,
not archival history.

That limit is useful because it keeps the bridge focused on the exact question
it is trying to answer:

> what is the latest proof I can safely use right now?

---

## 9. How to Read the Source

Read the source as a chain of responsibilities, from boundary to composition
root.

1. `examples/bridge/src/lib.rs`

   Start here for the namespace split and the high-level claim that the example
   moves finalization certificates between networks.

2. `examples/bridge/src/types/block.rs`

   This type tells you what can cross the trust boundary. A block is either
   local data or bridged evidence, and that fork is the rest of the example in
   miniature.

3. `examples/bridge/src/types/inbound.rs` and `examples/bridge/src/types/outbound.rs`

   Read these together as the evidence contract. They show what validators can
   ask the indexer to store or return.

4. `examples/bridge/src/application/ingress.rs`

   This is the narrow consensus-facing seam. It keeps simplex generic while the
   bridge policy stays in the actor.

5. `examples/bridge/src/application/actor.rs`

   This is the policy layer. It chooses between local data and bridged
   evidence, verifies foreign finalizations, publishes blocks before proposing
   them, and posts local finalizations back to the indexer.

6. `examples/bridge/src/bin/indexer.rs`

   This is the storage boundary made concrete. Focus on how the indexer keeps
   evidence reachable without becoming authoritative.

7. `examples/bridge/src/bin/validator.rs`

   This is the composition root. It wires authenticated p2p, encrypted stream
   transport, consensus, storage, and the application actor into one validator
   process.

If you read the files in that order, the example stays centered on the same
boundary: evidence is discovered elsewhere, verified locally, and only then
turned into chain payload.

---

## 10. Glossary and Further Reading

- **Finalization certificate** - the proof that a network finalized a block.
- **Bridge payload** - a local block whose content is a foreign finalization.
- **Indexer** - the shared service that stores and serves evidence by
  network.
- **Mailbox** - the narrow channel through which consensus asks the
  application to propose, verify, and report.
- **Namespace** - the boundary marker that keeps application, consensus, p2p,
  and indexer traffic distinct.
- **Local consensus loop** - the validator's own chain of propose, verify, and
  report calls.
- **Cross-network evidence loop** - the cycle by which one network's
  finalization becomes another network's payload.

Further reading:

- `examples/bridge/src/lib.rs`
- `examples/bridge/src/application/actor.rs`
- `examples/bridge/src/application/ingress.rs`
- `examples/bridge/src/bin/indexer.rs`
- `examples/bridge/src/bin/validator.rs`

For a conceptual sibling, read `commonware-p2p` next. That chapter explains
how authenticated connections move bytes between peers. `commonware-bridge`
builds on the same transport idea, but the unit of movement is evidence.
