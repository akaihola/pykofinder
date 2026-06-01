# Replace abcjs with abc2svg for `.abc` previews

Date: 2026-06-01

## Goal

Render `.abc` music-notation previews with [abc2svg] instead of abcjs.
Self-host the abc2svg JavaScript (no third-party CDN for the engine), obtained
and version-pinned through Python packaging tooling rather than committed blobs.

[abc2svg]: https://chiselapp.com/user/moinejf/repository/abc2svg/doc/trunk/README.md

## Decisions (confirmed with the user)

1. **No audio.** Drop the play control the abcjs version had. SVG sheet music
   only. (abc2svg's audio lives only in `abcweb`/`abcemb`, which take over the
   whole page body and pull a ~MB soundfont — not worth it here.)
2. **Embed in place** in pykofinder's existing preview DOM — no iframe.
3. **Fetch assets at runtime**, version-pinned in code, nothing committed to
   git, no new runtime dependency (stdlib `urllib`).

## Key finding that shapes the approach

abc2svg's "page" entry points are unsuitable for embedding:

| Entry point     | What it does on load                              |
| --------------- | ------------------------------------------------- |
| `abcweb-1.js`   | `document.body.innerHTML = …` (takes over page)   |
| `abcemb-1.js`   | `document.body.innerHTML = …` (takes over page)   |
| `abcemb2-1.js`  | writes into `.abc` elements, but only auto-runs   |
|                 | once on `window.load`; no re-render hook exposed  |

pykofinder loads previews dynamically via HTMX, so a once-on-load auto-renderer
does not fit. Instead we drive the **core API directly** — the same calls
`abcemb` makes internally:

```js
var svg = '';
var user = { img_out: function (s) { svg += s; },
             errmsg:  function (m) { /* collect */ },
             page_format: true };
var abc = new abc2svg.Abc(user);
abc.tosvg('preview', abcSource);   // fills `svg` via img_out
paper.innerHTML = svg;
```

This needs only **one** self-hosted file, `abc2svg-1.js` (~309 KB), which defines
`abc2svg.Abc`. No iframe, no soundfont, no runtime CDN. It mirrors the existing
abcjs integration, which already had a `renderAbcPreviews()` function invoked
from three hooks — we just rewrite that function's body.

Standard notation renders with the core alone. Exotic `%%` directives that need
optional modules (jianpu, tablature, grids, …) are out of scope; such a tune
throws and shows a caught per-preview error rather than breaking the page.

## Architecture

### Asset provisioning — `src/pykofinder/vendor.py` (new)

- Constants: `ABC2SVG_VERSION = "1.22.1"`, `ABC2SVG_FILES = ("abc2svg-1.js",)`,
  base URL `https://cdn.jsdelivr.net/npm/abc2svg@{version}/`.
- `vendor_dir() -> Path`: `${XDG_CACHE_HOME:-~/.cache}/pykofinder/abc2svg/{version}/`.
- `ensure_assets() -> Path`: download each missing file via `urllib.request`
  (short timeout) into `vendor_dir()`. Idempotent — skips files already cached,
  a no-op after the first online run. On network error: log a warning, leave a
  partial/empty dir, never raise.
- `is_provisioned() -> bool`: every file in `ABC2SVG_FILES` exists.

"Managed by packaging tools": version pinned in code, the wheel ships only the
fetcher (no blobs), `uv run pykofinder` self-provisions on first launch, and
updating is a one-line `ABC2SVG_VERSION` bump.

### Serving + head — `src/pykofinder/app.py`

- Remove `_ABCJS_CDN` / `_ABCJS_AUDIO_CSS` and their `<head>` injection
  (app.py:39-45, 138-140).
- Call `ensure_assets()` at startup.
- Mount a read-only static route `/vendor/abc2svg/<file>` serving `vendor_dir()`,
  guarded against path traversal (serve only names in `ABC2SVG_FILES`).
- Inject one script tag in the shell head: `<script src="/vendor/abc2svg/abc2svg-1.js">`
  (replacing the two abcjs tags). Keep the existing mermaid tag untouched.

### Preview HTML — `src/pykofinder/preview.py::_preview_abc`

Keep the hidden-source pattern (clean escaping, no attribute quoting issues);
drop the audio target:

```html
<div class="preview-abc">
  <textarea class="abc-source" hidden>…HTML-escaped ABC source…</textarea>
  <div class="abc-paper"></div>
</div>
```

The server still only embeds escaped source; the browser renders it. The
docstring is updated to name abc2svg and drop the synth references.

### Renderer — `src/pykofinder/styles.py` (COLUMN_JS)

Rewrite `renderAbcPreviews()` (styles.py:641-669): for each
`.preview-abc:not([data-abc-rendered])`, mark it, read `.abc-source` `.value`,
build `user`/`new abc2svg.Abc(user)`, `abc.tosvg('preview', value)`, set
`.abc-paper` innerHTML to the collected SVG. Guard `typeof abc2svg === 'undefined'
|| !abc2svg.Abc`. Wrap `tosvg` in try/catch (same containment as today) so one
bad score can't abort the whole pass. Drop all synth/`ABCJS` code.

Keep the three existing call sites unchanged (`DOMContentLoaded`,
`htmx:afterSettle`, deep-link restore — styles.py:675, 724, 734).

### CSS — `src/pykofinder/styles.py`

Keep `.preview-abc` max-width and the white `.abc-paper` sheet (abc2svg also
draws black glyphs). Remove the `.abc-audio` rule (styles.py:179-194 block).

### Graceful degradation

If assets weren't provisioned (offline first run), `/vendor/...` 404s and
`abc2svg` is undefined; `renderAbcPreviews()` early-returns, leaving the raw
source hidden and the paper empty. Server and all other previews keep working.

## Testing (TDD)

Unit (no network):
- `vendor.vendor_dir`: honours `XDG_CACHE_HOME`, path includes the version.
- `vendor.ensure_assets`: monkeypatch the downloader; asserts it requests the
  jsdelivr URL for a missing file, skips an existing one, and swallows a raised
  network error (returns without crashing).
- `_preview_abc`: emits `preview-abc`, `<textarea class="abc-source"` with the
  escaped source, an `.abc-paper` target, and **no** `abc-audio` / abcjs string.
  Rewrites test_preview.py:95-118 (the `abc-audio` assertion in
  `test_abc_has_paper_and_audio_targets` is dropped).
- App head: no abcjs CDN URLs; head references `/vendor/abc2svg/abc2svg-1.js`.
  Rewrites test_routes_new.py:308-324.
- Static route: with a dummy file placed in a temp cache dir,
  `/vendor/abc2svg/abc2svg-1.js` returns 200 with a JS content-type; a traversal
  path (`/vendor/abc2svg/../app.py`) is rejected.

Browser (integration, `verify-preview` skill):
- Preview a real `.abc` file, screenshot, confirm an SVG staff renders in
  `.abc-paper`. Validates the core API wiring end-to-end.

## Files touched

- `src/pykofinder/vendor.py` — new asset fetcher.
- `src/pykofinder/app.py` — drop abcjs head; provision + serve + inject core.
- `src/pykofinder/preview.py` — `_preview_abc` markup + docstring.
- `src/pykofinder/styles.py` — `renderAbcPreviews()` body + CSS.
- `tests/test_preview.py`, `tests/test_routes_new.py`, new `tests/test_vendor.py`.
- `README.md` — note self-hosted abc2svg, runtime-fetched, no audio.

## Out of scope / YAGNI

- Audio / MIDI / soundfont (dropped by decision).
- Optional abc2svg modules for exotic `%%` directives (degrade with a caught
  per-preview error).
- Build-time download hook (runtime provisioning chosen).
- Committing the vendored JS to git (cache dir only).
```
