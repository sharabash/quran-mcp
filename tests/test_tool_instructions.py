"""Tests for quran_mcp.middleware.tool_instructions.

Covers:
  - Instructions appended for content tools (tafsir, translation, quran)
  - No instructions appended for utility/metadata tools
  - Appended TextContent has audience=["assistant"] annotation
  - Original result content is preserved (not clobbered)
  - Grounding nudge included only when grounding is not acknowledged
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastmcp.server.middleware import MiddlewareContext
from fastmcp.tools import ToolResult

from quran_mcp.middleware.tool_instructions import (
    TOOL_INSTRUCTIONS,
    ToolInstructionsMiddleware,
    GROUNDING_NUDGE,
)


@dataclass
class FakeMessage:
    name: str = ""
    arguments: dict[str, Any] | None = None


def _ctx(tool_name: str) -> MiddlewareContext:
    return MiddlewareContext(message=FakeMessage(name=tool_name))


def _make_next(text: str = "canonical data", *, structured_content: dict[str, Any] | None = None):
    async def _next(context: MiddlewareContext) -> ToolResult:
        result = ToolResult(content=text)
        if structured_content is not None:
            result.structured_content = structured_content
        return result
    return _next


mw = ToolInstructionsMiddleware()


class TestInstructionAppending:
    """Instructions are appended to all content tools listed in TOOL_INSTRUCTIONS."""

    async def test_all_content_tools_get_instructions(self):
        for tool_name in TOOL_INSTRUCTIONS:
            result = await mw.on_call_tool(_ctx(tool_name), _make_next())
            # Original content + appended instruction
            assert len(result.content) == 2, f"{tool_name}: expected 2 content blocks"
            appended = result.content[1]
            assert appended.type == "text"
            assert len(appended.text) > 50  # non-trivial instruction

    async def test_appended_block_has_assistant_audience(self):
        result = await mw.on_call_tool(_ctx("fetch_tafsir"), _make_next())
        appended = result.content[1]
        assert appended.annotations is not None
        assert appended.annotations.audience == ["assistant"]

    async def test_original_content_preserved(self):
        result = await mw.on_call_tool(_ctx("search_quran"), _make_next("arabic text"))
        assert result.content[0].text == "arabic text"


class TestNoInstructionForUtilityTools:
    """Utility/metadata tools should pass through without modification."""

    async def test_list_editions_not_affected(self):
        result = await mw.on_call_tool(_ctx("list_editions"), _make_next())
        assert len(result.content) == 1

    async def test_fetch_mushaf_not_affected(self):
        result = await mw.on_call_tool(_ctx("fetch_mushaf"), _make_next())
        assert len(result.content) == 1

    async def test_fetch_grounding_rules_not_affected(self):
        result = await mw.on_call_tool(_ctx("fetch_grounding_rules"), _make_next())
        assert len(result.content) == 1

    async def test_unknown_tool_not_affected(self):
        result = await mw.on_call_tool(_ctx("totally_unknown"), _make_next())
        assert len(result.content) == 1


class TestInstructionContent:
    """Verify instruction text contains key guidance phrases."""

    async def test_tafsir_instruction_mentions_attribution(self):
        result = await mw.on_call_tool(_ctx("fetch_tafsir"), _make_next())
        text = result.content[1].text
        assert "Attribute" in text or "attribution" in text.lower()

    async def test_translation_instruction_mentions_no_paraphrase(self):
        result = await mw.on_call_tool(_ctx("fetch_translation"), _make_next())
        text = result.content[1].text
        assert "paraphrase" in text.lower()

    async def test_quran_instruction_mentions_grounding(self):
        result = await mw.on_call_tool(_ctx("fetch_quran"), _make_next())
        text = result.content[1].text
        assert "Grounded with quran.ai" in text


class TestGroundingNudgeConditional:
    """Grounding nudge is prepended only when grounding is not acknowledged."""

    async def test_nudge_omitted_when_grounding_acknowledged(self):
        """No grounding_rules in structured_content → nudge suppressed."""
        result = await mw.on_call_tool(
            _ctx("fetch_quran"),
            _make_next(structured_content={"ayahs": []}),
        )
        text = result.content[1].text
        assert GROUNDING_NUDGE not in text
        assert "fetch_grounding_rules" not in text

    async def test_nudge_included_when_grounding_not_acknowledged(self):
        """grounding_rules present in structured_content → nudge prepended."""
        result = await mw.on_call_tool(
            _ctx("fetch_quran"),
            _make_next(structured_content={"ayahs": [], "grounding_rules": "rules text"}),
        )
        text = result.content[1].text
        assert text.startswith(GROUNDING_NUDGE)

    async def test_nudge_omitted_without_structured_content(self):
        """Plain text result (no structured_content) → nudge suppressed."""
        result = await mw.on_call_tool(_ctx("fetch_tafsir"), _make_next())
        text = result.content[1].text
        assert "fetch_grounding_rules" not in text
