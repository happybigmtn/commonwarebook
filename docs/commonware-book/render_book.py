#!/usr/bin/env python3

from __future__ import annotations

import html
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent
SITE_ROOT = ROOT.parent

ORDER = [
    "runtime",
    "p2p",
    "consensus",
    "cryptography",
    "stream",
    "storage",
    "broadcast",
    "resolver",
    "coding",
    "codec",
    "math",
    "conformance",
    "macros",
    "utils",
    "parallel",
    "invariants",
    "collector",
    "deployer",
    "bridge",
    "sync",
    "chat",
    "estimator",
    "log",
    "reshare",
    "flood",
]

PUBLISHED = {"runtime", "p2p", "consensus"}

PARTS = [
    (
        "Part I. Foundations",
        "Execution, networking, and agreement under adversarial conditions.",
        ["runtime", "p2p", "consensus"],
    ),
    (
        "Part II. Evidence and State",
        "Identity, transport, storage, dissemination, recovery, representation, and compatibility.",
        ["cryptography", "stream", "storage", "broadcast", "resolver", "coding", "codec", "math", "conformance"],
    ),
    (
        "Part III. Shared Machinery",
        "Macros, utilities, execution policies, invariant search, request collection, and deployment.",
        ["macros", "utils", "parallel", "invariants", "collector", "deployer"],
    ),
    (
        "Part IV. Case Studies",
        "Composed systems that show how the primitives become working software.",
        ["bridge", "sync", "chat", "estimator", "log", "reshare", "flood"],
    ),
]


@dataclass
class Heading:
    level: int
    text: str
    anchor: str


@dataclass
class Chapter:
    slug: str
    title: str
    subtitle: str
    contract_html: str
    body_lines: list[str]
    body_html: str
    headings: list[Heading]
    summary: str
    word_count: int
    read_minutes: int


def strip_md(text: str) -> str:
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text.strip()


def slugify(text: str) -> str:
    text = strip_md(text).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "section"


def render_inline(text: str) -> str:
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
            lambda m: f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>',
            escaped,
        )
        escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
        escaped = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", escaped)
        rendered.append(escaped)
    return "".join(rendered)


def parse_list(
    lines: list[str], start: int, ordered: bool, list_class: str | None = None
) -> tuple[str, int]:
    tag = "ol" if ordered else "ul"
    item_re = re.compile(r"^\s*(?:\d+\.|[-*])\s+(.*)")
    items: list[str] = []
    current: list[str] = []
    i = start
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            break
        match = item_re.match(line)
        if match:
            if current:
                items.append(" ".join(current).strip())
            current = [match.group(1).strip()]
            i += 1
            continue
        if current and line.startswith("  "):
            current.append(line.strip())
            i += 1
            continue
        break
    if current:
        items.append(" ".join(current).strip())
    html_items = "".join(f"<li>{render_inline(item)}</li>" for item in items)
    class_attr = f' class="{list_class}"' if list_class else ""
    return f"<{tag}{class_attr}>{html_items}</{tag}>", i


def parse_blockquote(lines: list[str], start: int) -> tuple[str, int]:
    chunks: list[str] = []
    i = start
    while i < len(lines) and lines[i].startswith("> "):
        chunks.append(lines[i][2:])
        i += 1
    if chunks:
        marker = re.match(r"^\[!(\w+)\]\s*(.*)$", chunks[0].strip())
        if marker:
            kind = marker.group(1).lower()
            title = marker.group(2).strip()
            goal = ""
            why = ""
            paragraphs: list[str] = []
            list_items: list[str] = []
            for raw in chunks[1:]:
                stripped = raw.strip()
                if not stripped:
                    continue
                if stripped.lower().startswith("goal:"):
                    goal = stripped[5:].strip()
                elif stripped.lower().startswith("why:"):
                    why = stripped[4:].strip()
                elif re.match(r"^[-*]\s+", stripped):
                    list_items.append(re.sub(r"^[-*]\s+", "", stripped))
                else:
                    paragraphs.append(stripped)
            parts = [f'<div class="teaching-plate teaching-plate--{kind}">']
            parts.append(
                f'<div class="teaching-plate__header"><span class="teaching-plate__eyebrow">{html.escape(kind)}</span><span class="teaching-plate__title">{render_inline(title)}</span></div>'
            )
            if goal:
                parts.append(
                    f'<p class="teaching-plate__goal"><strong>Goal:</strong> {render_inline(goal)}</p>'
                )
            if paragraphs:
                for paragraph in paragraphs:
                    parts.append(f'<p>{render_inline(paragraph)}</p>')
            if list_items:
                items = "".join(f"<li>{render_inline(item)}</li>" for item in list_items)
                parts.append(f"<ul>{items}</ul>")
            if why:
                parts.append(
                    f'<p class="teaching-plate__why"><strong>Why it matters:</strong> {render_inline(why)}</p>'
                )
            parts.append("</div>")
            return "".join(parts), i
    body = render_inline(" ".join(chunks).strip())
    return f"<blockquote><p>{body}</p></blockquote>", i


def parse_code_fence(lines: list[str], start: int) -> tuple[str, int]:
    first = lines[start].strip()
    lang = first[3:].strip()
    code: list[str] = []
    i = start + 1
    while i < len(lines) and not lines[i].startswith("```"):
        code.append(lines[i])
        i += 1
    code_html = html.escape("\n".join(code))
    class_attr = f' class="language-{html.escape(lang, quote=True)}"' if lang else ""
    return f"<pre><code{class_attr}>{code_html}</code></pre>", min(i + 1, len(lines))


def is_table_separator(line: str) -> bool:
    stripped = line.strip()
    if "|" not in stripped:
        return False
    stripped = stripped.strip("|").replace(":", "").replace("-", "").replace(" ", "")
    return stripped == ""


def split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse_table(lines: list[str], start: int) -> tuple[str, int]:
    header = split_table_row(lines[start])
    i = start + 2
    rows: list[list[str]] = []
    while i < len(lines) and "|" in lines[i]:
        rows.append(split_table_row(lines[i]))
        i += 1
    thead = "".join(f"<th>{render_inline(cell)}</th>" for cell in header)
    tbody_rows = []
    for row in rows:
        cells = "".join(f"<td>{render_inline(cell)}</td>" for cell in row)
        tbody_rows.append(f"<tr>{cells}</tr>")
    body = "".join(tbody_rows)
    return f"<table><thead><tr>{thead}</tr></thead><tbody>{body}</tbody></table>", i


def parse_paragraph(lines: list[str], start: int) -> tuple[str, int]:
    parts: list[str] = []
    i = start
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            break
        if stripped.startswith("```"):
            break
        if stripped in {"---", "***"}:
            break
        if re.match(r"^#{1,6}\s+", stripped):
            break
        if line.startswith("> "):
            break
        if re.match(r"^\s*(?:[-*]|\d+\.)\s+", line):
            break
        if (
            "|" in line
            and i + 1 < len(lines)
            and is_table_separator(lines[i + 1])
        ):
            break
        parts.append(stripped)
        i += 1
    content = " ".join(parts).strip()
    return f"<p>{render_inline(content)}</p>", i


def render_markdown(lines: list[str]) -> tuple[str, list[Heading]]:
    i = 0
    pieces: list[str] = []
    headings: list[Heading] = []
    seen_ids: dict[str, int] = {}
    current_heading_text = ""
    pending_list_class: str | None = None
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped in {"**Reading map**", "Reading map"}:
            pieces.append('<p class="section-kicker">Reading map</p>')
            pending_list_class = "reading-map"
            i += 1
            continue
        if stripped in {"**Assumption ledger**", "Assumption ledger"}:
            pieces.append('<p class="section-kicker">Assumption ledger</p>')
            pending_list_class = "assumption-ledger"
            i += 1
            continue
        if stripped.startswith("```"):
            block, i = parse_code_fence(lines, i)
            pieces.append(block)
            continue
        if stripped in {"---", "***"}:
            pieces.append("<hr>")
            i += 1
            continue
        heading_match = re.match(r"^(#{2,4})\s+(.*)$", stripped)
        if heading_match:
            level = len(heading_match.group(1))
            text = heading_match.group(2).strip()
            base_anchor = slugify(text)
            count = seen_ids.get(base_anchor, 0)
            seen_ids[base_anchor] = count + 1
            anchor = base_anchor if count == 0 else f"{base_anchor}-{count + 1}"
            headings.append(Heading(level, strip_md(text), anchor))
            class_attr = ""
            if strip_md(text).lower() in {"0. chapter contract", "chapter contract"}:
                class_attr = ' class="chapter-contract__heading"'
            pieces.append(f'<h{level}{class_attr} id="{anchor}">{render_inline(text)}</h{level}>')
            current_heading_text = strip_md(text).lower()
            pending_list_class = None
            i += 1
            continue
        if line.startswith("> "):
            block, i = parse_blockquote(lines, i)
            pieces.append(block)
            continue
        if (
            "|" in line
            and i + 1 < len(lines)
            and is_table_separator(lines[i + 1])
        ):
            block, i = parse_table(lines, i)
            pieces.append(block)
            continue
        if re.match(r"^\s*[-*]\s+", line):
            list_class = None
            if pending_list_class:
                list_class = pending_list_class
                pending_list_class = None
            elif current_heading_text == "assumption ledger":
                list_class = "assumption-ledger"
            elif current_heading_text == "reading map":
                list_class = "reading-map"
            block, i = parse_list(lines, i, ordered=False, list_class=list_class)
            pieces.append(block)
            continue
        if re.match(r"^\s*\d+\.\s+", line):
            block, i = parse_list(lines, i, ordered=True)
            pieces.append(block)
            continue
        block, i = parse_paragraph(lines, i)
        pieces.append(block)
    return "\n".join(pieces), headings


def parse_chapter(path: Path) -> Chapter:
    lines = path.read_text().splitlines()
    title = ""
    subtitle = ""
    start = 0
    for idx, line in enumerate(lines):
        if line.startswith("# "):
            title = strip_md(line[2:])
            start = idx + 1
            break
    while start < len(lines) and not lines[start].strip():
        start += 1
    if start < len(lines):
        line = lines[start].strip()
        if line.startswith("## "):
            subtitle = strip_md(line[3:])
            start += 1
        elif line.startswith("*"):
            if line.endswith("*") and len(line) > 1:
                subtitle = strip_md(line.strip("* "))
                start += 1
            else:
                italic_lines = [line]
                start += 1
                while start < len(lines):
                    italic_lines.append(lines[start].strip())
                    if lines[start].strip().endswith("*"):
                        start += 1
                        break
                    start += 1
                subtitle = strip_md(" ".join(italic_lines).strip("* "))
    while start < len(lines) and not lines[start].strip():
        start += 1
    if start < len(lines) and lines[start].strip() == "---":
        start += 1
    while start < len(lines) and not lines[start].strip():
        start += 1

    contract_html = ""
    if start < len(lines):
        heading_match = re.match(r"^##\s+(.*)$", lines[start].strip())
        if heading_match:
            heading_text = strip_md(heading_match.group(1)).lower()
            if any(token in heading_text for token in ["chapter contract", "opening apparatus"]):
                contract_start = start
                start += 1
                contract_end = start
                while contract_end < len(lines):
                    stripped = lines[contract_end].strip()
                    if stripped == "---":
                        break
                    contract_end += 1
                contract_lines = lines[contract_start:contract_end]
                contract_html, _ = render_markdown(contract_lines)
                start = contract_end
                if start < len(lines) and lines[start].strip() == "---":
                    start += 1
                while start < len(lines) and not lines[start].strip():
                    start += 1

    body_lines = lines[start:]
    body_html, headings = render_markdown(body_lines)
    word_count = len(re.findall(r"\b[\w'-]+\b", "\n".join(lines)))
    read_minutes = max(1, round(word_count / 225))
    summary = ""
    paragraph_lines: list[str] = []
    for line in body_lines:
        if re.match(r"^##\s+", line):
            continue
        if not line.strip():
            if paragraph_lines:
                summary = " ".join(part.strip() for part in paragraph_lines)
                break
            continue
        if line.startswith("> ") or line.startswith("```") or re.match(r"^\s*(?:[-*]|\d+\.)\s+", line):
            continue
        paragraph_lines.append(strip_md(line))
    if not summary and paragraph_lines:
        summary = " ".join(paragraph_lines)
    if not subtitle or subtitle in {"An Advanced Explainer"}:
        subtitle = summary[:180].rstrip(".") + "." if summary else title
    return Chapter(
        slug=path.parent.name,
        title=title,
        subtitle=subtitle,
        contract_html=contract_html,
        body_lines=body_lines,
        body_html=body_html,
        headings=headings,
        summary=summary or subtitle,
        word_count=word_count,
        read_minutes=read_minutes,
    )


def relative_url(from_slug: str, to_slug: str) -> str:
    if to_slug == "index":
        return "../index.html"
    return f"../{to_slug}/page.html"


def chapter_state(slug: str) -> str:
    return "Featured" if slug in PUBLISHED else "Complete"


def teaser(text: str, limit: int = 140) -> str:
    text = strip_md(text).replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    cutoff = text[:limit].rsplit(" ", 1)[0].strip()
    return f"{cutoff}…"


def ordered_slugs(chapters: dict[str, Chapter]) -> list[str]:
    ordered = [slug for slug in ORDER if slug in chapters]
    extras = sorted(slug for slug in chapters if slug not in ordered)
    return ordered + extras


def group_label_for(slug: str) -> str:
    for label, _intro, slugs in PARTS:
        if slug in slugs:
            return label
    return "Commonware Book"


def chapter_page(chapter: Chapter, chapters: dict[str, Chapter]) -> str:
    slugs = ordered_slugs(chapters)
    idx = slugs.index(chapter.slug)
    prev_slug = "index" if idx == 0 else slugs[idx - 1]
    next_slug = "index" if idx == len(slugs) - 1 else slugs[idx + 1]
    prev_title = "Book Index" if prev_slug == "index" else chapters[prev_slug].title
    next_title = "Book Index" if next_slug == "index" else chapters[next_slug].title
    family = group_label_for(chapter.slug)

    toc_items = []
    current_parent_open = False
    for i, heading in enumerate(chapter.headings):
        cls = "toc-link"
        if heading.level == 2:
            if current_parent_open:
                toc_items.append("</ul></li>")
                current_parent_open = False
            toc_items.append(
                f'<li class="toc-item"><a class="{cls}" href="#{heading.anchor}">{html.escape(heading.text)}</a>'
            )
            next_heading = chapter.headings[i + 1] if i + 1 < len(chapter.headings) else None
            if next_heading and next_heading.level > 2:
                toc_items.append('<ul class="toc-sub">')
                current_parent_open = True
            else:
                toc_items.append("</li>")
        elif heading.level == 3:
            toc_items.append(f'<li><a class="{cls}" href="#{heading.anchor}">{html.escape(heading.text)}</a></li>')
    if current_parent_open:
        toc_items.append("</ul></li>")
    toc_html = "".join(toc_items)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, minimum-scale=1">
  <title>{html.escape(chapter.title)} — commonware-book</title>
  <meta name="description" content="{html.escape(chapter.summary[:200])}">
  <link rel="icon" href="../favicon.ico" type="image/x-icon">
  <link rel="stylesheet" href="../style.css">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,300..700;1,6..72,300..700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="../book.css">
  <link rel="stylesheet" href="../book-interactive.css">
</head>
<body>
  <header class="reading-bar" role="banner">
    <div style="width:min(100%, var(--page-max)); margin:0 auto; padding:0.7rem 1.35rem; display:flex; align-items:center; gap:0.9rem;">
      <span class="crumb">
        <a href="../index.html">commonware</a> / <a href="../index.html">book</a> / {html.escape(chapter.slug)}
      </span>
      <span class="chapter-title">{html.escape(chapter.title)}</span>
      <div class="prog">
        <span class="prog-label" id="prog-label">sec. 1</span>
        <div class="prog-track"><div class="prog-fill" id="prog-fill" style="width:0%"></div></div>
        <button class="nav-btn theme-toggle" id="theme-toggle" type="button" aria-label="Toggle color theme">dark</button>
        <a class="prev" href="{relative_url(chapter.slug, prev_slug)}">← prev</a>
        <a class="next" href="{relative_url(chapter.slug, next_slug)}">next →</a>
      </div>
    </div>
  </header>

  <header class="ch-header" aria-label="Chapter introduction">
    <div class="ch-meta">commonware-book · {html.escape(chapter.slug)} · {chapter_state(chapter.slug)} · {chapter.read_minutes} min read</div>
    <h1 class="ch-title">{html.escape(chapter.title)}</h1>
    <p class="ch-deck">{html.escape(chapter.subtitle)}</p>
    <div class="ch-divider" aria-hidden="true">✶</div>
  </header>

  <div class="page-shell">
    <main class="page-content" id="main-content">
      <div class="orientation" role="doc-intro">
        {html.escape(chapter.summary)}
      </div>
      {f'<section class="chapter-contract" aria-label="Chapter contract">{chapter.contract_html}</section>' if chapter.contract_html else ''}
      <div class="chapter-capsule" aria-label="Chapter facts">
        <div class="chapter-capsule__item">
          <div class="chapter-capsule__label">Family</div>
          <div class="chapter-capsule__value">{html.escape(family)}</div>
        </div>
        <div class="chapter-capsule__item">
          <div class="chapter-capsule__label">Chapter</div>
          <div class="chapter-capsule__value">{idx + 1} of {len(slugs)}</div>
        </div>
        <div class="chapter-capsule__item">
          <div class="chapter-capsule__label">Read</div>
          <div class="chapter-capsule__value">{chapter.read_minutes} min</div>
        </div>
        <div class="chapter-capsule__item">
          <div class="chapter-capsule__label">Next</div>
          <div class="chapter-capsule__value">{html.escape(next_title)}</div>
        </div>
      </div>
      <div class="toc-inline" aria-label="Chapter table of contents">
        <details>
          <summary>Contents</summary>
          <ul class="toc-list">{toc_html}</ul>
        </details>
      </div>
      <article class="prose" id="prose">
        {chapter.body_html}
      </article>

      <div class="end-marker" aria-hidden="true">
        <span class="end-glyph">✶ ✶ ✶</span>
        <span class="end-label">End of chapter</span>
      </div>

      <nav class="chapter-footer" aria-label="Chapter navigation">
        <a href="{relative_url(chapter.slug, prev_slug)}" class="foot-prev">
          <span class="foot-dir">← previous</span>
          <span class="foot-title">{html.escape(prev_title)}</span>
          <span class="foot-sub">{'commonware-book' if prev_slug == 'index' else prev_slug}</span>
        </a>
        <div class="foot-center">
          {html.escape(chapter.slug)}<br>
          <span style="font-size:0.65rem; letter-spacing:0.1em; text-transform:uppercase;">{chapter_state(chapter.slug).lower()} chapter</span>
        </div>
        <a href="{relative_url(chapter.slug, next_slug)}" class="foot-next">
          <span class="foot-dir">next →</span>
          <span class="foot-title">{html.escape(next_title)}</span>
          <span class="foot-sub">{'commonware-book' if next_slug == 'index' else next_slug}</span>
        </a>
      </nav>

      <footer class="site-footer">
        Built from <code>chapter.md</code> using the shared Commonware book renderer.
      </footer>
    </main>

    <aside class="toc-rail" aria-label="Table of contents">
      <div class="toc-label">Contents</div>
      <ul class="toc-list">{toc_html}</ul>
    </aside>
  </div>

  <script>
    (() => {{
      const root = document.documentElement;
      const key = 'commonware-book-theme';
      const button = document.getElementById('theme-toggle');
      const systemDark = window.matchMedia('(prefers-color-scheme: dark)');
      const saved = localStorage.getItem(key);
      const initial = saved || 'dark';
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
          if (progLabel) {{
            progLabel.textContent = active.textContent.trim();
          }}
        }}
      }});
    }}, {{ rootMargin: '-20% 0px -70% 0px' }});

    sections.forEach((section) => obs.observe(section));

    window.addEventListener('scroll', () => {{
      const rect = main.getBoundingClientRect();
      const total = Math.max(main.offsetHeight - window.innerHeight, 1);
      const scrolled = Math.max(0, -rect.top);
      const pct = Math.min(100, (scrolled / total) * 100);
      progFill.style.width = pct + '%';
    }}, {{ passive: true }});
  </script>
</body>
</html>
"""


def index_page(chapters: dict[str, Chapter]) -> str:
    def chapter_row(slug: str, number: int) -> str:
        chapter = chapters[slug]
        deck = teaser(chapter.subtitle or chapter.summary, 140)
        return f"""
            <li class="chapter-row">
                <a class="chapter-row__link" href="{slug}/page.html">
                    <div class="chapter-row__number">{number:02d}</div>
                    <div>
                        <div class="chapter-row__meta">
                            <span class="chapter-row__pill">{chapter.word_count:,} words</span>
                            <span class="chapter-row__pill">{chapter.read_minutes} min</span>
                        </div>
                        <h3 class="chapter-row__title">{html.escape(chapter.title)}</h3>
                        <p class="chapter-row__deck">{html.escape(deck)}</p>
                    </div>
                </a>
            </li>
        """

    group_html = []
    chapter_no = 1
    for label, intro, slugs in PARTS:
        rows = []
        start = chapter_no
        for slug in slugs:
            if slug not in chapters:
                continue
            rows.append(chapter_row(slug, chapter_no))
            chapter_no += 1
        items = "".join(rows)
        group_html.append(
            f"""
            <div class="chapter-group">
                <h2 class="chapter-group__title">{html.escape(label)}</h2>
                <p class="section-copy">{html.escape(intro)}</p>
                <ol class="chapter-list" start="{start}">{items}</ol>
            </div>
            """
        )

    total_words = sum(chapter.word_count for chapter in chapters.values())
    total_minutes = sum(chapter.read_minutes for chapter in chapters.values())
    total_count = len(chapters)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, minimum-scale=1">
    <title>Commonware</title>
    <meta name="description" content="Commonware chapters in recommended reading order.">
    <link rel="icon" href="favicon.ico" type="image/x-icon">
    <link rel="stylesheet" href="style.css">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,300..700;1,6..72,300..700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="book.css">
    <link rel="stylesheet" href="book-interactive.css">
    <style>
      .reading-bar__inner {{ width:min(100%, 92rem); margin:0 auto; padding:0.7rem 1.35rem; display:flex; align-items:center; justify-content:space-between; gap:1rem; font-family:var(--mono); font-size:0.68rem; letter-spacing:0.06em; text-transform:uppercase; color:var(--ink-muted); }}
      .reading-bar__crumbs a {{ color:var(--accent); text-decoration:none; }}
      .shell {{ width:min(100%, 92rem); margin:0 auto; padding:0 1.75rem 5rem; }}
      .hero {{ padding:4.8rem 0 1.8rem; }}
      .hero__title {{ margin:0; font-size:clamp(3.8rem, 10vw, 7.4rem); line-height:0.9; font-weight:500; letter-spacing:-0.055em; }}
      .chapter-row__meta,.chapter-row__number,.chapter-group__title {{ font-family:var(--mono); font-size:0.68rem; letter-spacing:0.12em; text-transform:uppercase; color:var(--ink-faint); }}
      .index-grid {{ display:block; }}
      .section {{ margin-bottom:2.8rem; }}
      .chapter-group + .chapter-group {{ margin-top:2.2rem; }}
      .chapter-group__title {{ margin:0 0 0.9rem; }}
      .chapter-list {{ list-style:none; padding:0; margin:0; border-top:1px solid var(--border-light); }}
      .chapter-row {{ border-bottom:1px solid var(--border-light); }}
      .chapter-row__link {{ display:grid; grid-template-columns:5rem minmax(0, 1fr); gap:1.2rem; padding:1rem 0; text-decoration:none; align-items:start; }}
      .chapter-row__number {{ padding-top:0.18rem; }}
      .chapter-row__title {{ margin:0 0 0.22rem; font-size:1.48rem; line-height:1.08; font-weight:500; color:var(--ink); }}
      .chapter-row__deck {{ margin:0; max-width:62ch; color:var(--ink-muted); font-size:0.98rem; line-height:1.5; }}
      .chapter-row__meta {{ display:flex; gap:0.65rem; flex-wrap:wrap; margin-bottom:0.45rem; }}
      .chapter-row__pill {{ padding:0.2rem 0.45rem; border:1px solid var(--border); border-radius:999px; background:rgba(255,255,255,0.6); }}
      @media (max-width: 700px) {{ .shell {{ padding:0 1rem 3.5rem; }} .reading-bar__inner {{ padding:0.7rem 1rem; flex-wrap:wrap; align-items:center; }} .chapter-row__link {{ grid-template-columns:3.5rem 1fr; }} }}
    </style>
</head>
<body>
  <header class="reading-bar" role="banner">
    <div class="reading-bar__inner">
      <div class="reading-bar__crumbs"><a href="index.html">commonware</a> / <span>book</span></div>
      <div>{total_count} chapters · {total_minutes} min</div>
      <button class="nav-btn theme-toggle" id="theme-toggle" type="button" aria-label="Toggle color theme">dark</button>
    </div>
  </header>
  <div class="shell">
    <section class="hero" aria-labelledby="book-title">
      <h1 class="hero__title" id="book-title">Commonware</h1>
    </section>
    <div class="index-grid">
      <main>
        <section class="section" aria-labelledby="contents-title">
          <p class="chapter-group__title" id="contents-title">Chapters</p>
          {''.join(group_html)}
        </section>
      </main>
    </div>
  </div>
  <script>
    (() => {{
      const root = document.documentElement;
      const key = 'commonware-book-theme';
      const button = document.getElementById('theme-toggle');
      const systemDark = window.matchMedia('(prefers-color-scheme: dark)');
      const saved = localStorage.getItem(key);
      const initial = saved || 'dark';
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
  </script>
</body>
</html>
"""


def write_pages() -> None:
    chapter_paths = {p.parent.name: p for p in ROOT.glob("*/chapter.md")}
    chapters = {slug: parse_chapter(path) for slug, path in chapter_paths.items()}

    shutil.copyfile(SITE_ROOT / "style.css", ROOT / "style.css")
    shutil.copyfile(SITE_ROOT / "favicon.ico", ROOT / "favicon.ico")
    shutil.copyfile(SITE_ROOT / "shared.js", ROOT / "shared.js")

    for slug, chapter in chapters.items():
        out_path = ROOT / slug / "page.html"
        if slug in PUBLISHED and out_path.exists():
            continue
        out_path.write_text(chapter_page(chapter, chapters))

    index_path = ROOT / "index.html"
    index_path.write_text(index_page(chapters))


if __name__ == "__main__":
    write_pages()
