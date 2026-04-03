# commonware-consensus

## Ordering in an Adversarial World

Every replicated system eventually has to answer one simple and uncomfortable question:

> When several machines disagree about what should happen next, who gets to decide?

If the network is small, honest, and perfectly synchronized, the answer can be informal. If the
network is Byzantine - meaning participants can lie, equivocate, or disappear on purpose - the
answer has to be a protocol.

`commonware-consensus` provides that protocol surface for Commonware systems. It orders **opaque**
messages in a Byzantine environment. "Opaque" is the important word. Consensus does not parse the
application payload and does not care whether the payload represents transactions, a state root, a
blob, or something stranger. The application decides what bytes deserve a digest. Consensus decides
what order those digests enter history.

The crate is organized as four layered primitives:

- **`simplex`** (BETA): a three-phase Byzantine consensus protocol with leader rotation and
  pluggable signature aggregation.
- **`aggregation`** (ALPHA): recoverable quorum certificates over an externally synchronized
  sequence of items.
- **`ordered_broadcast`** (ALPHA): reliable delivery from sequencers to validators, with chaining
  so equivocation becomes visible.
- **`marshal`** (ALPHA): the layer that turns certificates and delivered blocks into a finalized,
  application-facing stream.

---

## Backgrounder: Why Consensus Exists At All

Consensus is one of those subjects where the formal definitions arrive early and the intuition
often arrives late. Students quickly hear phrases like "agreement," "quorum," and "Byzantine fault
tolerance," but the deeper question is simpler:

Why is agreeing on a sequence of decisions so hard once more than one machine is allowed to matter?

The trouble starts the moment we stop treating one computer as the single source of truth.

If one process keeps the state, then the next action is whatever that process says it is. Once
state is replicated across several machines for availability, performance, or trust reasons, the
system needs a rule for turning many local views into one shared history.

That rule is consensus.

### The replicated-state-machine picture

A clean mental starting point is the replicated state machine.

Imagine several nodes each holding the same application state. If every honest node starts from the
same state and applies the same commands in the same order, they stay in sync. So the real problem
is not "compute the right answer" in the abstract. The problem is:

- which command comes next,
- whether that command is valid,
- and whether every honest node will eventually place it in the same position in history.

This is why consensus is usually about ordering, not about understanding the application payload in
full detail. The application knows what a transaction, block, or state root means. Consensus knows
how to turn competing proposals into one durable sequence.

### Vocabulary that actually matters

Some terms are worth grounding before the machinery shows up.

- **Agreement** means honest participants do not decide conflicting outcomes.
- **Validity** means the decided value satisfies the protocol's acceptance rules.
- **Termination** or **liveness** means honest participants eventually keep making progress.
- **Safety** is the stronger systems word for "nothing bad happens," usually meaning conflicting
  finalizations do not occur.
- **Partial synchrony** means the network may behave unpredictably for a while, but eventually
  becomes well behaved enough for progress.
- **Crash faults** mean nodes stop or restart.
- **Byzantine faults** mean nodes may lie, equivocate, omit messages, or strategically misbehave.
- A **leader** is the node currently allowed to propose the next value.
- A **quorum** is a set large enough that two such sets must overlap in at least one honest
  participant under the assumed fault model.
- A **certificate** is evidence that a quorum endorsed some subject.
- **Finality** means the system treats a decision as committed, not merely proposed or tentatively
  accepted.

Consensus protocols differ mainly in how they balance those terms under concrete failure models.

### Why majority voting is not enough

A beginner's first idea is often: "let every node vote, then take the majority."

That helps in one narrow moment, but it does not solve the whole problem. Majority of what?
Observed by whom? At which time? Over which proposal? With which guarantee that two different
majorities cannot emerge from different information at different moments?

Even with only crash faults, naive majority voting breaks once messages are delayed and different
nodes see different subsets of the world. One node may think proposal A has enough support, another
may think B does, and both may move on before learning about the other's evidence.

With Byzantine faults the problem becomes sharper. A malicious leader can send one proposal to half
the network and a different proposal to the other half. A malicious validator can equivocate. A
coalition can delay, omit, or strategically reorder messages. Now "just count votes" is not a
protocol. It is a slogan.

What the protocol really needs is a way to ensure that enough support for one history blocks enough
support for any conflicting history.

That is where quorum intersection enters.

### Why quorums work

The basic idea behind quorum protocols is elegantly simple: require enough participants to endorse a
decision that any two endorsement sets must overlap.

In a benign majority system, two majorities intersect. In a Byzantine setting with up to `f`
faulty participants among `N`, the protocol usually needs stronger thresholds. The familiar
`> 2N/3` rule exists because if fewer than `N/3` are Byzantine, then any two quorums of that size
must overlap in at least one honest participant.

That overlap is the lock that prevents the protocol from quietly supporting two conflicting
histories. Honest participants obey state-dependent voting rules. So if one quorum already
certified a value, the overlap participant carries that fact into future rounds and blocks unsafe
conflicts.

Quorums are not magic. They are geometry under a fault assumption.

### Why timeouts and leaders exist

If safety were the only concern, a protocol could simply wait forever for more evidence. Real
systems also need progress.

Progress gets hard because the network may be slow and leaders may fail. If every node proposes at
once, contention explodes. If only one leader may propose, the system needs a way to replace that
leader when it stalls.

So many consensus protocols use a repeating pattern:

1. select a leader,
2. let that leader propose,
3. gather votes under rules constrained by previous certificates,
4. if progress stalls, time out and advance to a new round or view.

This is why timeouts are not merely implementation details. They are part of the liveness story.
They turn uncertainty about the current leader into controlled movement to the next attempt.

### Why asynchronous consensus is fundamentally awkward

There is a famous result, FLP, that says deterministic consensus cannot guarantee termination in a
fully asynchronous system with even one crash failure. You do not need the full proof here. The
important lesson is that a protocol cannot always distinguish "the network is slow" from "the node
is dead."

Modern practical systems respond by weakening the model. They assume partial synchrony: delays may
be unbounded for a while, but eventually communication becomes timely enough. Under that assumption,
the protocol can preserve safety always and recover liveness once the network settles and an honest
leader gets a fair turn.

This is why high-quality consensus code is obsessed with timers, retry logic, and explicit round
structure. Those are not side concerns. They are the engineering embodiment of the model.

### Crash fault tolerance is not Byzantine fault tolerance

It helps to separate two worlds.

In crash-fault-tolerant replication, a node may stop responding, but it does not actively lie. That
world already requires leader election and log agreement, but it is gentler. A crashed node does
not sign two conflicting values or invent fake certificates.

Byzantine fault tolerance is harsher. A participant may:

- send different proposals to different peers,
- vote inconsistently,
- replay old messages in new contexts,
- refuse to relay critical information,
- or collaborate strategically with other faulty participants.

Once you admit that behavior, signatures, namespaces, certificates, and explicit evidence become
load-bearing. The protocol must not only reach agreement. It must do so while treating every
message as potentially strategic input from an adversary.

### Why certificates are more than receipts

A common beginner intuition is that a certificate simply says, "enough people agreed." That is only
half the story.

In many consensus protocols, a certificate is also a **state-carrying object**. It tells the next
round what history is safe to extend, what value is locked in, or what evidence must be respected
before the protocol moves on.

That is why protocol texts care so much about exactly what is being signed. Are validators signing a
proposal, a round number, a parent certificate, or all of the above? Can a signature from one phase
be replayed as evidence in another? Can a node prove who misbehaved, or only that "some quorum"
must have existed?

Those questions are not paperwork. They decide whether the system can preserve safety under attack
and whether faults are attributable after the fact.

### The key tradeoffs

Consensus design is a sequence of tradeoffs, not a march toward one universal optimum.

- **Low latency vs message complexity**: fewer phases are faster on the happy path, but every phase
  must still preserve quorum safety.
- **Attributability vs succinctness**: individually attributable signatures preserve blame
  evidence; threshold signatures compress evidence but hide exactly who signed.
- **Predictable leaders vs unpredictable leaders**: deterministic rotation is simple; randomized or
  VRF-driven leaders can improve adversarial robustness.
- **Protocol simplicity vs feature richness**: reconfiguration, backfill, and broadcast coupling
  solve real problems but complicate the mental model.
- **Tight application coupling vs opaque payloads**: application-aware consensus may optimize
  special cases, but opaque digests keep the core ordering logic cleaner and more reusable.

Different systems choose different points. What matters is that the protocol makes those choices
explicit.

### The bridge into Commonware

That is the right broad frame for `commonware-consensus`.

The crate is solving the classic problem of turning many validators and many possible proposals into
one ordered history, but it does so with a distinct point of view:

- consensus orders opaque digests rather than application-specific objects,
- quorum certificates are reusable context for later rounds rather than dead acknowledgments,
- leader election and signature aggregation are pluggable,
- and the surrounding layers exist to connect abstract agreement to real block delivery and
  recovery.

So when the chapter narrows into `simplex`, `aggregation`, `ordered_broadcast`, and `marshal`, read
them as parts of one argument. The broad problem is shared history under Byzantine uncertainty. The
Commonware answer is to build that history from explicit rounds, explicit certificates, explicit
namespace separation, and explicit recovery boundaries.

With that foundation in place, the detailed mechanics stop feeling ceremonial. They read as the
concrete moves required to keep one invariant true: honest participants may be distributed, delayed,
and attacked, but they still need one history they can all defend.

---

## 1. What Problem Does This Solve?

Distributed consensus asks a deceptively small question:

Given `N` participants, of which up to `f` may behave arbitrarily, how do the honest ones agree on
the same sequence of decisions?

The classical answer is PBFT and its descendants. Those protocols work, but their happy path is
expensive: many message phases, lots of all-to-all traffic, and enough ceremony per decision that
large validator sets feel the weight of it.

`commonware-consensus` takes a different route. **Simplex** keeps the common case to three phases -
notarize, nullify, finalize - and pushes as much work as possible into certificates that can be
reused across rounds. The key idea is that a quorum certificate should not be a dead receipt. It
should be the parent context for what comes next.

The design is built around three properties:

1. **Safety**: No two honest nodes finalize different values at the same height. This holds as long as fewer than `N/3` participants are Byzantine.
2. **Liveness**: The system continues to make progress under partial synchrony, given an eventually leader. Timeout and view-change mechanisms ensure the protocol does not stall indefinitely.
3. **Attributability**: With attributable schemes (ed25519, bls12381_multisig, secp256r1), the signature on a notarize or finalize vote can be used as evidence of a fault. With threshold schemes (bls12381_threshold), signatures cannot be attributed to individual validators — useful for internal liveness proofs but not for punishment.

The crate also separates concerns that many consensus implementations tangle together:

- **What** is being decided (the payload) is opaque to consensus. The `Automaton` trait provides digests; consensus orders them.
- **Who** decides (leader election) is pluggable. `RoundRobin` gives deterministic rotation; `Random` gives unpredictable leaders via threshold VRF.
- **How** signatures are aggregated is pluggable. Attributable schemes preserve fault evidence; threshold schemes give succinct certificates.

### Assumptions the Code Relies On

Before getting lost in the actors, make the trust model explicit. The implementation is written
against a specific world:

- Fewer than `N/3` participants are Byzantine in the active validator set.
- The network is partially synchronous: messages may be delayed, dropped, duplicated, or reordered,
  but after some unknown time there is enough timely delivery for an honest leader to gather a
  quorum.
- Honest participants run deterministic logic for leader election, proposal verification, and
  certification. If two honest nodes inspect the same `(epoch, view, payload)` and reach different
  conclusions, the protocol loses liveness even if the cryptography is perfect.
- Crashes are local, not arbitrary state rewrites. Durable state is whatever has crossed the
  relevant journal or archive sync boundary. Everything else must be treated as ephemeral and
  re-fetched.

Those assumptions are not footnotes. They explain why the crate spends so much code on journaling,
replay, and typed actor boundaries: the implementation is turning those assumptions into concrete
recovery rules.

---

## 2. Mental Model

Think of simplex as a voting machine with memory.

Each round, called a **view**, has a designated leader. The leader proposes a block. Validators then
move through three kinds of votes:

```
Propose → Notarize → Nullify → Finalize
                     ↑
                     └── If leader fails or block invalid: timeout → view change
```

**Notarize** asks: *is this proposal valid enough to build on?*  
If a validator accepts the proposal, it signs a notarize vote. Once more than `2N/3` validators do
that, the block has a notarization certificate. That does not yet mean "fully committed forever,"
but it does mean the block has crossed an important line: any safe future must account for it.

**Nullify** asks: *should we abandon this view and move on?*  
If the leader stalls or proposes nonsense, validators can vote to skip the view. Nullify votes carry
no payload, only the round identity. But they are not free-floating. They still have to respect
parent continuity. You cannot safely say "let us skip view `v`" unless you can also prove you are
not jumping over certified history that honest validators may already depend on.

**Finalize** asks: *are we ready to commit this block as part of the durable sequence?*  
A block can only be finalized after it has already been notarized. That ordering is the conceptual
center of the protocol. First establish that the proposal is admissible. Then establish that the
system is ready to commit it.

The invariant to hold onto is:

> **finalization requires notarization, and notarization requires proposal validity.**

Once that chain is in your head, the protocol becomes much easier to reason about. Every later
detail is there to protect one link in that chain.

### Composing the Layers

The four primitives stack like this:

```
marshal          ← delivers finalized blocks to the application
    ↑                (coordinates broadcast + simplex + backfill)
simplex          ← three-phase consensus
    ↑                (coordinates voter + batcher + resolver)
aggregation      ← quorum certificates over external sequence
    ↑                (coordinates with externally-provided ordered items)
ordered_broadcast← sequencer → validator reliable broadcast
```

Each layer solves a different failure problem:

- `simplex` handles Byzantine leaders and view changes.
- `ordered_broadcast` makes sequencer equivocation detectable through chaining.
- `aggregation` turns externally provided ordered items into quorum-certified facts.
- `marshal` closes the gap between "a block exists somewhere" and "the application can now consume
  finalized blocks in order."

---

## 3. Core Abstractions and Important Types

This chapter gets easier if you sort the types by the question they answer:

- **What time are we talking about?** `Epoch`, `View`, `Round`, `Height`
- **What is being voted on?** `Subject`, `Proposal`, `Certificate`
- **Who is allowed to influence the decision?** the elector and the signing scheme
- **How does data reach validators?** ordered broadcast, aggregation, marshal

That organization keeps the reader oriented around protocol questions instead
of turning the type list into a glossary dump.

### Identifier Types (`consensus/src/types.rs`)

The protocol uses four different notions of "where we are." Keeping them separate prevents a lot of
confusion later.

**`Epoch`**  
The validator-set boundary. If membership changes, the epoch changes. Certificates do not cross that
boundary.

**`View`**  
The leader-attempt counter inside one epoch. If a leader fails, the view increments.

**`Round`**  
The pair `(Epoch, View)`. This is the protocol's full "where are we right now?" coordinate.

**`Height`**  
The position of a finalized block in the output chain. Heights are application-visible history.
Rounds are protocol progress. One height may need several rounds before it is finalized.

All arithmetic is overflow-safe. `next()` panics on overflow (which is appropriate for identifiers that should never realistically overflow). Arithmetic that might legitimately underflow returns `Option` or saturates.

### The Trait Hierarchy (`consensus/src/lib.rs`)

`Automaton` is the boundary between consensus and the application. It tells consensus three things:

1. what the genesis digest is,
2. how to ask the application for a proposal,
3. how to ask the application whether a proposal is acceptable.

```rust
pub trait Automaton: Clone + Send + 'static {
    type Context;
    type Digest: Digest;

    fn genesis(&mut self, epoch: Epoch) -> impl Future<Output = Self::Digest> + Send;
    fn propose(&mut self, context: Self::Context) -> impl Future<Output = oneshot::Receiver<Self::Digest>> + Send;
    fn verify(&mut self, context: Self::Context, payload: Self::Digest) -> impl Future<Output = oneshot::Receiver<bool>> + Send;
}
```

The important abstraction choice is that consensus traffic carries **digests**, not full application
objects. That keeps consensus generic and keeps large payload movement in the broadcast layer where
it belongs.

`propose` and `verify` return one-shot channels rather than plain booleans because the application
may need time to decide. But once the channel resolves or closes, consensus treats the verdict as
final for that attempt.

`CertifiableAutomaton` adds one more hook between notarization and finalization. This is where the
application can say, in effect: "The block is valid, but I am not yet ready to finalize it."

```rust
pub trait CertifiableAutomaton: Automaton {
    fn certify(&mut self, round: Round, payload: Self::Digest) -> impl Future<Output = oneshot::Receiver<bool>> + Send {
        // default: always certify
        async move { receiver }
    }
}
```

The certify decision must be deterministic across honest participants. If equally honest validators
make different certify decisions on the same input, liveness falls apart.

**`Relay`** broadcasts full payloads to the network. Consensus only knows digests; the relay disseminates the data.

**`Reporter`** emits activity events (votes, finalizations, faults) for reward/penalty systems.

**`Monitor`** allows external actors to subscribe to consensus progress (latest finalized index).

### Simplex Types (`consensus/src/simplex/types.rs`)

`Subject<'a, D>` identifies what a validator is actually signing at a given moment:

```rust
pub enum Subject<'a, D: Digest> {
    Notarize { proposal: &'a Proposal<D> },
    Nullify { round: Round },
    Finalize { proposal: &'a Proposal<D> },
}
```

That split is worth noticing. `Notarize` and `Finalize` both point at a proposal. `Nullify` points
only at a round, because a nullify vote is not endorsing data; it is endorsing progress to the next
attempt.

`VoteTracker<S, D>` is the bookkeeper that prevents phase confusion and duplicate votes:

```rust
pub struct VoteTracker<S: Scheme, D: Digest> {
    notarizes: AttributableMap<Notarize<S, D>>,
    nullifies: AttributableMap<Nullify<S>>,
    finalizes: AttributableMap<Finalize<S, D>>,
}
```

`AttributableMap<T>` is keyed by validator index, so each validator gets at most one slot per
phase. That is how the code enforces the familiar protocol rule "one validator, one vote, per
phase, per round."

**`Context<D, P>`** carries round metadata for proposal verification:

```rust
pub struct Context<D: Digest, P: PublicKey> {
    pub round: Round,
    pub leader: P,
    pub parent: (View, D),
}
```

The `parent` field is the critical piece. If there is a gap between the current view and the parent view, the validator must possess a nullification for each discarded view before safely voting on a new proposal. This is the fork-safety mechanism: without parent nullifications, a malicious leader could cause honest validators to finalize a chain that bypasses an honest leader's block.

### Signing Schemes (`consensus/src/simplex/scheme/mod.rs`)

The scheme layer is where you decide what kind of evidence a certificate should preserve.

- **`ed25519`**, **`bls12381_multisig`**, **`secp256r1`**: Attributable. Each individual signature carries the signer's identity. Certificates contain `(index, signature)` pairs.
- **`bls12381_threshold`**: Non-attributable. Any `t` partial signatures can be combined to forge a signature for any other participant. Certificates contain only the recovered threshold signature.

Domain separation is enforced through namespace suffixes. Each subject signs under a different
namespace:

```rust
const NOTARIZE_SUFFIX: &[u8] = b"_NOTARIZE";
const NULLIFY_SUFFIX: &[u8] = b"_NULLIFY";
const FINALIZE_SUFFIX: &[u8] = b"_FINALIZE";
```

A signature made under `_NOTARIZE` cannot be replayed as `_FINALIZE`. That sounds like a small
cryptographic hygiene rule, but it blocks an entire class of "same bytes, wrong meaning" attacks.

### Leader Election (`consensus/src/simplex/elector.rs`)

There are two broad leader-election stories here.

**`RoundRobin`** says: rotate deterministically through the participant set.  
**`Random`** says: derive the next leader from certified randomness, so the leader is harder to
predict in advance.

Both implement the `Elector` trait:

```rust
pub trait Elector<S: Scheme>: Clone + Send + 'static {
    fn elect(&self, round: Round, certificate: Option<&S::Certificate>) -> Participant;
}
```

For view 1, there is no prior certificate to seed from, so the random elector falls back to the
deterministic path. After that, the certificate becomes part of the randomness source. Whatever the
scheme, the output must still be deterministic for a given input tuple.

### Ordered Broadcast (`consensus/src/ordered_broadcast/`)

Ordered broadcast is where the crate stops pretending that "a digest exists" is the same thing as
"the network can reconstruct the object behind that digest." The system has two roles:
**sequencers** introduce chunks, and **validators** make those chunks durable by acknowledging them.

The core object is the `Node`, not the bare chunk, because safety depends on
the chunk plus the ancestry that says what the next height is allowed to skip.
A node contains:

1. the chunk `(sequencer, height, payload)`,
2. the sequencer's signature over that chunk,
3. for non-genesis heights, a parent record carrying the previous payload digest, the parent's
   epoch, and the quorum certificate that locked in the parent.

That parent record matters more than it first appears. It means a sequencer cannot safely extend
height `h` until height `h-1` has already crossed the validator quorum. Ordered broadcast is not
"spray chunks and hope." It is a certificate-linked chain per sequencer.

The implementation mass lives in two internal memories inside `ordered_broadcast::Engine`:

- `tip_manager`: the best known node per sequencer. This answers the question "what is the latest
  non-conflicting claim this sequencer has made?"
- `ack_manager`: the validator acks and recovered certificates for each `(sequencer, height)`.
  This answers the question "what has quorum actually confirmed?"

That split is the real design. A node may exist before a quorum exists. A quorum may exist before
every peer has the node. The engine keeps those facts separate so it can reason about equivocation,
replay, and backpressure without conflating them.

### Aggregation (`consensus/src/aggregation/`)

Aggregation solves a narrower but very practical problem: an external process already decided the
order, and now validators need quorum certificates over the resulting `(height, digest)` stream.

So the unit here is the `Item<D>`:

```rust
pub struct Item<D: Digest> {
    pub height: Height,
    pub digest: D,
}
```

Unlike ordered broadcast, there is no per-sequencer parent chain. Each height is certified on its
own. The interesting implementation problem is therefore not ancestry; it is how to keep moving
when peers drift and local digest knowledge arrives late.

The engine models each height as either:

- `Pending::Unverified`: acks may already be arriving from the network, but the local automaton has
  not yet told us which digest belongs at that height.
- `Pending::Verified`: we now know the digest, so only matching acks count toward certificate
  recovery.

That distinction lets the engine overlap network work with application work. A peer can be ahead of
us and still help, but the local node will only combine shares once the automaton has fixed the
digest.

### Marshal (`consensus/src/marshal/`)

Marshal is the layer that turns "consensus has certificates" into "the application can consume a
gap-free history." It is not another consensus protocol. It is the ordering and repair layer above
consensus.

The core actor keeps four different kinds of memory:

- a prunable cache for recently seen blocks, notarizations, and finalizations,
- immutable finalized archives keyed by height,
- metadata for `last_processed_height`, which is the durable handoff point to the application,
- a FIFO pipeline of pending application acknowledgements so delivery stays sequential even if the
  application is slower than the network.

That architecture is the reason marshal can promise at-least-once, in-order delivery. Consensus may
learn about a finalization before the corresponding block is local. Broadcast may have the block
before the finalization arrives. Resolver may fill a gap later still. Marshal is the actor that
waits until those streams line up and only then advances the application-facing height.

**Starting height (floor)**: Marshal can be configured to only retain heights above a floor. This
supports snapshot-based state sync. The important detail is that the floor is not just a read hint.
It rewrites marshal's recovery boundary: blocks below the floor are pruned, pending acknowledgements
below the floor are dropped, and future backfill requests below the floor are rejected.

---

## 4. Execution Flow and Lifecycle

This is the section where the protocol stops being a list of definitions and
becomes a live sequence of obligations.
The main thing to watch is not the mailbox plumbing by itself. It is how the actor flow preserves
the invariants from the earlier sections while messages arrive late, certificates appear out of
order, and timeouts fire.

### Simplex as Three Cooperating Actors

Simplex is easiest to understand if you stop picturing "the consensus node" as one blob.
Implementation-wise it is three cooperating actors with sharply different jobs.

**The voter** owns temporal truth. It knows the current view, active rounds, parent ancestry,
deadlines, certification futures, and the crash-recovered local voting history. If you want to know
why a node is willing or unwilling to advance, this is the actor to inspect.

**The batcher** owns cryptographic fan-in and fan-out. Network votes arrive untrusted and possibly
conflicting. The batcher groups them by view, records pending versus verified votes, batch-verifies
signatures, recovers certificates, and decides whether a certified proposal should be forwarded to
missing voters or the next leader. It is also where a lot of attributable fault detection lives:
conflicting notarizes, finalize-after-nullify, and signer mismatches are all caught here.

**The resolver** owns certificate gaps. It wraps `commonware_resolver::p2p`, tracks a moving floor,
and asks peers for the nullifications or higher-view certificates the voter still lacks. Its state
is not "all certificates ever seen." It is "the smallest certificate window that still matters for
safe advancement."

That split is not cosmetic. It keeps each actor's failure model narrow:

- the voter reasons about safety and timers,
- the batcher reasons about signature validity and quorum formation,
- the resolver reasons about missing evidence and retries.

Because those responsibilities are disjoint, replay and testing stay manageable.

### Simplex Voter Lifecycle

The voter actor (`consensus/src/simplex/actors/voter/actor.rs`) is the heart of simplex. It opens
genesis, replays its journal into `state`, re-notifies the reporter and resolver about recovered
artifacts, initializes the current leader, and only then enters the steady-state loop.

That steady-state loop handles three classes of events:

1. **Incoming messages** (proposals, votes, certificates) via the mailbox.
2. **Timeout events** from the deterministic clock.
3. **Automaton responses** (verification, certification verdicts).

The loop uses `select_loop!` from `commonware_macros`, which matters because the voter always has
partially completed work in flight: pending propose requests, pending verify requests, pending
certify requests, and timeout deadlines.

**On receiving a proposal:**

```
1. Extract context (round, leader, parent) from proposal.
2. Check if we already have a notarize/finalize for this view → ignore if duplicate.
3. Check parent nullification: if parent.view < our latest known view,
   ensure we have nullifications for all views in between.
   If not → store proposal but don't vote yet (waiting for parent continuity).
4. Send verification request to automaton.
5. On verification true → send notarize vote to batcher.
6. On verification false → don't notarize (no negative vote; just stay silent).
```

The subtle point is step 3. `state.try_verify()` computes the parent payload only if the ancestry is
already certified. It explicitly refuses to use proposal verification as an excuse to backfill
missing history. A malicious proposer is not allowed to trick an honest node into chasing arbitrary
old certificates before the honest node has enough reason to care.

**On receiving a notarization certificate (>2N/3 notarizes):**

```
1. Record the notarization certificate in state.
2. Send certification request to automaton (via CertifiableAutomaton).
3. On certification true → send finalize vote to batcher.
4. On certification false → don't finalize.
```

Certification failure is not a quiet no-op. The voter journals the outcome, reports it, and informs
the resolver, which may need to re-open lower-view requests that were only tentatively satisfied by
the now-useless notarization.

**On timeout (no progress in current view):**

```
1. Send nullify vote to batcher.
2. If >2N/3 nullifications accumulated → enter view change.
3. In view change: advance view, reset vote trackers, request certificates from resolver.
```

**Parent nullification enforcement** (`consensus/src/simplex/types.rs:Context`):

The `parent` field carries `(View, Digest)` of the block this proposal is built on. If `parent.view` is less than the validator's latest known certified view, the validator must hold nullifications for every intermediate view before voting. This is checked in the voter actor before sending any notarize vote. Without this check, a malicious leader could publish a chain that skips an honest leader's block, and honest validators would unknowingly finalize it.

### What the Batcher Really Does

The batcher is more than a relay. Per view, it holds a `Round` with four distinct memories:

- `pending_votes`: everything received from the network, before verification,
- `verified_votes`: only votes that survived batch verification,
- `verifier`: a proposal-aware certificate recovery helper,
- cached certificates, so work stops once a notarization, nullification, or finalization is known.

Two details from `batcher::round.rs` are worth carrying in your head.

First, the batcher only tries to recover proposal-bound certificates for the leader's first
proposal. If the node is on the wrong side of a leader equivocation, it still records evidence and
can forward recovered certificates, but it does not spend more work helping a conflicting proposal
become a local candidate.

Second, the batcher tracks recent per-peer activity. That is not a Byzantine-proof oracle. It is a
practical skip heuristic: once the system has enough history, silent leaders stop receiving infinite
benefit of the doubt, and forwarding policies can preferentially target missing voters or the next
leader.

### What the Resolver Really Does

The resolver actor is the smallest one, but it carries the trickiest book-keeping.

Its `State` tracks:

- `floor`: the most recent notarization or finalization that is strong enough to anchor later views,
- `notarizations`: higher-view notarizations still waiting on the voter's certification result,
- `nullifications`: the skip proofs above the floor,
- `failed_views`: views where certification already failed, so future notarizations for that view
  are useless,
- `satisfied_by`: a map from higher-view notarizations to the lower-view requests they temporarily
  satisfied.

That last map is the non-obvious one. Suppose the resolver asked for view 7 and a peer answered
with a notarization from view 9. That may be enough to let the voter continue for now. But if view 9
later fails certification, the resolver must remember that view 7 is still missing and re-request
it. `satisfied_by` is how the implementation keeps that promise.

### Ordered Broadcast Internals

A sequencer's chain looks like this:

```
height=0: Node(chunk_0, parent=None)
height=1: Node(chunk_1, parent=cert_of(chunk_0))
height=2: Node(chunk_2, parent=cert_of(chunk_1))
...
```

The important implementation fact is the order of side effects.

1. `tip_manager.put(node)` records a new highest node for that sequencer.
2. If the node is new, the engine appends it to that sequencer's journal and syncs before exposing
   it further.
3. The automaton verifies the chunk payload asynchronously.
4. If verification succeeds and this node is a validator, the engine creates an `Ack`.
5. Before that ack is sent, the journal is synced again so a restart cannot cause the same validator
   to acknowledge two conflicting chunks at one height.
6. `ack_manager` accumulates acks and recovers a certificate once quorum is reached.

That is the real safety story. Chaining detects equivocation, but the journal sync boundary is what
stops an honest restart from *becoming* an equivocator.

Notice also what the proposer path forbids. `Engine::should_propose()` only returns a new context if
the current tip already has a certificate. A sequencer is not allowed to extend an uncertified tip.
The ordered-broadcast chain therefore advances one certified parent at a time.

### Aggregation Engine and `safe_tip`

Aggregation's most important implementation idea is `safe_tip`.

Each peer gossips `TipAck { ack, tip }`, where `tip` is the lowest height it still considers
unconfirmed. The engine pessimistically assumes the `f` highest reported tips may belong to faulty
validators. `safe_tip` therefore keeps:

- `hi`: the `f` highest reported tips,
- `lo`: the remaining `n-f` lowest tips.

The reported safe tip is the maximum element of `lo`. Why that one? Because if we throw away the
`f` most optimistic reports as potentially Byzantine, the highest remaining tip is still known to be
reached by at least one honest validator.

That gives the engine a principled fast-forward rule:

1. keep a small moving window of pending heights,
2. collect acks even before the local digest is known,
3. once the automaton verifies a digest, keep only matching acks,
4. when `safe_tip` rises above the local tip, fast-forward and prune work that is now too far
   behind active honest peers.

This explains an otherwise surprising design choice from `aggregation/mod.rs`: peers do **not**
gossip recovered certificates. They gossip `TipAck`s. The engine is optimized to stay near the
honest frontier, not to reconstruct a perfect historical archive of every certificate that ever
formed. If an application needs the full history, it must build that synchronization story itself.

### Marshal Core and Coding Mode

Marshal coordinates three input streams:

1. **Uncertified blocks** from broadcast (via `commonware_broadcast::buffered` or `coding::shards::Engine`).
2. **Notarizations** from simplex.
3. **Finalizations** from simplex.

Its core loop makes one ordering choice over and over:

> never let "we heard about a later certificate" outrun "the application has durably processed the
> earlier finalized block."

That is why `PendingAcks` exists. The actor may dispatch several finalized blocks to the
application, but it arms their acknowledgement waiters in FIFO order and advances
`last_processed_height` only in sequence. After draining the ready acknowledgements it syncs
application metadata once, then refills the pipeline.

Finalizations are also handled in a deliberately conservative order:

1. cache the finalization by round,
2. find the block locally if possible,
3. if block and finalization are both present, write them into the finalized archives,
4. try to repair any gaps those writes expose,
5. sync local finalized state before serving produce requests back to peers.

This "our durability before your convenience" ordering is easy to miss in the source, but it is the
right mental model for the actor.

**Backfill** is keyed, not generic. Marshal asks the resolver for exactly one of three things:

- `Request::Block(commitment)` when a finalization exists but the block is missing,
- `Request::Notarized { round }` when a notarization exists without its block,
- `Request::Finalized { height }` when a peer hints that a finalized height should exist locally.

Because the requests are explicit, marshal can also decide when to abandon them, when to keep local
subscriptions alive across floor changes, and when not to chase a digest-only request that could
hang forever.

**Standard vs. coding mode**: the core actor stays the same, but the buffer semantics change.
In standard mode the buffer holds whole blocks. In coding mode `marshal::coding::Marshaled`
converts an application block into an erasure-coded commitment before proposal time, and
`coding::shards::Engine` spreads shards across peers and reconstructs full blocks when notarization
or finalization makes the payload worth recovering. The ordering logic does not move; only the data
availability machinery changes.

---

## 5. Concurrency, Protocol, and Systems Semantics

These are the disciplines the code is trying to enforce. A consensus protocol is not only a sequence
of messages; it is a set of promises about quorum overlap, evidence, determinism, and recovery. The
implementation details matter because they are where those promises either survive contact with the
runtime or quietly disappear.

### Deterministic Runtime and Testing

All consensus actors run on `commonware_runtime::deterministic::Runner`. This is a simulated runtime that controls time explicitly, enabling deterministic test execution. Tests can advance time manually, fire multiple concurrent events, and verify deterministic outcomes.

The deterministic runtime is why the codebase can test Byzantine scenarios reproducibly: with a fixed seed, the same sequence of events always produces the same result. This is critical for testing protocols where timing matters (timeouts, view changes, competing proposals).

The important detail is how the tests make that reproducibility visible. They label validator,
reporter, application, engine, and network actors with `with_label(...)`, then often return
`context.auditor().state()` as a compact witness of the schedule that actually ran. Restart paths
use `start_and_recover()`: run until a checkpoint, resume from that checkpoint, and keep checking
protocol invariants instead of switching to a separate recovery harness.

That same style shows up in adversarial assertions. Consensus tests do not only wait for
finalization; they also inspect `oracle.blocked()` to ensure malicious or partitioned peers were
quarantined when the protocol expected them to be.

That combination is worth treating as methodology, not just testing style. A good consensus result
in this repository is backed by an execution witness, a replayable seed, and an explicit fault
assertion. That is how the crate avoids the common systems-writing failure mode where liveness is
described abstractly and failure behavior is left implicit.

### Actor Message Passing

All simplex actors communicate via typed channels. There is no shared mutable state between voter,
batcher, and resolver. That buys two things:

- clearer ownership of safety-critical state,
- deterministic tests that can isolate one actor with mock neighbors.

The price is explicit coordination. Certification success has to flow from voter to resolver. Newly
constructed votes have to flow from voter to batcher. Recovered certificates have to flow from
batcher or resolver back into voter state. The implementation accepts that plumbing cost because it
keeps each safety rule local.

### N3f1 Quorum Threshold

Throughout the crate, quorum is `N3f1::quorum(N)` = `N - N/3` (ceiling). For `N=4`, quorum is 3; for `N=7`, quorum is 5; for `N=10`, quorum is 7. This is the minimum quorum that guarantees:
- Safety: With `f = N/3` Byzantine nodes, any two quorums of size `>2N/3` must overlap in at least one honest node.
- Liveness: An honest quorum can always make progress (since `N - f = 2f + 1 > f` honest nodes).

### Certificate Assembly

Certificates are assembled by collecting attestations from `N3f1::quorum(N)`
participants. The assembly is scheme-dependent because different protocols
need different kinds of evidence out of the same quorum:

- **Attributable schemes** keep each participant visible in the certificate.
  That is the right shape when later auditing or blame matters.
- **Threshold schemes** compress the same quorum into one recovered
  signature. That is the right shape when the system wants succinct evidence
  more than individual attribution.

### Domain Separation in Namespaces

Namespaces are derived by appending a suffix to a base namespace:

```rust
// consensus/src/simplex/scheme/mod.rs
const NOTARIZE_SUFFIX: &[u8] = b"_NOTARIZE";
const NULLIFY_SUFFIX: &[u8] = b"_NULLIFY";
const FINALIZE_SUFFIX: &[u8] = b"_FINALIZE";
```

The scheme's `Namespace` trait is implemented for `simplex::scheme::Namespace`:

```rust
impl certificate::Namespace for Namespace {
    fn derive(namespace: &[u8]) -> Self {
        Self::new(namespace)  // pre-computes all suffixes
    }
}
```

When signing, the scheme passes the appropriate suffix-derived namespace to the underlying cryptographic primitive. The signature is bound to a specific subject type: a notarize signature cannot be interpreted as a finalize signature because the namespace differs.

### Single-Shot Verification and Certification

Both `Automaton::verify` and `CertifiableAutomaton::certify` are single-shot:

> Once the returned channel resolves or closes, consensus treats verification/certification as concluded and will not retry the same request.

This is a subtle but critical property. If the application is still uncertain (waiting for dependencies, waiting for time to pass), it must keep the channel open. Returning `false` is permanent — consensus will never retry. The application must only return `false` when the payload is *permanently* invalid, not when validity is still being determined.

This design prevents a class of liveness bugs where a slow verifier causes consensus to stall. Instead, the protocol simply waits. If the verifier eventually returns `true`, consensus proceeds. If it returns `false`, consensus treats the proposal as invalid and the leader times out.

### Journaling and Crash Recovery

Each subsystem draws its own durability boundary.

**Simplex voter** journals locally meaningful artifacts: votes it constructed, certificates it
accepted, and certification outcomes. Replay rebuilds `state`, re-emits reporter activity, and
re-seeds the resolver with recovered certificates. The journal is not a network transcript. It is
the minimum durable evidence needed to avoid re-voting inconsistently after restart.

**Ordered broadcast** keeps per-sequencer journals of nodes. The critical guarantee is not "every
packet is durable." It is "before I propose or acknowledge at height `h`, my disk state already
rules out later proposing or acknowledging a different payload at `h`."

**Aggregation** journals three things: locally signed acks, recovered certificates, and
fast-forwarded tips. That last category matters because tip advancement is a semantic choice to
abandon stale history. Replay has to remember that choice or it may resurrect work the node had
already decided was behind the honest frontier.

**Marshal** persists finalized archives plus the application's processed-height metadata. In-flight
subscriptions, waiter futures, and transient buffer contents are not the durable boundary. They are
ephemeral repair machinery. After a crash, marshal can recreate them from finalized state and fresh
resolver requests.

---

## 6. Failure Modes, Cancellation, and Correctness Concerns

This section is the protocol under stress. The happy path tells you what the design wants to do.
The failure sections tell you what the design is actually prepared to survive, what it can only
mitigate, and where the hard limits really are.

### Byzantine Fault Tolerance Limits

The `N/3` tolerance is a hard limit. If more than `N/3` participants are simultaneously Byzantine:

- **Safety can be violated**: A Byzantine quorum can finalize two conflicting blocks at the same height (by controlling which blocks propagate to which honest nodes).
- **Liveness can be violated**: A Byzantine coalition can always have a quorum to block finalization.

In practice, this means the system is secure against up to 33% adversarial participation. For 10 validators, this means 3 can be Byzantine. For 100 validators, 33 can be Byzantine.

### Quorum Overlap and Notarize-Before-Finalize

The shortest useful safety proof in this crate is the quorum-overlap argument.

Let quorum size be `q = N - floor(N/3)`. Any two quorums of size `q` overlap in more than `N/3`
participants. Since at most `N/3` are Byzantine, the overlap contains at least one honest
participant.

Now combine that with the local voting rules:

1. an honest validator signs at most one notarize per view,
2. an honest validator signs at most one finalize per view,
3. an honest validator only finalizes a proposal that was already notarized and certified locally.

Suppose two conflicting finalizations existed for the same view. Their signer sets would overlap in
an honest validator. That validator would have had to sign two conflicting finalizes for the same
view, which the local `VoteTracker` rules forbid. So two conflicting finalization certificates for
one view cannot both be produced while the fault bound holds.

That is the high-level proof. The rest of the implementation is there to protect its premises:
domain separation protects subject identity, the batcher catches duplicate or conflicting votes, and
the voter refuses to finalize without prior notarization and certification.

### Non-Attributable Threshold Signatures

With `bls12381_threshold`, the scheme is **non-attributable**: any `t` partial signatures can be combined to forge a signature for any other participant. This has a critical implication:

> Evidence cannot be exported to third parties. A signature that proves validator V participated in a quorum cannot be verified by an external observer — because an external observer cannot distinguish a genuine V signature from a forged one.

This is fine for internal liveness proofs (the local node knows it sent the signature). It is not fine for punishment protocols that require presenting evidence to an external arbiter.

For punishment protocols, use attributable schemes (ed25519, bls12381_multisig, secp256r1). The `reporter::AttributableReporter` filters events based on scheme: it only exposes attributable votes as evidence.

### VRF Randomness and the Commit-Then-Reveal Pattern

The `bls12381_threshold::vrf` variant produces seed signatures usable for randomness. The documentation includes a security warning:

> It is **not safe** to use a round's randomness to drive execution in that same round. A malicious leader can selectively distribute blocks to gain early visibility of the randomness output, then choose nullification if the outcome is unfavorable.

The recommended pattern is **commit-then-reveal**: bind randomness requests in finalized blocks at view `v` for use at view `v+100` (or any sufficiently distant view). By then, the randomness is finalized and cannot be influenced by the leader of `v+100`.

### Nullification and Fork Safety

The parent nullification requirement is the most subtle invariant in simplex. Consider this attack:

1. Honest leader proposes block B at view 5.
2. Validator V is slow; it receives B but hasn't notarized it yet.
3. Malicious leader at view 6 proposes a chain that skips B (built on view 4).
4. V, seeing the view 6 proposal with parent view 4, might notarize it — inadvertently finalizing a chain that skips B.

The nullification requirement prevents this: before V can notarize the view 6 proposal, it must have a nullification for view 5 (or B's notarization). If V doesn't have either, it cannot vote. This ensures that any finalized chain always includes all valid blocks from the previous certified view.

In proof-sketch form, the rule says:

- every proposal names a parent `(view, digest)`,
- if that parent is not the current floor, the validator must justify every skipped view with a
  nullification,
- therefore any honest notarize vote carries an implicit statement: "between my floor and this
  proposal, no unaccounted certified view was skipped."

That is why resolver state is organized around floors and missing nullifications. The resolver is
not merely fetching data. It is fetching the missing premises of the safety proof.

### Cancellation and Timeouts

The voter uses `leader_timeout` and `certification_timeout` to bound how long it waits. The invariant enforced at construction:

```rust
if cfg.leader_timeout > cfg.certification_timeout {
    panic!("leader timeout must be less than or equal to certification timeout");
}
```

The leader timeout must not exceed the certification timeout because certification (the application's `certify` call) happens after notarization. If the leader timeout were larger, a leader could propose, get notarized, then timeout before certification completes — causing unnecessary view changes.

Timeouts are clock-driven via `commonware_runtime::Clock`. In the deterministic runtime, tests can advance time explicitly, firing timeout events at precise moments.

### Marshal Gap Handling

Marshal delivers blocks in monotonically increasing order (no gaps). When a gap appears:

```
1. Marshal detects that it has a finalization for height h but no block at h-1.
2. It pauses finalization of h and emits a backfill request.
3. Resolver queries peers for the missing block.
4. On receipt, Marshal verifies and delivers h-1.
5. Finalization of h resumes.
```

If the gap cannot be filled (peer doesn't have it, or peer is malicious), Marshal will continue to retry. The application receives no updates until the gap is resolved.

### Double-Signing and Equivocation Detection

In `ordered_broadcast`, a sequencer that broadcasts two different chunks at the same height
creates detectable equivocation. `ordered_broadcast::types::Error::ChunkMismatch` captures that
fork. An honest validator is supposed to journal and sync before acknowledging, so restart logic
should keep it from signing both sides of the conflict.

In simplex, a validator that sends two different notarize votes at the same view produces equivocation. The `AttributableMap` enforces one vote per phase per validator: the second insert returns `false`.

### Fuzz Invariants as Executable Proof Obligations

The file `consensus/fuzz/src/invariants.rs` is worth reading as a compact statement of what the
crate thinks it must never violate. These are not prose comments. They are executable obligations
checked against randomized simplex executions.

The invariants include:

- **agreement**: all replicas that finalized a given view finalized the same digest,
- **no nullification in a finalized view**: finalization and nullification cannot both survive for
  one view,
- **no conflicting quorum notarizations**: two different digests cannot both gather quorum in one
  view,
- **finalization requires notarization**: every finalization must be backed by a notarization for
  the same `(view, payload)`,
- **certificate cardinality sanity**: attributable schemes expose a quorum-sized signer count,
  while non-attributable schemes must not pretend to reveal one,
- **no nullification and finalization in the same view per replica**.

This is a useful reading trick for the whole crate:

> the fuzz invariants tell you which theorems the implementation is trying to make executable.

They are not a formal proof, but they are extremely valuable regression tripwires. If a refactor
breaks one of these conditions under randomized schedules, the protocol has almost certainly lost
one of its core promises.

---

## 7. How to Read the Source Code

Read the consensus crate as an argument, not as a catalog.

Start with the temporal identifiers and the trait boundary to the application. Then read the vote
subjects and certificate machinery. Then read the voter state machine. Only after that should you
move outward into ordered broadcast, aggregation, and marshal. That order keeps the main protocol
idea in focus instead of burying it under support code.

### File Map

```
consensus/src/
  lib.rs                      ← trait hierarchy (Automaton, CertifiableAutomaton, Relay, Reporter, Monitor)
  types.rs                    ← Epoch, View, Height, Round, Participant, Delta types
  simplex/
    mod.rs                    ← module entry, public re-exports
    types.rs                  ← Subject, VoteTracker, AttributableMap, Context, Proposal, Vote types
    scheme/
      mod.rs                  ← Namespace derivation, scheme trait, domain separation constants
      ed25519.rs              ← attributable scheme
      bls12381_multisig.rs    ← attributable scheme
      bls12381_threshold.rs   ← non-attributable threshold scheme
      secp256r1.rs            ← attributable scheme
      reporter.rs             ← AttributableReporter for filtering attributable events
    elector.rs                ← RoundRobin and Random leader election
    actors/
      voter/
        actor.rs              ← main voter state machine (the most important file)
        round.rs              ← per-view state transitions and replay behavior
        slot.rs               ← proposal/certificate slot logic within a round
        state.rs              ← voter state (active views, certificates, etc.)
        ingress.rs            ← inbound message types
      batcher/
        actor.rs              ← vote batching and broadcast coordination
        round.rs              ← per-view vote accumulation, verification, and fault detection
      resolver/
        actor.rs              ← certificate exchange with peers
        state.rs              ← floor/nullification request tracking
  aggregation/
    mod.rs                    ← engine, configuration, pluggable scheme
    types.rs                  ← Item, Ack, TipAck, Certificate, Namespace
    engine.rs                 ← aggregation state machine
    config.rs                 ← engine configuration
    safe_tip.rs               ← tip advancement logic
  ordered_broadcast/
    mod.rs                    ← Engine, sequencer/validator roles, pluggable scheme
    types.rs                  ← Node, Chunk, Parent, Ack, Activity, Context
    engine.rs                 ← broadcast engine
    ack_manager.rs            ← tracks validator acknowledgments
    tip_manager.rs            ← tracks sequencer chain tips
  marshal/
    mod.rs                    ← Actor, Config, Update types
    core/actor.rs             ← main marshal actor
    standard/                 ← standard (non-erasure-coded) mode
    coding/mod.rs             ← erasure-coded mode and entry point
    coding/shards/engine.rs   ← shard dissemination and reconstruction
    resolver/handler.rs       ← backfill request handling
    resolver/p2p.rs           ← resolver network adapter
    ancestry.rs               ← block ancestry queries
    store/                    ← internal storage for blocks and certificates
consensus/fuzz/
  src/invariants.rs           ← randomized proof obligations for simplex safety
```

### Reading Order

For understanding the protocol:

1. **`consensus/src/types.rs`** — understand the identifier types (Epoch, View, Height, Round). All consensus decisions are scoped to these identifiers.
2. **`consensus/src/lib.rs`** — understand the trait hierarchy. Automaton is the key interface.
3. **`consensus/src/simplex/types.rs`** — understand Subject, VoteTracker, and Context. These encode the core protocol state.
4. **`consensus/src/simplex/scheme/mod.rs`** — understand domain separation (namespace suffixes). This is where cross-protocol attacks are prevented.
5. **`consensus/src/simplex/elector.rs`** — understand leader election determinism requirements.
6. **`consensus/src/simplex/actors/voter/actor.rs`** — the main state machine. Read this last and carefully.

For understanding the implementation substance around simplex:

7. **`consensus/src/simplex/actors/batcher/round.rs`** — see how pending votes become verified
   votes and how equivocation is detected.
8. **`consensus/src/simplex/actors/resolver/state.rs`** — see how floors, failed views, and
   re-requests are tracked.

For understanding the layers above simplex:

9. **`consensus/src/ordered_broadcast/engine.rs`** — the real propose / verify / ack / recover
   loop for sequencer chains.
10. **`consensus/src/aggregation/engine.rs`** and **`safe_tip.rs`** — certificate recovery over an
    external sequence and the honest-progress floor.
11. **`consensus/src/marshal/core/actor.rs`** and **`marshal/coding/mod.rs`** — how notarized and
    finalized data becomes a gap-free application stream in both standard and coding modes.
12. **`consensus/fuzz/src/invariants.rs`** — the executable safety claims.

### Key Invariants to Verify in Code

When reading, look for these enforcement points:

- **Parent nullification**: In `voter/actor.rs`, search for where `parent` context is checked before sending notarize votes.
- **Single-shot verification**: In `lib.rs`, the doc comment on `verify` explains the single-shot property. In `actor.rs`, look for how the oneshot channel is used.
- **Quorum assembly**: In `batcher/round.rs`, `ordered_broadcast/ack_manager.rs`, and
  `aggregation/engine.rs`, look for where quorum-sized signer sets turn into certificates.
- **Domain separation**: In `scheme/mod.rs`, look for the suffix constants and how they are used in `Namespace::derive`.
- **Deterministic election**: In `elector.rs`, the `Elector::elect` trait method has a determinism requirement in its docs. The implementation uses only the round, certificate, and pre-built permutation — no RNG, no clock.
- **Crash boundaries**: In `voter/actor.rs`, `ordered_broadcast/engine.rs`, and
  `aggregation/engine.rs`, look for where `append` and `sync` happen relative to network sends.
- **Executable proof obligations**: In `consensus/fuzz/src/invariants.rs`, read the invariant names
  before reading the fuzz harness. They summarize the intended safety story.

---

## 8. Glossary and Further Reading

### Glossary

**Attributable signature**: A signature that uniquely identifies the signer. With an attributable scheme, any party can verify that a specific validator signed a specific message.

**Certificate**: A quorum of signatures (or a threshold signature) over a common subject, proving that `>2N/3` validators have voted on the same value.

**Domain separation**: The technique of deriving distinct namespaces for different purposes so that a signature/primitive created for one purpose cannot be used for another. In simplex, `_NOTARIZE`, `_NULLIFY`, `_FINALIZE` provide domain separation.

**Epoch**: A period of time during which the validator set is fixed. Epochs increment on reconfiguration.

**Finalization**: The point at which a block is considered committed. After finalization, the block cannot be reverted without a coordinated chain reorg.

**Leader election**: The process of selecting which validator proposes the next block. In `RoundRobin`, this is deterministic. In `Random`, this uses VRF-derived randomness.

**N3f1 quorum**: The quorum size `N - N/3` (ceiling), which ensures overlap with any other quorum of the same size in a network with `N/3` Byzantine participants.

**Notarization**: A vote by a validator that a proposal is valid. A notarization certificate proves that `>2N/3` validators have verified and accepted the proposal.

**Nullification**: A vote to skip a view. Nullification certificates allow the next leader to safely skip a view without risking a fork.

**Simplex**: The three-phase (notarize → nullify → finalize) consensus protocol in `commonware-consensus`.

**Threshold signature**: A signature produced by combining partial signatures from multiple participants. The combined signature does not reveal which individual participants signed.

**View**: A single consensus round within an epoch, identified by `(epoch, view_number)`. Each view has a designated leader.

**VRF (Verifiable Random Function)**: A function that produces a pseudorandom output that can be verified by anyone given a public key. In `Random` leader election, VRF outputs determine the leader.

### Further Reading

- **PBFT**: Castro and Liskov, "Practical Byzantine Fault Tolerance" (1999) — the foundational BFT protocol. Simplex can be understood as a refinement of PBFT's insight (using quorum certificates as first-class objects) with a three-phase structure.
- **HotStuff**: Yin et al., "HotStuff: BFT Consensus with Linearity and Responsiveness" (2019) — introduces the view-based approach to BFT that simplex follows. HotStuff shows how to reduce message complexity to `O(N)` and achieve responsiveness.
- **The ABCD of BFT**: This codebase's own technical writing in `docs/blogs/` provides deep dives into the design rationale.
- **commonware-runtime**: The deterministic runtime (`runtime/src/deterministic.rs`) is what makes consensus testing tractable. Understanding it clarifies why all consensus code is async but testable.
- **commonware-cryptography**: The `certificate` module (`cryptography/src/certificate/`) implements the scheme abstraction. Understanding how `Attestation`, `Subject`, and `Namespace` compose will clarify the scheme layer.

---

## Open Questions For Interactive UI

This section identifies what the future interactive book site should animate, make explorable, or allow readers to verify interactively.

### V1: Simplex Three-Phase State Machine

**What to build**: An animated finite state machine showing transitions: `Propose → Notarize → Nullify → Finalize`. The reader selects a scenario:

- **(a) Normal path**: Leader proposes, `>2N/3` validators notarize, certification passes, `>2N/3` validators finalize.
- **(b) Leader failure**: Leader fails to propose or proposes invalid block. Validators accumulate nullify votes, timeout triggers view change.
- **(c) Competing proposals**: Two valid proposals at the same view. One gathers a quorum of notarizes; the other times out. View change advances to the next leader.

**What to show**: At each step, display the set of votes per phase as they accumulate. Show the quorum threshold line. When the threshold is crossed, animate the certificate formation. When timeout fires, animate the transition to the next view.

**Why this matters**: The phase gating is the core insight. Students often confuse "quorum reached" with "all votes collected." The threshold line makes the `N3f1 > 2N/3` requirement visual and concrete.

### V2: Leader Election Comparer

**What to build**: Side-by-side visualization of `RoundRobin` vs `Random` elector behavior over 50 rounds. For `Random`, show the VRF seed derivation chain: certificate → seed signature → leader index. Show how view 1 falls back to round-robin (no certificate available).

**What to show**: The permutation table for `RoundRobin`. For `Random`, show the certificate being fed into the VRF, and the resulting leader. Allow the reader to click "Advance 10 views" and watch the leader sequence differ.

**Why this matters**: Leader election is subtle. `Random`'s VRF dependency on prior certificates means view 1 must fall back to round-robin. The fallback is intentional — without a prior certificate, there's no seed for the VRF. Visualization clarifies this dependency chain.

### V3: VoteTracker Live View

**What to build**: Real-time accumulation of `Notarize`, `Nullify`, `Finalize` votes as they arrive. Per participant, show their vote status (none, voted, quorum reached). Display the quorum threshold as a horizontal line. Color-code the vote bars: attributable schemes show per-signer attribution; threshold schemes show aggregate only.

**What to show**: The moment a quorum forms. The exact count when `len >= N3f1::quorum(N)`. What happens when a duplicate vote arrives (AttributableMap insert returns false, bar stays the same).

**Why this matters**: Students often confuse "quorum reached" with "all votes collected." The threshold line makes the `N3f1 > 2N/3` requirement visual. The duplicate-vote behavior shows the one-vote-per-phase enforcement.

### V4: Ordered Broadcast Chain Explorer

**What to build**: A scrollable sequencer chain (nodes = chunks + certs) with validator signature collection. Display the parent certificate linking each node to the previous. Simulate epoch transition: when the epoch changes, show the validator set change and how it affects quorum calculation.

**What to show**: The chaining mechanism: each chunk certifies the previous. Simulate a fork: the
same sequencer broadcasts two chunks at height `h`. Show how `tip_manager` and `ack_manager`
diverge, how `ChunkMismatch` appears, and why the journal sync boundary is what keeps an honest
validator from acknowledging both sides.

**Why this matters**: The chaining mechanism is the key insight: each chunk certifies the previous, so an honest sequencer's misbehavior is detectable and attributable. The fork visualization makes the attributable fault detection concrete.

### V5: Marshal Block Ordering Timeline

**What to build**: A timeline of blocks flowing from broadcast → simplex (notarizations/finalizations) → marshal actor → application. Show where delays and gaps can occur. Simulate the backfill trigger: finalization for height `h` arrives, but block `h-1` is missing. Show the backfill request and the gap resolution.

**What to show**: The difference between standard and coding mode. In coding mode, show shards arriving from different peers and reconstruction before finalization. Show the floor/starting height: how Marshal ignores blocks below a configurable height.

**Why this matters**: Marshal is the bridge between consensus and application. It is where the ordered delivery guarantee is enforced and where gaps are handled. Visualization shows exactly where delays, gaps, and reorgs can occur — and how the system recovers.

### V6: Domain Separation Visualizer

**What to build**: Show how a signature over a proposal digest gets different bytes under different namespaces. Display the base namespace, the suffix (`_NOTARIZE`, `_NULLIFY`, `_FINALIZE`), and the resulting derived namespace. Show that a signature made under `_NOTARIZE` fails verification under `_FINALIZE`.

**What to show**: The exact bytes that get signed in each case. How the namespace is prepended. Why cross-protocol replay is impossible.

**Why this matters**: Domain separation is a cryptographic discipline that prevents entire classes of attacks. Making the byte-level derivation visible demystifies it.

### V7: Parent Nullification Checker

**What to build**: Given a scenario with gaps in the chain, show which views are missing nullifications. Display the validator's known certified view, the proposed block's parent view, and the gap. Show which votes are blocked pending parent nullification.

**What to show**: The exact check that happens in the voter actor: `if parent_view < latest_certified_view`. Which intermediate views need nullifications. How the check prevents the fork-safety attack.

**Why this matters**: Parent nullification is the most subtle invariant in simplex. A visual check mechanism makes it concrete rather than abstract.
