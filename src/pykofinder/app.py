import configparser
import html as html_lib
import json
import os
from pathlib import Path
from textwrap import dedent
from urllib.parse import quote as urlquote
from urllib.parse import unquote as urlunquote

from fasthtml.common import (
    Body,
    Div,
    Head,
    Html,
    Link,
    Meta,
    NotStr,
    Script,
    Style,
    Title,
    fast_app,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import FileResponse, HTMLResponse, RedirectResponse, Response

from pykofinder.columns import (
    initial_columns,
    list_column,
    list_vfs_column,
    render_breadcrumb,
)
from pykofinder.preview import render_preview
from pykofinder.styles import APP_CSS, COLUMN_JS, LIVE_RELOAD_JS
from pykofinder.vfs import REGISTRY

# CDN URL for mermaid.js (UMD build – sets window.mermaid on load)
_MERMAID_CDN = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"

# Static files bundled with the package (PWA manifest, service worker, icons)
_STATIC_DIR: Path = Path(__file__).parent / "static"

# Inline JS injected into every page to register the service worker
_SW_REGISTER_JS: str = dedent("""\
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/sw.js', {scope: '/'});
    }
""")

# HTML file extensions that get a "View as web page" button in the preview
_HTML_EXTS = {".html", ".htm"}

# Overridden by cli.py before serve() is called; also supports env var for reload mode
ROOT: Path = Path(os.environ.get("PYKOFINDER_ROOT", str(Path.home())))

LIVE_MODE: bool = os.environ.get("PYKOFINDER_LIVE", "").lower() in ("1", "true", "yes")

app, rt = fast_app(
    hdrs=(
        Style(APP_CSS),
        Script(COLUMN_JS),
    ),
    pico=False,
    live=False,
)


def _resolve_safe(path_str: str, root: Path | None = None) -> Path | None:
    """Resolve a user-supplied path and verify it falls within an allowed zone.

    Allowed zones
    -------------
    1. ROOT itself – any real file or directory that lives under ROOT.
    2. The resolved target of any *direct* symlink child of ROOT – lets
       directory symlinks placed in ROOT act as bookmarks whose subtrees are
       fully browsable.

    Symlinks *within* a bookmark subtree are only allowed when their resolved
    target falls inside zone 1 or the same zone-2 directory (or another
    bookmark target).  Symlinks that escape all allowed zones are denied.

    Path-traversal via ``..`` is defeated because the containment check
    operates on the fully-resolved path, not the raw string.
    """
    effective_root = root if root is not None else ROOT
    try:
        resolved_root = effective_root.resolve()
        resolved = Path(os.path.normpath(urlunquote(path_str))).resolve()

        # Zone 1: within ROOT
        try:
            resolved.relative_to(resolved_root)
            return resolved
        except ValueError:
            pass

        # Zone 2: within the resolved target of a direct symlink child of ROOT
        for child in effective_root.iterdir():
            if child.is_symlink():
                target = child.resolve()
                try:
                    resolved.relative_to(target)
                    return resolved
                except ValueError:
                    continue

        return None
    except Exception:
        return None


def _shell_html(*extra_head_scripts):
    """Return the full app-shell HTML page."""
    extra_scripts = [Script(LIVE_RELOAD_JS)] if LIVE_MODE else []
    return Html(
        Head(
            Title("pykofinder"),
            Meta(name="viewport", content="width=device-width, initial-scale=1"),
            Meta(name="theme-color", content="#0770C9"),
            Meta(name="mobile-web-app-capable", content="yes"),
            Meta(name="apple-mobile-web-app-capable", content="yes"),
            Meta(
                name="apple-mobile-web-app-status-bar-style",
                content="black-translucent",
            ),
            Meta(name="apple-mobile-web-app-title", content="pykofinder"),
            Link(rel="manifest", href="/manifest.json"),
            Link(rel="apple-touch-icon", href="/icons/icon-192.png"),
            Style(APP_CSS),
            Script(src="https://unpkg.com/htmx.org@1.9.12"),
            Script(src=_MERMAID_CDN),
            Script(COLUMN_JS),
            Script(_SW_REGISTER_JS),
            *extra_scripts,
            *extra_head_scripts,
        ),
        Body(initial_columns(ROOT)),
    )


@rt("/")
def index():
    """Redirect root to the finder namespace."""
    return RedirectResponse("/f/", status_code=302)


@rt("/sse/reload")
async def sse_reload():
    """Server-Sent Events stream; emits a reload event when files under ROOT change."""
    if not LIVE_MODE:
        from starlette.responses import Response

        return Response(status_code=404)

    from starlette.responses import StreamingResponse
    import asyncio

    async def event_generator():
        try:
            from watchfiles import awatch

            async for _changes in awatch(str(ROOT)):
                yield "data: reload\n\n"
        except Exception:
            # If watchfiles not available or error, just keep stream open
            while True:
                await asyncio.sleep(30)
                yield ": keepalive\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _make_bc_oob(path: Path, vpath: str = "") -> str:
    """Return breadcrumb HTML string with hx-swap-oob="true" set."""
    return render_breadcrumb(path, ROOT, vpath).replace(
        '<nav id="breadcrumb">', '<nav id="breadcrumb" hx-swap-oob="true">'
    )


def _build_prune_js(col: int) -> str:
    """Return a <script> that prunes sibling columns ≥ col and restores sentinel."""
    return dedent(f"""\
        <script>
        (function(){{
            var el = document.getElementById('col-{col}');
            while (el && el.id !== 'preview') {{
                var next = el.nextElementSibling;
                el.remove();
                el = next;
            }}
            var sentinel = document.createElement('div');
            sentinel.id = 'col-{col}';
            var preview = document.getElementById('preview');
            if (preview) preview.parentNode.insertBefore(sentinel, preview);
        }})();
        </script>""")


@rt("/click")
def click(path: str, col: int, vpath: str = "", fmt: str = "", leaf: bool = False):
    """Handle click on a directory, file, or VFS entry."""
    p = _resolve_safe(path)
    if p is None:
        return Div(
            "Access denied.",
            id=f"col-{col}",
            cls="column",
            style="color:#c00; padding:1rem;",
        )

    # ── VFS dispatch ──────────────────────────────────────────────────────────
    provider = REGISTRY.get(p)
    if provider is not None:
        resolved_fmt = fmt or provider.default_fmt(vpath)
        entries = provider.list_entries(p, vpath)

        if resolved_fmt == "spreadsheet":
            # Spreadsheet mode: collapse column to sentinel, OOB-update preview
            try:
                preview_html = provider.render_preview(
                    p, vpath, "spreadsheet", page=1, limit=1000, col=col
                )
            except Exception as exc:
                preview_html = (
                    f'<div class="preview-error">'
                    f"Preview error: {html_lib.escape(str(exc))}</div>"
                )
            sentinel = Div(id=f"col-{col}")
            preview_oob = NotStr(
                f'<div id="preview" hx-swap-oob="true">{preview_html}</div>'
            )
            bc_oob = NotStr(_make_bc_oob(p, vpath))
            return sentinel, preview_oob, bc_oob

        elif not entries:
            # No children at this vpath – either a true leaf (row detail) or an empty
            # folder (e.g. an empty table).  The two cases differ in the HTMX target:
            #   leaf=True  → request targets #preview with innerHTML
            #   leaf=False → request targets #col-{col} with outerHTML
            # leaf=1 is added to the hx-get URL of non-folder VFS entries in
            # list_vfs_column so the server can tell them apart.
            try:
                preview_html = provider.render_preview(
                    p, vpath, resolved_fmt, page=1, limit=1000, col=col
                )
            except Exception as exc:
                preview_html = (
                    f'<div class="preview-error">'
                    f"Preview error: {html_lib.escape(str(exc))}</div>"
                )
            bc_oob = NotStr(_make_bc_oob(p, vpath))
            if leaf:
                # True leaf: the response goes directly into #preview via innerHTML.
                # Include prune_js to clean up any stale right-hand columns.
                prune_js = _build_prune_js(col)
                return NotStr(preview_html + prune_js + _make_bc_oob(p, vpath))
            else:
                # Empty folder (e.g. empty table): request targeted #col-{col} via
                # outerHTML.  Return a sentinel for that slot and push the preview
                # content out-of-band into #preview.
                sentinel = NotStr(
                    f'<div id="col-{col}"></div>' + _build_prune_js(col + 1)
                )
                preview_oob = NotStr(
                    f'<div id="preview" hx-swap-oob="true">{preview_html}</div>'
                )
                return sentinel, preview_oob, bc_oob

        else:
            # Column mode: show entries as a column (tables or row listing)
            show_fmt_bar = any(e.icon == "📋" for e in entries)
            encoded_path = urlquote(str(p))
            new_col = list_vfs_column(
                entries=entries,
                fs_path_encoded=encoded_path,
                fs_path_raw=str(p),
                vpath=vpath,
                col_index=col,
                show_fmt_bar=show_fmt_bar,
                active_fmt=resolved_fmt,
                ext=p.suffix.lower(),
            )
            preview_clear = Div(id="preview", hx_swap_oob="true")
            bc_oob = NotStr(_make_bc_oob(p, vpath))
            return new_col, preview_clear, bc_oob

    # ── Real directory ────────────────────────────────────────────────────────
    if p.is_dir():
        # Return new column as main swap target; preview and breadcrumb cleared via OOB
        bc_oob = render_breadcrumb(p, ROOT).replace(
            '<nav id="breadcrumb">', '<nav id="breadcrumb" hx-swap-oob="true">'
        )
        new_col = list_column(p, ROOT, col_index=col)
        preview_clear = Div(id="preview", hx_swap_oob="true")
        return new_col, preview_clear, NotStr(bc_oob)

    # ── Regular file preview ──────────────────────────────────────────────────
    try:
        preview_html = render_preview(p)
    except Exception as e:
        preview_html = (
            f'<div class="preview-error">Preview error: {html_lib.escape(str(e))}</div>'
        )
    # For HTML files prepend a "View as web page" button
    if p.suffix.lower() in _HTML_EXTS:
        web_url = _web_url(p)
        if web_url:
            preview_html = (
                f'<div class="preview-webmode-bar">'
                f'<a href="{html_lib.escape(web_url)}" target="_blank"'
                f' rel="noopener noreferrer">🌐 View as web page</a></div>'
            ) + preview_html
    # Prune columns col-{col} and beyond (left over from prior directory navigation),
    # then recreate the col-{col} sentinel.
    prune_js = _build_prune_js(col)
    bc_oob = render_breadcrumb(p, ROOT).replace(
        '<nav id="breadcrumb">', '<nav id="breadcrumb" hx-swap-oob="true">'
    )
    return NotStr(preview_html + prune_js + bc_oob)


@rt("/vpage")
def vpage(path: str, vpath: str, page: int = 1, limit: int = 1000):
    """Return a paginated spreadsheet fragment for the given VFS table (target: #preview)."""
    p = _resolve_safe(path)
    if p is None or not p.is_file():
        return HTMLResponse("Not found", status_code=404)
    provider = REGISTRY.get(p)
    if provider is None:
        return HTMLResponse("Not found", status_code=404)
    try:
        html = provider.render_preview(
            p, vpath, fmt="spreadsheet", page=page, limit=limit, col=0
        )
    except Exception as exc:
        html = (
            f'<div class="preview-error">'
            f"Preview error: {html_lib.escape(str(exc))}</div>"
        )
    return NotStr(html)


@rt("/raw")
def raw(path: str):
    """Serve raw file bytes (used by PDF iframe)."""
    p = _resolve_safe(path)
    if p is None or not p.is_file():
        return HTMLResponse("Not found", status_code=404)
    return FileResponse(str(p))


def _parse_desktop_url(path: Path) -> str | None:
    """Parse a .desktop file and return URL if Type=Link, else None."""
    try:
        cp = configparser.ConfigParser(interpolation=None)
        cp.read(str(path), encoding="utf-8")
        if "Desktop Entry" in cp:
            entry = cp["Desktop Entry"]
            if entry.get("Type", "").strip() == "Link":
                url = entry.get("URL", "").strip()
                return url or None
    except Exception:
        pass
    return None


@rt("/restore")
def restore(path: str, vpath: str = ""):
    """Return a full app-shell HTML for the given path (deep-link restoration)."""
    p = _resolve_safe(path)
    if p is None:
        # Fall back to root view
        shell = initial_columns(ROOT)
        return HTMLResponse(repr(shell))

    # Build ancestor chain: ROOT plus each directory step down to p
    try:
        rel = p.relative_to(ROOT)
        parts = list(rel.parts)
    except ValueError:
        # Zone-2 path: p lives inside the resolved target of a direct symlink
        # child of ROOT.  Build parts as [symlink_name, *sub_path_parts] so
        # that all intermediate columns (ROOT → bookmark → … → p) are rendered.
        parts = None
        for child in ROOT.iterdir():
            if child.is_symlink():
                target = child.resolve()
                try:
                    rel_in_target = p.relative_to(target)
                    parts = [child.name] + list(rel_in_target.parts)
                    break
                except ValueError:
                    continue
        if parts is None:
            parts = [p.name]  # fallback: p is exactly the symlink target

    dirs: list[Path] = []
    cur = ROOT
    for part in parts:
        dirs.append(cur)
        cur = cur / part
    if cur.is_dir():
        dirs.append(cur)

    cols_html = ""
    for i, d in enumerate(dirs):
        if d.is_dir():  # pragma: no branch – dirs only ever contains directories
            sel = parts[i] if i < len(parts) else None
            col_obj = list_column(d, ROOT, col_index=i, selected_name=sel)
            cols_html += repr(col_obj)

    sentinel_idx = len([d for d in dirs if d.is_dir()])
    sentinel_html = f'<div id="col-{sentinel_idx}"></div>'

    preview_html = ""
    if p.is_file():
        provider = REGISTRY.get(p)
        if provider is not None:
            # VFS-backed file (e.g. SQLite .db): walk vpath segments, rendering
            # one column per level, then show a preview at the leaf.
            encoded_path = urlquote(str(p))
            vpath_parts = [seg for seg in vpath.split("/") if seg]
            for i in range(len(vpath_parts) + 1):
                current_vpath = "/".join(vpath_parts[:i])
                selected_vpath = (
                    "/".join(vpath_parts[: i + 1]) if i < len(vpath_parts) else None
                )
                entries = provider.list_entries(p, current_vpath)
                if not entries:
                    # Leaf or empty node: render preview regardless of vpath depth
                    # (e.g. JSON files have no navigable children even at root vpath).
                    try:
                        preview_html = provider.render_preview(
                            p, current_vpath, "folders", 1, 1000, col=sentinel_idx
                        )
                    except Exception as exc:
                        preview_html = f'<div class="preview-error">{html_lib.escape(str(exc))}</div>'
                    break
                show_fmt_bar = any(e.icon == "📋" for e in entries)
                vfs_col = list_vfs_column(
                    entries=entries,
                    fs_path_encoded=encoded_path,
                    fs_path_raw=str(p),
                    vpath=current_vpath,
                    col_index=sentinel_idx,
                    show_fmt_bar=show_fmt_bar,
                    active_fmt=provider.default_fmt(current_vpath),
                    ext=p.suffix.lower(),
                    selected_vpath=selected_vpath,
                )
                cols_html += repr(vfs_col)
                sentinel_idx += 1
            sentinel_html = f'<div id="col-{sentinel_idx}"></div>'
        else:
            try:
                preview_html = render_preview(p)
            except Exception as e:
                preview_html = (
                    f'<div class="preview-error">{html_lib.escape(str(e))}</div>'
                )

    preview_cls = "" if preview_html else "preview-empty"
    preview_div = f'<div id="preview" class="{preview_cls}">{preview_html}</div>'
    bc_html = render_breadcrumb(p, ROOT)

    full = (
        f'<div id="app-shell">{bc_html}'
        f'<div id="finder">{cols_html}{sentinel_html}{preview_div}</div></div>'
    )
    return HTMLResponse(full)


@rt("/open-link")
def open_link(path: str):
    """Redirect the browser to the URL stored in a .desktop link file."""
    p = _resolve_safe(path)
    if p is None or not p.is_file():
        return HTMLResponse("Not found", status_code=404)
    url = _parse_desktop_url(p)
    if not url:
        return HTMLResponse("Not a .desktop link file", status_code=400)
    return RedirectResponse(url, status_code=302)


# ── #23 helpers + routes ──────────────────────────────────────────────────────


def _mount_targets() -> dict[str, Path]:
    """Return named mounts exposed under ``/w/<mount>/...``.

    The root directory itself is always mounted under ``ROOT.name``. Each direct
    symlink child of ``ROOT`` is also mounted under the symlink name.
    """
    mounts = {ROOT.name: ROOT.resolve()}
    for child in ROOT.iterdir():
        if child.is_symlink():
            mounts[child.name] = child.resolve()
    return mounts


def _resolve_web_mount(path: str) -> Path | None:
    """Resolve a ``/w/`` path using named mounts.

    The first path segment names either the root mount (``ROOT.name``) or one of
    ROOT's direct symlink children. The remainder is resolved relative to that
    mount target and still validated through ``_resolve_safe()``.
    """
    stripped = path.lstrip("/")
    if not stripped:
        return None

    mount_name, _, remainder = stripped.partition("/")
    target_root = _mount_targets().get(mount_name)
    if target_root is None:
        return None

    candidate = target_root / remainder if remainder else target_root
    return _resolve_safe(str(candidate))


def _mounted_path_parts(p: Path) -> tuple[str, Path] | None:
    """Return ``(mount_name, relative_path)`` for a resolved path, or ``None``.

    Canonical URL generation for both ``/w/`` and ``/f/`` shares the same named-mount
    mapping. Prefer the visible ROOT tree, including descendants reached through direct
    symlink children, then fall back to standalone bookmark mounts.
    """
    effective_root = ROOT
    mounts = _mount_targets()
    root_mount = ROOT.name
    resolved_root = mounts[root_mount]

    try:
        rel_from_root = p.relative_to(resolved_root)
        visible_candidate = effective_root / rel_from_root
        if (
            visible_candidate.exists()
            and (visible_candidate == p or visible_candidate.resolve() == p)
        ) or not rel_from_root.parts:
            return root_mount, rel_from_root
    except ValueError:
        pass

    for child in effective_root.iterdir():
        if not child.is_symlink():
            continue
        try:
            rel_from_child = p.relative_to(child.resolve())
        except ValueError:
            continue
        visible_rel = (
            Path(child.name) / rel_from_child
            if rel_from_child.parts
            else Path(child.name)
        )
        return root_mount, visible_rel

    for mount_name, target in mounts.items():
        if mount_name == root_mount:
            continue
        try:
            return mount_name, p.relative_to(target)
        except ValueError:
            continue
    return None


def _finder_url(p: Path, vpath: str = "") -> str | None:
    """Return a canonical ``/f/`` URL for *p*, optionally preserving *vpath*."""
    mounted = _mounted_path_parts(p)
    if mounted is None:
        return None
    mount_name, rel = mounted
    url = f"/f/{mount_name}/{rel}"
    if vpath:
        url += f"?vpath={urlquote(vpath)}"
    return url


def _web_url(p: Path) -> str | None:
    """Return a canonical ``/w/`` URL for *p*, or ``None`` if it is unreachable."""
    mounted = _mounted_path_parts(p)
    if mounted is None:
        return None
    mount_name, rel = mounted
    return f"/w/{mount_name}/{rel}"


@rt("/w/{path:path}")
def web_static(path: str):
    """Serve a named-mount ``/w/<mount>/...`` file with the correct Content-Type."""
    p = _resolve_web_mount(path)
    if p is None or not p.is_file():
        return HTMLResponse("Not found", status_code=404)
    return FileResponse(str(p))


@rt("/f/")
def finder_root(path: str = "", vpath: str = ""):
    """Serve the finder root or redirect legacy ``/f/?path=...`` deep-links."""
    if path:
        p = _resolve_safe(path)
        if p is None or not p.exists():
            return HTMLResponse("Not found", status_code=404)
        canonical = _finder_url(p, vpath)
        if canonical is not None:
            return RedirectResponse(canonical, status_code=302)
        nav_js = (
            f"document.addEventListener('DOMContentLoaded',"
            f"function(){{_deepNavigate({json.dumps(str(p))}, {json.dumps(vpath or None)})}});"
        )
        return _shell_html(Script(nav_js))
    return _shell_html()


@rt("/f/{path:path}")
def finder_view(path: str = "", vpath: str = ""):
    """Serve the finder shell at an optional canonical mount-relative path.

    ``/f/`` renders the root view.
    ``/f/<mount>/<relative>`` renders the shell and deep-links to that file.
    """
    if not path:
        return _shell_html()

    mount_name, _, remainder = path.lstrip("/").partition("/")
    target_root = _mount_targets().get(mount_name)
    if target_root is None:
        return HTMLResponse("Not found", status_code=404)

    candidate = target_root / remainder if remainder else target_root
    p = _resolve_safe(str(candidate))
    if p is None or not p.exists():
        return HTMLResponse("Not found", status_code=404)

    nav_js = (
        f"document.addEventListener('DOMContentLoaded',"
        f"function(){{_deepNavigate({json.dumps(str(p))}, {json.dumps(vpath or None)})}});"
    )
    return _shell_html(Script(nav_js))


# ── PWA static files ─────────────────────────────────────────────────────────


@rt("/manifest.json")
def manifest():
    """Serve the Web App Manifest."""
    return FileResponse(
        str(_STATIC_DIR / "manifest.json"), media_type="application/manifest+json"
    )


@rt("/sw.js")
def service_worker():
    """Serve the service worker with the required Service-Worker-Allowed header."""
    data = (_STATIC_DIR / "sw.js").read_bytes()
    return Response(
        content=data,
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )


@rt("/icons/{name}")
def icon(name: str):
    """Serve a named icon from the bundled static/icons/ directory."""
    safe_name = Path(name).name  # strip any directory traversal
    icon_path = _STATIC_DIR / "icons" / safe_name
    if not icon_path.exists() or not icon_path.is_file():
        return HTMLResponse("Not found", status_code=404)
    return FileResponse(str(icon_path))


# ── #38 CORS middleware (scoped to /w/) ──────────────────────────────────────

_CORS_HEADERS: dict[str, str] = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "*",
}


class _WebStaticCORSMiddleware(BaseHTTPMiddleware):
    """Add CORS headers to every /w/ response; handle OPTIONS preflight."""

    async def dispatch(self, request, call_next):
        if not request.url.path.startswith("/w/"):
            return await call_next(request)
        if request.method == "OPTIONS":
            return Response(status_code=200, headers=_CORS_HEADERS)
        response = await call_next(request)
        response.headers.update(_CORS_HEADERS)
        return response


app.add_middleware(_WebStaticCORSMiddleware)


# ── Route priority fix ────────────────────────────────────────────────────────
# FastHTML registers a catch-all /{fname:path}.{ext:static} at index 0 that
# intercepts any path with a known static extension (including .html, .txt, …).
# Move /w/ and /f/ in front of it so they are matched first.
def _reorder_routes() -> None:
    routes = app.router.routes
    _prefixes = {
        "/w/{path:path}",
        "/f/",
        "/f/{path:path}",
        "/manifest.json",
        "/sw.js",
        "/icons/{name}",
    }
    priority, rest = [], []
    for r in routes:
        (priority if getattr(r, "path", "") in _prefixes else rest).append(r)
    routes[:] = priority + rest


_reorder_routes()
