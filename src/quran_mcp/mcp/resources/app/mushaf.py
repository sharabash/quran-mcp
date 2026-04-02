"""Resource: ui://mushaf.html — serves the mushaf MCP App.

Reads the built app.html from the apps/mcp/mushaf/dist/ directory
and serves it as a text/html;profile=mcp-app resource for MCP App hosts.
The resource module owns this build-path lookup directly so the serving
surface stays self-contained.

NOTE: FastMCP's @mcp.resource() decorator silently drops mime_type when
the function returns a bare str (defaults to text/plain). We must return
an explicit ResourceContent with the correct MIME type to get
text/html;profile=mcp-app on the wire.
"""

from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP
from fastmcp.resources import ResourceContent

MCP_APP_MIME = "text/html;profile=mcp-app"
MUSHAF_APP_PATH = Path(__file__).resolve().parents[3] / "apps" / "mcp" / "mushaf" / "dist" / "app.html"


def register(mcp: FastMCP) -> None:
    """Register the mushaf app HTML resource."""

    @mcp.resource(
        "ui://mushaf.html",
        name="Mushaf App",
        description=(
            "Interactive Quran mushaf app. "
            "Renders Arabic text in traditional mushaf layout with verse interaction, "
            "page navigation, and AI-assisted explanation."
        ),
        mime_type=MCP_APP_MIME,
        tags={"preview"},
    )
    async def mushaf_app() -> list[ResourceContent]:
        """Serve the mushaf app HTML."""
        if not MUSHAF_APP_PATH.exists():
            raise FileNotFoundError(
                f"Mushaf app HTML not found at {MUSHAF_APP_PATH}. "
                "Run the Svelte build: cd src/quran_mcp/apps/mcp/mushaf && npm run build"
            )
        html = MUSHAF_APP_PATH.read_text(encoding="utf-8")
        return [ResourceContent(
            html,
            mime_type=MCP_APP_MIME,
            meta={
                "ui": {
                    "csp": {
                        # QCF v2 per-page fonts loaded at runtime via FontFace API
                        "resourceDomains": ["https://verses.quran.foundation"],
                    },
                },
            },
        )]
