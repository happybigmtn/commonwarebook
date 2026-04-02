# Commonware Book Editorial Standard

This file captures the book-wide teaching and writing principles for the
Commonware book.

It is meant to evolve from two sources:

1. what already works in the strongest Commonware chapters,
2. lessons borrowed from excellent distributed-systems and technical-exposition
   books.

## What the Book Is Trying To Be

- a technical book, not a generated reference dump
- a systems lecture, not a line-by-line code explanation
- a guide to invariants, tradeoffs, and design pressure
- a composition story about how primitives become systems
- a code-substantive book, not a high-level tour that stops before the real
  machinery
- a book with stable teaching apparatus, not a collection of unrelated chapter
  voices

## Core Rule

Start from the systems question.

Then:

1. build the mental model,
2. name the invariant,
3. show the mechanism,
4. use code as evidence,
5. show what breaks and where the guarantee ends.

The chapter should answer, in order:

1. What pressure makes this crate necessary?
2. What is the cleanest mental model?
3. What assumptions is the chapter living under?
4. What invariant is being protected?
5. What mechanism enforces that invariant?
6. What alternative path was available, and why was it rejected?
7. What is the exact edge of the guarantee?

## New Depth Target

The current chapters are still too thin.

The target going forward is:

- each chapter should be roughly **3x longer** than the current draft when the
  crate is central to the system,
- the chapter should explain a much larger fraction of the crate's real code
  substance,
- the book should aim to cover roughly **90% of the code substance in the top
  10% of the codebase**, not by exhaustively paraphrasing files, but by choosing
  the modules, types, and flows that carry most of the conceptual weight,
- the rest should be covered by textbook-style background, comparisons,
  historical context, failure models, and "why this design exists" sections.

## Backgrounder Requirement

Every chapter should now contain a substantial **backgrounder** section near the
front.

Target:

- roughly **2,000 to 3,000 words** for central chapters when the topic needs
  real conceptual setup,
- enough broad background that a strong undergraduate reader can understand the
  topic class before the chapter narrows to the Commonware mechanism,
- written in a Feynman-style voice: concrete, energetic, concept-first, and
  eager to explain the problem from first principles rather than assuming the
  reader already lives inside the subfield.

The backgrounder is not filler and not a literature review.

It should provide:

- the broad problem class,
- the basic vocabulary,
- the naive mental model and where it breaks,
- the key tradeoffs of the space,
- and the minimum theory needed so the later code discussion feels inevitable
  rather than arbitrary.

The rest of the chapter should then narrow from that background into the crate's
specific invariant, mechanism, and guarantee boundary.

## Practical Coverage Rule

For each crate chapter:

- identify the **small set of files and types that explain most of the crate**,
- spend real time inside those files,
- trace the main control flow end to end,
- explain the key invariants at the points where the code enforces them,
- and only then widen back out into comparisons, background, and non-goals.

This is not "describe every line."

It is:

- cover the code that carries the substance,
- skip or compress the code that is repetitive or mechanically obvious,
- and use textbook exposition to make the dense parts easier to hold in the
  reader's head.

## What “Textbook-Style” Means Here

The chapter should not merely say what the code does.

It should also provide:

- background on the underlying problem class,
- the naive solution and why it breaks,
- the design fork where Commonware chooses one path over another,
- the historical or theoretical idea the implementation is borrowing,
- the main invariant that justifies the implementation shape,
- and a clear statement of the boundary between what the crate guarantees and
  what it leaves to higher layers.

The best current synthesis is:

- **Feynman** for energy, thought experiments, and excitement-first openings
- **SICP** for durable mental models and abstraction-first structure
- **Lamport** for explicit assumptions, claims, and proof-shaped exposition
- **OSTEP** for chapter mechanics, timelines, and compact pedagogical rhythm
- **DDIA** for design-space orientation and tradeoff framing
- **Noise / Security Engineering / Database Internals / PBFT / HotStuff** for
  chapter-specific ways of making boundaries, guarantees, and failure models
  precise

## Recommended Teaching Moves

- Start from a failure, bottleneck, or design pressure, not from the trait
  list.
- Give one governing metaphor early, then keep cashing it out through the
  chapter.
- State the chapter's highest-compression sentence near the top.
- Separate `assumption`, `invariant`, `mechanism`, and `limit` instead of
  blending them in one paragraph.
- Show behavior over time whenever the subject involves retries, rounds,
  queues, sleeps, or recovery.
- Compare one or two rejected alternatives before presenting the Commonware
  choice.
- Keep a readable mainline and push optional depth into clearly marked side
  matter.
- Reuse a small set of recurring callout types so the whole book teaches with
  the same cadence.
- End every chapter with a source-reading route and a "what this unlocks next"
  pointer.

## Stable Chapter Contract

Every substantial chapter should have a front-loaded contract:

- `crate`
- `one-sentence promise`
- `crux of the problem`
- `primary invariant`
- `naive failure`
- `reading map`

And every chapter should explicitly carry an **assumption ledger** near the
front:

- adversary
- trusted boundary
- invariant
- guarantee edge

## House Style Checklist

- Every chapter has exactly one governing metaphor. If a second metaphor shows
  up, the first one was too weak.
- Every major section begins with a question sentence and ends with a takeaway
  sentence.
- Every protocol phase should answer:
  - what question it solves,
  - what evidence it carries,
  - what state it changes,
  - what can block it,
  - what keeps it safe.
- Every dynamic mechanism should get at least one timeline, trace, or sequence
  view.
- Every code block must answer a conceptual question stated in nearby prose.
- Tradeoffs must be explicit: what improves, what worsens, what assumption
  makes the trade acceptable.
- `Safety`, `liveness`, `performance`, and `operator convenience` must not be
  collapsed into one undifferentiated claim.
- The closing apparatus should be consistent: limits, source-reading route,
  glossary, further reading.

## Book-Level Architecture

The book should feel like a small number of stable families, not a flat list of
crate names.

The most useful families so far are:

- execution and coordination
- trust and evidence
- transport and dissemination
- persistence and recovery
- coding / math / representation
- composition and case studies

Chapter order should help the reader build vocabulary family by family.

## Anti-Patterns To Avoid

- short elegant overviews that never cash out into real code
- "AI explainer" prose that reads like an answer to "what does this line do?"
- footnote-style sections that merely say "`X` wraps `Y`" or "`Z` is used for
  W" without connecting the code to a deeper systems claim
- type or module catalogs with no guiding argument
- code snippets dropped in without a conceptual question they answer
- background sections that float free of the implementation
- implementation details that appear with no systems pressure or invariant
  attached
- chapter decks that are really just first-paragraph dumps
- repeating the same design choice without ever naming the rejected alternative
- treating examples as CLI tours instead of composition stories
