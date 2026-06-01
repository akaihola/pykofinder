# abc2svg `.abc` Preview Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the abcjs `.abc` music-notation preview with self-hosted abc2svg, rendering SVG sheet music in-place (no audio), with the abc2svg engine fetched at runtime and version-pinned in code.

**Architecture:** A new `vendor.py` downloads the single core file `abc2svg-1.js` from the jsdelivr CDN into an XDG cache dir on startup (stdlib `urllib`, idempotent, never raises). `app.py` serves it at `/vendor/abc2svg/{name}` (mirroring the existing `/icons/{name}` route) and injects one `<script>` in the shell head instead of the two abcjs CDN tags. The browser renderer in `styles.py` drives abc2svg's core API directly (`new abc2svg.Abc(user)` + `abc.tosvg(...)`, SVG collected via `user.img_out`) into `.abc-paper`. Design doc: `docs/plans/2026-06-01-abc2svg-preview-design.md`.

**Tech Stack:** Python 3.12, python-fasthtml, starlette, pytest; abc2svg 1.22.1 (vanilla JS, LGPL3+).

---

## Background facts (read before starting)

- abc2svg is published on npm as `abc2svg@1.22.1`; jsdelivr mirrors it at
  `https://cdn.jsdelivr.net/npm/abc2svg@1.22.1/<file>`.
- Only **`abc2svg-1.js`** (~309 KB) is needed — it defines `abc2svg.Abc` and
  `abc2svg.Abc.prototype.tosvg`. The page-level scripts (`abcweb-1.js`,
  `abcemb-1.js`) overwrite `document.body` and must NOT be used.
- Core API used by the browser renderer:
  ```js
  var svg = '';
  var user = { img_out: function (s) { svg += s; },
               errmsg:  function (m) { /* ignore or collect */ },
               page_format: true };
  var abc = new abc2svg.Abc(user);
  abc.tosvg('preview', abcSource);   // appends SVG to `svg` via img_out
  paper.innerHTML = svg;
  ```
- Existing static-route pattern to mirror: `/icons/{name}` in `app.py:690-697`.
- The three renderer call sites in `styles.py` (DOMContentLoaded:734,
  htmx:afterSettle:675, deep-link restore:724) stay; only the function body
  changes.
- Run tests with: `uv run pytest <path> -v`. The repo enforces coverage via
  `addopts`, but single-test runs still pass.

---

## Task 1: `vendor.py` — `vendor_dir()`

**Files:**
- Create: `src/pykofinder/vendor.py`
- Test: `tests/test_vendor.py`

**Step 1: Write the failing test**

```python
# tests/test_vendor.py
from pathlib import Path

from pykofinder import vendor


def test_vendor_dir_honours_xdg_cache_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    d = vendor.vendor_dir()
    assert d == tmp_path / "pykofinder" / "abc2svg" / vendor.ABC2SVG_VERSION


def test_vendor_dir_falls_back_to_home_cache(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    d = vendor.vendor_dir()
    assert d == tmp_path / ".cache" / "pykofinder" / "abc2svg" / vendor.ABC2SVG_VERSION
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_vendor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pykofinder.vendor'`

**Step 3: Write minimal implementation**

```python
# src/pykofinder/vendor.py
"""Runtime provisioning of the self-hosted abc2svg JavaScript engine.

abc2svg renders ``.abc`` music notation to SVG entirely in the browser.  We do
not commit its (~309 KB) source to git; instead we download a version-pinned
copy from the jsdelivr CDN into an XDG cache dir on first launch.  Updating the
engine is a one-line bump of ``ABC2SVG_VERSION``.
"""

import logging
import os
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

# Pinned abc2svg release.  Bump to upgrade; the cache dir is version-scoped so
# old copies are simply ignored.
ABC2SVG_VERSION = "1.22.1"

# The only file we need: it defines abc2svg.Abc + .tosvg (the core SVG engine).
# The page-level scripts (abcweb/abcemb) clobber document.body and are unused.
ABC2SVG_FILES: tuple[str, ...] = ("abc2svg-1.js",)

_CDN_BASE = "https://cdn.jsdelivr.net/npm/abc2svg@{version}/"


def vendor_dir() -> Path:
    """Return the version-scoped cache directory for abc2svg assets."""
    cache_home = os.environ.get("XDG_CACHE_HOME")
    base = Path(cache_home) if cache_home else Path.home() / ".cache"
    return base / "pykofinder" / "abc2svg" / ABC2SVG_VERSION
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_vendor.py -v`
Expected: PASS (both tests)

**Step 5: Commit**

```bash
git add src/pykofinder/vendor.py tests/test_vendor.py
git commit -m "feat(vendor): version-scoped cache dir for abc2svg assets"
```

---

## Task 2: `vendor.py` — `ensure_assets()` and `is_provisioned()`

**Files:**
- Modify: `src/pykofinder/vendor.py`
- Test: `tests/test_vendor.py`

**Step 1: Write the failing tests**

```python
# append to tests/test_vendor.py


def test_ensure_assets_downloads_missing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    calls = []

    def fake_fetch(url: str) -> bytes:
        calls.append(url)
        return b"/* abc2svg */"

    monkeypatch.setattr(vendor, "_fetch", fake_fetch)
    vendor.ensure_assets()

    assert calls == [
        f"https://cdn.jsdelivr.net/npm/abc2svg@{vendor.ABC2SVG_VERSION}/abc2svg-1.js"
    ]
    assert (vendor.vendor_dir() / "abc2svg-1.js").read_bytes() == b"/* abc2svg */"


def test_ensure_assets_skips_existing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    d = vendor.vendor_dir()
    d.mkdir(parents=True)
    (d / "abc2svg-1.js").write_bytes(b"cached")

    def boom(url: str) -> bytes:  # must not be called
        raise AssertionError("should not download an already-cached file")

    monkeypatch.setattr(vendor, "_fetch", boom)
    vendor.ensure_assets()
    assert (d / "abc2svg-1.js").read_bytes() == b"cached"


def test_ensure_assets_swallows_network_error(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    def boom(url: str) -> bytes:
        raise OSError("network down")

    monkeypatch.setattr(vendor, "_fetch", boom)
    # Must not raise, and must not leave a half-written file.
    vendor.ensure_assets()
    assert not vendor.is_provisioned()


def test_is_provisioned_true_when_all_files_present(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert vendor.is_provisioned() is False
    d = vendor.vendor_dir()
    d.mkdir(parents=True)
    for name in vendor.ABC2SVG_FILES:
        (d / name).write_bytes(b"x")
    assert vendor.is_provisioned() is True
```

**Step 2: Run to verify failure**

Run: `uv run pytest tests/test_vendor.py -v`
Expected: FAIL — `AttributeError: module 'pykofinder.vendor' has no attribute 'ensure_assets'`

**Step 3: Implement**

Append to `src/pykofinder/vendor.py`:

```python
def _fetch(url: str) -> bytes:
    """Download ``url`` and return its bytes.  Isolated for test monkeypatching."""
    with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310 (https only)
        return resp.read()


def ensure_assets() -> Path:
    """Download any missing abc2svg files into :func:`vendor_dir`.

    Idempotent and best-effort: files already present are left untouched, and
    any network failure is logged and swallowed (the server still starts; the
    ``.abc`` preview simply renders nothing until a later online run).  A
    partial download is written atomically so a crash mid-fetch never leaves a
    truncated file behind.
    """
    d = vendor_dir()
    d.mkdir(parents=True, exist_ok=True)
    for name in ABC2SVG_FILES:
        target = d / name
        if target.exists():
            continue
        url = _CDN_BASE.format(version=ABC2SVG_VERSION) + name
        try:
            data = _fetch(url)
        except Exception as exc:  # network, HTTP, timeout — never fatal
            logger.warning("Could not download %s: %s", url, exc)
            continue
        tmp = target.with_suffix(target.suffix + ".part")
        tmp.write_bytes(data)
        tmp.replace(target)
    return d


def is_provisioned() -> bool:
    """True when every required abc2svg file is present in the cache dir."""
    d = vendor_dir()
    return all((d / name).is_file() for name in ABC2SVG_FILES)
```

**Step 4: Run to verify pass**

Run: `uv run pytest tests/test_vendor.py -v`
Expected: PASS (all six tests)

**Step 5: Commit**

```bash
git add src/pykofinder/vendor.py tests/test_vendor.py
git commit -m "feat(vendor): best-effort runtime download of abc2svg engine"
```

---

## Task 3: `_preview_abc` — drop audio, point docstring at abc2svg

**Files:**
- Modify: `src/pykofinder/preview.py:87-108`
- Test: `tests/test_preview.py:95-118`

**Step 1: Rewrite the existing tests to the new contract**

Replace `test_abc_embeds_source_in_textarea`, `test_abc_source_is_html_escaped`,
and `test_abc_has_paper_and_audio_targets` (test_preview.py:95-118) with:

```python
def test_abc_embeds_source_in_textarea(tmp_path):
    f = tmp_path / "tune.abc"
    f.write_text("X:1\nT:Test\nK:C\nCDEF|\n")
    result = render_preview(f)
    assert '<textarea class="abc-source"' in result
    assert "CDEF|" in result


def test_abc_source_is_html_escaped(tmp_path):
    """A tune with HTML-special characters must be escaped so it cannot break out."""
    f = tmp_path / "tune.abc"
    f.write_text("X:1\nT:A & B </textarea><script>x</script>\nK:C\nCDEF|\n")
    result = render_preview(f)
    assert "</textarea><script>" not in result
    assert "&amp;" in result
    assert "&lt;/textarea&gt;" in result


def test_abc_has_paper_target_and_no_audio(tmp_path):
    f = tmp_path / "tune.abc"
    f.write_text("X:1\nT:Test\nK:C\nCDEF|\n")
    result = render_preview(f)
    assert "abc-paper" in result
    assert "abc-audio" not in result
```

**Step 2: Run to verify failure**

Run: `uv run pytest tests/test_preview.py -k abc -v`
Expected: FAIL — `test_abc_has_paper_target_and_no_audio` fails because the
current markup still contains `abc-audio`.

**Step 3: Implement the markup change**

Replace `_preview_abc` (preview.py:87-108) with:

```python
def _preview_abc(path: Path) -> str:
    """Preview an ABC music notation file — rendered client-side by abc2svg.

    The server only embeds the raw notation (HTML-escaped) inside a hidden
    ``<textarea>``; the browser reads its ``.value`` and drives the abc2svg
    core API (``new abc2svg.Abc(...)`` + ``tosvg``) to paint the sheet music as
    SVG into ``.abc-paper`` (see ``renderAbcPreviews`` in COLUMN_JS).  There is
    no audio player — abc2svg's playback lives only in its page-level scripts,
    which take over the whole document.
    """
    try:
        content = path.read_text(encoding="utf-8")
        safe = html_lib.escape(content)
        return (
            '<div class="preview-abc">'
            f'<textarea class="abc-source" hidden>{safe}</textarea>'
            '<div class="abc-paper"></div>'
            "</div>"
        )
    except Exception as e:
        return (
            f'<div class="preview-error">Preview error: {html_lib.escape(str(e))}</div>'
        )
```

**Step 4: Run to verify pass**

Run: `uv run pytest tests/test_preview.py -k abc -v`
Expected: PASS (dispatch + 3 rewritten tests)

**Step 5: Commit**

```bash
git add src/pykofinder/preview.py tests/test_preview.py
git commit -m "feat(preview): abc2svg .abc markup (drop audio target)"
```

---

## Task 4: `app.py` — serve the vendored engine, swap the head scripts

**Files:**
- Modify: `src/pykofinder/app.py` (imports, head injection lines 39-45 & 138-140, new route near 690-697, startup call)
- Test: `tests/test_routes_new.py:308-324`

**Step 1: Rewrite the head/route tests**

Replace the two `test_abcjs_*` tests (test_routes_new.py:308-324) with:

```python
# ── abc2svg engine in page head + /vendor route ──────────────────────────────


def test_abc2svg_script_in_page_head(tmp_path, monkeypatch):
    """The shell head loads the self-hosted abc2svg engine, not abcjs."""
    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    resp = _client(tmp_path).get("/")
    assert resp.status_code == 200
    assert "/vendor/abc2svg/abc2svg-1.js" in resp.text
    assert "abcjs" not in resp.text


def test_vendor_route_serves_cached_file(tmp_path, monkeypatch):
    """/vendor/abc2svg/<name> serves a cached engine file as JavaScript."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    from pykofinder import vendor

    d = vendor.vendor_dir()
    d.mkdir(parents=True)
    (d / "abc2svg-1.js").write_bytes(b"/* engine */")

    resp = _client(tmp_path).get("/vendor/abc2svg/abc2svg-1.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers["content-type"]
    assert resp.content == b"/* engine */"


def test_vendor_route_rejects_unknown_name(tmp_path, monkeypatch):
    """Only whitelisted engine filenames are served (no traversal / arbitrary read)."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    resp = _client(tmp_path).get("/vendor/abc2svg/../app.py")
    assert resp.status_code == 404
```

Check the top of `tests/test_routes_new.py` for the existing `_client` helper
and `app_module` import alias; reuse them as the other tests in this file do.

**Step 2: Run to verify failure**

Run: `uv run pytest tests/test_routes_new.py -k "abc2svg or vendor" -v`
Expected: FAIL — head still references abcjs; `/vendor/...` route 404s for the
cached-file test (route not yet defined).

**Step 3: Implement**

(a) Imports — add near `app.py:32-34`:

```python
from pykofinder import vendor
```

(b) Remove the abcjs constants (app.py:39-45), i.e. delete the
`_ABCJS_CDN` and `_ABCJS_AUDIO_CSS` definitions and their comments.

(c) In `_shell_html` replace the three lines (app.py:138-140):

```python
            Link(rel="stylesheet", href=_ABCJS_AUDIO_CSS),
            Script(src=_MERMAID_CDN),
            Script(src=_ABCJS_CDN),
```

with:

```python
            Script(src=_MERMAID_CDN),
            Script(src="/vendor/abc2svg/abc2svg-1.js"),
```

(d) Provision on import — add after the `_STATIC_DIR` definition (app.py:48):

```python
# Download the abc2svg engine (best-effort, idempotent) so the .abc preview can
# render.  Safe to call on every startup; a no-op once cached.
vendor.ensure_assets()
```

(e) Add a route mirroring `/icons/{name}` — insert after the `icon` route
(after app.py:697):

```python
@rt("/vendor/abc2svg/{name}")
def abc2svg_asset(name: str):
    """Serve a whitelisted abc2svg engine file from the runtime cache dir."""
    if name not in vendor.ABC2SVG_FILES:
        return HTMLResponse("Not found", status_code=404)
    asset_path = vendor.vendor_dir() / name
    if not asset_path.is_file():
        return HTMLResponse("Not found", status_code=404)
    return FileResponse(str(asset_path), media_type="application/javascript")
```

**Step 4: Run to verify pass**

Run: `uv run pytest tests/test_routes_new.py -k "abc2svg or vendor" -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add src/pykofinder/app.py tests/test_routes_new.py
git commit -m "feat(app): serve vendored abc2svg engine; drop abcjs CDN head tags"
```

---

## Task 5: `styles.py` — drive the abc2svg core API; drop audio CSS

**Files:**
- Modify: `src/pykofinder/styles.py:641-669` (renderer), `:179-194` (CSS)

No new unit test (this is browser JS inside a Python string constant — verified
in Task 6 via the browser). Keep the change minimal and self-contained.

**Step 1: Replace `renderAbcPreviews()` (styles.py:641-669)**

```javascript
// Render any ABC music-notation previews that have not been drawn yet.  The
// server embeds the raw notation in a hidden <textarea class="abc-source">; we
// drive the abc2svg core API (new abc2svg.Abc + tosvg) which emits SVG via the
// user.img_out callback, and inject it into .abc-paper.  No audio: abc2svg's
// playback lives only in its page-level scripts, which clobber document.body.
function renderAbcPreviews() {
    if (typeof abc2svg === 'undefined' || !abc2svg.Abc) return;
    var blocks = document.querySelectorAll('.preview-abc:not([data-abc-rendered])');
    for (var i = 0; i < blocks.length; i++) {
        var block = blocks[i];
        block.setAttribute('data-abc-rendered', '1');
        var src = block.querySelector('.abc-source');
        var paper = block.querySelector('.abc-paper');
        if (!src || !paper) continue;
        // abc2svg can throw on scores needing unloaded modules / on bad input;
        // contain the failure to this one preview rather than aborting the pass.
        try {
            var svg = '';
            var user = {
                img_out: function (str) { svg += str; },
                errmsg: function () {},
                page_format: true
            };
            var abc = new abc2svg.Abc(user);
            abc.tosvg('preview', src.value);
            paper.innerHTML = svg;
        } catch (err) {
            paper.innerHTML = '<em>Could not render this ABC score: ' +
                String(err && err.message || err) + '</em>';
        }
    }
}
```

**Step 2: Remove the `.abc-audio` CSS rule (styles.py:192-194)**

Delete:

```css
.preview-abc .abc-audio {
    margin-top: 1rem;
}
```

Update the comment above `.preview-abc` (styles.py:179-181) to reference
abc2svg instead of abcjs:

```css
/* ABC music notation.  abc2svg draws black notes on a transparent background,
   invisible on the dark app theme, so give the score a white "sheet of paper"
   surface. */
```

**Step 3: Verify the Python module still imports and existing suite is green**

Run: `uv run pytest tests/test_preview.py tests/test_routes_new.py -q`
Expected: PASS (no syntax error in the JS string; preview/route tests green)

**Step 4: Commit**

```bash
git add src/pykofinder/styles.py
git commit -m "feat(styles): render .abc via abc2svg core API; drop audio CSS"
```

---

## Task 6: Browser verification

**Files:** none (manual/skill-driven verification)

**Step 1: Render a real `.abc` file in a browser**

Use the `verify-preview` skill (it launches the server rooted at a throwaway
dir, navigates the column view, opens the file, screenshots the preview).
Create a sample tune in the throwaway dir, e.g.:

```
X:1
T:Verification Scale
M:C
L:1/4
K:C
CDEF|GABc|
```

**Step 2: Confirm**

- The `.abc-paper` div contains an `<svg>` with rendered staff/notes.
- No console error referencing `ABCJS` or a failed `/vendor/abc2svg/...` fetch.
- The white sheet surface shows black notation (readable on the dark theme).

If the SVG is empty, check that `/vendor/abc2svg/abc2svg-1.js` returns 200 (the
engine downloaded) and that `abc2svg.Abc` is defined in the page console.

**Step 3: (No commit — verification only.)**

---

## Task 7: Full suite + README

**Files:**
- Modify: `README.md`

**Step 1: Run the whole test suite**

Run: `uv run pytest -q`
Expected: PASS, coverage report prints. Fix any abcjs-referencing test that was
missed (grep: `rg -i abcjs tests/`).

**Step 2: Update README**

Find the abcjs mention (`rg -n -i "abc" README.md`) and rewrite it to say:
`.abc` music notation is rendered to SVG by [abc2svg], self-hosted and fetched
at first launch into the user cache dir (no audio playback). Add a reference
link to `https://chiselapp.com/user/moinejf/repository/abc2svg`.

**Step 3: Confirm no stray abcjs references remain**

Run: `rg -i "abcjs|abc2svg-basic|abcjs-audio" src/ tests/ README.md`
Expected: no matches (all abcjs traces gone).

**Step 4: Commit**

```bash
git add README.md
git commit -m "docs: README notes abc2svg .abc rendering (self-hosted, no audio)"
```

---

## Done criteria

- `uv run pytest -q` passes.
- A real `.abc` file renders SVG sheet music in the browser (Task 6).
- No `abcjs` references remain anywhere (`rg -i abcjs` is empty).
- Nothing under the abc2svg cache dir is committed to git; the engine is fetched
  at runtime and pinned by `ABC2SVG_VERSION`.
```
