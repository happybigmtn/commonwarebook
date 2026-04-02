# Commonware Interactive Book Design Brief

This brief defines the desired visual and structural direction for the
Commonware interactive book.

The target is not a generic docs site. It should feel like a crafted digital
book with embedded labs and visual systems thinking. The operator reference for
this direction is "makingsoftware.com", especially:

- a title page that feels like a book cover rather than a product homepage
- chapter pages that read as immersive essays with visual modules integrated
  into the reading flow

We are not trying to reproduce that site exactly. We are trying to reuse its
most valuable editorial decisions and adapt them to Commonware's subject
matter.

## Concrete Reference Cues

As observed from the Making Software title page and the "Blending modes"
chapter on March 18, 2026, the strongest reusable cues are:

1. **Editorial serif plus technical mono**
   - Warm serif for titles and body copy
   - Distinct mono for metadata, counters, labels, and figure chrome
   - Small uppercase mono labels help the page feel like a reference manual

2. **Quiet paper palette**
   - Off-white background rather than bright white
   - Near-black text rather than pure black everywhere
   - One restrained accent color for links and indicators
   - Hairline borders and light outlines instead of heavy cards

3. **Centered ceremonial chapter headers**
   - Small metadata line first
   - Large centered title second
   - One-sentence deck third
   - Short divider mark or rule beneath

4. **Book chrome instead of product chrome**
   - A thin sticky reading bar works better than a full app navbar
   - Breadcrumbs, progression, and reading context should be visible
   - Navigation should help reading, not advertise the site

5. **Grouped table of contents**
   - The title page should group chapters into families
   - Group labels should feel archival or catalog-like
   - Chapter rows should carry extra metadata such as status or word count

6. **Figure-as-plate treatment**
   - Figures should feel framed and substantial
   - Captions and labels should be clearly separated from prose
   - The figure should feel like a deliberate stop in the reading rhythm

### Observed Title-Page Moves

Useful title-page moves from the reference site:

- a large cover-style masthead rather than a web-app hero
- a short manifesto-like introduction explaining what the book is and is not
- chapter groups rendered as editorial lists, not cards
- each chapter row carrying a title plus word-count-style metadata
- a visible progress/status block that reinforces "book in progress"
- optional editorial side matter such as common questions or notes from the
  author

### Observed Chapter-Page Moves

Useful chapter-page moves from the reference site:

- breadcrumb above the main chapter title
- a tiny mono metadata line near the title
- a centered serif headline and short deck
- a small divider glyph beneath the header
- a thin sticky header for reading context
- a strong sense of beginning and end, including an explicit end marker

## Core Visual Direction

The site should feel:

- calm
- intentional
- literary
- diagram-rich
- computational

It should **not** feel like:

- a software docs portal
- a blog with a few diagrams
- a dashboard
- a default markdown renderer

## Title Page Requirements

The title page should behave like a digital cover plus map.

Required design elements:

1. **Strong masthead**
   - Large typographic title
   - Short subtitle explaining the book's thesis
   - Edition or status marker
   - Immediate sense that this is a book, not a landing page

2. **Book-level navigation**
   - Chapter list presented as a reading map
   - Visual distinction between complete, in-progress, and future chapters
   - One-line promise for each chapter

3. **Generous whitespace**
   - Breathing room around title, subtitle, and chapter map
   - Avoid cramped documentation density

4. **Editorial tone**
   - Reading-oriented layout
   - No marketing CTA language
   - No pricing-page or docs-homepage tropes

5. **Visual rhythm**
   - Alternation between typography, small metadata, and chapter blocks
   - Subtle separators, rules, or grouped regions that imply sections in a
     printed volume

6. **Grouped chapter families**
   - Do not render the table of contents as one flat list
   - Group chapters into conceptual clusters
   - Use small mono labels or a catalog treatment for group names

7. **Annotated chapter rows**
   - Each chapter line should show more than a title
   - Good secondary fields:
     - completion state
     - word count
     - reading time
     - depth marker

8. **Cover-like composition**
   - The title should read like a cover lockup, not a hero banner
   - Avoid marketing CTA language above the fold
   - Secondary modules should feel like editorial apparatus: progress meters,
     notes, glossary links, FAQ, or edition details

### Title Page Anatomy

Preferred order:

1. Book title / lockup
2. Thesis or subtitle
3. Short editorial introduction
4. Grouped chapter map
5. Optional side apparatus such as status, glossary, or editorial notes

The title page should resemble a cover plus reading map, not a docs homepage
with feature cards.

## Chapter Page Requirements

Each chapter page should feel like a deep technical essay with embedded
interactive plates.

Required design elements:

1. **Book-like opening**
   - Chapter title
   - Optional chapter number or short deck
   - Brief orientation blurb near the top
   - Reading metadata if useful (module, focus, estimated depth)

2. **Readable longform typography**
   - Narrower prose measure than a normal docs page
   - Clear hierarchy from title → deck → section headers → body text
   - Serif or serif-like reading feel for prose is preferred
   - Monospace reserved for code and protocol artifacts

3. **Chapter-local table of contents**
   - Scannable and easy to jump through
   - Should feel like a book TOC, not a collapsible admin nav
   - Prefer a right rail on desktop and an inline version on mobile

4. **Embedded visual sections**
   - Visuals should appear at the points where the prose needs them
   - Each visualization should feel like a figure plate or interactive spread
   - Use framed regions, captions, and explanatory context

5. **Sidenotes / callout rhythm**
   - Use margin-style notes, boxed insights, or clearly separated explanatory
     callouts
   - Good candidates:
     - "Why this matters"
     - "Invariant"
     - "Failure mode"
     - "What to inspect in source"

6. **Scroll narrative**
   - The page should reward continuous reading
   - Visualizations should punctuate the essay rather than interrupt it
   - Avoid stacking too many isolated widgets without narrative connection

7. **Prev / next navigation**
   - Explicit movement through the book
   - Should feel like page-turning or chapter progression, not app routing

8. **Book chrome**
   - Prefer a slim sticky reading bar
   - It may include:
     - breadcrumb or module family
     - chapter title
     - previous / next controls
     - optional progress or reading settings
   - It should not look like a SaaS navbar

### Chapter Page Anatomy

Preferred order:

1. Sticky reading bar
2. Centered chapter header
3. Chapter-local table of contents
4. Main essay sections
5. Embedded figure / lab plates placed where prose needs them
6. End marker or closing apparatus
7. Previous / next chapter navigation

### Chapter Header Anatomy

Preferred structure:

1. Small breadcrumb or module-family label
2. Small mono metadata line
3. Large centered serif title
4. One-sentence deck centered below it
5. Short divider mark or rule

This opening should feel ceremonial and editorial, not like a blog title inside
a docs template.

## Visual Module Requirements

Each visualization scaffold should include:

- title
- short learning goal
- why it matters
- visible control area
- visible stage/scene area
- caption or explanatory note

Even before full interactivity exists, the scaffold should make the intended
interaction legible.

### Figure Plate Treatment

Each visualization block should feel like a plate in a technical atlas:

- clear boundary from prose
- visible stage area with meaningful height
- mono micro-labels for controls, axes, or states
- caption block under or beside the stage
- optional paired callout such as `Why this matters` or `Failure mode`
- enough spacing before and after to reset the reading rhythm

## Layout Principles

1. **One main reading column**
   - The essay should have a dominant center of gravity

2. **Secondary information should not overpower prose**
   - TOC, metadata, or callouts should support the reading flow

3. **Figures should feel substantial**
   - Use enough space for diagrams and interactive placeholders
   - Avoid tiny embedded cards that feel like dashboard widgets

4. **Consistency across chapters**
   - Reuse the same visual language for chapter headers, figure blocks, notes,
     and navigation

5. **Desktop / mobile adaptation**
   - Desktop can use a center reading column with a right rail
   - Mobile should collapse into one reading column without losing hierarchy
     or figure clarity

## Tone and Interaction

The book should feel like:

- an advanced but humane reference
- a guided systems-thinking object
- something that rewards careful exploration

It should avoid:

- hype language
- corporate polish without editorial depth
- generic AI-generated "article page" patterns

## Practical HTML/CSS Guidance

When assembling pages:

- preserve compatibility with the existing `docs/` site assets where possible
- use page-local `<style>` blocks when the base site CSS is too sparse for the
  book treatment
- prefer semantic HTML sections over div soup
- prefer CSS variables for book-specific tokens:
  - paper background
  - ink color
  - accent color
  - border color
  - chapter measure
  - figure surface styling
- create explicit containers for:
  - chapter header
  - TOC
  - body sections
  - figure / lab sections
  - sidenotes / callouts
  - chapter navigation

Recommended implementation cues:

- Use a serif stack for prose and display headings
- Use a mono stack for labels, metadata, counters, and figure chrome
- Use a lightly tinted paper background instead of stark white
- Use centered chapter-intro composition
- Use a sticky translucent reading bar rather than a full site header
- Use one restrained accent color for links, active states, and indicators
- Use hairline borders and understated outlines instead of big shadowed cards
- Keep the reading column narrow enough to feel literary
- Give figure sections more vertical space than a normal article embed

Avoid:

- default docs sidebars as the primary visual frame
- brightly colored dashboard cards
- dense app chrome
- giant marketing CTAs above the fold
- feature-grid homepages

## Operator Rule

If a generated page merely looks like "the current docs site but longer", it is
not good enough. It should read and feel like a genuine interactive book
chapter.

If a generated title page looks like a software landing page, it is also not
good enough. It should feel like the cover and table of contents of a serious
technical volume.
