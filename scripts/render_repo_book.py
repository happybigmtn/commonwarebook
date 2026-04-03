#!/usr/bin/env python3

"""Render a scaffolded repo book into HTML pages."""

from __future__ import annotations

import argparse
import html
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Heading:
    """Represents one heading inside a rendered chapter."""

    level: int
    text: str
    anchor: str


@dataclass(frozen=True)
class ChapterManifest:
    """Represents one chapter entry from the book manifest."""

    slug: str
    title: str
    deck: str
    focus: str
    chapter_dir: Path
    page_path: Path
    status: str


@dataclass(frozen=True)
class PartManifest:
    """Represents one chapter group from the book manifest."""

    title: str
    description: str
    chapters: list[str]


@dataclass(frozen=True)
class BookManifest:
    """Holds the parsed book metadata and chapter ordering."""

    slug: str
    title: str
    subtitle: str
    description: str
    repo_url: str
    output_dir: Path
    theme_key: str
    parts: list[PartManifest]
    chapters: list[ChapterManifest]


@dataclass(frozen=True)
class RenderedChapter:
    """Carries parsed markdown plus manifest data for rendering."""

    manifest: ChapterManifest
    title: str
    subtitle: str
    summary: str
    body_html: str
    headings: list[Heading]
    word_count: int
    read_minutes: int


def strip_md(text: str) -> str:
    """Remove simple markdown formatting from inline text."""

    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text.strip()


def slugify(text: str) -> str:
    """Convert a heading into a stable HTML anchor."""

    slug = re.sub(r"[^a-z0-9]+", "-", strip_md(text).lower())
    return slug.strip("-") or "section"


def render_inline(text: str) -> str:
    """Render a paragraph fragment with lightweight markdown support."""

    parts = re.split(r"(`[^`]+`)", text)
    rendered: list[str] = []
    for part in parts:
        if not part:
            continue
        if part.startswith("`") and part.endswith("`"):
            rendered.append(f"<code>{html.escape(part[1:-1])}</code>")
            continue
        escaped = html.escape(part)
        escaped = re.sub(
            r"\[([^\]]+)\]\(([^)]+)\)",
            lambda match: (
                f'<a href="{html.escape(match.group(2), quote=True)}">'
                f"{match.group(1)}</a>"
            ),
            escaped,
        )
        escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
        escaped = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", escaped)
        rendered.append(escaped)
    return "".join(rendered)


def is_table_separator(line: str) -> bool:
    """Return true when a line looks like a markdown table separator."""

    if "|" not in line:
        return False
    stripped = line.strip().strip("|").replace(":", "").replace("-", "")
    return stripped.replace(" ", "") == ""


def split_table_row(line: str) -> list[str]:
    """Split one markdown table row into cells."""

    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse_list(lines: list[str], start: int, ordered: bool) -> tuple[str, int]:
    """Parse a contiguous markdown list starting at `start`."""

    tag = "ol" if ordered else "ul"
    marker = r"\d+\." if ordered else r"[-*]"
    item_re = re.compile(rf"^\s*(?:{marker})\s+(.*)")
    items: list[str] = []
    current: list[str] = []
    index = start
    while index < len(lines):
        line = lines[index]
        match = item_re.match(line)
        if match:
            if current:
                items.append(" ".join(current).strip())
            current = [match.group(1).strip()]
            index += 1
            continue
        if current and line.startswith("  "):
            current.append(line.strip())
            index += 1
            continue
        break
    if current:
        items.append(" ".join(current).strip())
    html_items = "".join(f"<li>{render_inline(item)}</li>" for item in items)
    return f"<{tag}>{html_items}</{tag}>", index


def parse_code_fence(lines: list[str], start: int) -> tuple[str, int]:
    """Parse a fenced code block."""

    lang = lines[start].strip()[3:].strip()
    code: list[str] = []
    index = start + 1
    while index < len(lines) and not lines[index].startswith("```"):
        code.append(lines[index])
        index += 1
    class_attr = f' class="language-{html.escape(lang, quote=True)}"' if lang else ""
    code_html = html.escape("\n".join(code))
    return f"<pre><code{class_attr}>{code_html}</code></pre>", min(index + 1, len(lines))


def parse_table(lines: list[str], start: int) -> tuple[str, int]:
    """Parse a markdown table."""

    header = split_table_row(lines[start])
    rows: list[list[str]] = []
    index = start + 2
    while index < len(lines) and "|" in lines[index]:
        rows.append(split_table_row(lines[index]))
        index += 1
    thead = "".join(f"<th>{render_inline(cell)}</th>" for cell in header)
    body = "".join(
        "<tr>%s</tr>" % "".join(f"<td>{render_inline(cell)}</td>" for cell in row)
        for row in rows
    )
    return (
        f"<table><thead><tr>{thead}</tr></thead><tbody>{body}</tbody></table>",
        index,
    )


def parse_blockquote(lines: list[str], start: int) -> tuple[str, int]:
    """Parse a markdown blockquote."""

    chunks: list[str] = []
    index = start
    while index < len(lines) and lines[index].startswith("> "):
        chunks.append(lines[index][2:].strip())
        index += 1
    body = render_inline(" ".join(chunk for chunk in chunks if chunk))
    return f"<blockquote><p>{body}</p></blockquote>", index


def parse_paragraph(lines: list[str], start: int) -> tuple[str, int]:
    """Parse a plain markdown paragraph."""

    parts: list[str] = []
    index = start
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            break
        if stripped.startswith("```") or stripped in {"---", "***"}:
            break
        if re.match(r"^#{1,6}\s+", stripped):
            break
        if line.startswith("> "):
            break
        if re.match(r"^\s*(?:[-*]|\d+\.)\s+", line):
            break
        if "|" in line and index + 1 < len(lines) and is_table_separator(lines[index + 1]):
            break
        parts.append(stripped)
        index += 1
    return f"<p>{render_inline(' '.join(parts).strip())}</p>", index


def render_markdown(lines: list[str]) -> tuple[str, list[Heading]]:
    """Render markdown into HTML and collect navigable headings."""

    pieces: list[str] = []
    headings: list[Heading] = []
    seen: dict[str, int] = {}
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped:
            index += 1
            continue
        if stripped.startswith("```"):
            block, index = parse_code_fence(lines, index)
            pieces.append(block)
            continue
        if stripped in {"---", "***"}:
            pieces.append("<hr>")
            index += 1
            continue
        heading_match = re.match(r"^(#{2,4})\s+(.*)$", stripped)
        if heading_match:
            level = len(heading_match.group(1))
            text = heading_match.group(2).strip()
            base_anchor = slugify(text)
            count = seen.get(base_anchor, 0)
            seen[base_anchor] = count + 1
            anchor = base_anchor if count == 0 else f"{base_anchor}-{count + 1}"
            headings.append(Heading(level=level, text=strip_md(text), anchor=anchor))
            pieces.append(f'<h{level} id="{anchor}">{render_inline(text)}</h{level}>')
            index += 1
            continue
        if lines[index].startswith("> "):
            block, index = parse_blockquote(lines, index)
            pieces.append(block)
            continue
        if "|" in lines[index] and index + 1 < len(lines) and is_table_separator(lines[index + 1]):
            block, index = parse_table(lines, index)
            pieces.append(block)
            continue
        if re.match(r"^\s*[-*]\s+", lines[index]):
            block, index = parse_list(lines, index, ordered=False)
            pieces.append(block)
            continue
        if re.match(r"^\s*\d+\.\s+", lines[index]):
            block, index = parse_list(lines, index, ordered=True)
            pieces.append(block)
            continue
        block, index = parse_paragraph(lines, index)
        pieces.append(block)
    return "\n".join(pieces), headings


def load_manifest(path: Path) -> BookManifest:
    """Load and validate a repo-book manifest."""

    data = tomllib.loads(path.read_text())
    book = data["book"]
    parts = [
        PartManifest(
            title=item["title"],
            description=item["description"],
            chapters=list(item["chapters"]),
        )
        for item in data.get("parts", [])
    ]
    chapters = [
        ChapterManifest(
            slug=item["slug"],
            title=item["title"],
            deck=item["deck"],
            focus=item["focus"],
            chapter_dir=ROOT / item["chapter_dir"],
            page_path=ROOT / item["page_path"],
            status=item["status"],
        )
        for item in data.get("chapters", [])
    ]
    return BookManifest(
        slug=book["slug"],
        title=book["title"],
        subtitle=book["subtitle"],
        description=book["description"],
        repo_url=book["repo_url"],
        output_dir=ROOT / book["output_dir"],
        theme_key=book["theme_key"],
        parts=parts,
        chapters=chapters,
    )


def read_chapter_markdown(path: Path, fallback_title: str, fallback_deck: str) -> RenderedChapter:
    """Parse one chapter markdown file into renderable HTML and metadata."""

    lines = path.read_text().splitlines()
    title = fallback_title
    subtitle = fallback_deck
    start = 0
    for index, line in enumerate(lines):
        if line.startswith("# "):
            title = strip_md(line[2:])
            start = index + 1
            break
    while start < len(lines) and not lines[start].strip():
        start += 1
    if start < len(lines) and lines[start].startswith("*") and lines[start].endswith("*"):
        subtitle = strip_md(lines[start].strip("* "))
        start += 1
    while start < len(lines) and not lines[start].strip():
        start += 1
    body_html, headings = render_markdown(lines[start:])
    text = "\n".join(lines[start:])
    summary = ""
    for line in lines[start:]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith(">"):
            continue
        if re.match(r"^\s*(?:[-*]|\d+\.)\s+", stripped):
            continue
        summary = strip_md(stripped)
        break
    word_count = len(re.findall(r"\b[\w'-]+\b", text))
    read_minutes = max(1, round(word_count / 225))
    return RenderedChapter(
        manifest=ChapterManifest(
            slug=path.parent.name,
            title=fallback_title,
            deck=fallback_deck,
            focus=fallback_deck,
            chapter_dir=path.parent,
            page_path=Path(),
            status="Scaffold",
        ),
        title=title,
        subtitle=subtitle,
        summary=summary or subtitle,
        body_html=body_html,
        headings=headings,
        word_count=word_count,
        read_minutes=read_minutes,
    )


def render_toc(headings: list[Heading]) -> str:
    """Render the table of contents list for one chapter."""

    items: list[str] = []
    for heading in headings:
        if heading.level > 3:
            continue
        items.append(
            f'<li><a class="toc-link" href="#{heading.anchor}">'
            f"{html.escape(heading.text)}</a></li>"
        )
    return "".join(items)


def page_relative_url(current_slug: str, target_slug: str | None) -> str:
    """Build a chapter-relative URL for prev/next links."""

    if target_slug is None:
        return "../index.html"
    if target_slug == current_slug:
        return "./page.html"
    return f"../{target_slug}/page.html"


def render_reading_bar(
    book: BookManifest,
    chapter: RenderedChapter,
    prev_slug: str | None,
    next_slug: str | None,
) -> str:
    """Render the sticky reading bar."""

    return f"""
  <header class="reading-bar" role="banner">
    <div style="width:min(100%, var(--page-max)); margin:0 auto; padding:0.7rem 1.35rem; display:flex; align-items:center; gap:0.9rem;">
      <span class="crumb">
        <a href="/index.html">home</a> /
        <a href="/books/{book.slug}/index.html">{html.escape(book.title)}</a> /
        {html.escape(chapter.manifest.slug)}
      </span>
      <span class="chapter-title">{html.escape(chapter.title)}</span>
      <div class="prog">
        <span class="prog-label" id="prog-label">sec. 1</span>
        <div class="prog-track"><div class="prog-fill" id="prog-fill" style="width:0%"></div></div>
        <button class="nav-btn theme-toggle" id="theme-toggle" type="button" aria-label="Toggle color theme">dark</button>
        <a class="prev" href="{page_relative_url(chapter.manifest.slug, prev_slug)}">← prev</a>
        <a class="next" href="{page_relative_url(chapter.manifest.slug, next_slug)}">next →</a>
      </div>
    </div>
  </header>
"""


def render_footer_navigation(
    chapter: RenderedChapter,
    prev_title: str,
    prev_slug: str | None,
    next_title: str,
    next_slug: str | None,
) -> str:
    """Render the bottom chapter navigation."""

    prev_label = "Book index" if prev_slug is None else prev_slug
    next_label = "Book index" if next_slug is None else next_slug
    return f"""
      <nav class="chapter-footer" aria-label="Chapter navigation">
        <a href="{page_relative_url(chapter.manifest.slug, prev_slug)}" class="foot-prev">
          <span class="foot-dir">← previous</span>
          <span class="foot-title">{html.escape(prev_title)}</span>
          <span class="foot-sub">{html.escape(prev_label)}</span>
        </a>
        <div class="foot-center">
          {html.escape(chapter.manifest.slug)}<br>
          <span style="font-size:0.65rem; letter-spacing:0.1em; text-transform:uppercase;">{html.escape(chapter.manifest.status.lower())} chapter</span>
        </div>
        <a href="{page_relative_url(chapter.manifest.slug, next_slug)}" class="foot-next">
          <span class="foot-dir">next →</span>
          <span class="foot-title">{html.escape(next_title)}</span>
          <span class="foot-sub">{html.escape(next_label)}</span>
        </a>
      </nav>
"""


def render_theme_script(theme_key: str) -> str:
    """Render the shared theme and progress script."""

    return f"""
  <script>
    (() => {{
      const root = document.documentElement;
      const key = '{theme_key}';
      const button = document.getElementById('theme-toggle');
      const systemDark = window.matchMedia('(prefers-color-scheme: dark)');
      const saved = localStorage.getItem(key);
      const initial = saved || (systemDark.matches ? 'dark' : 'light');
      root.dataset.theme = initial;
      const syncButton = () => {{
        if (!button) return;
        const current = root.dataset.theme || 'light';
        button.textContent = current === 'dark' ? 'light' : 'dark';
        button.setAttribute('aria-label', current === 'dark' ? 'Switch to light mode' : 'Switch to dark mode');
      }};
      syncButton();
      button?.addEventListener('click', () => {{
        const current = root.dataset.theme === 'dark' ? 'light' : 'dark';
        root.dataset.theme = current;
        localStorage.setItem(key, current);
        syncButton();
      }});
    }})();

    const tocLinks = document.querySelectorAll('.toc-link');
    const sections = document.querySelectorAll('.prose h2[id], .prose h3[id]');
    const progFill = document.getElementById('prog-fill');
    const progLabel = document.getElementById('prog-label');
    const main = document.getElementById('main-content');
    const obs = new IntersectionObserver((entries) => {{
      entries.forEach((entry) => {{
        if (!entry.isIntersecting) return;
        tocLinks.forEach((link) => link.classList.remove('active'));
        const active = document.querySelector(`.toc-link[href="#${{entry.target.id}}"]`);
        if (active) {{
          active.classList.add('active');
          if (progLabel) progLabel.textContent = active.textContent.trim();
        }}
      }});
    }}, {{ rootMargin: '-20% 0px -70% 0px' }});
    sections.forEach((section) => obs.observe(section));
    window.addEventListener('scroll', () => {{
      const total = Math.max(main.offsetHeight - window.innerHeight, 1);
      const scrolled = Math.max(0, -main.getBoundingClientRect().top);
      progFill.style.width = Math.min(100, (scrolled / total) * 100) + '%';
    }}, {{ passive: true }});
  </script>
"""


def render_chapter_page(
    book: BookManifest,
    chapter: RenderedChapter,
    prev_slug: str | None,
    prev_title: str,
    next_slug: str | None,
    next_title: str,
    chapter_number: int,
) -> str:
    """Render a complete HTML page for one chapter."""

    toc_html = render_toc(chapter.headings)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, minimum-scale=1">
  <title>{html.escape(chapter.title)} — {html.escape(book.title)}</title>
  <meta name="description" content="{html.escape(chapter.summary[:200])}">
  <link rel="icon" href="/favicon.ico" type="image/x-icon">
  <link rel="stylesheet" href="/style.css">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,300..700;1,6..72,300..700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/commonware-book/book.css">
</head>
<body>
{render_reading_bar(book, chapter, prev_slug, next_slug)}
  <header class="ch-header" aria-label="Chapter introduction">
    <div class="ch-meta">{html.escape(book.slug)} · {html.escape(chapter.manifest.slug)} · {html.escape(chapter.manifest.status)} · {chapter.read_minutes} min read</div>
    <h1 class="ch-title">{html.escape(chapter.title)}</h1>
    <p class="ch-deck">{html.escape(chapter.subtitle)}</p>
    <div class="ch-divider" aria-hidden="true">✶</div>
  </header>
  <div class="page-shell">
    <main class="page-content" id="main-content">
      <div class="orientation" role="doc-intro">{html.escape(chapter.summary)}</div>
      <div class="chapter-capsule" aria-label="Chapter facts">
        <div class="chapter-capsule__item"><div class="chapter-capsule__label">Book</div><div class="chapter-capsule__value">{html.escape(book.title)}</div></div>
        <div class="chapter-capsule__item"><div class="chapter-capsule__label">Chapter</div><div class="chapter-capsule__value">{chapter_number} of {len(book.chapters)}</div></div>
        <div class="chapter-capsule__item"><div class="chapter-capsule__label">Read</div><div class="chapter-capsule__value">{chapter.read_minutes} min</div></div>
        <div class="chapter-capsule__item"><div class="chapter-capsule__label">Repo</div><div class="chapter-capsule__value">{html.escape(book.repo_url)}</div></div>
      </div>
      <div class="toc-inline" aria-label="Chapter table of contents">
        <details><summary>Contents</summary><ul class="toc-list">{toc_html}</ul></details>
      </div>
      <article class="prose" id="prose">
        {chapter.body_html}
      </article>
      <div class="end-marker" aria-hidden="true">
        <span class="end-glyph">✶ ✶ ✶</span>
        <span class="end-label">End of chapter</span>
      </div>
{render_footer_navigation(chapter, prev_title, prev_slug, next_title, next_slug)}
      <footer class="site-footer">
        Built from <code>chapter.md</code> using the generic repo-book renderer.
      </footer>
    </main>
    <aside class="toc-rail" aria-label="Table of contents">
      <div class="toc-label">Contents</div>
      <ul class="toc-list">{toc_html}</ul>
    </aside>
  </div>
{render_theme_script(book.theme_key)}
</body>
</html>
"""


def render_index_page(book: BookManifest, chapters: dict[str, RenderedChapter]) -> str:
    """Render the HTML index page for the book."""

    rows: list[str] = []
    chapter_number = 1
    for part in book.parts:
        items: list[str] = []
        for slug in part.chapters:
            chapter = chapters[slug]
            items.append(
                f"""
                <li class="chapter-row">
                  <a class="chapter-row__link" href="/books/{book.slug}/{slug}/page.html">
                    <div>
                      <div class="chapter-row__number">{chapter_number:02d}</div>
                      <div class="chapter-row__meta">
                        <span class="chapter-row__pill">{chapter.word_count:,} words</span>
                        <span class="chapter-row__pill">{chapter.read_minutes} min</span>
                      </div>
                      <h3 class="chapter-row__title">{html.escape(chapter.title)}</h3>
                      <p class="chapter-row__deck">{html.escape(chapter.subtitle)}</p>
                    </div>
                  </a>
                </li>
                """
            )
            chapter_number += 1
        rows.append(
            f"""
            <div class="chapter-group">
              <h2 class="chapter-group__title">{html.escape(part.title)}</h2>
              <p class="section-copy">{html.escape(part.description)}</p>
              <ol class="chapter-list">{''.join(items)}</ol>
            </div>
            """
        )
    total_minutes = sum(chapter.read_minutes for chapter in chapters.values())
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, minimum-scale=1">
  <title>{html.escape(book.title)}</title>
  <meta name="description" content="{html.escape(book.description)}">
  <link rel="icon" href="/favicon.ico" type="image/x-icon">
  <link rel="stylesheet" href="/style.css">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,300..700;1,6..72,300..700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/commonware-book/book.css">
</head>
<body>
  <header class="reading-bar" role="banner">
    <div class="reading-bar__inner" style="width:min(100%, 92rem); margin:0 auto; padding:0.7rem 1.35rem; display:flex; align-items:center; justify-content:space-between; gap:1rem; font-family:var(--mono); font-size:0.68rem; letter-spacing:0.06em; text-transform:uppercase; color:var(--ink-muted);">
      <div><a href="/index.html">home</a> / <span>{html.escape(book.title)}</span></div>
      <div>{len(book.chapters)} chapters · {total_minutes} min</div>
      <button class="nav-btn theme-toggle" id="theme-toggle" type="button" aria-label="Toggle color theme">dark</button>
    </div>
  </header>
  <div class="shell" style="width:min(100%, 92rem); margin:0 auto; padding:0 1.75rem 5rem;">
    <section class="hero" aria-labelledby="book-title" style="padding:4.8rem 0 1.8rem;">
      <h1 class="hero__title" id="book-title" style="margin:0; font-size:clamp(3.8rem, 10vw, 7.4rem); line-height:0.9; font-weight:500; letter-spacing:-0.055em;">{html.escape(book.title)}</h1>
      <p class="section-copy">{html.escape(book.subtitle)}</p>
      <p class="section-copy"><a href="{html.escape(book.repo_url, quote=True)}">{html.escape(book.repo_url)}</a></p>
    </section>
    <section aria-labelledby="contents-title">
      <p class="chapter-group__title" id="contents-title">Chapters</p>
      {''.join(rows)}
    </section>
  </div>
{render_theme_script(book.theme_key)}
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the renderer."""

    parser = argparse.ArgumentParser(description="Render a scaffolded repo book.")
    parser.add_argument("manifest", help="Path to books/<slug>/book.toml")
    return parser.parse_args()


def chapter_lookup(book: BookManifest) -> dict[str, ChapterManifest]:
    """Create a slug-to-chapter lookup."""

    return {chapter.slug: chapter for chapter in book.chapters}


def render_book(manifest_path: Path) -> None:
    """Render the index and chapter pages for one manifest."""

    book = load_manifest(manifest_path)
    by_slug = chapter_lookup(book)
    rendered: dict[str, RenderedChapter] = {}
    for chapter in book.chapters:
        chapter_md = chapter.chapter_dir / "chapter.md"
        rendered_chapter = read_chapter_markdown(
            chapter_md,
            fallback_title=chapter.title,
            fallback_deck=chapter.deck,
        )
        rendered[chapter.slug] = RenderedChapter(
            manifest=chapter,
            title=rendered_chapter.title,
            subtitle=rendered_chapter.subtitle,
            summary=rendered_chapter.summary,
            body_html=rendered_chapter.body_html,
            headings=rendered_chapter.headings,
            word_count=rendered_chapter.word_count,
            read_minutes=rendered_chapter.read_minutes,
        )

    for index, chapter in enumerate(book.chapters):
        prev_slug = book.chapters[index - 1].slug if index > 0 else None
        next_slug = book.chapters[index + 1].slug if index + 1 < len(book.chapters) else None
        prev_title = "Book index" if prev_slug is None else by_slug[prev_slug].title
        next_title = "Book index" if next_slug is None else by_slug[next_slug].title
        page_html = render_chapter_page(
            book=book,
            chapter=rendered[chapter.slug],
            prev_slug=prev_slug,
            prev_title=prev_title,
            next_slug=next_slug,
            next_title=next_title,
            chapter_number=index + 1,
        )
        chapter.page_path.parent.mkdir(parents=True, exist_ok=True)
        chapter.page_path.write_text(page_html)

    book.output_dir.mkdir(parents=True, exist_ok=True)
    (book.output_dir / "index.html").write_text(render_index_page(book, rendered))


def main() -> None:
    """CLI entry point."""

    args = parse_args()
    render_book((ROOT / args.manifest).resolve())


if __name__ == "__main__":
    main()
