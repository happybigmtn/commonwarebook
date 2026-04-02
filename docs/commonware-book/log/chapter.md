# commonware-log

## A Secret Log With a Public Commitment

---

## Commitments, Secrecy, and Order

This example sits at the intersection of two ideas that are easy to confuse:
secrecy and commitment. Secrecy says who may know a value. Commitment says how
everyone can agree that a value existed without revealing it. A hash is one of
the simplest commitment tools because it is short, stable, and easy to
verify.

The important vocabulary is payload, digest, and transcript. The payload is
the private message. The digest is the public fingerprint of that message. The
transcript is the ordered public record that consensus is willing to preserve.
If you put the payload directly into the transcript, you make consensus carry
data it does not need. If you hide the payload without a commitment, you make
agreement impossible. The example chooses the middle path: keep the secret
local and publish only the digest.

The naive approach is to let the protocol order raw secrets and hope
encryption solves the rest. That mixes privacy with agreement and makes the
system do more work than necessary. Another naive approach is to keep the
secret entirely out of the system and rely on ad hoc logs or side channels.
That protects privacy, but it destroys the public fact that lets the network
agree on what was proposed.

The tradeoff is simple but important. Commitments give you public
verifiability and compact state, but they do not give you the secret back.
That means the application must own the secret, consensus must own the order,
and persistence must keep the ordered commitment from being rewritten after
restart.

## 1. What Problem Does This Solve?

This chapter is not about hashing for its own sake. It is about deciding what
belongs inside the protocol and what must stay outside it.

`commonware-log` shows one clean answer: keep the payload private, publish only
the commitment, and let consensus order the commitment instead of the secret
itself. Each turn, a participant creates a 16-byte message, hashes it, and
gives consensus the digest. The raw message never becomes a protocol artifact.

That distinction matters. If the application pushed the full payload through
consensus, the protocol would have to carry secret data it does not need, know
more about payload handling than it should, and expose more of the system than
the example intends. Here, the application owns the secret. Consensus owns the
ordering of the commitment.

Persistence reinforces the same lesson. Consensus state is written to
`storage-dir`, so restart does not invent a new history. It resumes the same
one.

---

## 2. Mental Model

Think of each proposal as two separate objects.

The first is a sealed envelope. That is the private payload. The second is the
receipt. That is the public commitment.

The sender keeps the envelope. The network sees the receipt. Everyone can agree
on the receipt without ever opening the envelope. That is why the example uses a
hash instead of the raw message. The hash is short, stable, and easy to compare.
More importantly, it gives consensus the only thing it actually needs: a public
fact that names a private value without revealing it.

The genesis step uses the same pattern. Before the first real proposal, the
example hashes the fixed message `commonware is neat` to seed the protocol with
a known starting point. After that, each view is just another envelope and
another receipt.

The simplest way to remember the example is this:

> consensus is the receipt book, not the post office.

---

## 3. The Boundary

The whole example rests on one invariant:

**Consensus only needs the digest of the secret, never the secret itself.**

That invariant is enforced at the application boundary in
`examples/log/src/application/mod.rs` and
`examples/log/src/application/ingress.rs`. The application owns the hasher, the
secret generation loop, and the local logging. The mailbox exposes only the
digest to consensus.

Three pieces make that boundary work:

1. **`Application`** in `examples/log/src/application/actor.rs` owns the secret
   generation loop. On `Propose`, it fills a 16-byte buffer, hashes it, logs the
   secret locally, and sends the digest back.
2. **`Mailbox`** in `examples/log/src/application/ingress.rs` implements the
   consensus-facing traits. It translates consensus requests into actor
   messages and returns the digest or verification result on a one-shot
   channel.
3. **`Reporter`** in `examples/log/src/application/reporter.rs` records what
   consensus has already decided. It reports notarization, finalization, and
   nullification as observable events.

The `Scheme` alias is part of the same lesson. It ties the example to the
`ed25519` signing scheme used by simplex consensus. The example is not inventing
its own agreement mechanism. It is showing how an application plugs into the one
it already has.

The last piece is what the example refuses to do. `Mailbox::broadcast` stays
empty so the protocol cannot drift into transporting secrets it should only
commit to. The example is about agreeing on a public fact, not distributing
the private value behind it.

---

## 4. How The System Moves

The system has a simple rhythm, but the lecture is in the boundary crossing.

First, `main.rs` parses identities, builds the authorized peer set, configures
the network, and initializes the application plus consensus engine. That wiring
matters because it shows the example as a full distributed system, not a toy
function that happens to hash bytes.

Then the loop begins:

1. Consensus asks the application for a genesis digest.
2. The application hashes the fixed genesis message and returns the result.
3. When a participant's turn comes, consensus asks for a proposal.
4. The application generates a secret 16-byte message, hashes it, and returns
   the digest.
5. Consensus runs its normal validation and ordering logic on that digest.
6. The reporter emits progress when the digest is notarized or finalized.
7. The GUI renders those events so a human can watch the protocol breathe.

Two details are worth slowing down on.

The first is that the application does not hand consensus a message and ask it
to decide what to do with it. It hands consensus a digest. That keeps the
public protocol surface small and makes the payload opaque.

The second is that the application keeps the raw secret local. The digest moves
across the boundary; the secret does not. That is the heart of the example. A
private value becomes a public fact by being hashed, not by being exposed.

---

## 5. Why The Example Is Small

The example is deliberately narrow because its job is to teach a boundary, not
to solve every related problem.

It absorbs privacy pressure by keeping the raw payload out of the protocol.
The network does not need the secret to agree on the commitment.

It absorbs restart pressure because consensus state is persisted in
`storage-dir`. If the process dies and comes back, the example resumes the old
story instead of inventing a new one.

It absorbs observability pressure by separating protocol from presentation. The
reporter and GUI help a reader understand the run, but they do not shape the
protocol itself.

It also leaves work on the table on purpose. The example does not broadcast raw
messages, backfill missing payloads, support multiple epochs, or build a durable
archive of every secret ever proposed. Those problems belong to other layers.
Leaving them out keeps the lesson focused on the commitment boundary.

The most important omission is `Mailbox::broadcast`. The example does not use
consensus as a transport for private data. It uses consensus to agree on the
fact that some private data exists.

---

## 6. Failure Modes and Limits

The example is honest about its limits.

It does not support multiple epochs. `Application::genesis` asserts that the
epoch is zero. That keeps the example focused on the first commitment path.

It does not verify parent linkage in the application. If payloads were linked
to their parents, the application would need to check that relationship. This
example does not need that complexity to make its main point.

It does not try to make `verify` clever. The example returns `true` because the
interesting property is not cryptographic validation at that point. The
interesting property is that consensus is already working with a digest the
application produced.

It also does not promise recovery of the plaintext after the node forgets it.
The digest is enough for agreement. It is not enough to reconstruct the secret
once the node has moved on.

The limit to keep in mind is simple: this is a commitment example, not a full
secret-sharing or retrieval system.

---

## 7. How To Read The Source

Read the source as a boundary diagram, from composition root to observability.

Start with `examples/log/src/main.rs`.

Read it for the system shape: how identities are parsed, how peers are
authorized, how the network is wired, and where the application meets the
consensus engine. The point is not the CLI. The point is how the boundary is
assembled.

Next read `examples/log/src/application/actor.rs`.

That file contains the core move. It shows the application generating a
secret, hashing it, and deciding that the digest is the thing worth sharing.
The genesis path in the same file shows the same idea before the first real
proposal.

Then read `examples/log/src/application/ingress.rs`.

This is the boundary file. It shows how consensus talks to the application and
what the application refuses to do. The empty `broadcast` method is as
important as the implemented ones.

After that, read `examples/log/src/application/reporter.rs`.

This file tells you what the system thinks is worth observing: notarization,
finalization, and nullification. It is a clean view into protocol progress.

Finally, skim `examples/log/src/gui.rs`.

Treat it as a lens, not as the mechanism. It makes the run easier to watch, but
it is not the reason the example exists.

---

## 8. Glossary and Further Reading

- **Digest** - the public commitment to the secret message.
- **Genesis** - the first agreed-upon digest that starts the story.
- **Mailbox** - the consensus-facing boundary that turns requests into actor
  messages.
- **Reporter** - the observer that turns consensus activity into structured
  logs.
- **Persistence** - the fact that consensus state lives in `storage-dir` and
  can be resumed after restart.
- **Backfill** - intentionally omitted here so the chapter can stay focused on
  commitment rather than retrieval.

Further reading:

- `examples/log/src/main.rs`
- `examples/log/src/application/actor.rs`
- `examples/log/src/application/ingress.rs`
- `examples/log/src/application/reporter.rs`
- `docs/commonware-book/consensus/chapter.md`
