# commonware-runtime

## An Advanced Explainer

---

## Backgrounder: What a Runtime Is Really Doing

When people first meet async code, they often imagine the runtime as a kind of magical power
source. You write `async`, you write `await`, and "the runtime" somehow makes everything happen.
That mental model is good enough to get started, but it is too vague for systems work. If you are
trying to understand why distributed software flakes, why tests become irreproducible, or why one
storage bug only appears under load, you need a sharper picture.

A runtime is not your application logic. A runtime is the machinery that decides **when** your
logic runs, **how long** it may wait, **what** it is allowed to touch in the outside world, and
**what happens** when a task is cancelled, delayed, or crashed halfway through a side effect.

That sentence packs several ideas together, so it helps to unwrap them one by one.

### Start from the naive model

The beginner model of a program is usually:

1. instructions run in order,
2. a function call blocks until it returns,
3. time passes in the background,
4. and the computer is mostly doing one thing at once.

That model is not wrong for a small single-threaded toy. It breaks as soon as you build a network
service.

Suppose you have a node that must:

- accept inbound connections,
- send heartbeats every second,
- retry failed dials,
- flush blocks to disk,
- time out stale requests,
- and respond to application commands.

Those jobs overlap. While one request is waiting on the network, another should keep running. While
one task is sleeping, others should not stop. Once you admit overlap, the computer needs a policy
for choosing what runs next. That policy is one of the runtime's main jobs.

### Vocabulary worth getting straight

Several words get blurred together in casual explanations:

- A **task** is one unit of async work.
- A **future** is a computation that may not be ready yet.
- An **executor** polls runnable futures and decides their order.
- A **reactor** notices external events such as readable sockets or expired timers.
- A **scheduler** is the policy that says which ready task runs now and which one runs later.
- A **timer wheel** or **sleep heap** is a data structure for future wakeups.
- **Cancellation** means a task stops before it reaches its normal return point.
- **Backpressure** means some producer must slow down because the consumer or buffer is full.

Different ecosystems draw those boundaries differently, but the broad picture stays the same. A
runtime is coordinating a large set of partially finished computations around a stream of outside
events.

### Why async programs feel slippery

In ordinary sequential code, one bug usually has one trace. In concurrent code, the same logic can
be correct in one interleaving and wrong in another.

Imagine two tasks:

- task A sets `ready = true`,
- task B waits until `ready` becomes true and then sends a packet.

If A runs first, the system looks fine. If B checks before A publishes the flag, B may time out or
take a slower path. Add three more tasks, a timeout, and one disk write, and now you are no longer
debugging a single trace. You are debugging a space of possible traces.

This is the first big lesson of runtime design:

> Many distributed bugs are scheduling bugs in disguise.

The network did not "randomly" break. The kernel delivered one packet before another task had
flushed state. The clock advanced enough for a timeout to fire. A cancellation arrived after a data
page was written but before its metadata was synced. The point is not that concurrency is chaotic.
The point is that the runtime is making hidden decisions all the time, and those decisions shape
what the application experiences as reality.

### The outside world is part of the bug

Students often separate "logic bugs" from "systems bugs" too sharply. In real software, the
outside world leaks into the logic layer through four main channels:

- **Time**: retries, deadlines, leases, heartbeats, and pacing logic all depend on when timers
  fire.
- **Network**: packets can be delayed, dropped, duplicated, or reordered.
- **Storage**: writes can fail before, during, or after bytes become visible.
- **Scheduling**: one runnable task may run now, later, or not at all before a timeout matures.

If those channels are controlled entirely by the host operating system, then your test environment
is not just running the program. It is co-authoring each execution with the kernel, the clock, and
the filesystem.

That is fine for production. It is a problem for verification.

### Why naive testing stops working

A common first strategy for testing async systems is: "run the real thing a lot." This catches
some bugs, but it has three serious limits.

First, coverage is weak. Real time advances whether your code is ready or not. If a race depends on
one exact interleaving, repeating a live test ten thousand times may still miss it.

Second, failures are hard to replay. If a test fails only when the kernel schedules four tasks in a
particular order, you cannot easily ask the OS to "do that again, exactly."

Third, fault injection becomes expensive. If you want to test a crash between the data write and
the checksum write, or a partition where only half the links drop, or a timeout that matures just
before a child task publishes a result, you need much finer control than the live world offers.

That is why mature distributed systems eventually move toward simulation, determinism, or both.

### Determinism is not the same as single-threaded simplicity

When people hear "deterministic runtime," they sometimes imagine a toy environment that is too
simple to teach anything useful. That misses the point.

A deterministic runtime does **not** mean "there is only one possible schedule." It means the
schedule comes from an explicit, reproducible source rather than from ambient operating-system
entropy. A seeded random scheduler is still exploring many interleavings. The difference is that
seed `42` can be replayed.

The same is true for simulated time. Logical time is not fake time. It is time whose advancement is
defined by the executor. A test can advance from millisecond 10 to millisecond 11 only when the
runtime says so. That makes timeout behavior inspectable instead of mysterious.

And the same is true for storage or networking. In-memory implementations are not trying to pretend
they are a real disk platter or a real WAN. They are trying to expose the semantics the protocol
cares about:

- can a write be partial?
- can a packet arrive late or not at all?
- can this actor observe time passing before another actor publishes state?

If the answer matters to correctness, the runtime should model it directly.

### Cancellation and structured lifetime

Another naive intuition is that background tasks are basically free. Spawn one more worker. Spawn a
heartbeat loop. Spawn a retry task. If the parent goes away, surely the children will sort
themselves out.

That is how programs end up with orphaned work.

Structured concurrency is the idea that tasks should have a clear ownership tree. If a parent task
is responsible for a subtree of work, then killing the parent should also kill that subtree. If not,
timeouts, retries, and cleanup code become impossible to reason about. A child may still be
writing to storage after the parent believes shutdown is complete. A timer may still fire after the
state it was meant to guard has already been dropped.

So a good runtime is not just an I/O abstraction. It is also a lifetime discipline.

### Capability boundaries matter

One more conceptual move separates a reusable systems runtime from a pile of helpers: do not let
application code touch the world arbitrarily. Hand it a capability object instead.

Why does that matter?

Because "call global clock now," "open any file path," and "spawn any detached thread" are hard to
control in tests. A capability-bearing context can say:

- this is the clock you may use,
- this is the storage namespace you may open,
- this is how you spawn children,
- this is how metrics and tracing labels are inherited.

Once those capabilities flow through an explicit context, the same protocol body can run against a
simulator or against production backends without changing its logic. The task asks for "sleep," not
"Tokio sleep specifically." It asks to open a blob in a partition, not to open an arbitrary path on
the host filesystem.

That design makes code portable, but more importantly, it makes code testable.

### The main tradeoffs

Runtime design is full of tradeoffs. There is no single perfect point.

- A **live runtime** gives real sockets, real disks, and realistic contention, but less control.
- A **deterministic runtime** gives replay and fault injection, but it must choose what semantics to
  model explicitly.
- A **shared thread pool** is convenient, but hidden coupling between unrelated tasks is easier to
  create.
- **Detached tasks** can improve throughput, but they blur ownership and shutdown behavior.
- **Global time** is simple to call, but explicit logical time is far easier to test.

Good systems libraries do not eliminate those tradeoffs. They expose them cleanly and make the safe
choice easy.

### The bridge into Commonware

That is the conceptual backdrop for `commonware-runtime`.

The crate is not trying to be yet another general-purpose async ecosystem. It is solving a sharper
problem: Commonware protocols need to run against real production backends **and** against a
deterministic world where scheduling, time, storage faults, and network behavior can be replayed.

So as you read the rest of this chapter, keep three questions in mind:

1. Which part of the outside world is this interface pulling behind an explicit boundary?
2. Which correctness property becomes testable once that boundary exists?
3. Which runtime decisions remain live-policy choices, and which are now part of the protocol's
   reproducible model?

With that framing in place, the specific Commonware mechanisms stop looking like a bag of executor
plumbing and start looking like a coherent answer to the central systems question: how do you keep
concurrent protocol code honest when the outside world is allowed to misbehave?

---

## 1. Why This Runtime Exists

Most distributed bugs are not mysterious. They are scheduling bugs wearing a disguise.

A timeout fires one poll earlier than usual. A packet arrives before a sibling task has published
state. A write reaches durable storage, but the checksum update does not. A test passes 8,000
times, fails once, and then passes again. That is not "randomness" in the abstract. It is a system
borrowing decisions from the outside world:

- the kernel picks which task runs first,
- the clock decides when a timeout matures,
- the allocator decides when memory gets reused,
- storage decides how much of a write survives a crash,
- and the network decides which messages are late, dropped, or reordered.

`commonware-runtime` is built around one move: pull those decisions behind an explicit interface so
the same application logic can run in two worlds.

- In `deterministic::Runner`, the world is simulated and replayable. Scheduling comes from a seeded
  RNG. Time is logical. Storage and network are in-memory. Faults are injectible and repeatable.
- In `tokio::Runner`, the world is live. Threads are real. Sockets are real. Storage is the local
  filesystem. Optional `io_uring` backends turn the same traits into kernel I/O.

That split is not a portability trick. It is the core engineering idea of the crate. Protocol code
should describe what work needs to happen. The runtime should decide how that work is driven,
observed, and tested.

---

## 2. One Contract, Two Executors

The runtime boundary lives in `runtime/src/lib.rs`. The important traits are small:

- `Runner` starts the world.
- `Context` is the task's capability object.
- `Spawner`, `Clock`, `Network`, and `Storage` describe what a task may ask the outside world to do.
- `Blob`, `Sink`, and `Stream` are the handles returned by those capabilities.

The shape of `Runner` tells the whole story:

```rust
pub trait Runner {
    type Context;

    fn start<F, Fut>(self, f: F) -> Fut::Output
    where
        F: FnOnce(Self::Context) -> Fut,
        Fut: Future;
}
```

The application does not own an event loop. It contributes a root future. The runtime supplies the
world around it.

That is why the exact same protocol body can run here:

```rust
runner.start(|context| async move {
    let child = context.with_label("worker").spawn(|child_ctx| async move {
        child_ctx.sleep(Duration::from_secs(1)).await;
        "done"
    });
    child.await
});
```

and mean two very different things:

- in the deterministic runtime, `sleep` means "register an alarm in logical time";
- in the Tokio runtime, `sleep` means "schedule a real timer on Tokio";
- in both cases, `spawn` means "create a child task in the supervision tree."

That last point matters. The runtime boundary does not only abstract I/O. It also abstracts task
lifetime.

And the label is not cosmetic. In the deterministic runtime, `with_label(...)` gives the task a
stable place in the supervision tree and in the event trace the runtime audits. Tests can then ask
for `context.auditor().state()` and get a compact digest of what happened, not just a vague claim
that "seed 42 failed once."

That same runtime also exposes `start_and_recover()`, which returns a checkpoint carrying the
auditor, RNG, clock, storage, and other executor state forward into the next run. Crash-recovery
tests are therefore ordinary runtime executions: run until a checkpoint, resume from it, and verify
that the protocol still behaves correctly.

---

## 3. Tasks, Contexts, and the Supervision Tree

The clean mental model is:

- a task is a future,
- the executor polls futures,
- a context is the runtime identity attached to one task,
- and contexts form a tree.

Both runtimes store roughly the same context fields:

```rust
pub struct Context {
    name: String,
    attributes: Vec<(String, String)>,
    scope: Option<Arc<ScopeGuard>>,
    network: ...,
    storage: ...,
    tree: Arc<Tree>,
    execution: Execution,
    instrumented: bool,
}
```

The subtle field is `tree`. `Context::clone()` is not a cheap copy in the logical sense. In both
`deterministic.rs` and `tokio/runtime.rs`, cloning a context calls `Tree::child(&self.tree)` and
creates a new node in the supervision structure. The label may stay the same, but the lifetime
relationship changes.

`Tree` itself is deliberately small:

- each node holds a strong reference to its parent,
- each node holds weak references to its children,
- each node may hold one abort handle for the task attached to that node,
- aborting a node drains its child list and recursively aborts descendants.

The parent strong reference is easy to overlook. It exists so "unspawned" child contexts still
keep ancestry alive long enough for abort cascades to work. The child references are weak so the
tree does not leak when tasks finish normally.

The runtime therefore gives you structured concurrency in a very specific sense:

- if a parent subtree is aborted, every descendant is aborted;
- siblings survive;
- the tree is about lifetime ownership, not restart strategy.

That last clause is worth saying plainly. `Tree` is not an Erlang-style supervisor with policies
like "one-for-one restart." It is the raw cancellation skeleton that higher-level policies build
on.

---

## 4. Deterministic Execution Is a Scheduler, Not a Mock

The deterministic runtime is easiest to understand if you stop thinking of it as "fake Tokio" and
start thinking of it as a seeded event loop.

Its world state includes:

- a ready queue of runnable task IDs,
- a map of running tasks,
- a min-heap of sleepers,
- a logical clock,
- an auditor,
- and a shared RNG.

The loop is conceptually:

```text
1. Drain ready task IDs.
2. Shuffle them with the seeded RNG.
3. Poll each task once.
4. Advance logical time by one cycle.
5. Wake sleepers whose deadlines have passed.
6. Panic if nothing can ever make progress.
```

Two details are especially important.

First, the scheduler only randomizes one thing on purpose: the order of equally-ready tasks in a
cycle. That is enough to explore interleavings without making replay impossible.

Second, the same RNG is also threaded into injected storage faults. In `deterministic::Context::new`
the executor creates one shared seeded RNG and passes it both to the executor state and to
`FaultyStorage`. That means task interleavings and crash faults inhabit one deterministic world.
The seed is not just "task order." It is a reproducible execution universe.

This is why replay works well in practice. If seed `42` causes task A to flush just before task B
times out, and also causes the second storage write to become partial, seed `42` will do it again.

That turns deterministic execution into more than a convenience for tests. It becomes the repo's
reproducibility protocol. The strongest Commonware tests usually do three things together:

1. label the task tree with `with_label(...)` so the schedule has a readable shape,
2. return `context.auditor().state()` so the observed interleaving leaves a compact witness,
3. use `start_and_recover()` when recovery matters so crash boundaries are replayed, not
   paraphrased.

The ResearchClaw pass kept surfacing two generic weaknesses in systems evaluation: inconsistent
protocols and vague failure reporting. This runtime is Commonware's answer to both. It gives the
rest of the repository one clock, one scheduler, and one replay story, so later chapters can talk
about failure cases as repeatable executions rather than as folklore.

---

## 5. The Real Buffer Story: Ownership, Not Bytes

Most async runtimes talk about "buffers" as if the word meant one thing. `commonware-runtime`
spends real design effort on this because the crate has to support:

- cheap cloning of immutable payloads,
- mutable build-up of outgoing messages,
- scatter-gather I/O,
- pool-backed aligned allocations,
- and zero-copy conversion between mutable and immutable views when ownership permits.

### `IoBuf` and `IoBufMut`

`IoBuf` is immutable. It is backed by either:

- `bytes::Bytes`, or
- `PooledBuf`, which is a reference-counted view into an aligned pooled allocation.

`IoBufMut` is the mutable counterpart. It is backed by either:

- `bytes::BytesMut`, or
- `PooledBufMut`, which owns a mutable aligned allocation that may later return to the pool.

The normal write path is:

```rust
let mut buf = pool.alloc(4096);
buf.put_slice(payload);
let frozen: IoBuf = buf.freeze();
```

`freeze()` matters because it converts "mutable builder" into "shareable immutable payload" without
copying. If the buffer came from the pool, the frozen `IoBuf` still refers to the same allocation,
and that allocation returns to the pool only when the last immutable owner disappears.

### Why `try_into_mut` Exists

The most interesting method in this part of the crate is `IoBuf::try_into_mut`.

It succeeds only when the buffer has unique ownership of its backing storage. For `Bytes`, that
inherits `Bytes::try_into_mut` semantics. For pooled buffers, the implementation tries to unwrap
the `Arc<PooledBufInner>` and recover a `PooledBufMut` with the same readable window.

That last clause is subtle and useful. A uniquely owned *slice* of a pooled buffer can become
mutable again without copying. The pool representation tracks:

- the allocation start,
- the readable view offset,
- and the readable length.

So a slice can preserve its view while still recovering exclusive mutable ownership.

This is an ownership protocol, not a convenience method. It lets the runtime avoid unnecessary
"freeze, clone, copy, rebuild" churn on hot paths.

### Slices and Empty Views

The pooled implementation also makes a careful choice around empty ranges:

- slicing a pooled buffer to a non-empty range is zero-copy;
- slicing it to an empty range detaches to an empty `IoBuf::default()`.

That avoids pinning a large pooled allocation behind an empty logical view.

### `IoBufs` and `IoBufsMut`

The runtime also makes vectored I/O explicit. `IoBufs` and `IoBufsMut` are containers for one or
more chunks. They use a canonical small-shape representation:

- `Single` for zero or one chunk,
- `Pair` for two chunks,
- `Triple` for three chunks,
- `Chunked(VecDeque<...>)` only for four or more chunks.

That shape matters because the common case should stay cheap without making
unusual inputs awkward to represent.

The key contract shows up in `Blob::read_at_buf`: the implementation must fill caller-provided
buffer storage and preserve the chunk layout. That makes it possible to recycle pooled buffers
across reads instead of allocating fresh storage every time.

In other words, the runtime's buffer design is not "here is a nicer `Vec<u8>`." It is a way of
making allocation policy, sharing, mutability, and vectored layout visible in the type system.

---

## 6. Buffer Pools: Reuse, Alignment, and Policy

`runtime/src/iobuf/pool.rs` turns that ownership model into an allocation policy.

The pool is built from:

- power-of-two size classes from `min_size` to `max_size`,
- one lock-free `ArrayQueue` freelist per class,
- aligned heap allocations,
- weak back-references from buffers to the pool.

The weak back-reference gives the pool a nice shutdown property: if the pool is dropped while
buffers are still alive, those buffers remain valid and deallocate directly when dropped. They do
not try to return into a dead structure.

### The Two Presets

The crate defines two presets because network I/O and storage I/O want different tradeoffs.

`BufferPoolConfig::for_network()`:

- uses cache-line alignment,
- tracks classes up to 64 KiB,
- allows many buffers per class (`4096` by default),
- is tuned for many concurrent smaller allocations.

`BufferPoolConfig::for_storage()`:

- uses page alignment,
- tracks classes up to 8 MiB,
- allows far fewer buffers per class (`32` by default),
- is tuned for direct-I/O-friendly, larger allocations.

This is a concrete example of the runtime refusing to pretend that "a buffer is a buffer." Network
paths want breadth. Storage paths want aligned depth.

### What Happens on Oversize

There are two allocation APIs worth distinguishing:

- `try_alloc` fails with `PoolError::Oversized` or `PoolError::Exhausted`,
- `alloc` falls back to an untracked aligned heap allocation when the request is too large or the
  pool is exhausted.

So the pool is not a hard cap unless the caller asks it to be. The tracked pool handles the common
case. Fallback allocations preserve correctness when demand spikes.

### Budgeting

`with_budget_bytes` does not enforce a hard global byte limit. Instead it computes how many buffers
per class would approximately fit the budget if every class were equally provisioned:

```text
max_per_class = ceil(budget / sum(all_class_sizes))
```

That can overshoot the target in practice, because the pool always rounds up to at least one buffer
per class. Again, the runtime chooses a simple explicit rule over a clever opaque one.

---

## 7. Offset-Based Storage and Why It Matters

The storage API is offset-based:

```rust
fn read_at(&self, offset: u64, len: usize) -> ...
fn write_at(&self, offset: u64, bufs: impl Into<IoBufs> + Send) -> ...
fn resize(&self, len: u64) -> ...
fn sync(&self) -> ...
```

That seems mundane until you notice what it enables naturally:

- append-only logs,
- sparse rewrites,
- page caches,
- crash recovery formats,
- partial-write simulation.

A streaming `Read`/`Write` interface would hide the exact byte position where a crash landed.
`Blob` makes the position part of the contract.

Every blob also starts with a tiny fixed header:

```text
0..4  magic           = b"CWIC"
4..6  runtime_version = u16
6..8  blob_version    = u16
```

That header is the first crash filter. If a blob is shorter than 8 bytes on open, `Header::missing`
classifies it as absent or incompletely initialized and the storage layer rewrites a fresh header.
If the magic is wrong, the runtime treats that as corruption instead.

Short is recoverable initialization failure. Wrong magic is corrupted content. The distinction is
small but important.

---

## 8. Paged Append: How the Runtime Makes Partial Writes Recoverable

The most underappreciated storage code in the crate is
`runtime/src/utils/buffer/paged/append.rs`.

This wrapper takes an ordinary `Blob` and gives it a much stronger story for append-heavy use
cases:

- data is buffered logically,
- persisted physically in fixed-size pages,
- each physical page ends with a checksum record,
- recovery can walk backward and discard only the invalid tail.

### The Basic Layout

`Append<B>` keeps four pieces of state:

- `blob_state`: the underlying blob, the current page number, and the state of any previously
  committed partial page;
- `buffer`: the in-memory tip that has not been fully flushed yet;
- `cache_ref`: a page cache handle for concurrent reads;
- `id`: the cache identity of this append stream.

Logical bytes are grouped into fixed-size pages. Each physical page on disk is:

```text
[logical page bytes][checksum record]
```

The checksum record is not just one CRC. It stores two `(length, crc)` slots. That design supports
safe rewriting of a partial page.

### Why There Are Two CRC Slots

Suppose the last committed page on disk was partial. You want to append more data into that same
logical page. The dangerous part is not the new bytes. The dangerous part is replacing the old
authoritative checksum too early.

The code handles this by preserving the old CRC in one slot and writing the new CRC into the other
slot. `identify_protected_regions` decides which slot must remain untouched until the new write has
landed safely enough.

That is why `flush_internal` sometimes splits the first-page write into two physical writes instead
of blasting the whole first page in one go. The first write updates only the new data region. The
second write lands the alternate CRC slot and the remaining pages. If the process dies in the
middle, the old CRC still authenticates the previously committed page state.

This is the core crash-safety trick of the module. The checksum record is not only an integrity
check. It is also a commit protocol for partial-page rewrites.

### What `flush_internal` Actually Does

The flow is:

1. Cache the soon-to-be-written bytes in the page cache so concurrent readers can still see them.
2. Read the old partial-page state, if any.
3. Convert logical buffered bytes into physical pages with checksum records.
4. Drain or trim the in-memory tip so only the unwritten suffix remains buffered.
5. Update `current_page` and `partial_page_state`.
6. Write the physical pages, possibly in two pieces if an old partial page needs protection.

The code updates blob state before the write, which looks scary until you remember the repository's
storage rule: mutable operation errors are fatal. After a failed `write_at`, callers must not keep
using that blob as if nothing happened.

### Recovery on Reopen

Initialization does not trust the tail of the blob blindly. `read_last_valid_page` walks backward
from the end in physical-page-sized steps:

- if the trailing fragment is too short to contain a full physical page, it is invalid;
- if the last full physical page fails checksum validation, keep walking backward;
- when the first valid page is found, truncate everything after it.

If the last valid page is itself partial, `Append::new` pulls its logical data back into the
in-memory tip and remembers the CRC record. That means the append layer restarts exactly where it
should: after the last checksum-validated byte, not after the last raw file length.

This is stronger than "append and hope fsync wins." It is a concrete policy for recovering from
half-finished page writes.

---

## 9. Faulty Storage: Failure as Part of the Model

`runtime/src/storage/faulty.rs` turns storage faults into a deterministic part
of the runtime model.

The config can independently target:

- `open`,
- `read`,
- `write`,
- `sync`,
- `resize`,
- `remove`,
- `scan`.

The interesting part is not that failures exist. It is that partial progress
is modeled explicitly.

For writes:

- the wrapper computes the total byte count,
- may choose a random intermediate byte count,
- writes only that prefix,
- calls `sync`,
- updates tracked size,
- then returns an error.

For resizes, it can do the same thing with an intermediate length.

That is exactly the failure mode recovery code tends to under-test. A polite failure that leaves no
trace is easy. A failure that leaves *some* bytes durable is the real problem.

Because this wrapper is fed by the same seeded RNG in the deterministic runtime, "partial write
after 213 bytes" is reproducible, not merely possible.

This is one of the best examples of the crate's general philosophy: fault injection should not live
in a separate testing universe. It should be just another part of the runtime world.

---

## 10. Tokio Runtime: The Production Architecture

`runtime/src/tokio/runtime.rs` is the production form of the same contract.
It assembles Tokio, metrics, buffer pools, and backend selection into one
runtime that still looks like the abstract traits the rest of the crate uses.

`Runner::start` does this in order:

1. creates the root metrics registry,
2. builds a multi-thread Tokio runtime,
3. creates the panic policy wrapper,
4. starts process-metric collection,
5. creates separate network and storage buffer pools,
6. selects storage and network backends with `cfg_if!`,
7. wraps those backends in metered adapters,
8. constructs the root `Context`,
9. runs the root future under the panic interrupter.

Several choices here are worth calling out.

### Separate Network and Storage Pools

The production context carries both `network_buffer_pool` and `storage_buffer_pool`. That means the
same task can reach for the right allocation policy without guessing. Storage paths get
page-aligned buffers. Network paths get cache-line-aligned ones.

### Backend Selection Happens at Compile Time

The runtime chooses backends with feature flags:

- `iouring-storage` selects `storage::iouring`,
- otherwise it uses `storage::tokio`;
- `iouring-network` selects `network::iouring`,
- otherwise it uses `network::tokio`.

The application still sees the same `Storage` and `Network` traits. The executor decides which
concrete implementation sits behind them.

### Spawn Modes Matter

The context supports three execution modes:

- default shared async execution via `runtime.spawn`,
- shared blocking execution via `runtime.spawn_blocking`,
- dedicated OS-thread execution via `thread::spawn(... handle.block_on(...))`.

That is a practical separation:

- most protocol tasks want ordinary shared async scheduling,
- some CPU-heavy or blocking-adjacent work should move to Tokio's blocking pool,
- a few long-lived tasks deserve a dedicated thread.

### Shutdown Is Signaled, Not Assumed

`stop` does not kill the process. It triggers the shared `Stopper`, then waits for tasks to notice
the signal and drop their handles, optionally with a timeout. This matches the rest of the crate:
ownership and explicit lifecycle come before convenience.

### The Default Network Policy Is Adversarial

The default Tokio network config sets:

- `TCP_NODELAY = true`,
- `SO_LINGER = Some(Duration::ZERO)`,
- `read_write_timeout = 60s`.

That `SO_LINGER` default is intentional. Immediate close with RST is useful in adversarial systems
that want to reclaim sockets from misbehaving peers quickly instead of lingering in `TIME_WAIT`.

---

## 11. io_uring: Fast Path, Separate Event Loop, Real Caveats

The `io_uring` support is not a minor optimization layer. It introduces a second executor-like
subsystem inside the runtime.

### The Core Loop

`runtime/src/iouring/mod.rs` builds a dedicated event loop around one ring:

- submitters push operations into a bounded MPSC queue,
- an internal `eventfd` wakes the loop when new work arrives,
- the loop drains completions,
- stages SQEs,
- submits them,
- blocks in `io_uring_enter`,
- then routes CQE results back over oneshot channels.

Each in-flight operation occupies a waiter slot that stores:

- the completion sender,
- any buffer that must stay alive,
- any file descriptor handle that must stay alive,
- and any timeout state that must stay alive.

That design is about memory safety as much as speed. The kernel receives pointers into user memory.
The runtime therefore has to keep those buffers and FDs alive until the CQE arrives.

### What the Production Backends Actually Do

The two `io_uring` backends are not identical.

`network::iouring`:

- starts **two** dedicated rings, one for send and one for recv;
- forces `single_issuer = true`;
- warns that ring size must be chosen with connection concurrency in mind;
- carries a per-connection read buffer and a pool for recv allocations.

`storage::iouring`:

- starts one dedicated ring;
- also forces `single_issuer = true`;
- still handles some filesystem metadata work outside the ring, such as syncing directories after
  create/remove, because durable directory-entry updates are a separate filesystem concern.

So `io_uring` is not replacing the entire storage semantics. It is accelerating the data path while
the storage layer still owns correctness details like headers and directory durability.

### Effective Kernel Requirement

The generic `iouring` module documents:

- kernel 5.13+ for the multishot-poll wake path,
- kernel 6.1+ when `single_issuer` is enabled with deferred task run.

The runtime backends enable `single_issuer`, so the effective requirement for the production
`io_uring` backends is Linux 6.1 or newer.

### The Liveness Caveat You Should Actually Remember

This part deserves more than a footnote.

The `io_uring` loop enforces a bound on in-flight operations. If every waiter slot is occupied, the
loop cannot stage more queued work until some in-flight operation completes or is canceled.

That creates a real bounded-liveness hazard:

1. the first N operations fill the ring,
2. those operations are all waiting on work that is still queued behind them,
3. the queued work cannot be submitted because capacity is full,
4. nothing completes, so capacity never frees.

The documentation gives a concrete example with reads occupying all slots while the writes they
depend on are still queued.

This is not a bug in a small corner of the implementation. It is a structural limit of bounded
submission without dependency awareness.

The practical mitigation is cancellation via per-operation timeouts.

There is an important runtime-level detail here:

- the Tokio **network** backend wires both `op_timeout` and `shutdown_timeout` to
  `read_write_timeout`,
- the Tokio **storage** backend currently starts `IoUringStorage` with
  `iouring::Config::default()`, which means no per-op timeout and no shutdown timeout unless the
  storage backend is constructed differently.

So the network path ships with a liveness backstop. The storage path, by default, relies more on
workload structure. If in-flight storage operations can depend on later queued storage operations,
callers must reason about that carefully.

This is exactly the kind of production caveat a runtime chapter should surface. Fast paths are not
free. They come with concurrency structure that the caller has to respect.

---

## 12. How to Read the Runtime Source

If you want to turn this chapter back into code, read the crate in this order:

1. `runtime/src/lib.rs`
   Learn the public contract first: `Runner`, `Spawner`, `Clock`, `Network`, `Storage`, `Blob`,
   and the `read_at_buf` contract.

2. `runtime/src/deterministic.rs`
   Read `Config`, `Context::new`, the task structures, the sleeper queue, and the executor loop.
   That gives you the replayable world.

3. `runtime/src/utils/supervision.rs`
   Read `Tree` after `Context`, not before. Then it is obvious why cloning a context changes task
   lifetime.

4. `runtime/src/iobuf/mod.rs` and `runtime/src/iobuf/pool.rs`
   Read these as one subsystem. The point is ownership and layout, not syntax.

5. `runtime/src/storage/mod.rs`
   Read the header logic before the backends. It defines what "a valid blob" means.

6. `runtime/src/utils/buffer/paged/append.rs`
   Read this when you want to understand how the runtime turns offset-based blobs into crash-safe
   append structures.

7. `runtime/src/storage/faulty.rs`
   Read this after append and header handling so the partial-failure knobs mean something concrete.

8. `runtime/src/tokio/runtime.rs`
   Read this to see how the production stack is assembled from pools, telemetry, and backend
   selection.

9. `runtime/src/iouring/mod.rs`
   Read this last. It is easiest to understand once you already care about buffer lifetimes, FD
   lifetimes, and bounded-liveness tradeoffs.

That order follows the argument of the crate:

- first define the world,
- then make it replayable,
- then make I/O ownership explicit,
- then make storage recoverable,
- then make production fast without hiding the caveats.

---

## 13. The Big Picture

`commonware-runtime` is best understood as a discipline for making
scheduling, ownership, and recovery explicit.

It says:

- task lifetime should be explicit,
- time should be controllable,
- I/O ownership should be visible,
- crash recovery should be designed into the format,
- fault injection should be ordinary,
- and fast production paths should come with clear liveness rules.

That is why the crate matters so much to the rest of Commonware. It does not only run the other
primitives. It defines what sort of claims those primitives are allowed to make about scheduling,
durability, recovery, and reproducibility.
