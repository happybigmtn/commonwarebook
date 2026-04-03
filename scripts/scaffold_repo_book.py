#!/usr/bin/env python3

"""Scaffold a generic interactive-book workspace for a public repository."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class ChapterSpec:
    """Represents one chapter in a scaffolded repo book."""

    slug: str
    title: str
    focus: str


def slugify(value: str) -> str:
    """Convert a title-like string into a filesystem-safe slug."""

    chars: list[str] = []
    last_dash = False
    for raw in value.lower():
        if raw.isalnum():
            chars.append(raw)
            last_dash = False
            continue
        if not last_dash:
            chars.append("-")
            last_dash = True
    return "".join(chars).strip("-") or "repo-book"


def parse_repo_url(repo_url: str) -> tuple[str, str, str]:
    """Extract host, owner, and repo name from a repository URL."""

    parsed = urlparse(repo_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid repository URL: {repo_url}")
    pieces = [piece for piece in parsed.path.split("/") if piece]
    if len(pieces) < 2:
        raise ValueError(f"Repository URL is missing owner/repo: {repo_url}")
    owner = pieces[0]
    repo = pieces[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    return parsed.netloc, owner, repo


def parse_chapter_spec(raw: str) -> ChapterSpec:
    """Parse one chapter spec in `slug|title|focus` format."""

    parts = [part.strip() for part in raw.split("|", 2)]
    if len(parts) != 3 or not all(parts):
        raise ValueError(
            "Chapter specs must use the format `slug|title|focus`."
        )
    return ChapterSpec(slug=slugify(parts[0]), title=parts[1], focus=parts[2])


def default_chapters(repo_name: str) -> list[ChapterSpec]:
    """Return a default chapter lineup for a newly scaffolded repo book."""

    return [
        ChapterSpec(
            slug="architecture",
            title="Architecture and Boundaries",
            focus=(
                f"Map the top-level package layout, entry points, and system "
                f"boundaries for {repo_name}."
            ),
        ),
        ChapterSpec(
            slug="execution-flow",
            title="Execution Flow and Control Loop",
            focus=(
                "Explain the end-to-end control flow, orchestration layer, and "
                "how work moves through the system."
            ),
        ),
        ChapterSpec(
            slug="extension-points",
            title="Extension Points and Operator Surface",
            focus=(
                "Identify configuration knobs, plugin hooks, integrations, and "
                "the expected operator workflow."
            ),
        ),
        ChapterSpec(
            slug="risks-and-verification",
            title="Risks, Failure Modes, and Verification",
            focus=(
                "Cover correctness risks, testing strategy, observability, and "
                "what claims still need verification."
            ),
        ),
    ]


def build_parts(chapters: list[ChapterSpec]) -> list[tuple[str, str, list[str]]]:
    """Group chapters into two broad parts for the generated manifest."""

    midpoint = max(1, len(chapters) // 2)
    return [
        (
            "Part I. Orientation",
            "Map the system, its intent, and its main execution paths.",
            [chapter.slug for chapter in chapters[:midpoint]],
        ),
        (
            "Part II. Operation",
            "Focus on extension points, verification, and operational reality.",
            [chapter.slug for chapter in chapters[midpoint:]],
        ),
    ]


def render_manifest(
    book_slug: str,
    book_title: str,
    repo_url: str,
    repo_host: str,
    repo_owner: str,
    repo_name: str,
    default_branch: str,
    chapters: list[ChapterSpec],
) -> str:
    """Render the scaffolded book manifest."""

    part_lines: list[str] = []
    for title, description, part_chapters in build_parts(chapters):
        chapter_list = ", ".join(f'"{slug}"' for slug in part_chapters)
        part_lines.append(
            "\n".join(
                [
                    "[[parts]]",
                    f'title = "{title}"',
                    f'description = "{description}"',
                    f"chapters = [{chapter_list}]",
                    "",
                ]
            )
        )

    chapter_lines: list[str] = []
    for chapter in chapters:
        chapter_lines.append(
            "\n".join(
                [
                    "[[chapters]]",
                    f'slug = "{chapter.slug}"',
                    f'title = "{chapter.title}"',
                    f'deck = "{chapter.focus}"',
                    f'focus = "{chapter.focus}"',
                    f'chapter_dir = "books/{book_slug}/chapters/{chapter.slug}"',
                    f'page_path = "docs/books/{book_slug}/{chapter.slug}/page.html"',
                    'status = "Scaffold"',
                    "",
                ]
            )
        )

    return "\n".join(
        [
            "version = 1",
            "",
            "[book]",
            f'slug = "{book_slug}"',
            f'title = "{book_title}"',
            (
                f'subtitle = "An interactive engineering book about '
                f'{repo_name}."'
            ),
            f'repo_url = "{repo_url}"',
            f'repo_host = "{repo_host}"',
            f'repo_owner = "{repo_owner}"',
            f'repo_name = "{repo_name}"',
            f'default_branch = "{default_branch}"',
            (
                f'description = "Research-backed interactive walkthrough of '
                f'{repo_name}."'
            ),
            f'source_checkout = "books/{book_slug}/sources/repo"',
            f'research_dossier = "books/{book_slug}/research/dossier.md"',
            f'output_dir = "docs/books/{book_slug}"',
            f'theme_key = "repo-book-{book_slug}"',
            "",
            *part_lines,
            *chapter_lines,
        ]
    ).rstrip() + "\n"


def render_book_readme(
    book_slug: str,
    book_title: str,
    repo_url: str,
    repo_name: str,
) -> str:
    """Render the top-level README for a scaffolded book workspace."""

    return f"""# {book_title}

This workspace turns `{repo_url}` into a researched interactive book.

## Layout

- `book.toml`: manifest consumed by the renderer.
- `research/`: AutoResearchClaw handoff files and dossier.
- `chapters/`: chapter bundles produced by Fabro.
- `sources/repo/`: local checkout of `{repo_name}`.

## Suggested Flow

1. Clone the source repository into `sources/repo/`.
2. Use the research prompt in `research/autoresearchclaw-topic.md`.
3. Paste or export the dossier into `research/dossier.md`.
4. Run the generated Fabro configs in `fabro/runs/repo-books/{book_slug}/`.
5. Render the book with:

```bash
python3 scripts/render_repo_book.py books/{book_slug}/book.toml
```
"""


def render_research_readme(repo_url: str) -> str:
    """Render the research handoff instructions."""

    return f"""# Research Handoff

Use AutoResearchClaw to gather architecture notes, literature, issue context,
verification claims, and operational insights for `{repo_url}`.

This directory is the bridge between external research and the chapter-writing
pipeline.

## Files

- `autoresearchclaw-topic.md`: seed prompt for the research run.
- `dossier.md`: normalized evidence packet consumed by Fabro chapter runs.

## Notes

- Prefer upstream AutoResearchClaw setup instructions and its example config
  files when launching the research run.
- Normalize the final output into `dossier.md` so later stages can rely on a
  stable path.
"""


def render_dossier_stub(repo_url: str) -> str:
    """Render a placeholder research dossier."""

    return f"""# Research Dossier

Repository: `{repo_url}`

## Executive Summary

TODO: Summarize what the repository does and why it exists.

## Architectural Map

TODO: Capture packages, services, entry points, and data flow.

## Claims to Verify

- TODO: Add each important claim with its source file or external citation.

## Related Work

TODO: Link neighboring projects, papers, or standards.

## Open Questions

- TODO: Track unresolved uncertainty for later review.
"""


def render_autoresearchclaw_topic(
    book_title: str,
    repo_url: str,
    repo_name: str,
) -> str:
    """Render a repo-specific AutoResearchClaw briefing prompt."""

    return f"""Research `{repo_url}` and prepare a dossier for an interactive
book project called `{book_title}`.

Output requirements:

1. Explain the top-level architecture of `{repo_name}`.
2. Identify the most important source directories and entry points.
3. Describe the control loop or primary execution path.
4. Capture extension points, configuration surface, and operator workflow.
5. List correctness risks, failure modes, and how the project verifies itself.
6. Include claims that need explicit verification, tied to source paths.
7. Include external references only when they materially sharpen the book.

Normalize the final result into `books/<slug>/research/dossier.md`.
"""


def render_chapter_stub(chapter: ChapterSpec) -> str:
    """Render a starter `chapter.md` for one scaffolded chapter."""

    return f"""# {chapter.title}

*{chapter.focus}*

## Chapter Contract

- Reader outcome: TODO
- Primary evidence: TODO
- Visual promise: TODO

---

## What This Part Tries To Achieve

TODO: Explain the chapter in one paragraph.

## Mental Model

TODO: Give the simplest model that makes the system legible.

## Core Files and Abstractions

TODO: Reference real files after source inspection.

## Execution Flow

TODO: Walk the reader through the main control path.

## Operational Semantics

TODO: Explain what matters for running, extending, or trusting the system.

## Failure Modes and Verification Notes

TODO: Record correctness risks, caveats, and open verification work.

## How To Read The Source

TODO: Give a practical file-reading order.

## Glossary and Further Reading

TODO: Add terminology and pointers.

## Open Questions For Interactive UI

- TODO: What should animate?
- TODO: What should be explorable?
"""


def render_brief_stub(chapter: ChapterSpec) -> str:
    """Render a starter `brief.md` for one chapter."""

    return f"""# {chapter.title} Brief

## Chapter Promise

TODO: Describe what the reader should understand after this chapter.

## Focus

- {chapter.focus}

## Evidence Sources

- TODO: Add the source files and dossier notes that matter most.
"""


def render_review_stub() -> str:
    """Render an empty review stub."""

    return """# Review

## What is solid

TODO

## What still needs deeper verification

TODO

## Recommended next workflow

TODO
"""


def render_visuals_stub(chapter: ChapterSpec) -> str:
    """Render an empty but valid visuals file."""

    return """{
  "chapter": "%s",
  "visualizations": []
}
""" % chapter.title


def render_run_config(
    book_slug: str,
    chapter: ChapterSpec,
    workflow: str,
    suffix: str,
) -> str:
    """Render a Fabro run config for one chapter workflow."""

    run_name = chapter.title if not suffix else f"{chapter.title} page"
    chapter_dir = f"books/{book_slug}/chapters/{chapter.slug}"
    return f"""version = 1
graph = "../../../workflows/{workflow}/workflow.fabro"
goal = "Create {run_name} for {book_slug}."

[sandbox]
provider = "local"

[vars]
book_manifest = "books/{book_slug}/book.toml"
book_readme = "books/{book_slug}/README.md"
repo_display_name = "{book_slug}"
repo_root = "books/{book_slug}/sources/repo"
repo_readme = "books/{book_slug}/sources/repo/README.md"
research_dossier = "books/{book_slug}/research/dossier.md"
source_glob = "books/{book_slug}/sources/repo/**"
chapter_dir = "{chapter_dir}"
chapter_slug = "{chapter.slug}"
chapter_title = "{chapter.title}"
chapter_focus = "{chapter.focus}"
"""


def write_file(path: Path, contents: str, force: bool) -> None:
    """Write one scaffold file, optionally overwriting an existing file."""

    if path.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the scaffold generator."""

    parser = argparse.ArgumentParser(
        description="Scaffold a repo-to-book workspace."
    )
    parser.add_argument("--repo", required=True, help="Public repository URL.")
    parser.add_argument(
        "--book-slug",
        help="Filesystem slug for the book workspace. Defaults to repo name.",
    )
    parser.add_argument(
        "--book-title",
        help="Display title for the generated book. Defaults to repo name.",
    )
    parser.add_argument(
        "--default-branch",
        default="main",
        help="Expected default branch for the target repo.",
    )
    parser.add_argument(
        "--chapter",
        action="append",
        default=[],
        help="Custom chapter spec in `slug|title|focus` format.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing scaffold files.",
    )
    return parser.parse_args()


def main() -> None:
    """Create the scaffolded workspace and generated run configs."""

    args = parse_args()
    repo_host, repo_owner, repo_name = parse_repo_url(args.repo)
    book_slug = slugify(args.book_slug or repo_name)
    book_title = args.book_title or repo_name
    chapters = (
        [parse_chapter_spec(raw) for raw in args.chapter]
        if args.chapter
        else default_chapters(repo_name)
    )

    book_root = ROOT / "books" / book_slug
    files = {
        book_root / "book.toml": render_manifest(
            book_slug=book_slug,
            book_title=book_title,
            repo_url=args.repo,
            repo_host=repo_host,
            repo_owner=repo_owner,
            repo_name=repo_name,
            default_branch=args.default_branch,
            chapters=chapters,
        ),
        book_root / "README.md": render_book_readme(
            book_slug=book_slug,
            book_title=book_title,
            repo_url=args.repo,
            repo_name=repo_name,
        ),
        book_root / "research" / "README.md": render_research_readme(args.repo),
        book_root / "research" / "dossier.md": render_dossier_stub(args.repo),
        book_root / "research" / "autoresearchclaw-topic.md": (
            render_autoresearchclaw_topic(book_title, args.repo, repo_name)
        ),
    }

    for chapter in chapters:
        chapter_dir = book_root / "chapters" / chapter.slug
        files[chapter_dir / "brief.md"] = render_brief_stub(chapter)
        files[chapter_dir / "chapter.md"] = render_chapter_stub(chapter)
        files[chapter_dir / "review.md"] = render_review_stub()
        files[chapter_dir / "visuals.json"] = render_visuals_stub(chapter)

        run_root = ROOT / "fabro" / "runs" / "repo-books" / book_slug
        files[run_root / f"{chapter.slug}.toml"] = render_run_config(
            book_slug=book_slug,
            chapter=chapter,
            workflow="repo-chapter",
            suffix="",
        )
        files[run_root / f"{chapter.slug}-page.toml"] = render_run_config(
            book_slug=book_slug,
            chapter=chapter,
            workflow="repo-page",
            suffix="page",
        )

    for path, contents in files.items():
        write_file(path, contents, args.force)

    print(f"Scaffolded repo book at books/{book_slug}")
    print(f"Manifest: books/{book_slug}/book.toml")
    print(f"Run configs: fabro/runs/repo-books/{book_slug}/")


if __name__ == "__main__":
    main()
