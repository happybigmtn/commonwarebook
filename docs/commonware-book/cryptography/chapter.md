# commonware-cryptography

*How distributed systems manufacture evidence: identities, commitments, certificates, and shared keys.*

---

## 0. The Deal We're Making Here

When you hear the word "cryptography," you probably think of secret codes, spies, and complicated math. But in a distributed system, `commonware-cryptography` isn't really about keeping secrets. It's about manufacturing *evidence*. 

What do I mean by evidence? I mean a piece of data that answers a simple, brutal question: "What physical fact am I allowed to trust right now, even if I don't trust the computer that just handed it to me?"

The whole trick—and it is a very beautiful, subtle trick—is that a cryptographic primitive (like a signature or a hash) is completely useless unless its *meaning* survives intact when it moves from one machine to another. 

If you just take a bunch of raw bytes, hash them, and sign them, you are setting yourself up for a disaster. Why? Because the exact same bytes might mean something completely different tomorrow, or in a different part of the protocol. If you don't mathematically tie the data to its *meaning*, an attacker will take a valid signature from yesterday and replay it today to trick you. 

Here is your map to the code, so you can see exactly how we stop that from happening:

- **`cryptography/src/lib.rs`**: This is the basic vocabulary. `Signer`, `Verifier`, `Digest`, and `Commitment`.
- **`cryptography/src/transcript.rs`**: This is how we keep the story straight. It binds context and separates domains so meanings don't get mixed up.
- **`cryptography/src/certificate.rs`**: How we mathematically prove that a *group* of computers agreed on something.
- **`cryptography/src/secret.rs`**: How we handle private data in memory without accidentally leaving it lying around for attackers to find.
- **`cryptography/src/secp256r1/recoverable.rs`**: Signatures where you can figure out *who* signed it just by looking at the math of the signature itself.
- **`cryptography/src/bls12381/tle.rs`**: Time-lock encryption. Releasing evidence later.
- **`cryptography/src/handshake.rs`**: Turning static evidence into a live, authenticated conversation.
- **`cryptography/src/bls12381/dkg.rs`**: How a group keeps a single public identity even when the individuals in the group keep changing.

The rule of this chapter is simple: start from doubt. Ask yourself, "How could somebody trick me here?" Build a physical mental model of the problem, and only *then* look at the Rust traits we use to solve it.

---

## 1. What is Evidence, Anyway?

Before we look at the specific tools in the library, we need to understand the fundamental problem. Cryptography in a distributed system takes a private action (like a computer deciding a transaction is valid) and turns it into *publicly checkable evidence*.

If you look at the basic traits in the code, this is already staring you in the face:

- `Signer::sign(namespace, msg)`: Notice it doesn't just sign the message. It signs a `namespace` and a message. It ties the signature to a specific context.
- `Verifier::verify(namespace, msg, sig)`: To check the evidence later, you have to know the exact context it was made in.

This separation is not just for pretty code. If you look at `transcript.rs`, `Transcript::new` starts with a namespace. `commit` puts hard mathematical boundaries between pieces of data, and `append` lets you build up a message piece by piece. 

Why do we do this? Because naïve approaches fail in spectacular, embarrassing ways! 
- If you sign raw bytes without a namespace, someone can take your signature approving a test network transaction and use it to authorize a real bank transfer on the main network. The bytes are the same, but the context is different!
- If you use the same key for completely unrelated steps in a protocol, your evidence becomes "portable" in a very dangerous way.
- If you think "a quorum signed this" is the exact same thing as "a quorum agreed on what this *means*", you are confusing data compression with correctness.

Keep this picture in your head: we are studying how evidence stays meaningful as it flies across the network.

---

## 2. Why Bother With All This?

A network of computers doesn't wake up in the morning wanting to do elliptic curve math. It wakes up filled with doubt!

- "Who actually sent me this message?"
- "What did they *think* they were signing?"
- "Is this proof only good for this one step, or can I show it to someone else later?"
- "Did one machine decide this, or a whole committee?"
- "Can the committee keep the same public face even if the machines inside it get swapped out?"

`commonware-cryptography` exists to answer those questions. The crate is not mainly about calculation. It is about evidence. Calculation just turns bytes into other bytes. Evidence turns an event into a *fact* that a completely different computer can safely rely on.

Sometimes the evidence is simple: a public key (a name), a signature (an endorsement), or a digest (a commitment).
Sometimes it's collective: a certificate (a quorum agreed), or a threshold signature (compressing a group's agreement into one tiny proof).
And sometimes it's procedural: a transcript (recording the exact context), or a handshake (proving two computers are actually talking to each other right now, not playing back a recording).

---

## 3. The Basic Contract: Who, What, and Where?

If you open `cryptography/src/lib.rs`, you'll see we separate three things that programmers usually carelessly mix together:

1. **Who** did it? (The `Signer`, `Verifier`, `PublicKey`, `Signature` traits)
2. **What** are we talking about? (The `Digest`, `Digestible`, `Committable` traits)
3. **Where** did this happen? (Namespaces and domain separation).

A signature does *not* mean "these bytes are true." It means something much more specific: *"This exact signer endorsed this exact subject, inside this specific namespace, under this particular protocol's rules."*

If you change the namespace, the meaning changes. Change the subject, the meaning changes. Take away the signer, and you don't know who you are trusting.

### 3.1 Identity Is More Than Just a Key

You might think a public key is just a math tool used to verify a signature. But in a distributed system, it does a lot more heavy lifting: it is the *name* of the participant. It's how nodes know who to dial, who to listen to, and who to blame when things go wrong.

### 3.2 Commitments Are Facts With Boundaries

We casually say "just hash the data," as if we just want to make the data shorter. But compression isn't the point! The real value of a digest is that it takes a big, complicated structure and turns it into a *stable fact*. 

That's why the code separates `Digestible` (this object has a unique hash) from `Committable` (this object can provide the exact commitment the larger protocol needs). 

### 3.3 You Don't Have to Sign With Your Name Tag

A very neat trick in the crate is that identity keys (your name tag) and signing keys (the pen you sign with) don't have to be the same. 

Why? Because a committee might want one long-lived public identity to coordinate with, but they might want to use a totally different, fast, batchable scheme to prove they voted on something. Forcing them to be the same key hides what the system is actually doing.

### 3.4 Pick the Product, Not the Math

Don't think about "which elliptic curve should I use?" Think about "what kind of evidence do I need?" 

- Need to know exactly who signed, and do it fast? Use `ed25519`.
- Need the signature itself to magically tell you who signed it without them sending their key? Use `secp256r1::recoverable`.
- Need a giant committee to agree, but you still want to know exactly who voted? `bls12381::certificate::multisig`.
- Need a giant committee to agree, and you want the proof to be tiny, and you *don't care* who specifically voted? `bls12381::certificate::threshold`.

### 3.5 Recovering the Signer

Normally, I hand you a signature and I say, "Check if Bob signed this." You need Bob's public key to check it. 
But with a *recoverable signature*, you just look at the signature, the message, and the namespace, and the math goes backward and says, "Aha! The only person who could have made this is Bob!" You recover the public key *from* the signature. It saves you from having to send the key over the network.

### 3.6 Keeping Secrets Secret

We have a `Secret<T>` wrapper. What does it do? In Rust, when a variable goes out of scope, the compiler automatically calls a function called `Drop`. We implemented a custom `Drop` for `Secret<T>` that writes zeros over the memory so no one can read it later. It prevents the secret from being accidentally printed to a log file or left in RAM. 

But let me be very clear: it is not magic! If you take a piece of paper out of a self-destructing briefcase, write the secret on a sticky note, and leave the sticky note on your monitor, the briefcase can't help you! If you pull data *out* of `Secret<T>` and put it in a normal `String` or `Vec<u8>`, you've ruined the protection. The garbage collector won't zero out that new String. You still have to think.

---

## 4. Keeping the Story Straight (The Transcript)

If you just hash fields together willy-nilly, you are begging for trouble. 

Why? Imagine I have a protocol where I send you my First Name and my Last Name, and we hash them together. I send "RICHARD" and "FEYNMAN". The hash is `Hash("RICHARDFEYNMAN")`. 
But what if my first name is "RICHARDF" and my last name is "EYNMAN"? The hash is *exactly the same*! We've lost the boundary between the fields. An attacker can use this to cause massive confusion.

This is what `Transcript` fixes. It forces you to answer: "What exactly has been committed so far, and what is its structure?"

Look at how you use it in Rust:

```rust
// b"..." creates a byte string. This is our namespace.
let mut transcript = Transcript::new(b"stream-handshake");

// We commit the public keys. as_ref() borrows them as raw bytes.
transcript.commit(dialer_public_key.as_ref());
transcript.commit(listener_public_key.as_ref());

// We append some data, then commit the rest.
transcript.append(b"syn");
transcript.commit(syn_bytes);

// Finally, we roll all that history into one stable summary hash.
let summary = transcript.summarize();

// And we sign THAT summary, not just the raw bytes.
let proof = signer.sign(b"", summary.as_ref());
```

### 4.1 `commit` vs `append`

If you look at the code above, `append` says, "I am still writing this piece of data." 
`commit` says, "I am done with this piece. Put a hard mathematical boundary right here."

Even an empty `commit` changes the math, because the *structure* of the data is part of the proof. `commit` literally injects the length of the bytes into the hash so "RICHARD" and "FEYNMAN" can never be confused with "RICHARDF" and "EYNMAN".

### 4.2 Forking and Resuming

Real protocols branch out. You might use the history of a conversation up to this point to make a traffic key, and use the exact same history to make a totally different key for something else. 

`Transcript::fork` lets you split the timeline. `Transcript::summarize` lets you roll up the whole history into a single hash, and `resume` lets you pick up right where you left off later. It's a disciplined way to reuse history without getting your wires crossed.

---

## 5. When a Group Agrees (Committees and Certificates)

A single signature is easy: one guy did one thing. But distributed systems usually need a *committee* to agree. We call this a Certificate.

### 5.1 The Four Stages

1. **Attestation**: One guy raises his hand and signs.
2. **Verification**: We check if his signature is good.
3. **Assembly**: We gather enough good signatures to form a quorum.
4. **Recovered Verification**: Later on, somebody else looks at the final certificate to prove the quorum actually agreed.

### 5.2 Attributable Evidence (The Sign-In Sheet)

Some evidence is *attributable*. That means later on, you can look at the certificate and say, "Alice, Bob, and Charlie signed this, but Dave didn't." 

This is incredibly important if you need to *punish* people for misbehaving (like signing two conflicting things). You need to know exactly whose neck to wring! Ed25519 and BLS multisig give you this. They remember *who* did it by keeping a bitmap of the signers.

### 5.3 Threshold Evidence (The Locked Door)

Threshold schemes answer a totally different question. They say, "I have one tiny, mathematical proof that a quorum agreed." 

But there is a huge tradeoff! *Threshold signatures throw away the names of the people who signed.* They prove that *enough* power was there, but they absolutely cannot tell you *which* specific computers supplied it. 

If you need to punish individuals later, a threshold certificate is useless to you. But if you just need to prove to a smart contract that the committee agreed, and you want to save space, it is beautiful. Same committee, different evidence, different uses.

---

## 6. Turning Evidence into a Conversation

How do we take all these static proofs and turn them into a live, secure chat between two computers? That's the `handshake` module.

A handshake isn't just swapping keys. It's making sure both sides are looking at the exact same `Transcript` history, proving they are who they say they are, and agreeing on a secret that they will use to encrypt the rest of the conversation.

### 6.1 Why Three Messages?

We use `Syn`, `SynAck`, and `Ack`. Why three? Because it's the absolute minimum needed to stop guessing.
1. **Dialer**: "Hey, it's me. Here's my half of the math, and my claim about our history."
2. **Listener**: "I hear you. Here's my half, and here's a mathematical proof I derived the same secret."
3. **Dialer**: "Got it, here's *my* proof I calculated it correctly. We're good to go."

### 6.2 One-Way Streets

Once the channel is set up, the ciphers are *directional*. Sending and receiving use different nonces (numbers used once). Why? Because if they used the same math, an attacker could take an encrypted message you sent to me, and bounce it right back at you, and your computer would decrypt it and think *I* sent it! Making them directional structurally prevents this. 

### 6.3 Time is Evidence

We also check timestamps. An old message isn't just old; it's a replay attack! If it's too old, we don't try to be nice and figure it out. We reject it. Time itself is part of the evidence.

---

## 7. The Distributed Key Generation (DKG) Trick

DKG is often explained as "many computers generate one key." But that's missing the magic.

The real systems engineering magic is this: *A group of computers creates a single public identity, but no single computer ever knows the private key.* 

The outside world just sees one normal public key. But inside the committee, the secret is shattered into pieces. 

### 7.1 What DKG Actually Does

It spits out a public key for the world, a "polynomial" (a math object that ties it all together), and private shares for the committee members. It also leaves an audit trail so everyone can prove the math was done fairly without anyone cheating.

### 7.2 The Ship of Theseus (Resharing)

Generating the key once is cute. But what happens when a computer catches on fire, or we want to add a new member to the committee? 

This is where *Resharing* comes in. We can take the shattered pieces of the secret, mix them up, and hand them out to a *new* committee. 

The crazy part? *The public key never changes.* The outside world has no idea the committee changed. The public identity stays perfectly stable, while the private risk is constantly rotated. It's the Ship of Theseus, but for cryptography.

### 7.3 Time-Lock Encryption (TLE)

What if you want to encrypt a message today, but nobody can read it until tomorrow? You can't just ask people to promise not to look. 

In `bls12381/tle.rs`, we do a trick: we encrypt the message so it can *only* be unlocked by a specific signature that the committee hasn't created yet (like a signature they will make when block #100,000 is mined). The decryption key literally does not exist yet! We are using the committee's future threshold signature as the key to unlock the past.

---

## 8. What This Won't Fix For You

The grand theme of this chapter is that cryptography is only useful when it turns an action into un-fakeable, context-rich evidence.

But you have to use your brain.
- The crate will stop you from messing up the hashing, but it won't fix a fundamentally stupid protocol design.
- `Secret<T>` helps, but it won't magically hunt down every copy of a secret you casually left in memory.
- Threshold signatures are small, but they won't let you punish bad actors. 
- Handshakes are secure, but your computer's clock still needs to be relatively accurate.

When you are reading this crate, or building your own system, keep asking yourself one very simple question:

*"At this exact moment, what does my computer actually know for a physical fact, and what is it just assuming?"*

If you can answer that, you understand `commonware-cryptography`.