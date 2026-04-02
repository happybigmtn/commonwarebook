# Review: commonware-runtime Chapter Package

Audited against `runtime/src/` — checked technical accuracy of claims, line references, and grounding of visualizations in actual behavior.

---

## What is solid

**brief.md structure and depth.** The module purpose (abstract executor decoupling deterministic simulation from production), the source file prioritization, the chapter outline, and the claims-to-verify checklist are all well-formed. The distinction between the abstract runtime interface and concrete implementations is correctly drawn.

**chapter.md trait definitions and type descriptions.** Every trait cited — `Runner`, `Context`, `Spawner`, `Clock`, `Storage`, `Blob`, `Network`, `Sink`, `Stream`, `Listener` — has accurate signatures and correct descriptions of their contracts. The `Blob` offset-based I/O semantics (`read_at`/`write_at` with explicit offset), the `Header` format (8 bytes: `b"CWIC"` magic + runtime version + blob version), and the `open_versioned` version-range check are all exact matches to `storage/mod.rs`.

**Supervision tree mechanics.** The `Tree::abort()` cascade (upgrade `Weak::Tree`, recursively abort descendants, siblings untouched) and the lazy cleanup via `retain(weak.strong_count() > 0)` in `Tree::child()` are both accurately described. The test `idle_child_survives_descendant_abort` (line 169 in `supervision.rs`) is correctly cited as evidence.

**Deterministic executor scheduling.** The shuffle-then-poll loop, the `TaskWaker` wake-by-ref re-enqueue pattern, `skip_idle_time` optimization, and stall detection panic are all accurate to `deterministic.rs:556–662`. The `Auditor` state-digest mechanism (SHA-256 over `process_task` events) is correctly described.

**FaultyStorage partial-write logic.** The two-stage RNG draw (first to decide failure, second to decide partial vs complete within failures) is accurately captured. The claim that `open_versioned` returns `BlobVersionMismatch { expected, found }` matches `storage/mod.rs:55`.

**Fault injection as first-class abstraction.** The description of `FaultyStorage` as a deterministic, seeded wrapper — rather than ad-hoc mocking — is correct and reflects the actual design in `storage/faulty.rs`.

**Visualization grounding for executor state machine, supervision tree, blob header parser, network partition simulator, and clock advancement.** Source file citations (e.g., `runtime/src/deterministic.rs:534-662` for the executor loop, `runtime/src/storage/mod.rs:62-179` for the header) are correct. The ephemeral port range `32768..61000` matches `network/deterministic.rs:11`. The `Alarm` min-heap ordering (reverse `Ord`) is correctly described. The `skip_idle_time` behavior (jumps to next alarm when ready queue is empty) matches `deterministic.rs:409–431`.

---

## What still needs deeper verification

**1. `context.advance()` does not exist as a public API.** The chapter states the deterministic clock advances when "context.advance() is called explicitly (in tests)." No such method exists on `Context` or `Clock`. The clock advances only via the executor's internal `advance_time()` call (called each cycle) or when a sleeper's alarm fires. I corrected this in the Clock Advancement section, but the implications for test authors need clarification: to advance time in a test, call `context.sleep()` or `context.sleep_until()`, not an `advance()` method.

**2. BufferPool is not NUMA-aware despite documentation claims.** Multiple sections state the pool "uses sysinfo for NUMA-aware allocation." The actual `pool.rs` implementation uses power-of-two size classes with `crossbeam_queue::ArrayQueue` freelists and does not query NUMA topology. `sysinfo` is used only in `process/metered.rs` (for PID lookups), not in the buffer pool. I corrected the `BufferPool` description in chapter.md and brief.md, and fixed the "allocate" scene in visuals.json. However, the overall narrative around NUMA-aware I/O should be revisited if NUMA support is later added.

**3. `count_running_tasks` implementation relies on fragile string parsing.** The function in `utils/mod.rs:161` parses OpenMetrics-encoded output by searching for `runtime_tasks_running{kind="Task"}` lines ending in ` 1`. This works but is brittle — any change to label ordering or format would break it. Worth flagging as a maintenance concern, not a correctness bug.

**4. `external` feature pacing mechanism is underspecified.** The chapter mentions a pacer that "constrains how much logical time a future can consume per cycle," but the actual pacer implementation (`Blocker`/`Pacer` imports at `deterministic.rs:66`) is not described in detail. The docs in `deterministic.rs:9–19` describe the behavior correctly (sleep each cycle, constrain resolution latency), but a graduate-level chapter should dig deeper into how `pace()` works.

**5. Line number references may drift.** Several citations reference specific line numbers (e.g., `Context` at `deterministic.rs:887`, `Clock` at `lib.rs:466`, `Storage` at `lib.rs:629`). These are accurate at the time of writing but will become stale as the codebase evolves. Consider using symbolic references or accepting that these are approximate.

**6. `read_at_buf` contract is underspecified for pooled buffers.** The chapter states "implementation fills the provided buffer and returns it — no allocation occurs on the read path for pooled buffers." This is correct for `MemStorage` (`storage/memory.rs:159`), but the actual pooling behavior depends on which `Blob` implementation is used. In the deterministic runtime, `read_at` calls `self.pool.alloc(len)` which may allocate if the pool is empty — it's not guaranteed allocation-free. The `is_pooled()` distinction between `Bytes`-backed and `PooledBuf`-backed `IoBuf` is correctly made.

**7. Metrics scope cleanup: `ScopeGuard` is `pub(crate)` at `utils/mod.rs:437`.** The chapter describes it correctly, but the `cleanup` closure and `scope_id` mechanics could be explained more precisely for graduate readers.

---

## Recommended next workflow

1. **Source-ground the `external` pacer.** Read `runtime/src/deterministic.rs` with the `external` feature enabled to understand `Pacer` and `Blocker`. Add a subsection to the Clock section explaining exactly how logical time is constrained per cycle for external-process simulations.

2. **Add a concrete `context.advance()` replacement example.** Show how to test a 100ms timeout using `context.sleep()` calls: `context.sleep(Duration::from_millis(100)).await`. This makes the "cooperative time" invariant concrete for readers.

3. **Decide on NUMA narrative.** If NUMA-aware allocation is on the roadmap for `BufferPool`, keep the claim as aspirational with a note. If not, remove all NUMA references from the I/O patterns narrative and replace with the actual power-of-two size class + lock-free freelist story.

4. **Strengthen the `read_at_buf` contract description.** Distinguish between `read_at` (always allocates from pool) and `read_at_buf` (reuses caller-provided buffer). Clarify that pooled vs. non-pooled behavior depends on which `Blob` implementation is used.

5. **Consider a "known limitations" section.** The `count_running_tasks` string-parsing fragility, the lack of a public `advance()` API, and the absence of NUMA support are all worth explicitly noting so readers aren't misled.

6. **Verify the visualizations JSON is parseable and internally consistent.** Specifically check that all scene IDs referenced in `controls` and `checks` arrays exist in the `scenes` array, and that `system_events` arrays use actual method names (not invented ones like `BufferPool::allocate(4096) on NUMA node 0`).

---

## Page QA (post-generation review of `page.html`)

### Technical accuracy ✅
The page reflects `chapter.md` accurately. The `context.advance()` correction from the source review (no such public method exists) is correctly absent — the clock advancement figure (Figure 4) and prose describe cooperative time correctly. The BufferPool NUMA claim is absent from the prose (correct per the review's item 2 correction). The `FaultyStorage` two-stage RNG draw description matches source. All line number references in source callouts are consistent with the cited code.

### Visualization coverage ✅
All 8 visualizations from `visuals.json` are scaffolded in the page with meaningful placement:

| # | ID | Placement in page |
|---|----|-------------------|
| 1 | `executor-state-machine` | After Section 1 (The Problem), before Section 2 |
| 2 | `supervision-tree-abort` | After Section 2 (Mental Model), before Section 3 |
| 3 | `blob-header-parser` | In Section 3 (Core Abstractions) |
| 4 | `clock-advancement` | In Section 4 (Execution Flow) |
| 5 | `network-partition-simulator` | In Section 5 (Concurrency) |
| 6 | `buffer-pool-allocator` | In Section 5 (Concurrency) |
| 7 | `fault-injection-playground` | In Section 5 (Concurrency) |
| 8 | `metric-scope-lifecycle` | In Section 5 (Concurrency) |

Every figure has the required scaffold: `figure__header` (number + title), `figure__goal`, `figure__controls`, `figure__stage`, `figure__scene-caption`, `figure__why`, and `figure__caption`.

### Book design brief compliance ✅
- **Serif + mono hierarchy**: Newsreader serif for headings and prose; JetBrains Mono for all metadata, labels, captions, and code — correctly differentiated.
- **Paper palette**: `--paper: #f5f1ec` (warm off-white), `--ink: #1c1917` (near-black), `--accent: #b45309` (amber). Hairline borders throughout.
- **Centered editorial header**: Family label → meta line → large serif title → italic deck → divider rule. Ceremonial and on-brand.
- **Slim sticky reading chrome**: Slim translucent bar with breadcrumb path, chapter title, and static progress dots.
- **TOC rail**: Right-rail on desktop, collapsible inline on mobile. Active section highlighting via IntersectionObserver.
- **Figure-as-plate treatment**: Each figure is a framed region with distinct mono-numbered header, separated caption blocks, substantial vertical spacing (`margin: 2.5rem`).
- **Chapter-progression navigation**: Prev/Next chapter navigation at chapter end with book-index fallback; Next Up section with forward chapter links.
- **Sidenotes**: Callout boxes (invariant, failure, source, note) integrated throughout the prose.

### Fixes applied during this review
1. **BufferPool figure caption (line 1555)**: Stale control names removed (`pooled buffer toggle`, `alignment display`). Replaced with accurate controls: `allocation action, NUMA-aware toggle, alignment toggle`.
2. **Further Reading section**: Added between Glossary and Next Up sections. Required by the book design brief's chapter page anatomy (closing apparatus). Styled as a plain prose section with bulleted links to source docstrings and blog posts, matching the editorial tone.
3. **TOC rail and inline TOC**: Updated to include the new Further Reading entry.

### Open notes
- `visuals.json` field `learning_it_matters` (BufferPool allocator, line 257) should be `why_it_matters` for consistency — the HTML page handles this gracefully (the field is unused by the page scaffold which always uses the hardcoded `figure__why` block), but the JSON should be corrected.
- The Next Up section links to `cryptography/`, `broadcast/`, `storage/`, `consensus/` chapter pages — these will 404 until those chapters are assembled.
- Progress dots in the reading bar are static (three dots, only the first marked active) — they do not track actual scroll position. This is acceptable for a scaffold but should be connected to the IntersectionObserver for a live indicator in a later iteration.
