# commonware-storage: The Feynman Lectures on Data

*Logs first, views second, proofs when the reader must be convinced*

---

## Opening Apparatus

**The Promise:** I'm going to show you how `commonware-storage` does something wonderful. It keeps a durable log first, derives useful views from it second, and only adds cryptographic proofs when you absolutely have to convince someone else that your facts are straight.

**The Crux of the Matter:** You see, storage in a system where people might be trying to trick you (an *adversarial* system) isn't just one job. You need durability (don't lose the data), fast answers (don't make me wait), and cryptographic evidence (prove to me you didn't make this up). These three things pull in entirely different directions! If you try to build one magical data structure to do all three, you'll make a mess. You have to keep the responsibilities separate.

**The Primary Invariant:** The log is the durable authority. It is the fundamental truth. Views? You can rebuild them, compress them, or throw them away. But every answer you give must always trace back to that original, unalterable history.

**The Naive Failure:** If you treat the *current* snapshot of your database as the ultimate truth, recovering from a crash is going to involve a lot of guessing. Deleting old data becomes dangerous. And explaining proofs? Impossible, because once the history changes, the proof makes no sense.

**Your Map for this Chapter:**
- Section 2 gives you the mental model: log, then view, then proof.
- Section 3 walks through the core primitives, from `Persistable` all the way to QMDB.
- Section 4 tracks how the system moves—how it writes, recovers, proves, and prunes.
- Section 5 talks about the pressures this design absorbs.
- Section 6 tells you how it can break.
- Section 7 shows you how to actually read the source code.
- Section 8 is a glossary.

**Assumptions:**
- You know what happens when a computer crashes.
- You're okay with data structures where we only ever *append* (add to the end).
- You want to understand storage in terms of *proving things to adversaries*, not just building a generic database.

---

## Background: Why Storage Becomes a Systems Problem

Storage looks like a perfectly simple question until three things happen: a crash, a pruning of old data, or a skeptical reader who says, "I don't believe you."

Let's get our vocabulary straight right at the beginning:

- A **log** preserves the exact sequence of events. It's the history book.
- A **snapshot** captures what things look like *right now*.
- An **index** is a trick to speed up finding things in that history.
- A **proof** is the mathematical evidence you hand to someone else so they can check that your answer really came from the right history.
- A **prune** is when you throw away history you don't need anymore to save space.

The naive approach—the way we all learn to do it at first—is to treat the latest snapshot as the absolute truth and just throw away the path we took to get there. "Alice has 5 apples." Okay, but what if we crash? What if we need to prove she didn't just magic those apples out of thin air? Once recovery or proof generation matters, you need to know what happened *before* the current answer existed.

The grand trade-off is this: the best structure for surviving a crash and recovering your state is almost *never* the best structure for looking things up quickly. And neither of them is naturally good at generating cryptographic evidence! Logs are durable and easy to replay. Views are fast to query. Proof-bearing structures are convincing to outsiders. Real storage systems in the wild have to keep these roles separate, instead of pretending one giant ball of code can do it all perfectly.

That separation is the whole point of this chapter. The Commonware design starts from the durable record of events (the log), derives useful ways to look things up (the view), and *only then* adds the heavy machinery for proofs when a reader actually needs to be convinced.

---

## 1. What Problem Does This Solve?

Storage sounds incredibly simple until a distributed system comes along and asks you three questions all at the exact same time:

1. What survives when the power gets yanked?
2. What is the state of the world *right now*?
3. How do I mathematically prove that state to someone who thinks I'm lying?

Now, these questions overlap, sure, but they are *not* the same question! A local app running on your laptop can usually stop after the first two. But an adversarial system? A blockchain? It cannot. A node has to wake up from a crash, read the disk, rebuild what it knows, answer queries rapidly, and later, justify those answers to another peer or a client.

That is the exact problem `commonware-storage` was built to solve. It doesn't hand you one giant database object with a hundred configuration flags. Instead, it presents storage as a sequence of increasingly stronger promises:

- Remember the history, durably.
- Derive a fast, useful view from that history.
- Attach cryptographic evidence to the facts that matter.

This crate matters because those promises are at war with each other. A log is fantastic at surviving a crash. A lookup tree is fantastic at giving you an answer in a millisecond. A proof system is fantastic at convincing skeptics. The interesting engineering puzzle is how to get all three without lying to yourself that they are the same thing.

The Commonware answer? Start from the only piece of data you actually trust after a crash: the record of what happened.

---

## 2. Mental Model

If you only remember one sentence from this entire chapter, make it this one:

> **Start with a log, derive a view, then prove facts about that view.**

If you keep that rhythm in your head, the source code of this crate stops looking like a random pile of modules and starts looking like a symphony.

Imagine we have a key, let's call it `alice`, and her value changes over time:
- assign `alice = 5`
- delete `alice`
- assign `alice = 6`

If you think like someone using a standard SQL database, the only thing that feels "real" is that last line. `alice = 6`. The rest is just stale garbage state.

But if you think like `commonware-storage`, the durable truth is the *entire sequence of events*. The current value (`6`) is merely a **view** derived from that sequence. And a **proof**, when you need to produce one, must connect that answer (`6`) all the way back to an authenticated commitment over that full history.

This gives us a wonderfully clean vocabulary:
- **Log:** The durable, unchangeable record of operations.
- **View:** The clever data structure that turns the log into fast answers.
- **Proof:** The mathematical evidence tying an answer back to a trusted root.

Look at how the modules in the crate map perfectly onto this ladder:
- `journal` is your plain, simple log.
- `archive`, `freezer`, and `index` are different ways to take that durable history and turn it into usable views.
- `merkle::mmr` is the math that turns append-only history into evidence.
- `qmdb` is the climax: it composes all three layers into a proof-bearing database.

Every section that follows is just a different way of playing the same chord: keep the history durable, derive views from it, and export proofs only when someone asks for them.

---

## 3. The Core Ideas

Let's dive into the primitives. We'll start at the bottom and work our way up.

### 3.1 Storage starts by naming the crash boundary

The very first idea in the crate is also one of the most profound: *durability must be explicit*.

Take a look at `storage/src/lib.rs`. You'll find the `Persistable` trait. It says that any storage structure can `commit()`, `sync()`, and `destroy()`. 

```rust
pub trait Persistable {
    type Error;

    // "I promise the state will survive a crash."
    fn commit(&self) -> impl std::future::Future<Output = Result<(), Self::Error>> + Send {
        self.sync()
    }

    // "I promise it will survive a crash AND you won't have to do 
    // messy recovery work when you start back up."
    fn sync(&self) -> impl std::future::Future<Output = Result<(), Self::Error>> + Send;
    
    fn destroy(self) -> impl std::future::Future<Output = Result<(), Self::Error>> + Send;
}
```

This isn't just someone making the code look pretty. It tells you exactly what kind of system you are dealing with. The difference between `commit()` and `sync()` is magnificent! 

`commit()` says, "I wrote it down, it'll survive a crash." But `sync()` is stronger. `sync()` says, "Not only did it survive, but I've organized my desk so perfectly that when I wake up tomorrow, I don't have to do any cleanup work." The crate absolutely refuses to smudge the line between "the bytes are safe" and "the data structure is ready to go." 

Before we ever talk about queries or proofs, we ask the fundamental physics question: where is the durable boundary, and what exactly do we have in our hands when we cross it?

### 3.2 The authenticated journal is the bridge from bytes to proofs

A plain journal explains why append-only history is great for surviving crashes. An *authenticated* journal (`storage/src/journal/authenticated.rs`) explains how that exact same history becomes cryptographic evidence.

It does this by keeping two append-only structures walking side-by-side in perfect lockstep:
1. A contiguous journal of the items (the actual data bytes).
2. A Merkle Mountain Range (MMR) leaf for each item's digest (the math).

The code enforces an unbreakable rule: item *i* in the journal is exactly leaf *i* in the MMR. That is the bridge! Durable bytes on one side, proof-bearing mathematical positions on the other. They advance together.

This is why the batch API is so specific. You don't just "write" data. 
- First, you **stage** what you want to append.
- Then, you **merkleize** it—you compute the root hash *as if* you published it, to see what it would look like.
- Finally, you **finalize** it and **apply** it, making both the journal and the MMR step forward together.

A weaker system would mash all those steps into one `put()` function. By separating them, `commonware-storage` lets you fork speculative states, inspect the math before committing it to disk, and throw away stale work.

### 3.3 The log is still the durable truth

If you open `storage/src/journal/mod.rs`, you'll see an append-only log. Why do we love append-only storage so much? Because it makes failure *legible*. 

If my computer loses power halfway through writing a file, and I was overwriting old data in-place, what do I have when I reboot? A scrambled mess of old and new bytes. I have to guess what it means.

But if I only ever append? A partial write has a crystal-clear shape: "Ah, the history stops perfectly right *here*, and the checksum on this next chunk fails." Recovery isn't a magical repair job anymore; it's just a replay. You don't ask, "What did this database table look like before the crash?" You ask, "What are the durable operations I trust, and what view do they build when I play them back?"

The log is not a backup of your database. **The log is the truth.** The database is just a convenient shadow cast by that truth.

### 3.4 A view is the working answer, not the fundamental truth

Once we have our beautiful, durable log, we have to admit something: reading the whole log every time someone asks a question is ridiculously slow. We need a faster way to answer.

This is where the middle layer of the crate comes in. Modules like `archive`, `freezer`, `cache`, and `queue`. These aren't trying to be "new database engines." They are just different lenses—different ways to build a view over the durable history.

- **Archive:** A write-once store. It knows historical order matters, but mutation doesn't.
- **Freezer:** It keeps lookup structures on disk, refuses to do expensive compactions, and accepts that fetching really old data might be a bit slow. It's a deliberate bargain: how do we keep a view when RAM is tight and rewriting disk is costly?
- **Cache & Queue:** Narrow, hyper-specific views. 

The profound takeaway here is that a "view" doesn't have to be a standard B-Tree index. A view can be a queue cursor, or a map of byte offsets. It’s just a working answer layered on top of the rock-solid history.

### 3.5 An index is a compressed memory of where truth lives

Look at `storage/src/index/mod.rs`. The documentation starts right off the bat warning you that keys can collide. Most libraries hide this from you! They pretend hash collisions don't exist. Not here. 

When you ask the index for a key, it returns *every* value that maps to that translated key. The ambiguity is the point. The index isn't saying, "Here is the exact truth." It is saying, "Here is a shortlist of suspects. Go check the real log to be sure."

By shrinking keys using the `translator.rs` layer, we save massive amounts of memory. But we pay for it with collisions. 

```rust
// In memory: 
// The index might say "Ah, the data you want is probably at location 42 or 45!"
// Then you go to the log on disk, read the actual bytes at 42 and 45, and find the real key.
```

The system remains flawlessly correct because it always falls back to the durable log to resolve the ambiguity. It's a compressed memory of where the truth *probably* lives. 

### 3.6 Proof-bearing state starts when history becomes authenticated

Now we have a log, and we have fast views. The final trick is proving to someone else that we aren't lying.

Enter `storage/src/merkle/mmr/mod.rs`—the Merkle Mountain Range (MMR). What a name! It is an append-only authenticated data structure. You add things to it, and the positions of old nodes *never, ever change*. 

Why is that important? Because it perfectly matches our log! New events are appended. Old events are never rewritten. So when you hand someone a proof, the proof is about a growing, immutable history, not a tree that is constantly shifting its shape. 

The crate has two Merkle families, and they solve two different problems:
- **`bmt` (Binary Merkle Tree):** Great for a *fixed* batch of data. You know exactly how many items there are. It folds up cleanly and commits to the total size.
- **`mmr` (Merkle Mountain Range):** Great for a *growing* log. Appending new history doesn't force you to recalculate the positions of all the old data. 

### 3.7 QMDB is where the three layers snap together

Finally, we arrive at `storage/src/qmdb/mod.rs`. The docs say it plainly:

> *A database's state is derived from an append-only log of state-changing operations.*

That sentence is the entire philosophy of this crate, distilled into pure code. 

QMDB (Quick Merkle Database) composes the three layers we've been talking about:
1. The durable log of operations.
2. The active view (the snapshot).
3. The authenticated MMR to prove facts.

QMDB offers different variants depending on what you actually need to prove:

| Variant | What the state is | What you can mathematically prove | What machinery it requires |
| --- | --- | --- | --- |
| `keyless` | Just values at locations | "This value was written right here in the log." | Authenticated journal |
| `immutable` | Keys that are inserted once | "This key was set to this specific value." | Snapshot + insert-only log |
| `any` | Mutable keys | "This key had this value *at some point in time*." | Snapshot + update/delete logs |
| `current` | Mutable keys, but right now! | "This value is the *latest* value for this key." | Snapshot + bitmaps + grafted MMR |

Pay close attention to `current`. Proving something happened in the past is easy: "Look, here it is in the log." But proving it is the *current* value is incredibly hard! You have to prove that it is in the log, AND you have to mathematically prove that *no later operation ever deleted or changed it*. 

To do that, the system uses a **bitmap** (to track what is active) and **grafts** it onto the MMR. It replaces a normal hash in the tree with a hash that says, `hash(bitmap_chunk || ops_subtree_root)`. It literally intertwines the history (the ops) with the current truth (the bitmap) into a single cryptographic root. It is a stunning piece of engineering.

---

## 4. How the System Moves

Let's put the system in motion and watch how it breathes.

### 4.1 Write path: record, derive, then publish
You want to write something? First, you append it to the durable log. Only *after* the durable record exists on disk do you update the fast in-memory view. 

This means the fast path for queries is the derived view, but if the power goes out, the recovery path knows exactly where the truth is: the log. In QMDB, you stage the batch, merkleize it (speculate the math), apply it (write it), and then sync it to disk. 

### 4.2 Recovery path: replay, realign, rebuild
This is where append-only design shines. The computer crashes. It wakes up. What does it do?
It reads the log. It replays the operations. It rebuilds the snapshot in memory! 

In the source code, the function is literally called `build_snapshot_from_log`. The snapshot is not the stored truth. The snapshot is a house rebuilt from the blueprints found in the log vault. And if the process stopped after `commit()` but before `sync()`, it will neatly realign the MMR and the journal before serving any proofs.

### 4.3 Read path: the view finds the candidate, the log settles it
You want to read a key. We don't scan the whole log! We ask the compressed, memory-efficient Index: "Hey, where might this key be?" The Index gives us a candidate location. Then, we go to the actual durable log, read the bytes, and say, "Ah yes, this is the one." The view suggests; the log dictates.

### 4.4 Proof path: the same search, plus an authenticated ladder
Someone doesn't trust you? You do the same read path, but you attach the math. You find the operation in the history, you find its location, and you pull the Merkle proof (the ladder of hashes) that ties that location all the way up to the universally trusted Root Hash. 

### 4.5 Sync path: target the ops root, rebuild the rest
When you are syncing a node over the network, you don't download the crazy, complicated `current` grafted root first. You sync the raw, fundamental log operations using the standard MMR. Once you have the log downloaded and verified, your local machine *deterministically rebuilds* the bitmaps and the grafted MMR roots on its own! You sync the history, and you derive the state. Beautiful.

### 4.6 Pruning only works if the promise survives
When you delete old data to save disk space, you aren't just deleting bytes. You are messing with history. 

If you prune the journal, you just chop off the old parts. But if you prune QMDB's `current` state, you have to be careful! If you delete old log entries, you must leave behind "pinned digests"—little cryptographic monuments that say, "I threw away the data that used to be here, but here is the hash of what it was, so the tree math still works." You drop what you don't need, but you *never* lie about the structure that remains.

---

## 5. What Pressure It Is Designed To Absorb

Why go to all this trouble? Because real-world storage is squeezed by intense, opposing forces.

1. **Crash pressure:** Things break. Append-only logs and explicit `sync()` boundaries absorb this pressure perfectly.
2. **Memory pressure:** RAM is expensive. Translators and collision-prone indexes absorb this by shrinking keys down to tiny footprints.
3. **Write amplification pressure:** SSDs wear out if you constantly rewrite the same sectors. The `freezer` absorbs this by avoiding compaction.
4. **Proof expressiveness pressure:** Cryptography is heavy. Proving a current state is way harder than proving a historical event. The different QMDB variants let you pay only for the exact amount of "proof power" you actually need.

---

## 6. Failure Modes and Limits

Let's be honest about where this design bends or breaks.

**The log can be damaged.**
Hard drives rot. Cosmic rays flip bits. The journal has checksums to catch this, but if the log is corrupted, the truth is corrupted. Append-only doesn't prevent disk failure; it just makes it highly detectable and localized.

**The view can be ambiguous.**
Because our memory indexes use compressed keys, they have collisions. If you get unlucky (or an attacker crafts keys to collide), your fast view degrades. You have to check the log more often to find the real key. It slows down, but it *never* returns the wrong answer.

**The proof may say less than the application hopes.**
If you use `qmdb::any`, you can prove that "Alice had 5 apples on Tuesday." You *cannot* prove she still has 5 apples today. If you need to prove current state, you must pay the performance tax of `qmdb::current` and its bitmap grafting. You cannot magically extract a strong proof from a weak structure.

**Pruning can destroy meaning.**
If you prune too aggressively and throw away the pinned digests or the bitmap chunks you needed, your database might still be able to answer local reads... but you will suddenly find yourself unable to generate a valid Merkle proof for the network. 

---

## 7. How to Read the Source

If you want to read the code yourself, don't just open a random file. Read it like a climb from the durable bedrock up to the cloudy peaks of cryptography:

1. Open `storage/src/lib.rs`. Look at `Persistable`. Understand the bedrock.
2. Read `storage/src/journal/mod.rs`. This is the purest expression of the log.
3. Browse `archive/mod.rs`, `freezer/mod.rs`, and `index/mod.rs`. See how they derive views from the log to answer different questions.
4. Open `storage/src/merkle/mmr/mod.rs`. Watch the append-only history turn into math.
5. Finally, open `storage/src/qmdb/mod.rs` and read the variants in order (`keyless`, `immutable`, `any`, `current`).

If you jump straight into `qmdb/current`, the bitmap grafting will look like bizarre dark magic. But if you walk the path—log, then view, then proof—it will read like the only logical answer to a fascinating problem.

---

## 8. Glossary

- **Log:** The absolute truth. The durable, append-only sequence of records that survives power failures.
- **View:** A clever trick derived from the log to make queries fast. It is not the source of truth.
- **Proof-bearing state:** A data structure where any answer it gives can be tied to a trusted root hash with a compact proof.
- **Index:** A compressed memory of where data lives. It accepts collisions to save RAM.
- **Authenticated journal:** A log paired with an MMR. As the bytes hit the disk, the proof tree grows alongside it.
- **Grafting:** The genius trick of smashing a bitmap chunk (which says what is currently active) and an ops-MMR root (the history) into a single hash, so you can prove current state.
- **MMR (Merkle Mountain Range):** A tree of hashes perfectly designed for append-only logs because old nodes never change their positions.
- **QMDB (Quick Merkle Database):** A family of databases in this crate that prove facts by deriving their active state entirely from a log of operations.

### Further Reading
- [mmr.html](/home/r/coding/monorepo/docs/blogs/mmr.html)
- [adb-any.html](/home/r/coding/monorepo/docs/blogs/adb-any.html)
