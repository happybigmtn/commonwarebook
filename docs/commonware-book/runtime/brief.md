# Chapter Brief: commonware-runtime

## 1. Module Purpose

`commonware-runtime` separates async application logic from the machinery that drives it. The same
protocol code can run under a replayable deterministic executor or under a production Tokio-based
runtime with real sockets, real storage, telemetry, and optional `io_uring`. The chapter should
teach that this crate is not only an executor abstraction. It is the place where Commonware makes
explicit choices about task lifetime, logical time, buffer ownership, crash recovery, and
fault-injection semantics.

The updated chapter should stay concept-first and lecture-like, but it now needs to spend much more
time inside the code that carries the runtime's real weight:

- the `IoBuf` / `IoBufMut` ownership model and vectored forms,
- the buffer pool's size-class and alignment policy,
- page-oriented append with checksum-based recovery,
- deterministic storage fault injection,
- the supervision tree as structured cancellation,
- and the production Tokio plus `io_uring` architecture, including its liveness caveat.

---

## 2. Source Files That Matter Most

### `runtime/src/lib.rs`

**Why it matters:** Defines the public contract: `Runner`, `Spawner`, `Clock`, `Network`,
`Storage`, `Blob`, and the buffer-pool capability surface. The chapter should ground every runtime
claim in these traits before dropping into implementations.

### `runtime/src/deterministic.rs`

**Why it matters:** Shows how the abstract contract becomes a seeded scheduler with logical time,
an auditor, in-memory I/O, and shared seeded fault injection. This file explains why replay works
and why the same seed controls both scheduling and injected storage failures.

### `runtime/src/iobuf/mod.rs`

**Why it matters:** This is the runtime's actual I/O ownership vocabulary. `IoBuf` and `IoBufMut`
are not wrapper types for `Vec<u8>`. They encode immutable vs mutable ownership, pooled vs
`Bytes`-backed storage, zero-copy slicing, and recovery of mutable ownership via `try_into_mut`.
`IoBufs` and `IoBufsMut` make vectored I/O and chunk-layout preservation explicit.

### `runtime/src/iobuf/pool.rs`

**Why it matters:** Defines the aligned buffer pool, its power-of-two size classes, lock-free
freelists, tracked vs untracked allocations, and the separate network/storage presets. This file is
where the runtime turns the buffer ownership model into an allocation policy.

### `runtime/src/storage/mod.rs`

**Why it matters:** Defines the `Header` format and the distinction between missing headers,
corrupted headers, and version mismatches. The chapter should use this file to explain why short
blobs are recoverable initialization failures while wrong magic is treated as corruption.

### `runtime/src/utils/buffer/paged/append.rs`

**Why it matters:** Carries much of the runtime's storage sophistication. It turns an offset-based
blob into a page-oriented append structure with buffered writes, read caching, dual-CRC commit
records for partial-page rewrites, and backward recovery that truncates only the invalid tail.

### `runtime/src/storage/faulty.rs`

**Why it matters:** Makes faults part of the runtime model instead of a separate mock layer. It can
inject deterministic failures into open/read/write/sync/resize/remove/scan and, more importantly,
simulate partial writes and partial resizes that leave durable traces behind.

### `runtime/src/utils/supervision.rs`

**Why it matters:** Implements the task lifetime skeleton. Each cloned context becomes a child node
in a tree; aborting a node drains its descendants but leaves siblings alive. This is structured
cancellation, not a restart strategy.

### `runtime/src/tokio/runtime.rs`

**Why it matters:** Assembles the production stack. It builds the Tokio runtime, metrics registry,
process metrics collector, network and storage buffer pools, backend selection, panic policy, and
spawn-mode behavior. This file is the right place to explain how production differs from the
deterministic world.

### `runtime/src/iouring/mod.rs`

**Why it matters:** Defines the dedicated `io_uring` event loop, waiter bookkeeping, eventfd wake
path, and the bounded-liveness caveat. The chapter should use this file to explain both why the
fast path is fast and why the ring's bounded capacity creates dependency-sensitive deadlock risk.

### `runtime/src/network/iouring.rs` and `runtime/src/storage/iouring.rs`

**Why they matter:** Show how the generic `io_uring` loop is embedded into real runtime backends.
The network backend uses separate send and recv rings with timeouts derived from
`read_write_timeout`. The storage backend uses a single ring and still owns correctness details
like durable directory syncing outside the ring.

---

## 3. Expanded Chapter Outline

```text
1.  Why the Runtime Exists
    - Flakes as scheduling and durability bugs, not vague randomness
    - External entropy: scheduler, clock, storage, allocator, network
    - One contract, two worlds: deterministic replay vs production execution

2.  Contexts, Tasks, and the Runtime Boundary
    - `Runner` and the root future
    - `Context` as capability object plus runtime identity
    - Why cloning a context creates a new supervision node

3.  Deterministic Execution as a Seeded Scheduler
    - Ready queue, sleeper heap, logical time, shared RNG
    - Why the same seed governs both task order and injected storage faults
    - Stall detection as a statement that the whole simulated world is stuck

4.  The Buffer Ownership Model
    - `IoBuf` vs `IoBufMut`
    - `Bytes`-backed vs pooled-backed storage
    - `freeze`, zero-copy slices, and `try_into_mut`
    - `IoBufs` / `IoBufsMut` as explicit vectored layouts
    - `read_at_buf` preserving caller-provided chunk shape

5.  Buffer Pools as Allocation Policy
    - Power-of-two classes, alignment, lock-free freelists
    - Network preset vs storage preset
    - Tracked vs untracked fallback allocations
    - Pool-drop behavior and approximate budget sizing

6.  Offset-Based Storage and Paged Append Recovery
    - Why `Blob` is offset-based instead of stream-based
    - Header validation: missing vs corrupt vs version-mismatched
    - `Append<B>`: write buffer, page cache, dual-CRC records
    - Protected CRC regions for partial-page rewrite safety
    - Backward scan and truncation of invalid tails on reopen

7.  Fault Injection as Part of the World
    - `FaultyStorage` config surface
    - Partial writes and partial resizes as the hard failure mode
    - Deterministic reproducibility through the shared seeded RNG

8.  Supervision Tree and Structured Cancellation
    - Strong parent link, weak child links
    - Immediate abort of late-registered tasks
    - Descendants die; siblings do not
    - Why this is not an OTP-style restart supervisor

9.  Tokio Runtime Architecture
    - Registry, process metrics, panic policy
    - Separate network/storage pools
    - Compile-time backend selection
    - Shared, blocking, and dedicated spawn modes
    - Adversarial network defaults (`TCP_NODELAY`, `SO_LINGER`, timeouts)

10. io_uring Backend and Liveness Caveats
    - MPSC -> eventfd -> SQE/CQE event loop
    - Waiter slots keep buffers, FDs, and timeout state alive
    - Network backend: separate send/recv rings with timeouts
    - Storage backend: single ring plus out-of-ring directory durability
    - Bounded-capacity deadlock pattern and why timeouts matter
```

---

## 4. System Concepts to Explain at Graduate Depth

1. **Determinism is not a mock.** The deterministic runtime is a scheduler with a logical clock,
   not a pretend version of wall-clock Tokio. It explores interleavings by shuffling equally-ready
   tasks while keeping the world replayable.

2. **Buffer types encode ownership and layout.** `IoBuf` and `IoBufMut` are really about who owns
   storage, whether that storage is shared, whether it can return to a pool, and whether vectored
   layout must be preserved across I/O.

3. **`try_into_mut` is an ownership recovery protocol.** It succeeds only when the runtime can
   prove unique ownership of backing storage. For pooled buffers, even uniquely owned slices can
   recover mutable ownership while preserving their readable view.

4. **The pool is a policy layer, not just a cache.** The storage and network presets deliberately
   choose different alignment, class ceilings, and per-class capacity because the two paths have
   different pressure profiles.

5. **The append wrapper uses checksums as a commit protocol.** The dual-CRC record on each physical
   page is not only for corruption detection. It lets the runtime preserve the last committed
   partial-page state while writing a new one.

6. **Recovery walks backward from a known-good suffix.** `Append::new` does not assume the tail is
   valid. It scans backward until checksum validation succeeds, then truncates only the invalid
   suffix and reconstructs the logical tip from the last valid partial page if needed.

7. **Fault injection is coupled to scheduling.** In the deterministic runtime, storage faults and
   task ordering share the same seeded RNG, so "this interleaving plus this partial write" is a
   stable regression target.

8. **The supervision tree is about ownership, not policy.** It gives structured cancellation but
   intentionally stops short of restart semantics or mailbox behavior.

9. **The `io_uring` path has a structural liveness caveat.** A bounded ring cannot stage queued
   work if all in-flight slots are occupied, so workloads where in-flight operations depend on
   later queued operations require timeouts or stronger external guarantees.

---

## 5. Claims-to-Verify Checklist

- [ ] `Context::clone()` in both runtimes creates a new `Tree` child rather than a plain shallow
      copy of lifetime state.
- [ ] The deterministic runtime feeds the same seeded RNG into both the executor and
      `FaultyStorage`.
- [ ] `IoBuf::try_into_mut` succeeds for uniquely owned pooled slices and fails when ownership is
      shared.
- [ ] Empty pooled slices detach instead of retaining the original pooled allocation.
- [ ] `BufferPoolConfig::for_network()` and `for_storage()` differ in both alignment and
      `max_per_class`, reflecting different hot-path assumptions.
- [ ] `BufferPool::alloc` can fall back to untracked aligned allocations when tracked capacity is
      unavailable or the request is oversized.
- [ ] `Append::flush_internal` can split the first-page write to preserve the authoritative old CRC
      during partial-page rewrites.
- [ ] `Append::new` scans backward for the last checksum-valid page and truncates invalid tail
      bytes before resuming.
- [ ] `FaultyStorage` can produce partial writes and partial resizes, not only all-or-nothing
      failures.
- [ ] `Tree::abort()` drains descendants while leaving sibling subtrees alive.
- [ ] `tokio::Runner` builds separate network and storage buffer pools and chooses backends with
      compile-time feature flags.
- [ ] The Tokio network `io_uring` backend wires per-op and shutdown timeouts from
      `read_write_timeout`.
- [ ] The Tokio storage `io_uring` backend, as constructed in `tokio::Runner`, currently starts
      with default `iouring::Config` and therefore no built-in per-op timeout.

---

## 6. Writing Notes for the Next Pass

- Keep the tone lecture-like. Explain *why* the code is shaped this way before walking the
  mechanism.
- Prefer small pseudocode snippets and concrete timelines over long copied signatures.
- When discussing storage safety, emphasize that mutable-operation errors are fatal by repository
  convention; do not imply the runtime supports continuing after a failed write.
- Do not drift into generic Tokio tutorial territory. The valuable part is the Commonware-specific
  assembly of pools, metrics, supervision, and backend choice.
- Do not repeat the older inaccurate claim that the buffer pool is NUMA-aware. The current pool is
  aligned and classed, but not NUMA-aware.
