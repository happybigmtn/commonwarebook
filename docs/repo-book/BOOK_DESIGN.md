# Repo Book Design Brief

The generic repo-book pages should inherit the same editorial instincts as the
Commonware book without assuming the subject is a distributed-systems crate.

## Tone

- Explain systems like a patient senior engineer onboarding a strong peer.
- Prefer operational detail over promotional framing.
- Make uncertainty explicit when the dossier or source does not fully support a
  claim.

## Visual Direction

- Serif-led reading layout with mono metadata and navigation chrome.
- Paper-tinted background, hairline borders, and restrained accent color.
- Right-rail table of contents on desktop and inline table of contents on
  mobile.
- Framed figure sections that feel like technical plates, not dashboard cards.
- Clear distinction between prose, code, glossary material, and side commentary.

## Page Structure

Each chapter page should include:

1. Breadcrumb plus lightweight reading bar.
2. Chapter header with title, deck, and quick metadata.
3. A short orientation paragraph for the reader.
4. Main prose with a navigable heading structure.
5. Explicit figure or lab sections sourced from `visuals.json`.
6. Chapter footer with progression to adjacent chapters.

## Source Grounding

- Use real file paths and API names from the target repository.
- Make visual specs traceable back to real code paths or documented behavior.
- Treat the dossier as supporting evidence, not as a substitute for source
  inspection.
