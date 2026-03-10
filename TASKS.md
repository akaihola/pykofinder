# pykofinder Tasks

## How tracking works

- **TASKS.md** (this file) is the session-level scratchpad. Use it to track
  work-in-progress and orient a fresh agent at the start of a session.
- **ISSUES.md** is the open-issue registry. Only open or in-progress issues live there;
  closed issues are pruned immediately and their full text is preserved in git history.

**Workflow for an issue:**

1. Add a new issue block to ISSUES.md with `**Status:** open`.
2. When starting work: change status to `in-progress` and add a `[~]` entry below.
3. When done: remove the issue block from ISSUES.md entirely and commit (the git diff
   _is_ the closure record). Move the entry here to **Done** with a one-line summary.

**Status legend for this file:**
`[ ]` open · `[~]` in-progress · `[x]` done

---

## In progress

---

## Open

_Items without an issue number are not yet tracked in ISSUES.md._

- [ ] #41 Dotfile column appears empty when a hidden path segment is active in deep-link restore
- [ ] #40 Web-mode bar missing when opening an HTML file via direct `/f/` URL
- [ ] Pagination for large directories (> 500 entries)
- [ ] Search/filter within a column
- [ ] PPTX slide image rendering via LibreOffice (better fidelity than text extraction)

---

## Done

- [x] #39 Canonical `/f/<mount>/<relative>` URLs + legacy `/f/?path=` fallback; align markdown links, browser history sync, VFS URLs, and `pykoclaw-pykofinder`
- [x] #38 CORS on `/w/` – `Access-Control-Allow-Origin: *` + OPTIONS preflight
- [x] #37 Browser regression now uses the real keyboard-only survival flow
- [x] #36 Browser regression test covers folder-column survival after ArrowLeft/ArrowRight
- [x] #35 Browser regression test covers ArrowLeft URL sync in a real page
- [x] #34 ArrowLeft updates the URL back to the selected parent item/root
- [x] #33 PWA – manifest, service worker, icons, head tags, 20 tests
- [x] #32 Column focus-state visual indicators – col-focused / col-ancestor / col-descendant
- [x] #31 Enhanced keyboard navigation – Home/End/PgUp/PgDn + Left/Right focus model
- [x] #30 JSON VFS preview – implement `render_preview` + fix `restore()` guard
- [x] #29 SQLite table/row navigation not reflected in URL
- [x] #28 Direct URL to VFS file shows "No preview available" instead of table list
- [x] #27 Deep-link restore missing `selected` highlight on entries
- [x] #26 Deep-link zone-2 sub-path missing columns + HTMX re-init after restore
- [x] #25 Dotfile visibility toggle in `<nav>`
- [x] #24 Empty SQLite table corrupts column layout
- [x] #23 Static webserver `/w/` + finder `/f/` routes
- [x] #22 Plain URL linkification (`linkify-it-py`)
- [x] #21 Mermaid diagram rendering
- [x] #20 Wikilink rendering `[[PageName]]`
- [x] #19 Markdown relative link normalization
- [x] #18 Virtual-FS navigation + view-format switching (SQLite + registry)
- [x] #17 Fix hanging SSE test – replace `c.stream()` with `asyncio.run(sse_reload())` unit call
- [x] #16 Bind address CLI option `--bind` / `-b` with `PYKOFINDER_BIND` env var
- [x] #15 Keyboard navigation – `keydown` IIFE in COLUMN_JS for ↑↓→←/Enter/Escape
- [x] #14 Source code syntax highlighting with Pygments "friendly" theme
- [x] #13 Breadcrumb navigation – `~ / dir / subdir / file` trail with OOB swap
- [x] #12 `.desktop` link file support – `🔗` icon, `/open-link` redirect, preview card
- [x] #11 Symlink "Access denied." bug – zone-based `_resolve_safe`, 16 unit tests
- [x] #10 Selected state – `<li>.selected` CSS + click-delegation JS
- [x] #9 Preview pane always at least 1/3 viewport width
- [x] #8 Move project context to AGENTS.md for pi auto-loading
- [x] #7 Raw UTF-8 text fallback preview – `<pre class="preview-raw">` (≤256 KB)
- [x] #6 Auto-reload – SSE `/sse/reload` + `LIVE_RELOAD_JS` + `watchfiles`
- [x] #5 URL sync and deep-link navigation – `pushState`, `/restore`, `_deepNavigate()`
- [x] #4 Zoom button – expand preview to full viewport width
- [x] #3 Auto-adjust column width to fit longest visible filename
- [x] #2 Tooltip for truncated filenames (`title=p.name`)
- [x] #1 Image preview – PNG, JPEG, GIF, WebP, SVG → `<img>` tag
- [x] Initial scaffold – `app.py`, `cli.py`, `columns.py`, `preview.py`, `styles.py`, `rendering.py`
