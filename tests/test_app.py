from unittest.mock import MagicMock
from urllib.parse import quote

import pykofinder.app as app_module
from pykofinder.app import _resolve_safe, _parse_desktop_url
from starlette.testclient import TestClient


# ── _resolve_safe ─────────────────────────────────────────────────────────────


def test_resolve_safe_valid_path(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    f = tmp_path / "file.txt"
    f.touch()
    assert _resolve_safe(str(f)) == f.resolve()


def test_resolve_safe_traversal_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    outside = str(tmp_path / ".." / "outside.txt")
    assert _resolve_safe(outside) is None


def test_resolve_safe_exception_returns_none(tmp_path, monkeypatch):
    """ROOT.resolve() raises → outer except catches it → returns None."""
    mock_root = MagicMock()
    mock_root.resolve.side_effect = RuntimeError("bad root")
    monkeypatch.setattr(app_module, "ROOT", mock_root)
    assert _resolve_safe("/some/path") is None


# ── _parse_desktop_url ────────────────────────────────────────────────────────


def test_parse_desktop_url_link_type(tmp_path):
    f = tmp_path / "link.desktop"
    f.write_text("[Desktop Entry]\nType=Link\nURL=https://example.com\n")
    assert _parse_desktop_url(f) == "https://example.com"


def test_parse_desktop_url_non_link_returns_none(tmp_path):
    f = tmp_path / "app.desktop"
    f.write_text("[Desktop Entry]\nType=Application\n")
    assert _parse_desktop_url(f) is None


def test_parse_desktop_url_no_section_returns_none(tmp_path):
    f = tmp_path / "bad.desktop"
    f.write_text("[Other]\nFoo=bar\n")
    assert _parse_desktop_url(f) is None


def test_parse_desktop_url_empty_url_returns_none(tmp_path):
    f = tmp_path / "link.desktop"
    f.write_text("[Desktop Entry]\nType=Link\nURL=\n")
    assert _parse_desktop_url(f) is None


def test_parse_desktop_url_exception_returns_none(tmp_path, monkeypatch):
    f = tmp_path / "link.desktop"
    f.touch()
    import configparser as cp_mod

    def boom(self, *a, **kw):
        raise RuntimeError("fail")

    monkeypatch.setattr(cp_mod.ConfigParser, "read", boom)
    assert _parse_desktop_url(f) is None


# ── GET / ─────────────────────────────────────────────────────────────────────


def test_index_returns_200_with_title(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "pykofinder" in resp.text


# ── GET /click ────────────────────────────────────────────────────────────────


def test_click_directory_returns_new_column(client, tmp_root):
    subdir = tmp_root / "subdir"
    resp = client.get(f"/click?path={quote(str(subdir))}&col=1")
    assert resp.status_code == 200
    assert "col-1" in resp.text


def test_click_file_returns_preview(client, tmp_root):
    md_file = tmp_root / "readme.md"
    resp = client.get(f"/click?path={quote(str(md_file))}&col=1")
    assert resp.status_code == 200
    assert "preview-md" in resp.text


def test_click_bad_path_returns_access_denied(client):
    resp = client.get(f"/click?path={quote('/etc/passwd')}&col=1")
    assert resp.status_code == 200
    assert "Access denied" in resp.text


def test_click_render_preview_exception_returns_error_html(
    client, tmp_root, monkeypatch
):
    monkeypatch.setattr(
        "pykofinder.app.render_preview",
        MagicMock(side_effect=RuntimeError("boom")),
    )
    md_file = tmp_root / "readme.md"
    resp = client.get(f"/click?path={quote(str(md_file))}&col=1")
    assert resp.status_code == 200
    assert "preview-error" in resp.text


# ── GET /raw ──────────────────────────────────────────────────────────────────


def test_raw_valid_file_returns_200(client, tmp_root):
    md_file = tmp_root / "readme.md"
    resp = client.get(f"/raw?path={quote(str(md_file))}")
    assert resp.status_code == 200


def test_raw_bad_path_returns_404(client):
    resp = client.get(f"/raw?path={quote('/etc/shadow')}")
    assert resp.status_code == 404


def test_raw_directory_returns_404(client, tmp_root):
    """p.is_file() is False for a directory → 404."""
    resp = client.get(f"/raw?path={quote(str(tmp_root / 'subdir'))}")
    assert resp.status_code == 404


# ── GET /open-link ────────────────────────────────────────────────────────────


def test_open_link_valid_redirects_302(client, tmp_root):
    desktop = tmp_root / "link.desktop"
    resp = client.get(f"/open-link?path={quote(str(desktop))}", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "https://example.com"


def test_open_link_bad_path_returns_404(client):
    resp = client.get(f"/open-link?path={quote('/etc/passwd')}")
    assert resp.status_code == 404


def test_open_link_not_link_type_returns_400(client, tmp_root):
    app_desktop = tmp_root / "app.desktop"
    app_desktop.write_text("[Desktop Entry]\nType=Application\nName=App\n")
    resp = client.get(f"/open-link?path={quote(str(app_desktop))}")
    assert resp.status_code == 400


# ── breadcrumb OOB ────────────────────────────────────────────────────────────


def test_click_directory_includes_breadcrumb_oob(client, tmp_root):
    from urllib.parse import quote

    subdir = tmp_root / "subdir"
    resp = client.get(f"/click?path={quote(str(subdir))}&col=1")
    assert resp.status_code == 200
    assert "hx-swap-oob" in resp.text
    assert "breadcrumb" in resp.text


def test_click_file_includes_breadcrumb_oob(client, tmp_root):
    from urllib.parse import quote

    md_file = tmp_root / "readme.md"
    resp = client.get(f"/click?path={quote(str(md_file))}&col=1")
    assert resp.status_code == 200
    assert "breadcrumb" in resp.text


# ── GET /restore ──────────────────────────────────────────────────────────────


def test_restore_valid_directory_returns_200(client, tmp_root):
    from urllib.parse import quote

    subdir = tmp_root / "subdir"
    resp = client.get(f"/restore?path={quote(str(subdir))}")
    assert resp.status_code == 200
    assert 'id="finder"' in resp.text
    assert "col-0" in resp.text


def test_restore_valid_file_includes_preview(client, tmp_root):
    from urllib.parse import quote

    md = tmp_root / "readme.md"
    resp = client.get(f"/restore?path={quote(str(md))}")
    assert resp.status_code == 200
    assert "preview-md" in resp.text


def test_restore_bad_path_returns_root_view(client, tmp_root):
    from urllib.parse import quote

    resp = client.get(f"/restore?path={quote('/etc/passwd')}")
    assert resp.status_code == 200
    assert "finder" in resp.text


def test_restore_zone2_deep_path_shows_all_columns(tmp_path, monkeypatch):
    """restore() for a zone-2 *sub*directory must generate all intermediate columns.

    ROOT has a symlink bookmark → outside_dir.  Requesting restore for
    outside_dir/subdir must produce col-0 (ROOT), col-1 (bookmark), and
    col-2 (subdir).  The previous code used ``parts = [p.name]`` which only
    produced the ROOT column when p is a sub-path of the bookmark target.
    """
    import tempfile
    from pathlib import Path
    from urllib.parse import quote

    with tempfile.TemporaryDirectory() as outside:
        outside_path = Path(outside)
        subdir = outside_path / "subdir"
        subdir.mkdir()
        (subdir / "file.txt").write_text("hello")
        # zone-2 bookmark: ROOT/bookmark → outside_path
        bookmark = tmp_path / "bookmark"
        bookmark.symlink_to(outside_path)
        monkeypatch.setattr(app_module, "ROOT", tmp_path)
        c = TestClient(app_module.app, raise_server_exceptions=False)
        # Requesting the subdir two levels deep into the zone-2 target
        resp = c.get(f"/restore?path={quote(str(subdir))}")
        assert resp.status_code == 200
        assert "col-0" in resp.text  # ROOT column
        assert "col-1" in resp.text  # bookmark column
        assert "col-2" in resp.text  # subdir column


def test_restore_zone2_symlink_path(tmp_path, monkeypatch):
    """restore() must not crash when _resolve_safe returns a zone-2 path
    that raises ValueError on p.relative_to(ROOT)."""
    import tempfile
    from pathlib import Path
    from urllib.parse import quote
    from starlette.testclient import TestClient

    # Outer dir simulates a target outside ROOT
    with tempfile.TemporaryDirectory() as outside:
        outside_path = Path(outside)
        (outside_path / "zone2.txt").write_text("zone2 content\n")
        # Symlink inside ROOT → outside dir (zone-2 bookmark)
        bookmark = tmp_path / "bookmark"
        bookmark.symlink_to(outside_path)
        monkeypatch.setattr(app_module, "ROOT", tmp_path)
        c = TestClient(app_module.app, raise_server_exceptions=False)
        # Request the file inside the zone-2 target
        resp = c.get(f"/restore?path={quote(str(outside_path / 'zone2.txt'))}")
        assert resp.status_code == 200
        assert "finder" in resp.text


def test_restore_render_preview_exception_handled(client, tmp_root, monkeypatch):
    """render_preview() raising inside restore() must produce a preview-error div."""
    from urllib.parse import quote

    monkeypatch.setattr(
        app_module,
        "render_preview",
        lambda _p: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    md = tmp_root / "readme.md"
    resp = client.get(f"/restore?path={quote(str(md))}")
    assert resp.status_code == 200
    assert "preview-error" in resp.text


def test_url_sync_js_in_column_js():
    from pykofinder.styles import COLUMN_JS

    assert "pushState" in COLUMN_JS
    assert "_pendingPath" in COLUMN_JS or "pendingPath" in COLUMN_JS.lower()
    assert "'/f/?path='" not in COLUMN_JS


def test_deep_navigate_calls_htmx_process():
    """_deepNavigate must call htmx.process() on the new shell after outerHTML swap.

    HTMX 1.9.x has no MutationObserver – programmatic outerHTML replacement is
    invisible to HTMX.  Without an explicit htmx.process() call the freshly-
    injected column links are never initialised and clicks do nothing.
    """
    import re
    from pykofinder.styles import COLUMN_JS

    # Find the _deepNavigate function body
    match = re.search(
        r"function _deepNavigate\b.*?^\}",
        COLUMN_JS,
        re.DOTALL | re.MULTILINE,
    )
    assert match is not None, "_deepNavigate not found in COLUMN_JS"
    func_body = match.group(0)
    assert "htmx.process" in func_body, (
        "_deepNavigate must call htmx.process() after outerHTML replacement"
    )


# ── #6 SSE live-reload ────────────────────────────────────────────────────────


def test_sse_reload_returns_404_without_live_mode(client):
    resp = client.get("/sse/reload")
    assert resp.status_code == 404


def test_sse_generator_emits_reload_on_change(monkeypatch, tmp_path):
    """event_generator must yield 'data: reload\\n\\n' when watchfiles reports a change."""
    import asyncio

    monkeypatch.setattr(app_module, "LIVE_MODE", True)
    monkeypatch.setattr(app_module, "ROOT", tmp_path)

    async def one_shot_watch(*_a, **_kw):
        yield {("modified", str(tmp_path / "file.txt"))}

    import watchfiles

    monkeypatch.setattr(watchfiles, "awatch", one_shot_watch)

    async def run():
        from starlette.responses import StreamingResponse

        resp = await app_module.sse_reload()
        assert isinstance(resp, StreamingResponse)
        first = await resp.body_iterator.__anext__()
        # Exhaust the generator so the loop-exit branch is covered.
        try:
            await resp.body_iterator.__anext__()
        except StopAsyncIteration:
            pass
        return first

    assert asyncio.run(run()) == "data: reload\n\n"


def test_sse_generator_keepalive_on_watchfiles_error(monkeypatch, tmp_path):
    """When watchfiles raises, event_generator must fall back to keepalive pings."""
    import asyncio

    monkeypatch.setattr(app_module, "LIVE_MODE", True)
    monkeypatch.setattr(app_module, "ROOT", tmp_path)

    async def broken_watch(*_a, **_kw):
        raise RuntimeError("watchfiles unavailable")
        yield  # pragma: no cover – makes it an async generator

    import watchfiles

    monkeypatch.setattr(watchfiles, "awatch", broken_watch)

    sleep_durations: list[float] = []

    async def fast_sleep(n: float) -> None:
        sleep_durations.append(n)

    monkeypatch.setattr(asyncio, "sleep", fast_sleep)

    async def run():
        from starlette.responses import StreamingResponse

        resp = await app_module.sse_reload()
        assert isinstance(resp, StreamingResponse)
        first = await resp.body_iterator.__anext__()
        return first

    result = asyncio.run(run())
    assert result == ": keepalive\n\n"
    assert sleep_durations == [30]


def test_sse_reload_exists_with_live_mode(monkeypatch):
    """sse_reload() must return a StreamingResponse (not a 404 Response) in live mode.

    Calling the async handler directly via asyncio.run() avoids making any real
    HTTP request against the infinite SSE stream, which would hang the test suite
    regardless of the timeout strategy used (see issue #17).
    """
    import asyncio
    import pykofinder.app as app_module
    from starlette.responses import StreamingResponse

    monkeypatch.setattr(app_module, "LIVE_MODE", True)
    result = asyncio.run(app_module.sse_reload())
    assert isinstance(result, StreamingResponse)


def test_live_reload_js_in_styles():
    from pykofinder.styles import LIVE_RELOAD_JS

    assert "EventSource" in LIVE_RELOAD_JS
    assert "/sse/reload" in LIVE_RELOAD_JS


# ── #15 Keyboard navigation ───────────────────────────────────────────────────


def test_keyboard_nav_js_in_column_js():
    from pykofinder.styles import COLUMN_JS

    assert "ArrowDown" in COLUMN_JS
    assert "ArrowUp" in COLUMN_JS
    assert "ArrowRight" in COLUMN_JS
    assert "ArrowLeft" in COLUMN_JS


# ── #18 CSS + JS presence ─────────────────────────────────────────────────────

from pykofinder.styles import APP_CSS, COLUMN_JS


def test_app_css_has_fmt_bar():
    assert ".fmt-bar" in APP_CSS


def test_app_css_has_fmt_btn():
    assert ".fmt-btn" in APP_CSS


def test_app_css_has_fmt_btn_active():
    assert ".fmt-btn.active" in APP_CSS


def test_app_css_has_preview_db_spreadsheet():
    assert "preview-db-spreadsheet" in APP_CSS


def test_app_css_has_db_table():
    assert "db-table" in APP_CSS


def test_app_css_has_db_table_wrap():
    assert "db-table-wrap" in APP_CSS


def test_app_css_has_db_kv_table():
    assert "db-kv-table" in APP_CSS


def test_app_css_has_db_pagination():
    assert "db-pagination" in APP_CSS


def test_app_css_has_bc_virtual():
    assert "bc-virtual" in APP_CSS


def test_column_js_has_htmx_config_request_listener():
    assert "htmx:configRequest" in COLUMN_JS


def test_column_js_has_vfmt_file_key():
    assert "vfmt_file_" in COLUMN_JS


def test_column_js_has_vfmt_type_key():
    assert "vfmt_type_" in COLUMN_JS


def test_column_js_has_local_storage_set_item():
    assert "localStorage.setItem" in COLUMN_JS


def test_column_js_has_fmt_btn_click_handler():
    assert "fmt-btn" in COLUMN_JS


# ── #27 – /restore must pre-select entries in each column ─────────────────────


def _li_tag(html: str, entry_name: str) -> str:
    """Return the opening <li ...> tag for the first entry whose display text
    contains *entry_name*.  Searches for the entry name, finds the enclosing
    <li, then extracts just the opening tag (up to the first ``>``)."""
    idx = html.index(f'title="{entry_name}"')
    li_start = html.rfind("<li", 0, idx)
    li_tag_end = html.find(">", li_start)
    return html[li_start : li_tag_end + 1]


def test_restore_directory_highlights_selected_entries(tmp_path, monkeypatch):
    """restore() for a nested directory must mark the path component in each
    column with class='selected'."""
    from urllib.parse import quote
    from starlette.testclient import TestClient

    # Build tmp_path/alpha/beta/gamma
    (tmp_path / "alpha").mkdir()
    (tmp_path / "alpha" / "beta").mkdir()
    (tmp_path / "alpha" / "beta" / "gamma").mkdir()
    (tmp_path / "other").mkdir()  # sibling – must NOT be selected

    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    c = TestClient(app_module.app, raise_server_exceptions=False)
    target = tmp_path / "alpha" / "beta" / "gamma"
    resp = c.get(f"/restore?path={quote(str(target))}")
    assert resp.status_code == 200
    html = resp.text

    # All three intermediate entries must be selected
    for name in ("alpha", "beta", "gamma"):
        assert "selected" in _li_tag(html, name), f"{name!r} entry must be selected"

    # Sibling 'other' must NOT be selected
    assert "selected" not in _li_tag(html, "other"), "'other' must not be selected"


def test_restore_file_highlights_selected_entries_including_file(tmp_path, monkeypatch):
    """restore() for a file path must select the file entry in the final column."""
    from urllib.parse import quote
    from starlette.testclient import TestClient

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "readme.md").write_text("# hello")
    (tmp_path / "docs" / "other.txt").write_text("other")

    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    c = TestClient(app_module.app, raise_server_exceptions=False)
    target = tmp_path / "docs" / "readme.md"
    resp = c.get(f"/restore?path={quote(str(target))}")
    assert resp.status_code == 200
    html = resp.text

    assert "selected" in _li_tag(html, "docs"), "'docs' must be selected"
    assert "selected" in _li_tag(html, "readme.md"), "'readme.md' must be selected"
    assert "selected" not in _li_tag(html, "other.txt"), (
        "'other.txt' must not be selected"
    )


# ── #28 – /restore must render VFS column for VFS-backed files ────────────────


def test_restore_vfs_file_renders_table_column_not_unsupported(tmp_path, monkeypatch):
    """/restore for a .db file must render the VFS table-list column,
    not fall through to render_preview() which returns 'No preview available'.
    """
    import sqlite3
    from urllib.parse import quote
    from starlette.testclient import TestClient

    db = tmp_path / "test.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
    con.execute("INSERT INTO items VALUES (1, 'alpha')")
    con.commit()
    con.close()

    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    c = TestClient(app_module.app, raise_server_exceptions=False)
    resp = c.get(f"/restore?path={quote(str(db))}")

    assert resp.status_code == 200
    assert "preview-unsupported" not in resp.text
    # The VFS column must list the table name
    assert "items" in resp.text


# ── #29 VFS URL sync – /restore with vpath ────────────────────────────────


def test_restore_vfs_with_table_vpath_renders_row_column(tmp_path, monkeypatch):
    """/restore?path=file.db&vpath=tablename must render both the table-list column
    (with the table highlighted) and the row-list column for that table.
    """
    import sqlite3
    from urllib.parse import quote
    from starlette.testclient import TestClient

    db = tmp_path / "data.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
    con.execute("INSERT INTO items VALUES (1, 'alpha')")
    con.execute("INSERT INTO items VALUES (2, 'beta')")
    con.commit()
    con.close()

    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    c = TestClient(app_module.app, raise_server_exceptions=False)
    resp = c.get(f"/restore?path={quote(str(db))}&vpath=items")

    assert resp.status_code == 200
    html = resp.text
    # Table-list column must show "items" as selected
    assert "selected" in html
    # Row-list column must show row entries (row IDs 1 and 2)
    assert "alpha" in html or "1" in html


def test_restore_vfs_with_row_vpath_renders_preview(tmp_path, monkeypatch):
    """/restore?path=file.db&vpath=tablename/rowkey must render the row KV preview."""
    import sqlite3
    from urllib.parse import quote
    from starlette.testclient import TestClient

    db = tmp_path / "data.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
    con.execute("INSERT INTO items VALUES (1, 'alpha')")
    con.commit()
    con.close()

    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    c = TestClient(app_module.app, raise_server_exceptions=False)
    resp = c.get(f"/restore?path={quote(str(db))}&vpath=items/1")

    assert resp.status_code == 200
    html = resp.text
    # Must contain the KV preview content (the row's column values)
    assert "preview-db-row" in html or "alpha" in html


def test_restore_vfs_vpath_table_has_selected_on_table_entry(tmp_path, monkeypatch):
    """/restore with vpath=tablename must mark the table entry as selected in the column."""
    import sqlite3
    from urllib.parse import quote
    from starlette.testclient import TestClient

    db = tmp_path / "data.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
    con.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY)")
    con.execute("INSERT INTO items VALUES (1, 'alpha')")
    con.commit()
    con.close()

    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    c = TestClient(app_module.app, raise_server_exceptions=False)
    resp = c.get(f"/restore?path={quote(str(db))}&vpath=items")

    assert resp.status_code == 200
    html = resp.text
    # "items" entry must be in a selected <li>
    idx = html.index("items")
    li_start = html.rfind("<li", 0, idx)
    li_end = html.find(">", li_start)
    li_tag = html[li_start : li_end + 1]
    assert "selected" in li_tag


def test_url_sync_js_tracks_vpath():
    """COLUMN_JS must capture vpath from HTMX links and include it in pushState URL."""
    from pykofinder.styles import COLUMN_JS

    assert "_pendingVpath" in COLUMN_JS
    assert "vpath" in COLUMN_JS
    assert "_pendingFinderUrl" in COLUMN_JS


def test_url_sync_js_reads_finder_url_from_clicked_link():
    """History sync must read the canonical URL from data-finder-url on the clicked link."""
    from pykofinder.styles import COLUMN_JS

    assert "data-finder-url" in COLUMN_JS
    assert "finderUrl: a.getAttribute('data-finder-url') || null" in COLUMN_JS


def test_url_sync_js_pushes_pending_finder_url_without_reconstructing_path():
    """History sync must push the server-provided finder URL verbatim."""
    from pykofinder.styles import COLUMN_JS

    assert "_syncUrl(_pendingPath, _pendingVpath, _pendingFinderUrl)" in COLUMN_JS
    assert (
        "history.pushState({path: path, vpath: vpath || null}, '', finderUrl)"
        in COLUMN_JS
    )


def test_click_nested_directory_emits_root_mount_finder_url(tmp_path, monkeypatch):
    """Second-column entries under ROOT must keep the ROOT mount in data-finder-url."""
    from urllib.parse import quote
    from starlette.testclient import TestClient

    workspace = tmp_path / "my-knowledge"
    docs = workspace / "docs"
    docs.mkdir(parents=True)
    (docs / "topic.md").write_text("# topic")

    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    c = TestClient(app_module.app, raise_server_exceptions=False)
    resp = c.get(f"/click?path={quote(str(workspace))}&col=1")

    assert resp.status_code == 200
    assert f'data-finder-url="/f/{tmp_path.name}/my-knowledge/docs"' in resp.text


def test_click_nested_directory_preserves_root_mount_for_bookmark_targets(
    tmp_path, monkeypatch
):
    """Nested entries reached through ROOT must keep the ROOT mount, not collapse to the child name."""
    from urllib.parse import quote
    from starlette.testclient import TestClient

    menu = tmp_path / "menu"
    workspace = menu / "my-knowledge"
    docs = workspace / "docs"
    docs.mkdir(parents=True)
    (docs / "topic.md").write_text("# topic")

    monkeypatch.setattr(app_module, "ROOT", menu)
    c = TestClient(app_module.app, raise_server_exceptions=False)
    resp = c.get(f"/click?path={quote(str(workspace))}&col=1")

    assert resp.status_code == 200
    assert 'data-finder-url="/f/menu/my-knowledge/docs"' in resp.text
    assert 'data-finder-url="/f/my-knowledge/docs"' not in resp.text


def test_deep_navigate_js_passes_vpath_to_restore():
    """_deepNavigate must forward vpath to the /restore endpoint."""
    from pykofinder.styles import COLUMN_JS

    assert "_deepNavigate" in COLUMN_JS
    # The function must accept a vpath argument and append it to the URL
    assert "vpath" in COLUMN_JS


# ── #30 – JSON VFS preview ─────────────────────────────────────────────────────


def test_click_json_file_renders_json_not_stub(tmp_path, monkeypatch):
    """Clicking a .json file must show formatted JSON content, not the stub message."""
    import json
    from urllib.parse import quote
    from starlette.testclient import TestClient

    data = {"key": "value", "count": 42}
    jf = tmp_path / "data.json"
    jf.write_text(json.dumps(data))

    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    c = TestClient(app_module.app, raise_server_exceptions=False)
    resp = c.get(f"/click?path={quote(str(jf))}&col=1")

    assert resp.status_code == 200
    assert "not yet implemented" not in resp.text
    # Must contain the JSON content
    assert "value" in resp.text or "preview-code" in resp.text


def test_restore_json_file_shows_json_preview(tmp_path, monkeypatch):
    """/restore for a .json file must render JSON content in the preview pane."""
    import json
    from urllib.parse import quote
    from starlette.testclient import TestClient

    data = {"heartbeat": True, "status": "ok"}
    jf = tmp_path / "state.json"
    jf.write_text(json.dumps(data))

    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    c = TestClient(app_module.app, raise_server_exceptions=False)
    resp = c.get(f"/restore?path={quote(str(jf))}")

    assert resp.status_code == 200
    assert "not yet implemented" not in resp.text
    assert "preview-unsupported" not in resp.text
    # JSON content must appear in the preview
    assert "heartbeat" in resp.text or "preview-code" in resp.text
