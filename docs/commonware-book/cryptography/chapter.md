# commonware-cryptography

*How distributed systems manufacture evidence: identities, commitments,
certificates, and shared keys.*

---

## 0. Chapter Contract

`commonware-cryptography` is the part of the library that turns cryptographic
work into evidence the rest of the stack can trust.

The promise of this chapter is to show how identities, transcripts,
certificates, handshakes, and DKG all answer the same question: what fact is
the system allowed to trust now?

The crux is that a primitive only matters here when it preserves meaning
across protocol stages, peers, and later verification.

The primary invariant is that no signature, digest, certificate, or shared key
may be interpreted without the namespace, transcript state, and committee
context that made it valid.

The naive failure is to hash or sign raw bytes in isolation, then assume the
same bytes mean the same thing everywhere. That is how replay, ambiguity, and
blame confusion enter a protocol.

**Reading map**

- `cryptography/src/lib.rs` for the vocabulary of signers, verifiers, digests,
  and commitments
- `cryptography/src/transcript.rs` for context binding and domain separation
- `cryptography/src/certificate.rs` and the BLS certificate modules for
  attributable and threshold evidence
- `cryptography/src/secret.rs` for custody discipline around private material
- `cryptography/src/secp256r1/recoverable.rs` for signatures that can recover
  the signer key from the signature itself
- `cryptography/src/bls12381/tle.rs` for delayed evidence release through
  timelock encryption
- `cryptography/src/handshake.rs` for evidence turned into a live authenticated
  channel
- `cryptography/src/bls12381/dkg.rs` for stable public identity under changing
  private custody

**Assumption ledger**

- Adversary: active network peers, replay, stale evidence, and dishonest
  committee members
- Trusted boundary: transcript construction, namespace binding, certificate
  formation, and handshake state
- Invariant: every proof stays tied to the exact protocol meaning that created
  it
- Guarantee edge: the crate can reject misbound or stale evidence and preserve
  evidence semantics, but it cannot infer the caller's intent or repair a wrong
  protocol design

Read the chapter in that order and keep the contract in view. The tone should
stay lecture-like: start from doubt, build a mental model, and only then name
the mechanisms that resolve it.

---

## 1. Background: Cryptography as Checkable Evidence

Before the library-specific machinery matters, it helps to name the broad
problem cryptography solves in a distributed system: it turns private acts into
publicly checkable evidence.

At the code level, the basic vocabulary is already explicit:

- `Signer::sign(namespace, msg)` binds a signature to a namespace and message.
- `Verifier::verify(namespace, msg, sig)` checks that same binding later.
- `Transcript::commit`, `append`, `fork`, `resume`, and `summarize` build the
  context that gives those bytes meaning.
- `Digestible` and `Committable` separate "one unique digest" from "the
  commitment this larger protocol needs."

That separation is not decorative. The code in `transcript.rs` proves the
point. `Transcript::new` starts from a namespace, `commit` flushes byte
boundaries into the state, and `append` lets the caller keep building one
message without accidentally changing the meaning of earlier bytes.

The temptation is to treat these tools as independent tricks. They are not.
They solve the same deeper problem: how do we make a claim that survives being
checked later, in a different process, by someone who was not present when the
claim was made?

That is why naive approaches fail so often.

- Signing raw bytes without a namespace makes the same signature mean too many
  things.
- Hashing data without saying what the digest represents leaves room for
  replay and substitution.
- Using the same key or transcript for unrelated protocol steps makes evidence
  portable in the wrong way.
- Assuming "a quorum signed this" is the same as "a quorum agreed on the same
  meaning" confuses compression with correctness.

Keep that picture in mind: the rest of the chapter is not a tour of isolated
primitives. It is a study of how evidence stays meaningful as it moves through a
distributed protocol.

---

## 2. What Problem Does This Solve?

A distributed system does not wake up wanting elliptic curves. It wakes up with
doubt.

- Who exactly sent this message?
- What did they believe they were signing?
- Is this evidence local to one protocol step, or can I carry it to a third
  party?
- Did one node act, or did a committee act?
- Can the committee keep the same public identity while the private holders
  behind it change?

`commonware-cryptography` exists to answer those questions.

That is the first mental shift to make before reading the crate. The crate is
not mainly about computation. It is about evidence.

Computation turns bytes into other bytes. Evidence turns an event into a fact
that other components can rely on.

Sometimes the evidence is simple:

- a public key that names a participant,
- a signature that ties that participant to a statement,
- a digest that commits to a value.

Sometimes the evidence is collective:

- a certificate that says a quorum endorsed the same subject,
- a threshold signature that compresses committee agreement into one proof,
- a public polynomial that tells the world what key a committee is jointly
  holding.

Sometimes the evidence is procedural:

- a transcript that records what context was bound before signing or deriving
  randomness,
- a handshake that proves two peers landed in the same conversation,
- a resharing protocol that preserves a committee's public identity across
  membership change.

The crate is therefore best read as a sequence of evidence transforms. Raw
inputs enter, a protocol binds meaning to them, and the output becomes a fact
that another component may trust later.

---

## 3. The Basic Contract: Who, What, and In What Context?

Before the crate becomes sophisticated, it establishes a common language in
`cryptography/src/lib.rs`.

That language separates three concerns that systems often blur together:

1. who acted
2. what was being referred to
3. what context gave that act its meaning

The first concern appears in the familiar traits:

- `Signer`
- `Verifier`
- `PublicKey`
- `Signature`

The second appears in:

- `Digest`
- `Digestible`
- `Committable`

The third concern, context, is enforced more strongly in the transcript layer,
but you can already see it here through namespaces and domain separation.

This separation is not academic. It prevents one of the oldest mistakes in
systems cryptography: treating a signature as if it were self-explanatory.

A signature does not mean "this byte string is true." It means something much
narrower:

> this signer endorsed this subject in this namespace under this protocol
> interpretation.

Take away the namespace and the meaning may change. Take away the committed
structure of the subject and the meaning may change. Take away the signer and
you no longer know whose action you are depending on.

### 3.1 Identities Are More Than Verification Keys

At first glance, a public key looks like a purely technical object: the thing
you need in order to verify a signature. In a distributed system it does more
work than that. It is often the name by which the rest of the protocol knows a
participant.

That is why identity matters even when the system later adopts committee-level
signing or threshold mechanisms. Nodes still need something stable to dial,
order, authenticate, block, or blame.

The code reflects that in the certificate and DKG layers. `Scheme::me()`
lets a signing scheme know whether it owns one participant position. `participants()`
keeps the ordered public identity set around. `Provider::scoped()` and
`Provider::all()` decide whether a scheme is tied to a specific round or can
verify across rounds because the public identity is stable.

### 3.2 Commitments Are Facts With Boundaries

A digest is also easy to underestimate. We casually say "hash the data," as if
the point were compression. But the real value is not that the digest is short.
The value is that it turns a structured object into a stable fact.

That is why the crate distinguishes `Digestible` from `Committable`.

- `Digestible` says an object has one unique digest.
- `Committable` says an object can provide the commitment a larger protocol
  needs, even when that commitment is not just "hash these raw bytes."

The warning on `Committable` is not ornamental. It states that two objects with
the same digest must not map to different commitments. That keeps digest
equality aligned with higher-level protocol meaning.

### 3.3 Identity Keys and Signing Keys Can Differ

One of the most useful choices in the crate is that identity keys do not have to
be the same as signing keys.

If you are used to small examples, that can seem unnecessarily flexible. Why
not let one key do everything?

Because real systems usually want two different properties:

- a stable identity that says who a participant is inside the protocol,
- and a signing mechanism optimized for the evidence the protocol wants to
  export.

Those are sometimes the same thing. Sometimes they are not. A committee may
want one long-lived public identity for coordination while using a separate
certificate scheme to prove quorum support. Once threshold systems and resharing
enter the story, forcing those roles to collapse would only hide the real
design.

### 3.4 Scheme Matrix: Pick the Product, Not the Brand Name

At this point it helps to stop thinking in terms of "supported curves" and
start thinking in terms of evidence products. The crate ships several schemes,
but they are not interchangeable. Each one answers a slightly different trust
question.

| Module | Evidence product | Attributable? | Batch-friendly? | Recoverable signer? | Operational shape |
| --- | --- | --- | --- | --- | --- |
| `ed25519` | Single-signer signatures and attributable certificates | Yes | Yes | No | Same key material can name and sign; good default when simple signer-specific evidence matters |
| `secp256r1::standard` | Single-signer signatures and attributable certificates | Yes | No | No | HSM-friendly, deterministic signing, eager per-signature verification |
| `secp256r1::recoverable` | Single-signer signatures that carry enough information to recover the public key | Yes | No | Yes | Useful when the signature itself should identify the signer without shipping a separate key field |
| `bls12381::certificate::multisig` | Aggregated but still attributable committee certificates | Yes | Yes | No | Keeps a signer bitmap and aggregated proof; supports separate identity and signing keys |
| `bls12381::certificate::threshold` | Constant-size threshold certificates | No | Yes | No | Needs DKG and resharing; proves quorum power existed, not which members supplied it |

Two observations matter more than the table itself.

First, the matrix is not ranking schemes from weak to strong. It is separating
evidence semantics from implementation details. Threshold certificates are not
"the advanced version" of attributable certificates. They are a different
product with different export semantics.

Second, the matrix explains why the crate allows identity keys and signing keys
to diverge. Ed25519 can collapse them comfortably. BLS multisig often should
not. Threshold signing cannot, because the public committee identity survives
even while the private shares behind it are refreshed.

The code path for batchable schemes makes that distinction visible again in
`Scheme::verify_certificates_bisect`: when batch verification fails, the code
splits the range and keeps bisecting until it isolates the bad certificate(s).
That is a concrete example of evidence semantics shaping implementation.

### 3.5 Recoverable Signatures: When the Signature Carries the Signer Hint

Most signatures require the verifier to already know which public key to check.
Recoverable signatures change the packaging. In `secp256r1::recoverable`, the
signature carries a recovery identifier alongside the ECDSA material, so the
verifier can reconstruct the public key from three things:

- the namespace,
- the message,
- and the signature itself.

That does not create new trust. It repackages existing trust so the signer can
be inferred rather than supplied out of band.

The code makes one subtle choice worth noticing: signatures are normalized into
their low-`s` form, and the recovery identifier is adjusted accordingly. That is
not cosmetic tidiness. It ensures the recovered identity corresponds to one
canonical signature representation rather than several equivalent encodings.

So the right mental model is:

- ordinary signature: "verify this against the key I gave you,"
- recoverable signature: "recover the key that must have produced this,"
- certificate: "reason about one signer or many signers as a protocol-level
  set."

### 3.6 Secret Handling: What the Wrapper Protects, and What It Cannot

The crate also includes a `Secret<T>` wrapper. This is not a new cryptographic
primitive. It is custody discipline for private material already in memory.

`Secret<T>` does four concrete things:

- redacts `Debug` and `Display`,
- zeroizes the wrapped storage on drop,
- requires explicit `expose()` or `expose_unwrap()` to touch the inner value,
- and compares in constant time when the inner type supports constant-time
  equality.

That is already valuable. A lot of leaks are not dramatic key extractions. They
are log lines, panic output, careless equality checks, or stale bytes left
behind after a value is dropped.

But the wrapper is deliberately modest about its guarantee. It is built for
flat value types, not pointer-rich containers. If you wrap a `Vec<u8>` or a
`String`, zeroizing the outer structure does not automatically scrub the heap
buffer it pointed to. If you derive temporaries from the secret inside
`expose()`, those temporaries may live on the stack unless you wrap them in
their own zeroizing container.

So the right lecture note here is:

> `Secret<T>` improves secret custody inside the crate, but it does not relieve
> the caller from thinking about copies, indirection, and derived temporaries.

---

## 4. Transcript Discipline: Meaning Before Math

If there is one place where the crate quietly saves the rest of the system from
footguns, it is the transcript abstraction.

Why is a transcript needed at all? Because "just hash the fields together" is
not a method. It is an invitation to ambiguity.

If you build commitments ad hoc, bad things happen:

- field boundaries blur,
- different protocol stages accidentally accept the same bytes,
- randomness is derived from context that was never fully bound,
- valid evidence from one place gets replayed in another place where it should
  not mean the same thing.

The transcript fixes this by forcing the protocol to answer a basic question
before any cryptographic operation succeeds:

> what exactly has been committed so far, and in what structure?

That is why the transcript belongs in the evidence layer. It is not merely a
convenient hashing wrapper. It is the mechanism that turns context into a
first-class invariant.

Schematically, the discipline looks like this:

```rust
// Conceptually: first bind meaning, then derive evidence from it.
let mut transcript = Transcript::new(b"stream-handshake");
transcript.commit(dialer_public_key.as_ref());
transcript.commit(listener_public_key.as_ref());
transcript.append(b"syn");
transcript.commit(syn_bytes);

let summary = transcript.summarize();
let proof = signer.sign(b"", summary.as_ref());
```

The point of the snippet is not the exact API shape. The point is the order of
thought. First decide what conversation this is. Then decide what part of the
conversation is complete. Only then derive a digest, signature, or key.

### 4.1 `commit` Versus `append`

The `commit` and `append` split is a small detail with large consequences.

- `append` says, "I am still building this unit."
- `commit` says, "This unit is finished and now part of the permanent story."

That distinction rules out a class of accidental equivalences where different
construction sequences collapse into the same hash state. In other words, the
transcript does not just record content. It records the boundaries that make
content interpretable.

The code in `Transcript::commit` and `Transcript::append` makes that explicit:
`append` accumulates bytes, while `commit` flushes the length-tagged boundary
into the hasher. Even an empty commit matters because the structure itself is
part of the proof.

### 4.2 `fork`, `summarize`, and `resume`

Real protocols branch. They derive one value for traffic keys, another for
confirmation, another for later replayable evidence, and sometimes a compact
summary for storage or transport.

The transcript API treats that branching as something explicit:

- `fork` creates a new branch that shares history but not future meaning,
- `summarize` turns the current state into a stable commitment,
- `resume` lets later work continue from that committed point.

This matters because reuse is dangerous when it is implicit and powerful when
it is deliberate. The transcript gives the system a disciplined way to reuse
history without pretending two different conversations are the same one.

The source code makes this hard to miss: `Transcript::fork` seeds a new
transcript from the current summary, `resume` restarts from a prior summary but
with a different start tag, and `noise` derives an opaque RNG from that same
history. Same ingredients, different meanings.

### 4.3 Derived Randomness Is Still Evidence-Bound

The transcript also supports deriving randomness from committed history. That is
an easy point to miss. We often talk as though randomness floats in from the
sky and everything else follows from it. In protocol design, the opposite is
often safer: let randomness emerge from context that has already been nailed
down.

So the transcript is really teaching one lesson over and over:

> meaning must be assembled before mathematics can safely speak for the
> protocol.

---

## 5. Committee Evidence: Agreement, Blame, and Compression

A single signature tells you one actor took one action. Many distributed
protocols need a stronger fact:

> enough of the committee endorsed the same subject that the rest of the system
> may now move.

That is the job of the certificate layer.

The crate begins with attestations: per-participant endorsements over the same
subject. Those attestations can then be checked individually, batch verified,
assembled into a certificate, and later shown as evidence that some threshold
of support existed.

At this point the lecture becomes more interesting, because committee agreement
can mean two importantly different things.

### 5.1 What the Certificate Module Actually Models

`cryptography/src/certificate.rs` fixes what counts as committee evidence
before curve-specific code gets to optimize anything.

It models four stages:

1. attestation
   - one participant index plus one scheme-specific signature or share

2. verification
   - scheme logic checks which attestations are valid and which signer indices
     are invalid

3. assembly
   - enough verified attestations are transformed into a certificate product

4. recovered verification
   - a later verifier checks the exported certificate against the subject and
     the committee context

The module also defines `Signers`, a bitmap over participant indices. That
bitmap is the compact public statement of who participated. `Signers::from`
asserts that signer indices are unique, and `Read for Signers` uses the
participant count as an upper bound during decoding. That is a concrete example
of the chapter's main theme: structure is part of security.

The abstraction is preventing the system from blurring together "I saw some
signatures" and "I now possess reusable committee evidence."

### 5.2 Attributable Evidence

Attributable schemes preserve signer identity in the exported evidence because
some systems need the certificate to support later blame, auditing, or
slashing.

That means a recovered certificate can support questions like:

- who signed?
- how many signed?
- did one participant sign two conflicting subjects?
- can I show a third party exactly which participants were responsible?

This is evidence with blame attached. It is valuable whenever fault
attribution is part of the protocol's safety story.

In Commonware, the attributable family includes:

- Ed25519 certificates, which carry per-signer signatures ordered by signer
  index,
- Secp256r1 certificates, which do the same but prefer eager individual
  verification over batching,
- and BLS multisignatures, which compress the signatures themselves while still
  retaining a signer bitmap.

That last case is easy to misunderstand, so it is worth stating carefully.
BLS multisig is not threshold signing. It aggregates signatures, but it still
remembers which indices participated. That is why it lives on the attributable
side of the line.

### 5.3 Threshold Evidence

Threshold schemes answer a different question:

> can the committee produce one compact proof that the threshold was met?

This is evidence with compression attached.

Once enough valid shares exist, the system can produce a small, strong proof of
collective agreement. That is wonderful for transport, storage, and external
consumption. But it changes what the evidence can say.

The crucial tradeoff is not subtle and the crate is refreshingly explicit about
it: threshold signatures are non-attributable. They prove that enough of the
committee could have acted together. They do not give a third party the same
signer-by-signer blame story that attributable certificates can.

The threshold module makes this concrete in two ways.

First, individual attestations are only partial signatures indexed by
participant. They are useful inside the live protocol because the current
committee can authenticate the transport peer that sent them and can validate
the share against the public polynomial.

Second, the exported certificate throws those individual shares away and keeps
only the recovered threshold signature. By the time the proof leaves the
committee boundary, it no longer tells an outsider which partials were used.

That is why the crate says the evidence is non-attributable, not merely less
convenient to attribute.

### 5.4 Threshold Versus Attributable: Two Different Kinds of Proof

The fastest way to keep the distinction straight is to compare what each proof
supports after it leaves the local protocol.

| Question a verifier wants to ask later | Attributable certificate | Threshold certificate |
| --- | --- | --- |
| Did quorum support this subject? | Yes | Yes |
| Which participants signed? | Yes | No |
| Can I prove signer-specific equivocation to a third party? | Yes | No |
| Can current committee members still use partials locally for liveness or blame? | Yes | Yes, locally |
| Does certificate size stay constant as the committee grows? | No, though aggregation can help | Yes |

The subtle row is the fourth one. Threshold partials can still matter locally.
If a peer connection is authenticated, a participant can know which neighbor
sent which partial share. That can drive local blocking or progress decisions.
What it does not give you is safe external fault evidence. Once enough partials
exist, other parties can often synthesize equivalent-looking evidence.

That local-versus-exported distinction is one of the most important ideas in the
whole cryptography crate.

### 5.5 The Trust Question Changes With the Product

This is where the foundry metaphor earns its keep. The raw material in both
cases may look similar: a subject and many participants. But the finished
product serves a different trust question.

- Attributable certificate:
  "Which participants endorsed this, and can I prove that outside the local
  protocol?"
- Threshold certificate:
  "Did enough committee power exist to endorse this, in a compact form other
  systems can consume?"

Same committee. Different evidence. Different downstream uses.

The source makes that difference operational too: `verify_attestations` splits
verified from invalid signer indices, `assemble` collapses a valid set into one
certificate, and `verify_certificates_bisect` keeps batch verification honest by
bisecting failures instead of trusting a big batch blindly.

---

## 6. Authenticated Key Exchange: Turning Evidence Into a Channel

The handshake module answers the question of how evidence becomes a live,
ongoing secure conversation.

It is tempting to describe a handshake as "the part where two peers agree on a
shared secret." That is true in the same way that describing a court hearing as
"the part where paperwork changes hands" is true. It misses the purpose.

The purpose of the handshake is to transform prior evidence about identity and
context into a channel that can keep making trustworthy progress.

That requires four things:

1. both sides must enter the same transcript,
2. both sides must authenticate who they think the peer is,
3. both sides must derive the same secret material from that shared history,
4. the resulting traffic must fail loudly under replay or reordering.

### 6.1 Why Three Messages?

The handshake uses three messages: `Syn`, `SynAck`, and `Ack`.

That shape is not ornamental. It is the minimum conversation needed for each
side to stop guessing and start proving.

Very roughly:

1. the dialer says, "here is my ephemeral contribution and my claim about this
   conversation,"
2. the listener answers, "I saw that claim, here is my own contribution, and
   here is evidence that I derived the same conversation state,"
3. the dialer closes the loop with its own confirmation.

Only then does the system treat the channel as ready.

The code shows this directly. `Context::new` forks the transcript under the
handshake namespace. `dial_start` commits the current time and the dialer's
ephemeral key before producing `Syn`. `SynAck` carries the listener's ephemeral
key, a signature, and a confirmation summary. `Ack` closes the loop with the
listener's confirmation.

### 6.2 Directionality Is Part of the Safety Story

After the handshake succeeds, the channel gets directional ciphers.

That may sound like a plain engineering choice, but it is really another form
of evidence discipline. Send and receive are not interchangeable stories. They
must not share one nonce space, because that would let two different histories
pretend to be the same one.

So the channel carries two linked guarantees:

- confidentiality and authenticity for traffic,
- and a directional notion of sequence, so out-of-order reuse becomes
  decryption failure instead of silent confusion.

This is a recurring Commonware pattern: when something dangerous can be made
structurally impossible, prefer that over hoping every caller remembers the
rule.

### 6.3 Time Is Also Evidence

The handshake checks timestamps as well.

That may look like mundane plumbing until you remember the chapter's main
theme. A replay is not just an old packet. It is stale evidence reintroduced in
the wrong moment and asking to be trusted again.

A timestamp window turns time into part of the trust claim. Too old, and the
evidence is stale. Too far in the future, and the peer is speaking from outside
the protocol's intended clock horizon. Either way, the right answer is not to
reinterpret the proof generously. The right answer is to reject it.

---

## 7. Shared Keys Over Time: Continuity Without Central Custody

This is where the crate stops being merely about authenticated action and
starts dealing with institutional continuity.

Distributed Key Generation, or DKG, is often summarized as "many parties
generate one key together." Correct, but still too shallow.

The deeper systems statement is this:

> a committee creates one public identity that everyone can rely on, while no
> single participant ever holds the whole secret behind it.

That is the key idea. The outside world gets one stable public fact. The inside
of the committee gets distributed custody.

### 7.1 What DKG Produces

The finished product of DKG is not just secret shares. It is a package of
trust:

- a public key the world can verify against,
- a public polynomial that commits to the shared key and its evaluations,
- private shares spread across participants,
- commitments and logs that let participants check whether the sharing process
  stayed coherent,
- and a round-scoped description of who the dealers and players were when this
  output was formed.

Again the foundry picture helps. Raw material goes in: a committee, some
randomness, a protocol, and a synchrony assumption. What comes out is a public
identity with no single owner.

The source mirrors that story in the types. `Info` binds the round, dealers,
players, previous output, and mode. `Output` packages the public sharing data.
`Dealer` and `Player` are state machines, not one-shot helpers. `SignedDealerLog`
and `observe` let an external auditor reconstruct the public result.

### 7.2 Why Resharing Is the Real Operational Story

If DKG were only about birthing a key once, it would be interesting but narrow.
Resharing is what turns it into systems infrastructure.

Resharing answers the practical question:

> can the public identity remain stable while the private holders rotate,
> recover, or change membership?

In a long-lived protocol, that question is unavoidable. Machines fail. Members
leave. New members join. Security policy changes. A committee that cannot
refresh its private structure without changing its public identity forces the
whole surrounding system to restart trust from scratch.

Resharing avoids that reset. It preserves continuity at the public surface
while refreshing risk underneath.

### 7.3 Why the DKG Source Is Long

`bls12381/dkg.rs` is long because it is doing something operationally delicate,
not because the authors forgot how to factor code.

The protocol has to account for:

- dealers who may be honest or dishonest,
- players who may acknowledge or fail to acknowledge,
- reveals used to recover progress when direct agreement fails,
- synchrony assumptions that cannot be wished away,
- and the difference between what participants can verify locally and what an
  outsider can later prove.

That is why this part of the crate should be read slowly. The difficulty is not
ornamental complexity. The difficulty is the real cost of preserving continuity
without handing one machine the secret crown jewels.

The comments in the file are worth reading as part of the design. They explain
why `Player::resume` exists, why missing dealings surface as
`MissingPlayerDealing`, and why the protocol distinguishes honest progress from
operator mistakes during recovery.

### 7.4 TLE: Delayed Evidence Release, Not Just Another Encryption Primitive

The `bls12381/tle.rs` module is easy to overlook because it does not look like
the certificate path. It matters for the same reason, though: it turns future
committee evidence into a release condition.

Timelock encryption here means:

> encrypt a message now so that it becomes decryptable only once a valid
> signature over some target becomes available later.

The target might be a round number, epoch, timestamp, or some other public
event the protocol expects the committee to sign in the future. The decryption
key is not an independent secret handed around off to the side. It is derived
from the signature over that target.

The code makes the shape of that construction concrete:

- `encrypt` samples `sigma`,
- derives `r = H3(sigma || message)`,
- computes `U = r * G`,
- masks `sigma` with the pairing output,
- and masks the message with `H4(sigma)`.

`decrypt` reverses the process only if the signature matches the target. That
means TLE is really a release gate that reuses BLS12-381 structure, hardened
ciphertext handling, and threshold signing so no single actor owns the release
capability alone.

---

## 8. Pressure, Limits, and Reading Order

The chapter's unifying idea is simple: cryptography matters here when it turns
an action into evidence that survives later scrutiny.

That also tells you where the guarantees stop.

- The crate can reject misbound evidence, but it cannot repair a bad protocol
  design.
- `Secret<T>` helps with custody, but it does not magically scrub every copy or
  every pointer-rich container.
- Threshold partials remain useful inside the committee boundary, but they do
  not export the same blame story as attributable certificates.
- DKG preserves public continuity, but it still depends on the protocol
  assumptions spelled out in the source comments.
- Handshakes bind context and prove liveness, but they still need honest clock
  bounds and matching identities.

If you want the sharpest reading of the crate, keep asking the same question
while you read every file:

> At this point, what fact does the system know, what is it still unsure about,
> and what evidence makes it safe to proceed?

That question, more than any one curve or scheme, is the real subject of
`commonware-cryptography`.
