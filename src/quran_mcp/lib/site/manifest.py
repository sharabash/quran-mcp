"""Public HTTP route manifest.

Every browser-facing route the server exposes is declared here in a single
dict keyed by classification, then by URL path.

Classifications control how the handler serves each route:

    "static"    — FileResponse with explicit media type and cache headers.
    "pages"     — Read file text, serve as HTMLResponse. Supports custom
                  error messages when the asset isn't built yet.
    "downloads" — FileResponse with Content-Disposition: attachment header
                  so the browser downloads instead of rendering.
    "dirs"      — Prefix-matched directory mount. Any request under the
                  prefix resolves to a file in the base directory.
                  Subdirectories work (e.g. /screenshots/new/foo.png).
                  Only files whose extension is in "types" are served.

Adding a route: add one entry to the right classification.
Adding a classification: add a new key here + a handler function in handlers.py.

Per-route options:

    "file"      — Path to the asset on disk (exact routes).
    "dir"       — Path to the base directory (dir routes).
    "type"      — MIME type for the response (static files).
    "types"     — Extension -> MIME type map (dir routes).
    "headers"   — Response headers dict. Defaults to 1-hour public cache
                  if omitted: {"Cache-Control": "public, max-age=3600"}.
    "required"  — If True (the default), the server refuses to start when
                  the asset is missing, and returns 500 at request time.
                  If False, the server starts fine and silently skips the
                  route (falls through to MCP transport or 404).
    "missing"   — Custom error message shown when a required page is missing
                  (pages only). Useful for build instructions.

Generated routes (/documentation/data.json, /.health) are not in this
manifest because they produce dynamic responses, not file-backed assets.
They live as explicit cases in handlers.py.
"""

from __future__ import annotations

from typing import Any

from quran_mcp.lib.assets import asset_path
from quran_mcp.lib.documentation.runtime import (
    documentation_page_path,
    documentation_usage_examples_dir,
)

routes: dict[str, dict[str, dict[str, Any]]] = {
    "static": {
        "/icon.png": {"file": asset_path("icons/icon.png"), "type": "image/png"},
        "/icon.svg": {"file": asset_path("icons/icon.svg"), "type": "image/svg+xml", "required": False},
        "/og-image.png": {"file": asset_path("og-image.png"), "type": "image/png", "required": False},
        "/sitemap.xml": {"file": asset_path("sitemap.xml"), "type": "application/xml", "headers": {"Cache-Control": "public, max-age=86400"}},
        "/shared-theme.css": {"file": asset_path("shared-theme.css"), "type": "text/css", "headers": {"Cache-Control": "public, max-age=86400"}},
    },
    "pages": {
        "/": {"file": asset_path("landing.html")},
        "/privacy": {"file": asset_path("privacy.html")},
        "/support": {"file": asset_path("support.html")},
        "/documentation": {
            "file": documentation_page_path(),
            "headers": {"Cache-Control": "no-cache"},
            "required": False,
            "missing": (
                "Svelte docs app not built yet. Run: "
                "cd src/quran_mcp/apps/public/documentation && npm install && npm run build"
            ),
        },
    },
    "downloads": {
        "/SKILL.md": {"file": asset_path("SKILL.md")},
        "/GROUNDING_RULES.md": {"file": asset_path("GROUNDING_RULES.md")},
    },
    "dirs": {
        "/screenshots/": {
            "dir": asset_path("screenshots"),
            "types": {".png": "image/png"},
            "required": False,
        },
        "/documentation/assets/": {
            "dir": documentation_usage_examples_dir(),
            "types": {
                ".svg": "image/svg+xml",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".webp": "image/webp",
            },
            "required": False,
        },
    },
}


def validate_required_assets() -> list[str]:
    """Return a list of missing required assets. Empty means all good.

    Called once at startup. Iterates the same routes dict that
    contributors edit — no separate dependency model to keep in sync.
    """
    missing: list[str] = []

    for classification, entries in routes.items():
        for path, entry in entries.items():
            if not entry.get("required", True):
                continue

            if classification == "dirs":
                target = entry.get("dir")
                if not target or not target.is_dir():
                    missing.append(f"{path} -> {target} (dir)")
            else:
                target = entry.get("file")
                if not target or not target.is_file():
                    missing.append(f"{path} -> {target} (file)")

    return missing
