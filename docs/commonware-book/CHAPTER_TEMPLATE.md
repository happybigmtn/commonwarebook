# Chapter Template

Use this template when drafting new Commonware book chapters.

## Title

One sentence subtitle if needed.

---

## Front Matter

Before the main body begins, make sure the chapter can answer these quickly:

- `crate`
- `one-sentence promise`
- `crux`
- `primary invariant`
- `naive failure`
- `reading map`

Also include an **Assumption Ledger** near the front:

- adversary
- trusted boundary
- invariant
- guarantee edge

## 1. What Problem Does This Solve?

Start from the systems problem, not the API surface.

Questions to answer:

- What real failure or engineering bottleneck makes this crate necessary?
- What naive approach breaks down?
- What does this crate take responsibility for?

## 1.5 Backgrounder

Before the chapter narrows into the crate's mechanism, include a substantial
backgrounder section that teaches the broader topic area.

Target:

- around 2,000 to 3,000 words when the topic is central or conceptually dense,
- enough conceptual setup that a strong undergraduate reader could follow the
  rest of the chapter without already being a specialist,
- written in a Feynman-style voice: direct, concrete, from first principles,
  and willing to explain why the field asks these questions at all.

The backgrounder should cover:

- the broad problem class,
- the essential vocabulary,
- the naive or classical approach,
- where that approach breaks,
- the main tradeoffs,
- and the theoretical or historical idea the Commonware design is borrowing.

Then the chapter can narrow from "how this topic works in general" to "why this
crate's mechanism has the shape it does."

## 2. Mental Model

Give the reader one strong picture to carry through the chapter.

Examples:

- "small theater" for scheduling
- "postal system" for p2p
- "voting machine with memory" for consensus

If a second metaphor starts showing up later, strengthen the first one instead
of adding another.

## 3. The Core Ideas

Group the types and mechanisms by concept, not by file.

Good pattern:

- the central invariants
- the main types that exist because of those invariants
- the key abstraction boundary to the rest of the system
- the most important rejected alternative

Avoid:

- long type inventories with no conceptual grouping
- micro-sections whose whole job is to say "`X` wraps `Y`" or "`X` is used for
  Z" without explaining the deeper systems pressure
- code blocks that do not answer a conceptual question

## Coverage Expectation

This chapter should be materially more detailed than a polished blog post.

Target:

- go deep enough that the reader can understand the small set of files that
  carry most of the crate's substance,
- make the chapter long enough to feel like a real technical lecture, not a
  tour,
- and use code walkthroughs to illuminate key invariants and control flow, not
  to paraphrase obvious syntax.

Practical rule:

- if the crate is central, the chapter should probably be about 3x longer than a
  crisp first draft,
- it should walk a real reader through the **10% of the code that explains 90%
  of the crate**,
- and it should use textbook-style background to make that dense code readable.

Useful supporting material to include:

- one short background section on the broader problem class,
- one comparison against the naive or classical alternative,
- one explicit statement of the guarantee boundary.

## 4. How the System Moves

Trace the main control flow.

Questions to answer:

- what are the actors or stages?
- what must happen first?
- what state transitions matter?
- where can progress stall?
- where in the code the invariant is enforced

This section should usually contain a real end-to-end walkthrough of the main
actor loop, engine loop, pipeline, or algorithm path.

For protocol chapters, each major phase should answer:

- what question this phase answers,
- what evidence it carries,
- what state it changes,
- what can block it,
- what keeps it safe.

## 5. What Pressure It Is Designed To Absorb

Explain concurrency, backpressure, determinism, performance, and composition.

This section should answer:

- what kinds of bad behavior does the design tolerate?
- what tradeoffs did the implementation choose?
- what guarantees are strong, and which are only practical heuristics?
- what alternative design path was available, and why this crate did not take it

Whenever the subject is dynamic, add at least one timeline, trace, or sequence
description here or in section 4.

## 6. Failure Modes and Limits

This is the shadow of the design.

Explain:

- what the crate forbids,
- what it can only mitigate,
- what its hard limits are,
- what kinds of evidence or recovery it relies on.

Keep `safety`, `liveness`, `performance`, and `operator convenience` distinct.
Do not blur them into one claim.

## 7. How to Read the Source

Teach the reader how to approach the code without getting lost.

Good pattern:

1. first file to read
2. what idea to understand there
3. next file and why
4. which support files matter only after the main mechanism is clear

Also include:

- which files are the "90% of substance" files,
- which files are mostly supporting machinery,
- and which files can be safely skimmed on a first serious reading.

Prefer a route that feels like an argument:

1. vocabulary / assumptions,
2. main mechanism,
3. support machinery,
4. optional or more specialized depth.

## 8. Glossary and Further Reading

Keep glossary entries short and conceptually useful.

The point is to reinforce the chapter's main ideas, not to restate type names.

Also add:

- one line on what this chapter unlocks for the next chapter,
- and 2-5 carefully chosen further-reading pointers.
