# Module Chapter Template

Reusable Fabro workflow for generating one chapter of the Commonware interactive
book.

The workflow is parameterized through run-config variables so the same Graphviz
file can target any crate in the repo.

Required variables:

- `module_slug`
- `module_display_name`
- `crate_path`
- `readme_path`
- `source_glob`
- `chapter_dir`
- `supplemental_context`
- `module_focus`

The workflow writes these files into `$chapter_dir`:

- `brief.md`
- `chapter.md`
- `visuals.json`
- `review.md`

This template uses Claude Code in CLI backend mode, routed to MiniMax's
Anthropic-compatible endpoint via `sandbox.env`. The actual model is supplied by
the run config, not hard-coded in the Graphviz file.
