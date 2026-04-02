# commonware-coding

*A Lecture on Recoverability, Commitments, and Agreement Under Partial Information*

---

## Opening Apparatus

**Promise.** This chapter shows how coding lets a distributed system recover a
payload, bind shards to one object, and preserve agreement while every node
still sees only fragments.

**Crux.** Partial information is the normal case in an adversarial network, so
the protocol has to turn fragments into evidence instead of pretending they are
already the payload.

**Primary invariant.** A checked shard must point to one encoded object under
one commitment, and honest nodes must not diverge about that object.

**Naive failure.** The naive story is "split the block, send pieces around, and
recover later." That fails because raw fragments do not tell honest nodes
whether they belong to the same valid encoding story.

**Reading map.**

- `coding/src/lib.rs`: the traits and invariants.
- `coding/src/reed_solomon.rs`: threshold recovery.
- `coding/src/zoda/mod.rs`: phased checking and validating checks.
- `coding/src/zoda/topology.rs`: how security becomes dimensions.

**Assumption ledger.**

- The network is adversarial.
- Encoding must be deterministic.
- "Checked" means the shard has already crossed the protocol's validation bar.

With that map in hand, the lecture begins where the system actually hurts: at
the moment when no one has the whole picture.

## Backgrounder: Redundancy, Evidence, and Erasure

The broad idea behind coding is simple: if one copy of data is fragile, make the
system hold more than one copy's worth of information. That sounds like plain
replication, but replication is only the first rung on the ladder.

If you send the whole payload to every node, the system becomes easy to reason
about but expensive to run. Network use scales with the number of receivers, and
the sender stays the bottleneck. Classical error-correcting codes do better by
splitting information into pieces with redundancy arranged by algebra rather
than by brute force. A receiver does not need every piece, only enough of the
right ones.

That tradeoff matters because distributed systems do not live in a friendly
world. Nodes fail, links drop packets, and some participants may lie. A fragment
by itself is not proof that it belongs to a valid reconstruction. If the system
only knows "here are some shards," then a malicious sender can mix pieces from
different payloads or force honest nodes to disagree about what they saw.

So the background problem is not just recovery. It is recovery under partial
information.

The classical alternatives each miss something:

- **Replication** is easy but wasteful.
- **Parity checks** can detect some corruption but do not always recover the
  original object.
- **Erasure coding** improves efficiency, but raw shards still need a way to be
  tied to one specific encoded object.

That last point is the important one for adversarial protocols. The system needs
both redundancy and evidence. Redundancy says enough missing pieces can be
repaired. Evidence says the pieces all belong to the same story.

This gives the core tradeoff in the crate:

- more redundancy buys more tolerance for loss and delay,
- more checking buys more confidence before reconstruction,
- and both cost bandwidth, compute, or protocol complexity.

`commonware-coding` lives at that intersection. It is not trying to make shards
magically self-describing. It is teaching the system how to turn redundancy into
something honest nodes can trust.

## 1. What Problem Does This Solve?

A distributed system rarely gets to wait for full information before acting.
That is the setting for `commonware-coding`.

Suppose a leader has a 4 MiB block and fifty validators need it. The naive
plan is simple: send the whole block to every validator. The leader now pushes
200 MiB across the network while everyone else waits, even though the rest of
the system has bandwidth to spare.

Erasure coding fixes that first problem. The leader can turn one payload into
many shards, give a different shard to each validator, and let the validators
help disseminate the block. The sender stops being the only node doing useful
work.

But this crate exists because that is not the whole problem.

Once the payload is split, every participant sees only a fragment. They must
make decisions under partial information. One node sees shards A, B, C.
Another sees A, D, E. Consensus may move forward before either node has the
full payload in hand. So the real question is not only "can we reconstruct the
data later?" It is also "what can we safely believe now?"

That is why `commonware-coding` is about three things at once:

- **recoverability**: enough shards should recover the original payload;
- **commitments**: shards should be tied to one specific encoded object;
- **agreement**: honest nodes should not form incompatible beliefs from
  different subsets of shards.

This is the chapter's governing idea:

> Coding matters in adversarial systems because nodes must agree before any one
> of them has the whole picture.

`commonware-coding` gives the rest of the system a way to reason about that
partial picture without pretending it is already complete.

---

## 2. Mental Model

The right mental model is a **proof-carrying jigsaw**.

The payload is the finished picture. The shards are the puzzle pieces. The
commitment is the picture on the box. A checked shard is not just a loose
piece; it is a piece that carries enough evidence to say, "I belong to this
box, at this position, in this reconstruction story."

That picture does real work.

In an ordinary jigsaw, nobody worries that a malicious participant slipped in a
piece from a different puzzle. In a distributed system, that is exactly the
problem. A sender can fabricate shards. A relay can mix shards from different
payloads. A receiver can see only a subset and still need to decide whether to
vote, relay, or refuse to proceed.

So the proof-carrying jigsaw is trying to answer three questions in order:

1. If enough pieces survive, can I reconstruct the picture?
2. If I am handed a piece, can I tell whether it belongs to the stated box?
3. Before full reconstruction, can I already know that the box describes a
   real puzzle rather than nonsense?

Reed-Solomon and ZODA are both answers inside this mental model, but they are
answers to different systems questions.

Reed-Solomon says: "If enough correctly checked pieces survive, I can recover
the payload."

ZODA says: "Before recovery, while pieces are still moving through the network,
I can already certify something stronger about the validity of what is being
disseminated."

That difference is the heart of the crate. The point is not to compare two
features on a checklist. The point is to see two different moments when a
distributed system asks, "Do I know enough yet?"

---

## 3. The Core Ideas

Read `commonware-coding` from the outside in. The trait guarantees matter more
than the algorithm internals.

### 3.1 Configuration Is the Recoverability Contract

`coding/src/lib.rs`

```rust
pub struct Config {
    pub minimum_shards: NonZeroU16,
    pub extra_shards: NonZeroU16,
}
```

This is the main tradeoff surface of the crate.

`minimum_shards` is the threshold. It tells you how many checked shards must
survive before recovery is possible.

`extra_shards` is the redundancy budget. It tells you how much extra network
and storage cost you pay so that loss, delay, or malicious withholding does not
immediately destroy recoverability.

`Config::total_shards()` is just:

```rust
minimum_shards + extra_shards
```

But the important idea is not the sum. The important idea is that the crate
forces you to separate "how much information must survive" from "how much slack
the system buys."

### 3.2 `Scheme` Turns Shards Into Evidence

The standard interface is `Scheme`.

```rust
pub trait Scheme {
    type Commitment: Digest;
    type Shard;
    type CheckedShard;

    fn encode(...) -> Result<(Self::Commitment, Vec<Self::Shard>), Self::Error>;
    fn check(...) -> Result<Self::CheckedShard, Self::Error>;
    fn decode(...) -> Result<Vec<u8>, Self::Error>;
}
```

The order matters.

`encode` creates a commitment and a shard set.

`check` turns a raw shard into a checked shard. That checked form is the first
big conceptual move in the crate. It says that the system should not treat raw
network material as if it were ready for reconstruction. Evidence travels with
the shard, and the type system makes that visible.

`decode` reconstructs from checked shards only.

The trait documentation then adds the real distributed-systems content.

**Check agreement** means that if two honest nodes accept their own shards,
they should not later disagree about one another's shards under the same
commitment.

**Unique commitments** means `encode` is deterministic. One payload and one
configuration should not produce several commitments that all decode
successfully. The commitment must stay a stable name for "the thing we are
talking about."

**Commitment binding** means checked shards from one commitment must not decode
under another. Without that rule, the system could silently assemble a picture
from pieces taken from different boxes.

### 3.3 `PhasedScheme` Separates Local Knowledge From Forwarded Knowledge

Some coding schemes answer a harder question than plain recoverability. They
care about what a node can know after receiving its own shard but before
reconstruction.

That is why `PhasedScheme` exists.

```rust
pub trait PhasedScheme {
    type StrongShard;
    type WeakShard;
    type CheckingData;
    type CheckedShard;

    fn encode(...) -> Result<(Commitment, Vec<StrongShard>), Error>;
    fn weaken(...) -> Result<(CheckingData, CheckedShard, WeakShard), Error>;
    fn check(...) -> Result<CheckedShard, Error>;
    fn decode(...) -> Result<Vec<u8>, Error>;
}
```

The vocabulary is deliberate.

A **strong shard** is what the encoder sends first. It carries enough material
for the receiver to do local work.

`weaken` says: from that stronger object, the receiver can derive the checking
data it needs, confirm its own shard, and produce a **weak shard** suitable for
forwarding.

Other participants can then use the checking data plus the weak shard to decide
whether the forwarded piece fits the same valid story.

This is not ornamentation. It captures a common systems fact: first recipients
often know more than relays, and the protocol should say what proof survives
that transition.

### 3.4 `ValidatingScheme` Marks the Stronger Promise

`ValidatingScheme` is a small trait with a large meaning.

It marks schemes where a successful `check` proves more than shard inclusion.
It proves that the shard came from a valid encoding of some underlying payload.

That is the conceptual leap from ordinary commitment-bound coding to ZODA. The
system does not merely learn "this piece belongs to that box." It learns that
the box itself came from a valid encoding story.

### 3.5 The Trait Ladder Is Really a Guarantee Ladder

At first glance, the crate seems to offer several overlapping abstractions:
`Scheme`, `PhasedScheme`, `ValidatingScheme`, and the adapter
`PhasedAsScheme<P>`. Read them as a ladder of increasingly strong statements
about what the rest of the system may conclude.

`Scheme` gives the baseline distributed-systems contract:

- the encoder deterministically names one encoded object with one commitment;
- `check` filters raw network material into checked evidence;
- `decode` converges on one payload, or fails.

`PhasedScheme` adds a timing claim:

- the first receiver can learn more than later relays;
- that extra local knowledge can be distilled into `CheckingData`;
- later weak shards can then be judged against the same story before full
  reconstruction.

`ValidatingScheme` adds the strongest semantic claim:

- a successful check means not just "membership under this commitment,"
- but "membership in a valid encoding story under this commitment."

Finally, `PhasedAsScheme<P>` shows how these layers relate. The adapter turns a
phased scheme back into a plain `Scheme` by calling `weaken` inside `check`,
storing the resulting `CheckingData`, and then requiring all adapted checked
shards to agree on that checking data during `decode`.

That is useful for tests and generic code, but it also teaches a conceptual
lesson. If you flatten a phased scheme back into `Scheme`, you keep its
decode-time safety properties and lose the operational advantage of
weak-shard forwarding. The type system is telling you when certainty appears.

---

## 4. How the System Moves

The crate becomes clear once you follow the data in time.

### 4.1 The Standard Story: Encode, Check, Recover

For a plain `Scheme`, the motion is:

```text
payload
  -> encode
  -> commitment + raw shards
  -> check each shard against the commitment
  -> gather enough checked shards
  -> decode
  -> payload
```

That sequence says something important about trust.

The network first learns a commitment. Then each participant tests the shard it
received against that commitment. Only after enough checked shards accumulate
does anyone try to reconstruct the payload.

Reed-Solomon follows that path in a direct way, but the directness can hide how
much safety work the implementation is doing.

The encode path in `coding/src/reed_solomon.rs` is not merely "run an erasure
coder." It first forces the payload into one canonical byte layout:

1. prefix the payload with its original length;
2. split the prefixed bytes into `k = minimum_shards` equal-sized shards;
3. round the shard length up to an even number, because the SIMD backend wants
   that regularity;
4. fill all remaining tail bytes with zero padding.

That preparation step is the first agreement mechanism in the file. A leader is
not allowed to choose several different byte layouts that all decode to the same
high-level payload. The layout has to be canonical before coding even begins.

Then the implementation does the obvious Reed-Solomon work:

5. produce `m = extra_shards` recovery shards with cached encoders;
6. hash every original and recovery shard;
7. build one BMT root over the whole shard family;
8. package each outgoing shard as `Chunk { shard, index, proof }`.

The important shift happens at `check`. A raw `Chunk` is still only a proposal:
"here is some shard data, and here is a Merkle proof that claims it belongs at
index `i`." `Chunk::verify` turns that proposal into a `CheckedChunk` only if
three things line up together:

- the caller's expected index matches the embedded shard index;
- the Merkle proof actually proves inclusion under the stated root;
- the verifier records the root and the shard digest inside the checked value.

That last point matters. `CheckedChunk` does not merely say "proof passed once."
It carries the root it was checked against so that `decode` can reject
cross-commitment mixing later.

So the real Reed-Solomon timeline in Commonware is this:

```text
payload
  -> canonical byte layout
  -> original shards + recovery shards
  -> BMT root
  -> checked chunks
  -> RS decode
  -> canonical re-encode
  -> rebuilt BMT root
  -> payload
```

The striking step is the one near the end. `decode` does not trust recovery
just because the Reed-Solomon engine produced bytes. It:

- rejects empty input and too-few chunks;
- rejects invalid indices and duplicate indices;
- rejects checked chunks whose remembered root differs from the decode-time
  commitment;
- reconstructs missing originals;
- re-encodes those originals to regenerate the recovery shards;
- rebuilds the Merkle tree over the full shard family;
- and only then accepts the root as consistent.

That means decode is not only a recovery routine. It is a *canonicality audit*.
The code is asking whether reconstructing the object and re-encoding it
produces the same commitment story.

Only after that does `extract_data` strip the 4-byte length prefix and verify
that every tail byte after the declared payload length is zero. That final zero
padding check is why the crate can reject non-canonical shard families that
would otherwise decode to the same visible bytes. The agreement guarantee is
not merely "we all got back something parseable." It is "we all got back the
unique payload compatible with one canonical encoding under this commitment."

### 4.2 The Phased Story: Validate Earlier, Forward Less

For a `PhasedScheme`, the motion is richer:

```text
payload
  -> encode
  -> commitment + strong shards
  -> weaken(my strong shard)
  -> checking data + checked self shard + weak shard
  -> receive weak shards from others
  -> check those weak shards
  -> gather enough checked shards
  -> decode
```

The key shift is when knowledge becomes available.

In the standard story, the system's strongest statement often arrives at
decode-time: "now we have enough to reconstruct."

In the phased story, a node can say something useful earlier. After handling
its own strong shard, it has checking data that lets it evaluate incoming weak
shards before full reconstruction.

This is why `StrongShard`, `WeakShard`, and `CheckingData` deserve their own
types. They are not implementation clutter. They are the stages in which local
certainty changes.

ZODA's encode path makes that visible in code.

First, the payload is interpreted as field elements and arranged into a matrix.
Then that matrix is Reed-Solomon encoded row-wise into a larger matrix with
`encoded_rows`. Each encoded row is hashed, and those row hashes are committed
with a BMT root.

At that point the implementation creates the actual commitment. It does not
commit directly to the payload bytes. It starts a transcript, commits the
original byte length and the row-commitment root, and summarizes that
transcript. That summary becomes the stable commitment to "this encoded object
of this byte length."

Only then does the code derive the extra machinery that makes ZODA special:

- a checking matrix from transcript-derived noise,
- a checksum matrix `Z = XH` over the original data matrix,
- and a transcript-driven shuffle of encoded row indices.

That ordering is not decorative. The checksum is itself committed back into the
transcript before row sampling is finalized. The chapter should linger on that
point because it closes a real attack surface: followers must not be tricked
into validating different local challenge stories against the same outward
commitment.

Each `StrongShard` then contains:

- the original byte length,
- the row-commitment root,
- a multi-proof for the sampled encoded rows,
- the sampled rows themselves,
- and the shared checksum matrix.

The strong shard is therefore a first-recipient artifact. It carries enough
material for the owner to reconstruct the local checking context.

`weaken` is the crucial pivot. Given your own strong shard, it:

1. strips the shard down to a `WeakShard` containing only rows plus proof;
2. reconstructs `CheckingData` from the commitment, byte length, root, and
   checksum;
3. immediately self-checks the weak shard against that checking data.

So `weaken` is not "compress and forward." It is "derive the local proof system
that all later forwarded evidence must satisfy."

`CheckingData::check` then performs the actual early-validity test:

- it re-derives the topology from the commitment story;
- re-derives the checking matrix and shuffled row indices from the transcript;
- verifies that the shard's rows are included in the committed row set at the
  right sampled positions;
- computes the shard's local checksum image `X'_S H`;
- compares it against the corresponding rows of the encoded checksum matrix.

That last comparison is the heart of ZODA. The shard is not only being asked,
"do you belong to the announced row commitment?" It is being asked, "are you
consistent with the checksum relation that a valid encoding would induce?"

The decode path then turns that early evidence back into recovery. It fills an
evaluation vector at the shuffled row positions, counts how many distinct rows
were actually supplied, recovers the coefficient form, and truncates back to
the original `data_bytes`.

This is why the trait split matters so much. A plain scheme postpones its
strongest statement until reconstruction. A validating phased scheme says much
more as soon as the first honest recipient has successfully weakened its own
shard.

### 4.3 Topology Is Part of the Argument

ZODA introduces `Topology` to decide:

- how many rows the encoded matrix has,
- how many samples each shard carries,
- how many column samples are needed,
- and how the implementation reaches its security target.

That can sound like sizing logic. It is proof layout.

`Topology::reckon` is where a verbal security target turns into numbers the
code can enforce. It chooses:

- how many data columns the unencoded matrix should have;
- how many rows the payload therefore occupies;
- how many samples each shard must carry;
- how many encoded rows are needed after redundancy and power-of-two padding;
- and how many checksum columns are required to reach the target security.

The function optimizes within proof constraints, not just within performance
constraints. It tries to increase the number of columns because ZODA is more
efficient with wider matrices, but it only accepts a candidate shape if the
required sample count still fits inside the encoded row budget.

Two details are especially worth teaching.

First, the encoded row count is rounded up to a power of two. That is partly a
technical convenience for the math machinery, but it also changes the sampling
space against which the security calculation is made.

Second, checksum columns are doubled in effect because the code is simulating a
larger extension field using pairs of base-field columns. So topology is not
just deciding geometry. It is deciding how much evidence an honest node gets
per shard about the claim that the leader really encoded one coherent payload.

That is why the chapter should treat topology as part of the proof, not an
appendix. In ZODA, matrix shape is a security statement.

---

## 5. Two Systems Questions, Two Answers

Now we can say cleanly what Reed-Solomon and ZODA each contribute.

The wrong comparison is "simple scheme versus advanced scheme." The right
comparison is "what statement can the rest of the distributed system safely
make at each stage?"

| Stage | Reed-Solomon | ZODA |
| --- | --- | --- |
| After one shard is checked | "This shard belongs at this index under this commitment." | "This shard belongs under this commitment and is consistent with a valid encoding story." |
| During forwarding | Relays mostly move commitment-bound pieces. | First recipients can derive checking data, then forward weaker shards without losing the proof story. |
| At threshold | Enough checked chunks can reconstruct one canonical payload. | Enough checked shards can reconstruct one payload, and the system already had stronger local validity evidence earlier. |
| Main uncertainty window | Between first checks and final decode. | Narrower, because the validity relation is already being checked before decode. |

### 5.1 Reed-Solomon Answers the Recoverability Question

Reed-Solomon is the right answer when the system's first question is:

> If enough honest pieces survive, can everyone recover the same payload later?

That is the recoverability question.

The scheme spreads the data across more shards than are strictly necessary and
lets any threshold-sized subset rebuild the original payload. Add a commitment
and inclusion proofs, and each receiver can reject shards that do not belong to
the advertised encoded object.

This is already a strong distributed-systems story. It gives the network a
stable commitment, a way to check shard membership, and a deterministic decode
path that converges by canonical re-encoding and root reconstruction.

But notice when the strongest knowledge appears. Reed-Solomon is most natural
when the system can afford to say, "We will know the final answer once enough
checked shards arrive and we reconstruct."

That is not a weakness. It is a choice about where certainty becomes available.

### 5.2 ZODA Answers the Early-Agreement Question

ZODA becomes interesting when the system's question changes:

> Before reconstruction, while shards are still moving, can a node already know
> that the dissemination is not arbitrary nonsense?

That is the early-agreement question.

If a malicious leader invents Reed-Solomon-looking shards and commits to them,
honest nodes may spend time relaying and collecting before the fraud becomes
obvious. The problem is not that recovery fails in the end. The problem is that
the system had to operate under ambiguity for too long.

ZODA shortens that ambiguous period. A checked shard does not merely say that it
matches the commitment. It says it comes from a valid encoding story. That is
why `ValidatingScheme` is the real climax of the crate.

So the contrast between the two schemes is not "basic versus advanced" or
"faster versus safer." The better contrast is:

- Reed-Solomon is for systems that need strong recoverability once enough
  evidence accumulates.
- ZODA is for systems that need useful agreement guarantees earlier, while
  evidence is still partial and the protocol may already be moving.

Both live inside the proof-carrying jigsaw. They simply answer different
questions about when a node has enough proof to act.

### 5.3 Why `PhasedAsScheme` Is a Useful but Instructive Compromise

The adapter deserves one more note because it shows how these schemes fit into a
larger codebase.

If some higher layer wants a uniform `Scheme` interface, `PhasedAsScheme<Zoda>`
lets ZODA participate without rewriting every caller. But the adapter also
proves a conceptual point: if the caller insists on the plain scheme interface,
the phased system must stash checking data inside the checked shard and then
verify consistency at decode time.

That works, and it is correct, but it is no longer the full distributed-systems
story ZODA was built to tell. The adapter keeps the safety theorem while hiding
the operational theorem about when certainty becomes available.

---

## 6. What Pressure It Is Designed To Absorb

`commonware-coding` lives where bandwidth pressure and trust pressure meet.

### 6.1 It Spreads Transmission Work Across the Network

Coding exists because the leader should not be the only node paying the full
dissemination cost. By making the payload recoverable from a subset of shards,
the crate lets the rest of the network help carry the block.

### 6.2 It Makes Partial Information Explicit

The crate never pretends that seeing one shard is equivalent to seeing the
payload. Instead it names the intermediate states: raw shard, checked shard,
strong shard, weak shard, checking data. That vocabulary is how the rest of the
system avoids over-claiming what it knows.

### 6.3 It Protects Agreement, Not Just Local Success

The dangerous outcome is not merely "my node failed to decode." The dangerous
outcome is "two honest nodes each accepted what they saw, but those local views
cannot be reconciled into one global payload."

That is why check agreement and commitment binding sit at the center of the
crate's contract. They are what keep partial information from turning into
divergent belief.

### 6.4 It Leaves Parallelism as Policy

The hot paths take a `commonware_parallel::Strategy`. That matters because
parallelism affects throughput, but it should not blur the algorithmic story.
The same coding guarantees can run with different execution policies depending
on the surrounding runtime.

### 6.5 It Makes Canonicality Part of the Safety Budget

An adversarial system cannot afford to say, "all these byte layouts decode to
equivalent application data, so any of them is fine." That attitude creates
room for split commitments, replay confusion, and cross-node disagreement about
what exactly was disseminated.

Commonware's coding crate is stricter. Reed-Solomon requires one canonical
length-prefix-and-zero-padding layout, and decode re-derives the full shard
family to confirm that the commitment is the unique one compatible with the
recovered payload. ZODA similarly refuses to separate its validation story from
the transcript, checksum, and sampling story that produced the commitment.

In other words, canonicality is not polish. It is the difference between
"recover something" and "recover the one object consensus thought it was
talking about."

### 6.6 The Tests Act Like Executable Proof Obligations

This crate is unusually readable if you treat its tests as the theorem checklist
for the public traits.

`coding/src/lib.rs` asks the broad contract questions:

- can different threshold-sized subsets round-trip to the same payload?
- do mixed commitments get rejected?
- does decode reject an empty checked-shard set?
- do phased checks reject weak shards derived from a different commitment?

`coding/src/reed_solomon.rs` then nails down the concrete canonicality story:

- duplicate indices must be rejected;
- tampered checked chunks must fail;
- mismatched config and proof shape must fail;
- non-canonical shard families that happen to decode must still be rejected.

`coding/src/zoda/mod.rs` does the same for early-validity claims:

- duplicate checked-shard indices should reduce to insufficient unique rows;
- checksum malleability attempts should fail after challenge binding;
- decode must reject checked shards whose commitment story no longer matches.

Those tests matter because the higher-level protocol will not re-prove these
facts every time it uses the crate. It assumes the coding layer has already
made them true.

---

## 7. Failure Modes and Limits

This is the shadow of the design.

### 7.1 Missing Information Still Matters

If fewer than `minimum_shards` checked shards are available, decode must fail.
No commitment scheme can manufacture missing information out of nothing.

### 7.2 Commitments Prevent Some Confusion, Not All Delay

Reed-Solomon checks can reject the wrong index, the wrong proof, duplicate
indices, and shards mixed across commitments. Those are important failures to
catch, because they are exactly what adversarial senders and sloppy integration
layers produce.

But catching membership does not automatically give early certainty about the
validity of the whole encoding. That is the line Reed-Solomon stops at.

### 7.3 Plain Recoverability Is Not Early Validity

This is the central limit of the simpler story. A malicious sender can choose
an arbitrary family of encoded-looking shards and a matching commitment.
Nothing forces honest nodes to learn immediately that the larger encoding story
is bad. They may only discover that later, when reconstruction or deeper
cross-checking begins.

That is not an implementation bug. It is the systems reason for having ZODA.

### 7.4 Stronger Guarantees Need More Structure

ZODA buys earlier certainty by carrying more machinery: strong shards, weak
shards, checking data, sampled rows, checksum columns, topology sizing. The
crate is explicit about that price. Earlier agreement is possible, but it is
not free.

### 7.5 Determinism Is Part of the Safety Story

If encoding were nondeterministic, one payload could admit several commitments.
Then the commitment would stop being a stable handle for consensus and
dissemination. Determinism is therefore not a cosmetic implementation choice.
It is part of what lets the wider system coordinate on one object while seeing
only fragments of it.

### 7.6 Even Valid Coding Does Not Remove All Higher-Level Risks

This chapter has intentionally treated the coding layer as a truth-preserving
subsystem. But it is still only one layer.

Coding does not decide:

- whether the payload should have been proposed at all;
- whether the sender is authorized;
- whether the recovered payload is semantically acceptable to the application;
- or whether the network collected shards quickly enough for liveness goals.

So the crate's guarantees are powerful, but they are also scoped. It protects
the statement "these fragments describe one coherent encoded object" far better
than it protects the larger statement "this object should become part of the
system's history." Higher layers still have to make that second judgment.

---

## 8. How to Read the Source, Glossary, and Further Reading

Do not start with the algebra. Start with the promises, then read the concrete
scheme, then read the stronger scheme.

### Reading Order

1. **`coding/src/lib.rs`**  
   Read `Config`, `Scheme`, `PhasedScheme`, and `ValidatingScheme`. This file
   names the invariants the rest of the crate must preserve.

2. **`coding/src/reed_solomon.rs`**  
   Read this next to see the cleanest full story of encode, commitment, check,
   and decode.

3. **`coding/src/zoda/mod.rs`**  
   Read this when you want to see how the crate moves from recoverability to
   earlier validity guarantees.

4. **`coding/src/zoda/topology.rs`**  
   Read this after the main ZODA flow is clear. It explains how security goals
   become concrete sample counts and matrix dimensions.

5. **Blog context**  
   Read `docs/blogs/coding.html` and `docs/blogs/zoda.md` for the surrounding
   systems motivation: leader bottlenecks, delayed reconstruction, and why
   earlier guarantees matter to higher-level protocols.

### What to Watch For

- where the crate distinguishes raw shards from checked shards;
- where commitments become the stable name of the encoded object;
- where decode enforces commitment binding;
- where ZODA upgrades the meaning of a successful check;
- and where matrix sizing becomes part of the proof story rather than a pure
  performance detail.

### Glossary

**Commitment**  
A digest that names one encoded object and anchors later shard checks.

**Checked shard**  
A shard that has already been validated against the right commitment and index.

**Check agreement**  
The guarantee that honest nodes who accept their own shards will also agree on
one another's shards under the same commitment.

**Commitment binding**  
The rule that checked shards from one commitment must not decode under another.

**`minimum_shards`**  
How many checked shards must survive before recovery is possible.

**`extra_shards`**  
How much redundancy the system buys beyond the minimum threshold.

**Strong shard**  
The richer shard form first sent by a phased scheme.

**Weak shard**  
The forwarded shard form checked later by other participants.

**Checking data**  
Auxiliary material derived from a strong shard that lets later participants
validate weak shards.

**Validating scheme**  
A scheme where a successful check proves valid encoding, not merely shard
membership.

### Further Reading

- `coding/src/lib.rs`
- `coding/src/reed_solomon.rs`
- `coding/src/zoda/mod.rs`
- `coding/src/zoda/topology.rs`
- [docs/blogs/coding.html](/home/r/coding/monorepo/docs/blogs/coding.html)
- [docs/blogs/zoda.md](/home/r/coding/monorepo/docs/blogs/zoda.md)
