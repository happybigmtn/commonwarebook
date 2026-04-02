# Module Page Template

Reusable Fabro workflow for turning a reviewed chapter bundle into a navigable
HTML page that embeds visuals into the reading experience.

Inputs:

- `docs/commonware-book/BOOK-DESIGN.md`
- `$chapter_dir/brief.md`
- `$chapter_dir/chapter.md`
- `$chapter_dir/visuals.json`
- `$chapter_dir/review.md`

Output:

- `$chapter_dir/page.html`

The page should fit inside the existing `docs/` site conventions while reading
like a chapter in an interactive technical book.

The workflow is expected to follow the explicit book design brief in
`docs/commonware-book/BOOK-DESIGN.md`, not just a generic "make it nicer"
instruction.

In particular, the page should aim for the concrete editorial anatomy described
there:

- serif-led reading typography with mono metadata and figure chrome
- off-white paper background with restrained accent color
- centered chapter header with metadata, title, deck, and divider
- right-rail or inline chapter TOC depending on screen size
- framed figure plates instead of dashboard-style widgets
- sticky reading chrome that feels like book navigation rather than app chrome
- page review edits that stay inside the current chapter directory
