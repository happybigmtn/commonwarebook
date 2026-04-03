# commonware-runtime

## An Advanced Explainer by Richard Feynman

---

## Backgrounder: What a Runtime Is Really Doing

You know, when people first meet async code, they often imagine the runtime as a kind of magical power source. You write `async`, you write `await`, and "the runtime" somehow—behind the curtain—makes everything happen. It's like turning on a light switch. You don't need to know how the power plant works to read a book.

That mental model is perfectly fine to get started. But when you're building systems software—real distributed systems where nodes crash, networks partition, and time is a slippery thing—that vague model isn't good enough. If you're trying to figure out why your distributed database flakes out under load, or why a test fails once every thousand runs, you need to understand the machinery. You need to look inside the box.

A runtime is **not** your application logic. A runtime is the machinery that decides **when** your logic runs, **how long** it's allowed to wait, **what** it is allowed to touch in the outside world, and **what happens** when a task is canceled, delayed, or blows up halfway through writing to disk.

That's a lot of ideas packed into one sentence, so let's unwrap them carefully.

### Start from the Naive Model

The beginner's model of a computer program usually goes like this:

1. Instructions run one after another, in order.
2. If you call a function, the whole thing stops and waits until that function returns.
3. Time just passes in the background, like a ticking clock on the wall.
4. And the computer is mostly doing exactly one thing at a time.

Now, that model isn't wrong for a small, simple toy program. But it shatters into pieces the moment you try to build a network service. 

Suppose you have a node that has to:
- Accept incoming connections from other computers,
- Send heartbeats every second to prove it's alive,
- Retry failed connections,
- Write chunks of data (blocks) to a disk,
- Timeout requests that are taking too long,
- And actually respond to what the user wants to do.

These jobs overlap! While one request is sitting there waiting for a packet from the network, another part of your program should keep running. While one task is sleeping, the others shouldn't stop. As soon as you admit that things overlap, the computer needs a **policy** for choosing what runs next. That policy is one of the runtime's main jobs.

### Why Async Programs Feel Slippery

In ordinary, step-by-step code, if you have a bug, it usually happens the same way every time. But in concurrent code, the exact same logic can be perfectly correct in one situation, and completely wrong in another.

Imagine you have two tasks. 
- Task A sets a flag: `ready = true`.
- Task B waits until `ready` becomes true, and then sends a packet.

If Task A runs first, everything is beautiful. But what if Task B checks the flag *just before* Task A sets it? Task B might think "Oh, it's taking too long" and take a slower path, or throw an error. Add three more tasks, a network timeout, and a disk write, and suddenly you aren't debugging a single sequence of events. You are debugging a whole *space* of possible sequences.

This brings us to the first big lesson of runtime design, and I want you to remember this:

> **Many distributed bugs are just scheduling bugs in disguise.**

The network didn't "randomly" break. The operating system kernel simply delivered one packet before another task had finished writing its state to memory. The clock ticked just enough for a timeout to fire. A cancellation arrived after a page of data was written, but before its checksum was saved. 

The point is not that concurrency is chaotic. The point is that the runtime is making hidden decisions all the time—deciding who goes next, who waits, who gets the network—and those decisions shape what your application experiences as "reality."

### The Outside World is Part of the Bug

Students often draw a sharp line between "logic bugs" (my `if` statement is wrong) and "systems bugs" (the disk is full). But in real software, the outside world leaks into your logic through four main channels:

1. **Time:** Retries, deadlines, heartbeats. They all depend on when timers go off.
2. **Network:** Packets can be delayed, dropped, copied, or scrambled.
3. **Storage:** Writing to a disk can fail before, during, or after the bytes actually hit the platter.
4. **Scheduling:** The task that is ready to run might run *now*, or *later*, or *not at all* before a timeout happens.

If those channels are completely controlled by the host operating system (like Linux or Windows), then when you run a test, you aren't just testing your code. You are co-authoring a performance with the kernel, the hardware clock, and the filesystem. 

That's fine when you're running in production. But it is a nightmare for verification.

### Why "Just Run It a Lot" Fails

When people first try to test async systems, they say: "Let's just run the real thing ten thousand times in a loop." That catches some obvious bugs, but it hits a wall quickly.

First, real time marches on whether your code is ready or not. If a bug only happens during one incredibly specific sequence of events, running it 10,000 times might still miss it.
Second, when it *does* fail, you can't easily reproduce it. You can't ask the operating system, "Hey, can you schedule those four threads exactly the same way you just did?" 
Third, testing specific failures—like what happens if the network drops exactly half the packets, or the disk crashes halfway through writing a checksum—requires much finer control than the real world gives you.

That is why mature systems engineers eventually realize they need simulation and determinism.

### Determinism: A Replayable Universe

When people hear "deterministic runtime," they sometimes think of a toy environment, something too simple to be useful. They miss the point!

A deterministic runtime does **not** mean "there is only one possible schedule." It means the schedule comes from an explicit, mathematical source (like a Random Number Generator, or RNG) instead of the chaotic noise of the operating system. A seeded RNG is still exploring billions of possibilities. The profound difference is that if you use seed `42`, it will do the *exact same thing* every time you run it.

The same is true for simulated time. Logical time isn't fake time. It's time that the runtime controls. The clock only advances from millisecond 10 to millisecond 11 when the runtime says, "Okay, everyone has done what they need to do for this millisecond." That makes timeouts inspectable and repeatable, instead of mysterious.

### The Bridge into Commonware

This brings us to `commonware-runtime`. 

This crate isn't trying to be just another general-purpose async toy. It is solving a very sharp problem: Commonware protocols need to run blazing fast against real production hardware **AND** they need to run in a deterministic, simulated world where scheduling, time, disk failures, and network drops can be mathematically replayed.

So, as we dive into the code, keep three questions in your head:
1. Which part of the outside world is this interface hiding behind a boundary?
2. What correctness property can we suddenly test because that boundary exists?
3. Which decisions remain "live" choices, and which ones become part of our repeatable, deterministic model?

Let's look at how we actually write this in Rust.

---

## 1. One Contract, Two Executors

The magic of the runtime boundary lives in `runtime/src/lib.rs`. The core traits are small, but they carry a lot of weight.

Here is the most important one. Let's look at the Rust syntax carefully:

```rust
pub trait Runner {
    /// Context defines the environment available to tasks.
    type Context;

    /// Start running a root task.
    fn start<F, Fut>(self, f: F) -> Fut::Output
    where
        F: FnOnce(Self::Context) -> Fut,
        Fut: Future;
}
```

**Let's break down the Rust here:**
- `pub trait Runner` means we are defining a shared behavior (a trait) that different types can implement. It's like an interface.
- `type Context;` is an **associated type**. It says, "Whoever implements this `Runner` trait will also provide a specific type called `Context`." In the production runtime, this might hold real network sockets. In the deterministic runtime, it might hold simulated ones.
- `fn start<F, Fut>(self, f: F) -> Fut::Output` is a generic function. It takes ownership of `self` (the runner), and it takes a function `f` of type `F`. It returns whatever the Future `Fut` outputs.
- The `where` clause is where Rust puts its constraints. It says: 
  - `F` must be a function (`FnOnce`) that takes `Self::Context` and returns a `Fut`. 
  - `Fut` must be a `Future` (which is Rust's representation of an async computation).

Notice what this implies: **The application does not own the event loop.** It just gives the runtime a "root future" (your main program logic). The runtime supplies the world around it through the `Context`.

Because of this design, the exact same protocol code can run like this:

```rust
runner.start(|context| async move {
    let child = context.with_label("worker").spawn(|child_ctx| async move {
        child_ctx.sleep(Duration::from_secs(1)).await;
        "done"
    });
    child.await
});
```

And it means two entirely different things depending on the `runner`:
- In the **deterministic runtime**, `sleep` means "register an alarm in our simulated logical clock."
- In the **Tokio runtime** (production), `sleep` means "tell the real operating system to wake this thread up in exactly one real second."

In both cases, `spawn` means "create a child task." And that brings us to lifecycles.

---

## 2. Tasks, Contexts, and the Supervision Tree

A clean mental model for this is:
- A **task** is a future (a piece of work to be done).
- The **executor** polls these futures to make progress.
- A **context** is the runtime identity given to one task.
- And contexts form a **tree**.

When you clone a context in `commonware-runtime`, you aren't just copying data. In Rust, cloning a context creates a *child context* attached to a new node in a supervision tree. 

If a parent task aborts or fails, every child task below it in the tree is automatically aborted. But siblings survive. It's a structured way to ensure that when you shut down a subsystem, you don't leave "orphaned" background tasks running amok, leaking memory and network connections.

---

## 3. The Buffer Story: Ownership, Not Bytes

Most async runtimes talk about "buffers" as if they are just arrays of bytes. But `commonware-runtime` thinks deeply about *ownership* because we have to do zero-copy conversions between reading, modifying, and sending data.

We have two main types:
- `IoBuf` (Immutable - you can only read it)
- `IoBufMut` (Mutable - you can write to it)

Let's look at a fascinating piece of code from `runtime/src/iobuf/pool.rs`. This is how an immutable buffer tries to become mutable again *without copying any memory*:

```rust
pub fn try_into_mut(self) -> Result<PooledBufMut, Self> {
    let Self { inner, offset, len } = self;
    match Arc::try_unwrap(inner) {
        // Preserve the existing readable view:
        Ok(inner) => Ok(PooledBufMut {
            inner: ManuallyDrop::new(inner),
            cursor: offset,
            len: offset.checked_add(len).expect("slice end overflow"),
        }),
        Err(inner) => Err(Self { inner, offset, len }),
    }
}
```

**Let's walk through this Rust magic:**
- `pub fn try_into_mut(self)` takes ownership of the buffer (`self`).
- It destructures itself: `let Self { inner, offset, len } = self;`. Here, `inner` is an `Arc` (Atomic Reference Counted pointer). An `Arc` allows multiple parts of the program to share the exact same data safely.
- `Arc::try_unwrap(inner)` is the critical check. It asks: "Am I the *only* person holding a reference to this data?" 
- If `Ok` (yes, I am the only owner), it means no one else is reading this buffer. Therefore, it is mathematically safe to mutate it! It constructs a `PooledBufMut` (a mutable buffer) using `ManuallyDrop` to manage the memory carefully, keeping the exact same memory layout. No bytes were copied!
- If `Err` (no, someone else has a clone of this `Arc`), it fails and gives you the immutable buffer back.

This isn't just convenience; it's an **ownership protocol**. It allows the runtime to avoid expensive "freeze, clone, copy, rebuild" cycles on hot network paths. You take a buffer from the pool, fill it, freeze it, maybe realize you are the only one holding it, unfreeze it, modify it, and send it. All with zero memory allocations!

---

## 4. Paged Append: Recoverable Storage

Let's talk about storage. The crate uses an offset-based API for storage:
```rust
fn read_at(&self, offset: u64, len: usize) -> ...
fn write_at(&self, offset: u64, bufs: impl Into<IoBufs>) -> ...
```

Why offset-based instead of a continuous stream? Because if the system crashes, a stream hides where the crash happened. `write_at` forces you to be explicit about exactly where bytes are landing.

But the most brilliant piece of engineering is in `runtime/src/utils/buffer/paged/append.rs`. It provides an `Append` wrapper that makes partial, crashed writes recoverable.

Imagine you are appending data to a file. The power goes out. Did the last few bytes make it to disk? Were they corrupted? `Append` solves this by grouping logical bytes into fixed-size physical pages. At the end of every physical page on disk, it writes a **Checksum Record** (a CRC). 

But here's the genius part: what happens if you crash while *rewriting* a partial page? To prevent destroying the old, valid checksum before the new data is safe, the checksum record actually contains **two** slots!

Let's look at how the `Append` structure is initialized when opening a blob from disk:

```rust
pub async fn new(
    blob: B,
    original_blob_size: u64,
    capacity: usize,
    cache_ref: CacheRef,
) -> Result<Self, Error> {
    // 1. Read backward from the end of the file to find the last valid checksum!
    let (partial_page_state, pages, invalid_data_found) =
        Self::read_last_valid_page(&blob, original_blob_size, cache_ref.page_size()).await?;
    
    if invalid_data_found {
        // 2. If we found garbage data at the tail, chop it off immediately.
        let new_blob_size = pages * (cache_ref.page_size() + CHECKSUM_SIZE);
        blob.resize(new_blob_size).await?;
        blob.sync().await?;
    }

    // ... (sets up the memory buffers for new writes)
}
```

**What is this doing?**
Instead of blindly trusting the file length, `read_last_valid_page` walks backward from the end of the file. It checks the CRC of each physical page. 
- If the trailing fragment is too short, it's invalid.
- If the checksum fails, it steps backward again.
- The moment it finds a mathematically valid page, it **truncates** the file right there, throwing away the partially written garbage from the crash.

This is how real databases survive power outages. It's not "append and hope the filesystem synced." It's a concrete, mathematical policy for recovering half-finished writes.

---

## 5. Faulty Storage: Embracing Chaos

Now, how do we test this recovery logic? We don't pull the plug on the server. We use `runtime/src/storage/faulty.rs`. 

In the deterministic runtime, we can tell the simulated storage layer to inject faults. But it doesn't just return an "I failed" error. It models **partial progress**.

When the runtime tells `FaultyStorage` to write 1000 bytes, the seeded RNG might decide: "I'm going to write exactly 213 bytes, sync them to disk, and *then* throw an error." 

This leaves a trace of partial data. And because the RNG is seeded, this exact failure—crashing precisely after byte 213—is **100% reproducible**. If seed `42` crashes after 213 bytes and triggers a bug in your recovery code, you can run seed `42` all day long to debug it. 

Fault injection isn't living in a separate testing universe. It is a fundamental, controllable part of the runtime world.

---

## 6. io_uring: The Fast Path and its Dangers

When you run in production on modern Linux (6.1+), `commonware-runtime` can use `io_uring`. This is a radical shift from standard async I/O. 

Instead of asking the kernel to do something and waiting, `io_uring` sets up two circular queues (rings) shared in memory between your program and the Linux kernel. You push requests (Submission Queue Entries, SQEs) into one ring, and the kernel pushes results (Completion Queue Entries, CQEs) into the other.

But there is a catch—a big one. The runtime has a bounded number of slots for operations in flight. If every slot is occupied by an operation that is waiting for something else to happen (like waiting for a network read, which depends on a write that is stuck in the queue), the ring is full. You can't submit the write because the ring is full of reads! 

This is a **bounded-liveness hazard**. It's a deadlock caused by queue capacity.

The runtime mitigates this by wiring `op_timeout` into network requests. If a read sits there forever blocking the ring, the timeout fires, the operation is canceled, the slot frees up, and the system breathes again. This is exactly the kind of nuance you must understand when building high-performance systems. Fast paths are never free; they come with structural limits that you must respect.

---

## The Big Picture

`commonware-runtime` is best understood not as a library of helpers, but as a strict **discipline**. 

It argues that:
- Task lifecycles should be an explicit tree.
- Time should be something you can control.
- Memory ownership should be visible in the Rust type system to prevent copies.
- Crash recovery shouldn't be an afterthought; it must be designed into the file format.
- Fault injection is just normal physics in a deterministic world.

That is why this crate sits at the bottom of the Commonware stack. It defines the physics of the universe that the rest of the protocols live in. Once you control the physics, you can build systems that don't just run fast—they run correctly, every single time.