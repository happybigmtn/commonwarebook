# Repo Book Pipeline

This directory documents the generic "public repo to researched interactive book"
pipeline that sits alongside the existing Commonware-specific book.

## What This Adds

- A scaffold generator that creates a book workspace for any public repository.
- Reusable Fabro workflows for chapter drafting and page assembly.
- A manifest-driven renderer that turns chapter markdown into a browsable book.
- An explicit research handoff for AutoResearchClaw so literature, architecture
  notes, and verification claims feed the book instead of staying trapped in an
  external run log.

## Expected Flow

1. Scaffold a workspace:

```bash
python3 scripts/scaffold_repo_book.py \
  --repo https://github.com/owner/repo \
  --book-slug owner-repo
```

2. Clone the target repository into the scaffolded source checkout:

```bash
git clone https://github.com/owner/repo books/owner-repo/sources/repo
```

3. Use AutoResearchClaw to produce a research dossier in
   `books/owner-repo/research/`.

4. Run the generated Fabro chapter configs to draft chapter bundles.

5. Run the generated Fabro page configs to assemble HTML chapter pages.

6. Render the book index and the chapter wrappers:

```bash
python3 scripts/render_repo_book.py books/owner-repo/book.toml
```

## AutoResearchClaw Handoff

We use AutoResearchClaw as the research subsystem, not the final page builder.
That keeps responsibilities clean:

- AutoResearchClaw gathers evidence, related work, architecture notes, and
  claim verification inputs.
- Fabro turns that dossier into chapter briefs, chapters, visual specs, and
  reviewed pages.
- The renderer packages those artifacts into an interactive book shell.

The scaffold writes:

- `books/<slug>/research/README.md`
- `books/<slug>/research/dossier.md`
- `books/<slug>/research/autoresearchclaw-topic.md`

These are the contract between AutoResearchClaw and the book pipeline.

## Manifest Contract

Each scaffolded book is driven by `books/<slug>/book.toml`.

The manifest controls:

- book metadata
- source checkout location
- dossier location
- chapter order
- part grouping
- output path

The renderer only depends on this manifest and the chapter directories, so the
same rendering path can be reused across repositories.
