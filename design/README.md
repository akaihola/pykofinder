# Miller columns design study — "Trail"

Interactive prototype: [miller-columns.html][proto] (open it in a browser; it is a
single self-contained file, no server needed).
Screenshots: [`shots/`][shots]. Reference material gathered for the study: [`refs/`][refs].

The prototype is a mock — a fake filesystem, no HTMX, no preview backend. It exists
to settle the *visual and interaction* questions before touching
`src/pykofinder/styles.py` and `src/pykofinder/columns.py`.

Toolbar toggles in the prototype: dotfiles, density (comfortable/compact),
column condensing, light/dark. Keyboard: `↑ ↓ → ←`.

## The problem with the current design

Today's columns are a faithful macOS Finder clone: flat white panes, 1px grey
separators, a blue selection bar, no headers. That inherits Finder's three real
weaknesses:

1. **The path is implied, never drawn.** You infer the trail from four disconnected
   blue bars. With a repeated directory name (`src/pykofinder/…`) that inference
   costs a beat every time.
2. **Columns are anonymous.** Nothing on a column says which folder it is. Scroll
   down and you have lost the only clue — the highlighted parent row — off-screen.
3. **Depth is destructive.** Go six levels deep and the ancestors scroll off the
   left edge entirely. Finder's answer is a horizontal scrollbar, which is the
   worst possible answer: the context you lose is exactly the context you need.

## The design

### 1. The trail is drawn, not inferred

An accent elbow leaves the selected row and lands on the *next column's header*.
The line is solid from the focused column and a soft thread for the rest, so the
whole path reads as one continuous stroke without shouting.

This is the idea behind the Miller-with-borders reference and One Commander's
item-to-contents bracket, but terminating on a **labelled header** instead of a
bare column edge — so the connector doesn't just point, it names its destination.

### 2. Three selection states, all legible

Finder has two (blue / grey), and the grey one is nearly invisible. Ours:

| Column | Treatment | Reads as |
| --- | --- | --- |
| Focused | solid accent fill | "you are here" |
| Ancestor | accent-tinted pill, accent border, accent text | "the trail you walked" |
| Descendant | dashed hairline outline, no fill | "remembered, not active" |

### 3. Depth is expressed as light

Each column left of the focus recedes ~3% toward the window chrome. The focused
column is the only pure-white surface on screen. You can find your place with
peripheral vision, before reading anything.

### 4. Column headers

Sticky, with the folder name and a live item count. The focused column's header
carries a 2px accent underline. Costs 30px of vertical space and removes the
"which folder is this?" question permanently.

### 5. Condensing, instead of scrolling away

When the columns plus a 30%-of-viewport preview no longer fit, the leftmost
ancestors fold into 34px spines: a vertical folder name plus the icon of the
child that was chosen there. Click a spine to expand it back.

This is the One Commander idea, and it is the single biggest usability win over
Finder — **ancestors never leave the screen**. Six levels deep you still see the
whole path, and one click returns any level to full width.

### 6. Quieter chrome

- No hard column separators. Columns are rounded cards floating on the chrome;
  separation comes from tone and a hairline shadow, not from lines.
- Rows are inset pills (7px radius, 5px gutter), not full-bleed bars.
- File extensions render in tertiary ink, so the *name* is what you scan.
- Bottom scroll fade when a column overflows, so a cut-off list looks cut off.
- Keyboard cursor is a focus ring *independent* of selection, so arrowing through
  a column without committing is visible.
- Real dark theme. All colour is derived from `--accent` and a handful of ink
  levels via `color-mix()`; theming is a token swap.

## What it would take to build

| Piece | Effort | Where |
| --- | --- | --- |
| Tokens, columns, rows, three selection states, headers, dark theme | pure CSS | `styles.py` (`APP_CSS`) |
| Column header markup + item count | small | `columns.py` (`list_column`, `list_vfs_column`) |
| Trail overlay | ~50 lines JS, repaint on render/scroll/resize | `styles.py` JS block, next to `recalcColumnWidth` |
| Condensing spines | ~30 lines JS in the existing width pass | replaces `recalcColumnWidth`'s clamp logic |

The trail overlay is the only piece needing new JS machinery. Everything else is a
restyle of markup that already exists.

## Open questions for review

1. **Trail weight.** Is the elbow the right amount of ink at 6+ columns, or should
   the non-focused segments drop to a dotted hairline?
2. **Emoji icons.** Kept as-is for the study. A monochrome glyph set (folder
   chevron + type letter) would be calmer and would remove the platform-dependent
   emoji rendering, at the cost of scannability. Worth a separate pass.
3. **Condense trigger.** Currently reserves 30% of the viewport for the preview.
   Should the user be able to pin a column against condensing?
4. **Density default.** Comfortable (26px rows) vs compact (21px). Compact fits
   ~40% more entries; comfortable is easier to hit on a touch screen.

[proto]: ./miller-columns.html
[shots]: ./shots/
[refs]: ./refs/
