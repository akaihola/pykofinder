"""Tests for issues #23 (/w/ static server, /f/ finder view, #21 mermaid CDN)."""

from urllib.parse import quote

import pykofinder.app as app_module
from starlette.testclient import TestClient


def _client(root):
    """Return a TestClient with ROOT pointing at *root*."""
    return TestClient(app_module.app, raise_server_exceptions=False)


# ── #23 GET /w/ – static webserver ───────────────────────────────────────────


def test_web_static_serves_file_via_root_mount(tmp_path, monkeypatch):
    """/w/{ROOT.name}/{path} returns 200 and the file content."""
    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    (tmp_path / "hello.txt").write_text("hello world")
    resp = _client(tmp_path).get(f"/w/{tmp_path.name}/hello.txt")
    assert resp.status_code == 200
    assert resp.text == "hello world"


def test_web_static_serves_file_via_symlink_mount(tmp_path, monkeypatch):
    """/w/{symlink-name}/{path} resolves through a direct symlink child of ROOT."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "guide.txt").write_text("symlink mount")
    root = tmp_path / "menu"
    root.mkdir()
    (root / "coleaders").symlink_to(workspace, target_is_directory=True)
    monkeypatch.setattr(app_module, "ROOT", root)

    resp = _client(root).get("/w/coleaders/guide.txt")
    assert resp.status_code == 200
    assert resp.text == "symlink mount"


def test_web_static_404_for_missing_file(tmp_path, monkeypatch):
    """/w/{mount}/{path} returns 404 when the file does not exist."""
    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    assert (
        _client(tmp_path).get(f"/w/{tmp_path.name}/no_such_file.txt").status_code == 404
    )


def test_web_static_404_for_unknown_mount(tmp_path, monkeypatch):
    """Unknown mount names under /w/ are rejected."""
    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    (tmp_path / "hello.txt").write_text("hello world")
    assert _client(tmp_path).get("/w/unknown/hello.txt").status_code == 404


def test_web_static_correct_content_type_html(tmp_path, monkeypatch):
    """/w/{mount}/file.html serves with Content-Type: text/html."""
    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    (tmp_path / "page.html").write_text("<h1>Hi</h1>")
    resp = _client(tmp_path).get(f"/w/{tmp_path.name}/page.html")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


def test_web_static_traversal_denied(tmp_path, monkeypatch):
    """/w/{mount}/../etc/passwd is blocked (path escapes ROOT)."""
    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    assert _client(tmp_path).get(f"/w/{tmp_path.name}/../etc/passwd").status_code == 404


# ── #38 CORS on /w/ ──────────────────────────────────────────────────────────


def test_web_static_cors_header_present(tmp_path, monkeypatch):
    """/w/{mount}/{path} GET response carries Access-Control-Allow-Origin: *."""
    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    (tmp_path / "photo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    resp = _client(tmp_path).get(f"/w/{tmp_path.name}/photo.png")
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "*"


def test_web_static_cors_methods_header(tmp_path, monkeypatch):
    """/w/ GET response advertises GET and OPTIONS in Access-Control-Allow-Methods."""
    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    (tmp_path / "doc.txt").write_text("hi")
    resp = _client(tmp_path).get(f"/w/{tmp_path.name}/doc.txt")
    methods = resp.headers.get("access-control-allow-methods", "")
    assert "GET" in methods
    assert "OPTIONS" in methods


def test_web_static_options_preflight_200(tmp_path, monkeypatch):
    """/w/ OPTIONS preflight returns 200 with CORS headers."""
    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    (tmp_path / "photo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    resp = _client(tmp_path).options(f"/w/{tmp_path.name}/photo.png")
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "*"


def test_web_static_options_allow_headers(tmp_path, monkeypatch):
    """/w/ OPTIONS preflight echoes Access-Control-Allow-Headers: *."""
    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    (tmp_path / "photo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    resp = _client(tmp_path).options(f"/w/{tmp_path.name}/photo.png")
    assert resp.headers.get("access-control-allow-headers") == "*"


def test_web_static_cors_not_on_other_routes(tmp_path, monkeypatch):
    """/f/ and other routes do NOT carry Access-Control-Allow-Origin."""
    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    resp = _client(tmp_path).get("/f/")
    assert resp.headers.get("access-control-allow-origin") is None


# ── #23 GET /f/ – finder deep-link ────────────────────────────────────────────


def test_finder_view_serves_shell_with_canonical_root_mount_path(tmp_path, monkeypatch):
    """/f/{ROOT.name}/{path} returns the full app shell with an inline _deepNavigate call."""
    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    (tmp_path / "readme.md").touch()
    resp = _client(tmp_path).get(f"/f/{tmp_path.name}/readme.md")
    assert resp.status_code == 200
    body = resp.text
    assert "pykofinder" in body
    assert "_deepNavigate" in body
    assert "readme.md" in body


def test_finder_view_root_serves_shell(tmp_path, monkeypatch):
    """/f/ (no path) returns the full app shell without an inline deep-link call."""
    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    resp = _client(tmp_path).get("/f/")
    assert resp.status_code == 200
    body = resp.text
    assert "pykofinder" in body
    # The inline nav script uses no-space 'DOMContentLoaded',function() pattern.
    # COLUMN_JS uses 'DOMContentLoaded', function() with a space – different.
    assert "'DOMContentLoaded',function()" not in body


def test_root_redirects_to_finder(tmp_path, monkeypatch):
    """GET / redirects to /f/."""
    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    c = TestClient(
        app_module.app, raise_server_exceptions=False, follow_redirects=False
    )
    resp = c.get("/")
    assert resp.status_code == 302
    assert resp.headers.get("location", "").startswith("/f/")


def test_finder_view_404_for_missing(tmp_path, monkeypatch):
    """/f/{mount}/{path} returns 404 when the file does not exist."""
    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    assert (
        _client(tmp_path).get(f"/f/{tmp_path.name}/no_such_thing.md").status_code == 404
    )


def test_finder_view_serves_shell_with_canonical_symlink_mount_path(
    tmp_path, monkeypatch
):
    """/f/{symlink-name}/{path} resolves through a direct symlink child mount."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "guide.md").write_text("# Guide")
    root = tmp_path / "menu"
    root.mkdir()
    (root / "coleaders").symlink_to(workspace, target_is_directory=True)
    monkeypatch.setattr(app_module, "ROOT", root)

    resp = _client(root).get("/f/coleaders/guide.md")
    assert resp.status_code == 200
    body = resp.text
    assert "pykofinder" in body
    assert "_deepNavigate" in body
    assert "guide.md" in body


def test_finder_url_prefers_root_mount_for_symlink_child_descendants(
    tmp_path, monkeypatch
):
    """Paths reached through the visible ROOT tree keep the ROOT mount in canonical URLs."""
    workspace = tmp_path / "workspace"
    docs = workspace / "docs"
    docs.mkdir(parents=True)
    root = tmp_path / "menu"
    root.mkdir()
    (root / "my-knowledge").symlink_to(workspace, target_is_directory=True)
    monkeypatch.setattr(app_module, "ROOT", root)

    assert app_module._finder_url(docs.resolve()) == "/f/menu/my-knowledge/docs"


def test_finder_url_for_unresolved_symlink_child_in_root(tmp_path, monkeypatch):
    """col-0 entries are unresolved symlink paths; _finder_url must canonicalize them.

    Regression: _mounted_path_parts received /menu/my-knowledge (symlink, unresolved)
    but compared visible_candidate.resolve() == p, yielding
    /real/path == /menu/my-knowledge → False, so _finder_url returned None and
    the browser URL dropped back to /f/ on every col-0 click.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    root = tmp_path / "menu"
    root.mkdir()
    symlink = root / "my-knowledge"
    symlink.symlink_to(workspace, target_is_directory=True)
    monkeypatch.setattr(app_module, "ROOT", root)

    # Unresolved symlink path – exactly what path.iterdir() yields in columns.py
    assert app_module._finder_url(symlink) == "/f/menu/my-knowledge"


def test_finder_view_query_path_redirects_to_canonical_mount_path(
    tmp_path, monkeypatch
):
    """Legacy /f/?path=... redirects to /f/{mount}/{relative} for workspace-local files."""
    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    note = tmp_path / "docs" / "guide.md"
    note.parent.mkdir()
    note.write_text("# Guide")

    resp = TestClient(
        app_module.app, raise_server_exceptions=False, follow_redirects=False
    ).get(f"/f/?path={quote(str(note))}")
    assert resp.status_code in (301, 302, 307, 308)
    assert resp.headers.get("location") == f"/f/{tmp_path.name}/docs/guide.md"


def test_finder_view_query_path_redirect_preserves_vpath(tmp_path, monkeypatch):
    """Legacy /f/?path=... keeps vpath when redirecting to the canonical URL."""
    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    db = tmp_path / "data.db"
    db.write_text("")

    resp = TestClient(
        app_module.app, raise_server_exceptions=False, follow_redirects=False
    ).get(f"/f/?path={quote(str(db))}&vpath=items/1")
    assert resp.status_code in (301, 302, 307, 308)
    assert resp.headers.get("location") == f"/f/{tmp_path.name}/data.db?vpath=items/1"


def test_finder_view_404_for_unknown_mount(tmp_path, monkeypatch):
    """Unknown mount names under /f/ are rejected."""
    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    (tmp_path / "readme.md").write_text("# hello")
    assert _client(tmp_path).get("/f/unknown/readme.md").status_code == 404


# ── #23 HTML preview – "View as web page" button ─────────────────────────────


def test_html_preview_has_webmode_button(tmp_path, monkeypatch):
    """Clicking an HTML file injects a '🌐 View as web page' link."""
    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    f = tmp_path / "index.html"
    f.write_text("<h1>Hello</h1>")
    resp = _client(tmp_path).get(f"/click?path={quote(str(f))}&col=1")
    assert resp.status_code == 200
    body = resp.text
    assert "/w/" in body
    assert "🌐" in body or "web page" in body.lower()


def test_htm_preview_has_webmode_button(tmp_path, monkeypatch):
    """.htm files also get the 'View as web page' button."""
    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    f = tmp_path / "page.htm"
    f.write_text("<p>hi</p>")
    resp = _client(tmp_path).get(f"/click?path={quote(str(f))}&col=1")
    assert resp.status_code == 200
    assert "/w/" in resp.text


def test_non_html_preview_no_webmode_button(tmp_path, monkeypatch):
    """Non-HTML file previews do NOT have the 'View as web page' button."""
    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    f = tmp_path / "readme.md"
    f.write_text("# Hello")
    resp = _client(tmp_path).get(f"/click?path={quote(str(f))}&col=1")
    assert resp.status_code == 200
    assert "preview-webmode-bar" not in resp.text


# ── #21 mermaid CDN in page head ─────────────────────────────────────────────


def test_mermaid_js_in_page_head(tmp_path, monkeypatch):
    """The app index page includes a mermaid.js CDN script tag."""
    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    resp = _client(tmp_path).get("/")
    assert resp.status_code == 200
    assert "mermaid" in resp.text.lower()


def test_mermaid_js_cdn_url_present(tmp_path, monkeypatch):
    """The mermaid CDN URL is in the page source."""
    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    resp = _client(tmp_path).get("/")
    assert "cdn.jsdelivr.net" in resp.text
    assert "mermaid" in resp.text


# ── abcjs CDN in page head ───────────────────────────────────────────────────


def test_abcjs_cdn_in_page_head(tmp_path, monkeypatch):
    """The app index page includes the abcjs CDN script tag (basic bundle with synth)."""
    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    resp = _client(tmp_path).get("/")
    assert resp.status_code == 200
    assert "abcjs" in resp.text
    assert "cdn.jsdelivr.net" in resp.text


def test_abcjs_audio_css_in_page_head(tmp_path, monkeypatch):
    """The audio player needs abcjs-audio.css to style its synth controls."""
    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    resp = _client(tmp_path).get("/")
    assert "abcjs-audio.css" in resp.text
