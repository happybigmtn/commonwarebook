# Chapter Brief: commonware-cryptography

## 1. Chapter Contract

**Promise:** `commonware-cryptography` is the monorepo's evidence layer: it
turns cryptographic operations into facts the rest of the system can trust.

**Crux:** A primitive matters here only when it preserves meaning across
protocol stages, peers, and later verification.

**Primary invariant:** No signature, digest, certificate, or shared key may be
interpreted without the namespace, transcript state, and committee context that
made it valid.

**Naive failure:** Hash or sign raw bytes in isolation, then assume the same
bytes mean the same thing everywhere. That is how replay, ambiguity, and blame
confusion enter a protocol.

**Reading map:**

- `cryptography/src/lib.rs` for the vocabulary of signers, verifiers, digests,
  and commitments
- `cryptography/src/transcript.rs` for context binding and domain separation
- `cryptography/src/certificate.rs` and the BLS certificate modules for
  attributable and threshold evidence
- `cryptography/src/secret.rs` for secret custody and zeroization caveats
- `cryptography/src/secp256r1/recoverable.rs` for public-key-recoverable
  signatures
- `cryptography/src/bls12381/tle.rs` for timelock encryption as
  evidence-gated release
- `cryptography/src/handshake.rs` for evidence turned into a live authenticated
  channel
- `cryptography/src/bls12381/dkg.rs` for stable public identity under changing
  private custody

**Assumption ledger:**

- Adversary: active network peers, replay, stale evidence, and dishonest
  committee members
- Trusted boundary: transcript construction, namespace binding, certificate
  formation, and handshake state
- Invariant: every proof stays tied to the exact protocol meaning that created
  it
- Guarantee edge: the crate can reject misbound or stale evidence and preserve
  evidence semantics, but it cannot infer the caller's intent or repair a wrong
  protocol design

The rest of the chapter should keep returning to that contract. The tone should
feel like a lecture that starts from doubt, builds a mental model, and only
then names the mechanisms that resolve the doubt.

---

## 2. Module Purpose

`commonware-cryptography` is the monorepo's evidence layer. It provides the
primitives that let distributed systems answer questions like:

- who said this,
- what exactly did they sign,
- can a committee attest to this as a group,
- can that attestation be shown to a third party,
- and can a shared key survive changes in the people who hold it.

The crate is not just "a bag of signature schemes." It is a framework for
turning cryptographic facts into systems-level trust. That includes:

- single-party identities and signatures,
- transcripts and namespaces for domain separation,
- certificates assembled from many participants,
- authenticated key exchange for live channels,
- and threshold-key lifecycle tools such as DKG and resharing.

The deepest design question in this crate is not "which curve is used?" It is
"what fact does this construction let the rest of the system trust?"

---

## 2. Source Files That Matter Most

### `cryptography/src/lib.rs`
**Why it matters:** Defines the common language: `Signer`, `Verifier`,
`PublicKey`, `Signature`, `Digest`, `Digestible`, `Committable`, and
`BatchVerifier`. This is the conceptual front door of the crate.

### `cryptography/src/transcript.rs`
**Why it matters:** The transcript abstraction is the anti-footgun device of the
crate. It explains how Commonware binds context before hashing, signing, or
deriving randomness, and why ad hoc hashing is dangerous.

### `cryptography/src/certificate.rs`
**Why it matters:** Defines the certificate model, the split between
attributable and non-attributable schemes, and the difference between identity
keys and signing keys. This is where the chapter's "what counts as evidence?"
story becomes precise.

### `cryptography/src/secret.rs`
**Why it matters:** Explains the actual custody guarantee for private material:
redaction, zeroization, explicit exposure, and the sharp limit around
pointer-containing types and copied temporaries.

### `cryptography/src/secp256r1/recoverable.rs`
**Why it matters:** Adds a second single-signer evidence mode. Recoverable
signatures show how one signature can identify its signer without shipping a
separate public key field, while still remaining distinct from certificate
evidence.

### `cryptography/src/handshake.rs`
**Why it matters:** Shows how identities, transcripts, signatures, and key
derivation become a live authenticated channel. This is the cleanest concrete
example of the crate's abstractions working together.

### `cryptography/src/bls12381/certificate/mod.rs`
**Why it matters:** Introduces the two committee-level stories in BLS12-381:
attributable multisignatures and non-attributable threshold signatures.

### `cryptography/src/bls12381/certificate/threshold/mod.rs`
**Why it matters:** Makes the threshold tradeoff concrete. Partial signatures
are compact and composable, but they do not preserve third-party fault
attribution.

### `cryptography/src/bls12381/dkg.rs`
**Why it matters:** This is where "shared trust" becomes an operational
protocol. DKG and resharing explain how a committee can keep one public key
stable while the people behind the key change over time.

### `cryptography/src/bls12381/tle.rs`
**Why it matters:** Extends the chapter beyond signatures and certificates.
TLE shows how future signature availability can become a release condition for
encrypted data, which fits the chapter's evidence-first frame.

### `docs/blogs/commonware-cryptography.html`
**Why it matters:** Gives the high-level product story the chapter should absorb
without becoming marketing copy: seeds, links, and views are three ways
cryptographic evidence becomes useful in a system.

---

## 3. Chapter Outline

```
0.  Chapter Contract
    - One-sentence promise
    - Crux, invariant, failure mode
    - Reading map and assumption ledger

1.  Why Distributed Systems Need Evidence
    - Start from doubt, not primitives
    - Explain the difference between computing bytes and manufacturing facts
    - Introduce the central question: what can the rest of the system trust?

2.  Mental Model: The Trust Foundry
    - Four products: identities, commitments, certificates, shared keys
    - Keep asking: what goes in, what comes out, who can trust it?
    - Use the metaphor to connect the whole crate

3.  The Basic Contract: Who, What, and In What Context?
    - Signer / Verifier / PublicKey / Signature
    - Digest, Digestible, Committable
    - Identity keys versus signing keys
    - Namespaces as part of meaning, not metadata
    - Scheme matrix: what each supported scheme exports
    - Recoverable signatures as a distinct single-signer packaging choice
    - Secret handling as custody discipline rather than new crypto

4.  Transcript Discipline
    - Meaning before math
    - `commit` vs `append`
    - `fork`, `resume`, `summarize`, and derived randomness
    - Domain separation as a systems invariant, not a crypto nicety

5.  Committee Evidence
    - Certificate module anatomy: attestation, verification, assembly, export
    - `Signers` bitmap and bounded certificate decoding
    - Attestations and certificates
    - Attributable evidence versus threshold evidence
    - Threshold-vs-attributable evidence table
    - Blame versus compression
    - What third parties can and cannot safely conclude

6.  Authenticated Key Exchange
    - The handshake as proof of shared conversation, not setup boilerplate
    - Why three messages exist
    - Directional ciphers, ordering, replay windows, and timestamps

7.  Shared Keys Over Time
    - DKG as distributed custody for one public identity
    - Resharing as continuity under membership change
    - TLE as delayed evidence release gated by future signatures
    - Why the long protocol exists: recoverability, synchrony, and proof limits
    - DKG reveal bounds, complaint handling, and replay/resume caveats

8.  Pressure, Limits, and Reading Order
    - What kinds of adversarial pressure the design absorbs
    - Where the guarantees stop
    - How to read the crate without drowning in implementation detail
```

---

## 4. System Concepts to Explain at Graduate Depth

1. **Evidence versus computation.** A cryptographic primitive matters here only
   insofar as it lets one component convince another component, or a third
   party, that some event really happened.

2. **Transcript discipline.** The transcript is not a convenience wrapper. It
   is the mechanism that prevents context-stripping mistakes when hashing,
   signing, or deriving randomness.

3. **Attribution versus compactness.** Attributable schemes preserve signer
   identity and exportable fault evidence. Threshold schemes compress committee
   agreement, but sacrifice third-party attribution.

4. **Scheme choice is evidence choice.** The scheme matrix should feel like a
   product-selection guide, not a feature checklist. The reader should leave
   knowing why recoverable secp256r1, BLS multisig, and threshold BLS solve
   different problems.

5. **Identity keys versus signing keys.** The crate allows these to differ
   because some systems want long-lived identity even when the signing material
   rotates or is shared.

6. **Handshake as proof, not just setup.** The authenticated handshake proves
   both parties are in the same protocol context and derive the same shared
   secret before any transport starts using the channel.

7. **Secret custody is not solved by one wrapper.** `Secret<T>` is worth
   teaching because it improves redaction and zeroization while still having
   concrete limits around copies, heap indirection, and temporaries.

8. **DKG and resharing as operational continuity.** The interesting property is
   not merely "many parties make one key." It is "the public key stays stable
   while the set of private holders changes."

9. **TLE as delayed evidence release.** The chapter should explain TLE as data
   becoming available when future signature evidence appears, not as an exotic
   side quest disconnected from the trust story.

10. **Voice target.** The finished chapter should feel broad, explanatory, and
   concept-first all the way through. Code snippets, if used, should illustrate
   evidence and trust invariants rather than narrate source files line by line.

---

## 5. Interactive Visualizations to Build Later

1. **Transcript explorer**  
   Show how `commit`, `append`, `fork`, and `resume` affect transcript history,
   and why two similar-looking transcripts diverge.

2. **Certificate comparer**  
   Side-by-side attributable versus threshold certificate formation: same
   committee, different evidence semantics.

3. **Handshake timeline**  
   Dialer and listener views of `Syn`, `SynAck`, and `Ack`, with transcript
   state and derived ciphers shown after each step.

4. **DKG / reshare round table**  
   Dealers, players, commitments, private shares, acknowledgements, reveals,
   and final public output shown as one visible protocol.

---

## 6. Claims-to-Verify Checklist

- [ ] Namespace/domain separation is always part of signing and verification,
  not an optional add-on.
- [ ] `Transcript` distinguishes `commit` from `append`, and forks produce
  diverging histories rather than aliases.
- [ ] The scheme matrix distinguishes attributable certificates, threshold
  certificates, and recoverable single-signer signatures.
- [ ] Attributable schemes can safely expose signer-specific evidence to third
  parties.
- [ ] Threshold schemes are explicitly non-attributable.
- [ ] `Secret<T>` is described with its real limits: flat types only, explicit
  exposure, and no magical protection against copied temporaries.
- [ ] Recoverable secp256r1 signatures require the exact namespace and message
  to recover the signer.
- [ ] The handshake binds both parties into one transcript before deriving
  traffic keys.
- [ ] Send and receive ciphers are directional and nonce counters do not repeat.
- [ ] DKG / resharing preserve a committee public identity while refreshing the
  private sharing.
- [ ] The DKG section explains reveal/synchrony caveats instead of presenting
  threshold custody as unconditional.
- [ ] TLE is explained as evidence-gated delayed release and not just "future
  decryption somehow happens."
