# Miller columns design study — "Trail"

Interactive prototype: [miller-columns.html][proto] — open it in a browser, no server
needed. It loads two files from [`vendor/`][vendor], so keep the directory alongside it.
Screenshots: [`shots/`][shots]. Reference material for the study: `design/refs/`
(downloaded locally, not committed).

The prototype is a mock — a fake filesystem, no HTMX, no preview backend. It exists
to settle the *visual and interaction* questions before touching
`src/pykofinder/styles.py` and `src/pykofinder/columns.py`.

Settings live behind the ⚙ menu: dotfiles, row density, dark theme.
Keyboard: `↑ ↓ → ←`. Horizontal scroll (`⇧`+wheel, trackpad swipe, or the scrollbar)
drives the condensing dial described below.

## The problem with the current design

Today's columns are a faithful macOS Finder clone: flat white panes, 1px grey
separators, a blue selection bar, no headers. That inherits Finder's three real
weaknesses:

1. **The path is implied, never drawn.** You infer the trail from four disconnected
   blue bars. With a repeated directory name (`src/pykofinder/…`) that inference
   costs a beat every time.
2. **Columns are anonymous.** Nothing on a column says which folder it is. Scroll
   down and you have lost the only clue — the highlighted parent row — off-screen.
3. **Depth is destructive.** Go six levels deep and either the ancestors scroll off
   the left edge or the preview is pushed off the right. Finder's answer is a
   horizontal scrollbar that just translates the strip, which trades one lost pane
   for another.

## The design

### 1. Horizontal scroll is a condensing dial, not a pan

This is the centrepiece, and it replaces the automatic-condensing heuristic of the
first draft. `scrollLeft` is read as a 0–100% dial:

| Position | Layout |
| --- | --- |
| **0%** | every column unfolded; the preview overflows off the right edge |
| **k · (99%/n)** | the leftmost *k* columns folded to spines |
| **99%** | every column folded; the preview fills what is left |
| **99–100%** | the spine strip itself slides away; at 100% the preview is alone |

So the scrollbar means *"how much of the window do you want to spend on columns?"*
Nothing is ever lost off an edge you can't get back from, and the two extremes are
both genuinely useful: 0% is "show me the whole tree", 100% is "read this document".

**The default position is the least folding that still gives the preview its full
width** (45% of the window, clamped to 420–760px) — so the preview is never clipped
on arrival, and the deepest columns are always the ones you keep.

Mechanically: `#finder` scrolls, `#rail` supplies the scroll range, and `#stage` is
`position: sticky` so nothing actually translates — the scroll offset is read as a
number. That gives native scrollbar, trackpad and `⇧`+wheel support for free.
Clicking a spine scrolls back just far enough to unfold it.

### 2. The trail is drawn, not inferred

An accent elbow leaves the selected row and lands on the *next column's header* —
solid from the focused column, a soft thread for the rest. Its vertical run sits on
the centre line of the gutter between the two columns.

This is the idea behind the Miller-with-borders and One Commander item-to-contents
brackets, but terminating on a **labelled header** instead of a bare column edge —
so the connector doesn't just point, it names its destination. When a column is
folded, the elbow runs to its spine icon instead, so the trail survives condensing.

### 3. Three selection states, all legible

Finder has two (blue / grey), and the grey one is nearly invisible. Ours:

| Column | Treatment | Reads as |
| --- | --- | --- |
| Focused | solid accent fill | "you are here" |
| Ancestor | accent-tinted pill, accent border, accent text | "the trail you walked" |
| Descendant | dashed hairline outline, no fill | "remembered, not active" |

### 4. Depth is expressed as light

Each column left of the focus recedes ~3% toward the window chrome. The focused
column is the only pure-white surface on screen. You can find your place with
peripheral vision, before reading anything.

### 5. Column headers

Sticky, with the folder name and a live item count. The focused column's header
carries a 2px accent underline. Costs 26px of vertical space and removes the
"which folder is this?" question permanently.

### 6. Spines keep folded ancestors on screen

A folded column is a 34px strip: the folder name set vertically, plus the icon of
the child that was chosen there. Six levels deep in a 1000px window you still see
the whole path. Click one to unfold it.

### 7. Seti icons

Files use the **Seti UI** icon font — the one VS Code ships as its "Seti" file icon
theme. MIT, one 37 KB `.woff`, no per-icon requests, and it comes with an existing
extension mapping.

`vendor/build-seti-map.py` joins the two upstream sources into a single 13 KB
`vendor/seti-map.js` (248 extensions, 92 exact filenames, 180 light-theme colour
overrides, plus per-icon colours):

| Source | License | Provides |
| --- | --- | --- |
| [jesseweed/seti-ui][seti] `mapping.less`, `ui-variables.less` | MIT | extension → icon name → colour |
| [microsoft/vscode][vscode] `theme-seti` | MIT | icon name → font codepoint, light-theme colours |

Both licenses are in [`vendor/SETI-LICENSE.md`][lic]. Regenerate with
`uv run --no-project python design/vendor/build-seti-map.py`.

Directories deliberately do **not** use a Seti glyph — they get a plain drawn folder
that inherits the row's colour, so folders read as structure and files read as
content. A short `SUPP` table in the prototype covers five extensions Seti has
glyphs for but never bound (`.nix`, `.db`, `.sqlite`, `.lock`, `.desktop`).

### 8. Quieter chrome

- No hard column separators. Columns are rounded cards floating on the chrome;
  separation comes from tone and a hairline shadow, not from lines.
- Compact rows (21px) by default; comfortable (26px) in settings.
- File extensions render in tertiary ink, so the *name* is what you scan.
- Bottom scroll fade when a column overflows, so a cut-off list looks cut off.
- Keyboard cursor is a focus ring *independent* of selection, so arrowing through
  a column without committing is visible.
- Real dark theme. All colour derives from `--accent` and a few ink levels via
  `color-mix()`; theming is a token swap.

## What it would take to build

| Piece | Effort | Where |
| --- | --- | --- |
| Tokens, columns, rows, three selection states, headers, dark theme | pure CSS | `styles.py` (`APP_CSS`) |
| Column header markup + item count | small | `columns.py` (`list_column`, `list_vfs_column`) |
| Seti font + map | 50 KB of static assets | `static/`, served like the existing PWA assets |
| Scroll dial (rail/stage/strip + `applyScroll`) | ~60 lines JS | replaces `recalcColumnWidth`'s clamp logic |
| Trail overlay | ~50 lines JS, repaints on render / column scroll / dial | `styles.py` JS block |
| Settings popover | small | `columns.py` (`render_breadcrumb`) + CSS |

Two caveats for the real implementation:

- **Do not transition column width.** Folding tracks the scroll 1:1; a CSS
  transition makes the trail paint against stale geometry.
- The trail must repaint on column body scroll as well as on the dial, and skip any
  segment whose origin has scrolled out of its column body or off the left edge.

## Screenshots

| File | Shows |
| --- | --- |
| `01-default.png` | opening state, three columns |
| `02-deep-default.png` | six levels deep, default dial position |
| `03-scroll-000.png` | dial at 0% — nothing folded, preview overflows right |
| `04-scroll-035.png` | dial mid-way |
| `05-scroll-099.png` | dial at 99% — all folded, preview fills |
| `06-scroll-100.png` | dial at 100% — preview alone |
| `07-settings.png` | the ⚙ menu |
| `08-dark.png` | dark theme |

## Open question

**Trail weight at 6+ columns.** Settled as good at the current 2px solid / soft
thread. Worth one more look once it is running against real directory listings,
where more columns are scrolled mid-list and more segments get suppressed.

[proto]: ./miller-columns.html
[shots]: ./shots/
[vendor]: ./vendor/
[lic]: ./vendor/SETI-LICENSE.md
[seti]: https://github.com/jesseweed/seti-ui
[vscode]: https://github.com/microsoft/vscode/tree/main/extensions/theme-seti
