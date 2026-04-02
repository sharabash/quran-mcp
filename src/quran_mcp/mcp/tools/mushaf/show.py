"""Tool: show_mushaf — open the Quran mushaf app.

Model + app visible. Returns structured_content for App hosts (the app
receives page data as JSON) and a text fallback for non-App hosts.
"""

from dataclasses import asdict
from typing import Annotated

from pydantic import Field

from fastmcp import Context, FastMCP
from fastmcp.tools import ToolResult
from mcp.types import TextContent

from quran_mcp.lib.presentation.client_hint import detect_client_hint
from quran_mcp.lib.mushaf.query import get_page_data, resolve_page
from quran_mcp.lib.mushaf.types import DEFAULT_MUSHAF_ID, PageData
from quran_mcp.mcp.tools._tool_context import resolve_app_context
from quran_mcp.mcp.tools._tool_errors import (
    STANDARD_RESOURCE_ERROR_CONTRACT,
    invalid_request_error,
    service_unavailable_error,
)


def _format_text_fallback(data: PageData) -> str:
    """Format page data as readable text for non-App hosts."""
    parts: list[str] = []

    # Header
    chapter_list = ", ".join(
        f"{name} ({ch_id})" for ch_id, name in sorted(data.chapter_names.items())
    )
    parts.append(f"Mushaf Page {data.page_number}/{data.total_pages}")
    parts.append(f"Surahs: {chapter_list}")

    # Verse range
    if data.verses:
        first = data.verses[0].verse_key
        last = data.verses[-1].verse_key
        parts.append(f"Verses: {first} — {last}")

    parts.append("")

    # Surah headers
    for hdr in data.surah_headers:
        parts.append(f"═══ {hdr.name_arabic} ({hdr.name_simple}) ═══")
        if hdr.bismillah_pre:
            parts.append("بِسْمِ ٱللَّهِ ٱلرَّحْمَـٰنِ ٱلرَّحِيمِ")
        parts.append("")

    # Arabic text grouped by verse
    verse_by_id = {v.verse_id: v.verse_key for v in data.verses}
    current_verse_key = None
    verse_text: list[str] = []

    for line in data.lines:
        for word in line.words:
            vk = verse_by_id.get(word.verse_id, "?")
            if vk != current_verse_key:
                if current_verse_key and verse_text:
                    parts.append(f"[{current_verse_key}] {' '.join(verse_text)}")
                current_verse_key = vk
                verse_text = []
            if word.char_type_name == "word":
                verse_text.append(word.text)

    # Flush last verse
    if current_verse_key and verse_text:
        parts.append(f"[{current_verse_key}] {' '.join(verse_text)}")

    return "\n".join(parts)


def register(mcp: FastMCP) -> None:
    """Register the show_mushaf tool."""

    @mcp.tool(
        name="show_mushaf",
        title="Show Mushaf Page",
        description=(
            "Open the Quran mushaf (traditional page/book reading view) to a specific location. "
            "Renders a full-page mushaf view with Arabic calligraphy, "
            "verse markers, and surah headers. "
            "Entry points: page number, surah[+ayah], or juz. "
            "If no parameters are given, opens page 1 (Al-Fatiha). "
            f"Parameters are mutually exclusive — use only one entry point. {STANDARD_RESOURCE_ERROR_CONTRACT}"
        ),
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
        meta={"ui": {"resourceUri": "ui://mushaf.html"}},
        version="0.1.1",
        tags={"preview", "mushaf", "app"},
    )
    async def show_mushaf_tool(
        page: Annotated[
            int | None,
            Field(
                default=None,
                description="Page number (1-604). Mutually exclusive with surah/juz.",
            ),
        ] = None,
        surah: Annotated[
            int | None,
            Field(
                default=None,
                description="Surah number (1-114). Optionally combined with ayah.",
            ),
        ] = None,
        ayah: Annotated[
            int | None,
            Field(
                default=None,
                description="Ayah number within the surah. Requires surah parameter.",
            ),
        ] = None,
        juz: Annotated[
            int | None,
            Field(
                default=None,
                description="Juz number (1-30). Mutually exclusive with page/surah.",
            ),
        ] = None,
        ctx: Context | None = None,
    ) -> ToolResult:
        """Show a mushaf page with full rendering data."""
        if ayah is not None and surah is None:
            raise invalid_request_error("ayah requires surah parameter")

        app_ctx = resolve_app_context(ctx)
        pool = app_ctx.db_pool
        if not pool:
            raise service_unavailable_error()

        try:
            page_number = await resolve_page(
                pool, page=page, surah=surah, ayah=ayah, juz=juz,
                mushaf_id=DEFAULT_MUSHAF_ID,
            )
            data = await get_page_data(pool, page_number, DEFAULT_MUSHAF_ID)
        except ValueError as exc:
            raise invalid_request_error(str(exc)) from exc

        # Pre-select the target ayah when surah+ayah are specified
        if surah is not None and ayah is not None:
            verse_key = f"{surah}:{ayah}"
            # Verify the verse actually exists on the resolved page
            if any(v.verse_key == verse_key for v in data.verses):
                data.initial_selected_verse = verse_key

        text_fallback = _format_text_fallback(data)
        structured = asdict(data)
        structured["client_hint"] = detect_client_hint(ctx)
        structured["interactive"] = (
            app_ctx.settings.mcp_apps.show_mushaf.interactive
            if app_ctx.settings else True
        )

        return ToolResult(
            content=[TextContent(type="text", text=text_fallback)],
            structured_content=structured,
        )
