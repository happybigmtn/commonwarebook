# Review: consensus Interactive Book Materials

## What is solid

**Technical accuracy of core claims**: The three-phase protocol description (Notarize → Nullify → Finalize), the quorum threshold formula `N3f1::quorum(N) = N - N/3`, the parent nullification requirement, and the trait hierarchy (Automaton / CertifiableAutomaton / Relay / Reporter / Monitor) all match the source.

**Signing scheme characterization**: Attributable vs. non-attributable distinction is correct. The non-attribution implication of `bls12381_threshold` (any `t` partials can forge any other participant's signature) is accurately described. The VRF commit-then-reveal security warning is present and correctly framed.

**Protocol mechanics**: The `Context.parent` field carries `(View, Digest)` and the fork-safety check (`if parent_view < latest_certified_view` require intermediate nullifications) is correctly described. The single-shot property of `verify` and `certify` (channel closure = terminal verdict) is accurately captured.

**Domain separation**: The namespace suffixes `_NOTARIZE`, `_NULLIFY`, `_FINALIZE` are correctly identified. The description of `Nullify` signing only a `Round` (no digest payload) matches `Subject::Nullify { round: Round }` in `simplex/types.rs:283-289`.

**Marshal delivery semantics**: "At-least-once, monotonically increasing order" is documented in `marshal/mod.rs` and confirmed correct.

**Leader election**: The Random elector's round-robin fallback for view 1 (no certificate available) is correctly described and the `elector.rs:175` assertion confirms it panics if `certificate=None` for view > 1.

**N3f1 quorum overlap properties**: The safety/liveness argument (any two quorums of `>2N/3` overlap in at least one honest node; honest quorum = `N - f = 2f + 1 > f`) is standard and correctly applied.

---

## What still needs deeper verification

1. **Marshal stability label (chapter intro)**: The chapter introduction says `marshal` is BETA, but `marshal/mod.rs:83` and `marshal/standard/mod.rs:28` both use `stability_scope!(ALPHA)`. The brief correctly lists it as ALPHA. The chapter intro should be corrected to `marshal (ALPHA)`.

2. **Duplicate fifth component claim**: The chapter intro says "A fifth component, `marshal`, sits above simplex" after listing four components including marshal. This is confusing. The text should be cleaned up to avoid implying a fifth distinct primitive.

3. **TipAck source file reference in visuals.json**: `visuals.json` lists `consensus/src/ordered_broadcast/types.rs:TipAck` as a source file for the ordered broadcast chains visualization. `ordered_broadcast/types.rs` does not define `TipAck` — it is defined in `consensus/src/aggregation/types.rs:262`. The ordered_broadcast `Ack` type (`ordered_broadcast/types.rs:767`) lacks a `tip_height` field. The visualization's `scene_tipack` caption and system events describe the aggregation `TipAck`, not the ordered_broadcast type.

4. **Brief file path minor**: The brief lists `consensus/src/simplex/actors/voter/actor` without the `.rs` extension. Not a functional issue, but inconsistent with other file references.

5. **Aggregation stability unannotated**: `aggregation/mod.rs` lacks explicit `stability_scope!` or `stability_mod!` annotations at the module level, unlike `ordered_broadcast` (which has `stability_scope!(ALPHA {` at line 83). The brief correctly assumes ALPHA, but the absence of an explicit annotation in source is worth noting — CI may not enforce stability for aggregation if the check is cfg-gated.

6. **Nullify vote description precision**: The chapter says nullify votes "carry no payload, only a round identifier." This is accurate but could misleadingly suggest the round is the full `Subject::Nullify` message. The actual signing input is `round.encode()`, and the namespace suffix `_NULLIFY` is also included in the signature domain. Worth noting that "no payload" means no *application* payload, not no protocol metadata.

---

## Recommended next workflow

1. **Fix the marshal stability label** in `chapter.md` introduction — change BETA → ALPHA to match source.
2. **Remove duplicate "fifth component" sentence** or clarify that marshal is the fourth primitive described and is used as the delivery layer above simplex.
3. **Correct the TipAck source file** in `visuals.json` — change `ordered_broadcast/types.rs:TipAck` to `aggregation/types.rs:TipAck` for the ordered broadcast visualization's `scene_tipack`. Alternatively, verify whether the TipAck scene belongs in the ordered_broadcast visualization at all, since TipAck lives in aggregation.
4. **Verify the aggregation stability annotation gap** — confirm whether CI checks enforce stability annotations on `aggregation/`. If not, this is a CI tooling issue separate from the book content.
5. **Cross-reference the marshal/coding mode description** — the chapter says coding mode uses `coding::shards::Engine`. Verify this is the correct module path and that the interaction is accurate before building the Marshal V5 visualization.

---

## Page QA (post-generation review of `page.html`)

### What was fixed

**Visual ordering and numbering (structural)**
The DOM order and numbering were scrambled. The original sequence was: FSM(1), LeaderElection(2), VoteTracker(3), **DomainSep(6)**, **OrderedBroadcast(4)**, **Marshal(5)**, ParentNullify(7). This placed DomainSep before OrderedBroadcast in the reading flow but labeled it 6, and placed Marshal after OrderedBroadcast but labeled it 5. Fixed to: FSM(1), LeaderElection(2), VoteTracker(3), OrderedBroadcast(4), Marshal(5), DomainSep(6), ParentNullify(7). All HTML figure comments now match their inner visual-number spans.

**Missing scenes added**
- Leader Election visual was missing `scene_50_round_comparison` — inserted before the `Random with Certificate Feeds VRF` scene.
- Marshal visual was missing `scene_coding_mode` (shard reconstruction path) — inserted before the `Floor Height` scene.

**Navigation placeholders resolved**
- Reading bar prev/next (`href="#"`) now point to `/commonware-book/runtime/page.html` and `/commonware-book/p2p/page.html`.
- Bottom `ch-next` block (which had `href="#"` and label `commonware-cryptography`) updated to `/commonware-book/p2p/page.html` with correct chapter title and description.

### Verified correct (not changed)
- Chapter intro correctly lists all four primitives with correct stability labels (marshal is ALPHA, not BETA — the review.md items 1 and 2 were already resolved in the generated page).
- TipAck source in the HTML `visual-sources` block correctly reads `aggregation/types.rs:TipAck` (matching the review.md item 3 finding that visuals.json has the wrong path, but the HTML generation already used the correct source).
- All 7 visualizations from `visuals.json` are present with controls, scenes, and checks.
- BOOK-DESIGN.md cues: serif (Libre Baskerville) + mono (JetBrains Mono) hierarchy present, paper palette (`#f8f5f0`), centered editorial chapter header, slim sticky reading bar, substantial figure plates with caption/goal/why/controls/stage/scenes/checks, chapter-progression navigation.
- Chapter-local TOC in right rail with `details open` element.
- Responsive layout with mobile TOC collapse.
