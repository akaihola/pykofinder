# pykofinder

A macOS Finder-style column-view file browser and previewer, served as a local
web application. Navigate directories by clicking column entries; previews render
inline for Markdown, DOCX, PPTX, PDF, images, plain text, and source code.

## Features

- **Column view** – multi-pane navigation à la macOS Finder
- **Rich previews** – Markdown (with plugins), DOCX, PPTX, PDF, images, plain text, source code with syntax highlighting (Pygments "friendly" theme), ABC music notation (rendered as sheet music with an audio player via abcjs)
- **Markdown extras** – wikilinks (`[[PageName]]`), Mermaid diagrams, plain-URL linkification, relative-link normalisation
- **Virtual filesystem** – SQLite databases are browsable as navigable table → row columns; additional VFS providers for JSON and CSV files
- **Static web server** – `/w/<mount>/<path>` serves any file under a named mount with the correct Content-Type (useful for HTML files); the root directory itself is mounted as `/w/<ROOT.name>/...`, and each direct symlink child of ROOT is mounted under its own name
- **Canonical finder URLs** – workspace-local navigation uses `/f/<mount>/<path>` in the address bar; legacy `/f/?path=<absolute>` remains accepted for compatibility fallbacks
- **Breadcrumb trail** – `~ / dir / subdir / file` navigation bar; includes a `.*` dotfile toggle that persists across sessions
- **URL sync** – browser URL stays in sync with the selected path using canonical `/f/<mount>/<path>` URLs for workspace-local files; deep-link any location directly
- **Keyboard navigation** – `↑↓` move within a column; `→`/`Enter` open; `←` go back while keeping the URL in sync with the visible parent/root state; `Home`/`End`/`PgUp`/`PgDn` scroll; column focus states visually indicated
- **Live reload** – `--live` flag restarts the server on code changes and refreshes the browser on content changes via SSE
- **Zoom** – expand preview pane to full viewport width
- **`.desktop` hyperlinks** – open service URLs directly from the browser
- **Symlink support** – safely follows symlink bookmarks in the configured root
- **PWA** – installable as a Progressive Web App; includes a Web App Manifest, service worker (stale-while-revalidate for the app shell, network-only for dynamic partials), and full icon set

## Installation

```bash
uv sync
```

## Usage

```bash
uv run pykofinder [OPTIONS] [ROOT]
```

| Option          | Default   | Env var             | Description                      |
| --------------- | --------- | ------------------- | -------------------------------- |
| `ROOT`          | `$PWD`    | `PYKOFINDER_ROOT`   | Root directory to browse         |
| `--port`        | `8000`    | –                   | TCP port to listen on            |
| `--bind` / `-b` | `0.0.0.0` | `PYKOFINDER_BIND`   | Network interface to bind to     |
| `--live`        | off       | `PYKOFINDER_LIVE=1` | Enable auto-reload (development) |

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full development workflow and rules.

Quick start:

```bash
uv sync
timeout 120 uv run pytest          # unit + integration tests with coverage

# Real-browser regression tests (requires PLAYWRIGHT_BROWSERS_PATH)
# Covers ArrowLeft URL sync and the keyboard-only parent-column survival regression.
timeout 120 PLAYWRIGHT_BROWSERS_PATH="$PLAYWRIGHT_BROWSERS_PATH" \
  uv run --with "playwright==1.57.0" pytest tests/test_browser_keyboard.py
```

## Architecture

```
src/pykofinder/
├── app.py          # FastHTML app, routes, _resolve_safe()
├── cli.py          # Typer CLI entry point
├── columns.py      # Column HTML generation + breadcrumb + pruning JS
├── preview.py      # Preview dispatcher (md / docx / pptx / pdf / img / code / raw)
├── rendering.py    # markdown-it-py instance with plugins
├── styles.py       # CSS + Pygments theme + HTMX + keyboard + live-reload JS
├── vfs.py          # Virtual-filesystem registry + provider protocol
├── providers/      # VFS backends: SQLite, JSON, CSV
└── static/         # Bundled PWA assets: manifest.json, sw.js, icons/
```

## License

MIT
