"""Tests for mushaf MCP tool wrappers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest
import quran_mcp.mcp.tools.mushaf.fetch as mushaf_fetch_tool
import quran_mcp.mcp.tools.mushaf.show as mushaf_show_tool

from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from quran_mcp.lib.mushaf.types import (
    PageData,
    PageLine,
    PageVerse,
    SurahHeader,
    MushafWord,
)


@dataclass
class _StubAppContext:
    db_pool: object | None = True
    settings: object | None = field(
        default_factory=lambda: SimpleNamespace(
            mcp_apps=SimpleNamespace(
                show_mushaf=SimpleNamespace(interactive=False),
            )
        )
    )


@asynccontextmanager
async def _stub_lifespan(server) -> AsyncIterator[_StubAppContext]:
    yield _StubAppContext()


@asynccontextmanager
async def _no_db_lifespan(server) -> AsyncIterator[_StubAppContext]:
    yield _StubAppContext(db_pool=None)


@pytest.fixture()
def mcp() -> FastMCP:
    server = FastMCP("mushaf-tool-test", lifespan=_stub_lifespan)
    mushaf_show_tool.register(server)
    mushaf_fetch_tool.register(server)
    return server


@pytest.fixture()
def mcp_no_db() -> FastMCP:
    server = FastMCP("mushaf-tool-no-db-test", lifespan=_no_db_lifespan)
    mushaf_show_tool.register(server)
    mushaf_fetch_tool.register(server)
    return server


def _sample_page_data(page_number: int = 50) -> PageData:
    return PageData(
        page_number=page_number,
        mushaf_edition_id=5,
        total_pages=604,
        lines=[
            PageLine(
                line_number=1,
                words=[
                    MushafWord(
                        word_id=1,
                        verse_id=10,
                        text="ٱللَّهُ",
                        char_type_name="word",
                        line_number=1,
                        position_in_line=1,
                        position_in_verse=1,
                    )
                ],
            )
        ],
        verses=[
            PageVerse(
                verse_id=10,
                verse_key="2:255",
                chapter_id=2,
                verse_number=255,
            )
        ],
        surah_headers=[
            SurahHeader(
                chapter_id=2,
                name_arabic="البقرة",
                name_simple="Al-Baqarah",
                bismillah_pre=True,
                appears_before_line=1,
            )
        ],
        chapter_names={2: "Al-Baqarah"},
    )


class TestShowMushaf:
    async def test_ayah_requires_surah_uses_invalid_request(self, mcp: FastMCP):
        with pytest.raises(ToolError, match=r"^\[invalid_request\] ayah requires surah parameter$"):
            async with Client(mcp) as client:
                await client.call_tool("show_mushaf", {"ayah": 5})

    async def test_missing_db_uses_service_unavailable(self, mcp_no_db: FastMCP):
        with pytest.raises(ToolError, match=r"^\[service_unavailable\] Database not available$"):
            async with Client(mcp_no_db) as client:
                await client.call_tool("show_mushaf", {"page": 1})

    async def test_successful_show_returns_structured_page(
        self, mcp: FastMCP, monkeypatch: pytest.MonkeyPatch
    ):
        async def _fake_resolve_page(pool: object, **kwargs) -> int:
            assert pool is True
            assert kwargs["surah"] == 2
            assert kwargs["ayah"] == 255
            return 50

        async def _fake_get_page_data(pool: object, page_number: int, mushaf_id: int) -> PageData:
            assert pool is True
            assert page_number == 50
            assert mushaf_id == 5
            return _sample_page_data(page_number=page_number)

        monkeypatch.setattr(mushaf_show_tool, "resolve_page", _fake_resolve_page)
        monkeypatch.setattr(mushaf_show_tool, "get_page_data", _fake_get_page_data)

        async with Client(mcp) as client:
            result = await client.call_tool("show_mushaf", {"surah": 2, "ayah": 255})

        payload = result.structured_content
        assert payload["page_number"] == 50
        assert payload["initial_selected_verse"] == "2:255"
        assert payload["chapter_names"] == {"2": "Al-Baqarah"}
        assert payload["interactive"] is False
        assert "Mushaf Page 50/604" in result.content[0].text


class TestFetchMushaf:
    async def test_missing_db_uses_service_unavailable(self, mcp_no_db: FastMCP):
        with pytest.raises(ToolError, match=r"^\[service_unavailable\] Database not available$"):
            async with Client(mcp_no_db) as client:
                await client.call_tool("fetch_mushaf", {"page": 1})

    async def test_invalid_page_uses_invalid_request(
        self, mcp: FastMCP, monkeypatch: pytest.MonkeyPatch
    ):
        async def _fake_get_page_data(pool: object, page_number: int, mushaf_id: int) -> PageData:
            raise ValueError(f"Page number must be 1-604 for mushaf {mushaf_id}, got {page_number}")

        monkeypatch.setattr(mushaf_fetch_tool, "get_page_data", _fake_get_page_data)

        with pytest.raises(
            ToolError,
            match=r"^\[invalid_request\] Page number must be 1-604 for mushaf 5, got 0$",
        ):
            async with Client(mcp) as client:
                await client.call_tool("fetch_mushaf", {"page": 0})

    async def test_successful_fetch_returns_structured_page(
        self, mcp: FastMCP, monkeypatch: pytest.MonkeyPatch
    ):
        async def _fake_get_page_data(pool: object, page_number: int, mushaf_id: int) -> PageData:
            assert pool is True
            assert page_number == 7
            assert mushaf_id == 5
            return _sample_page_data(page_number=page_number)

        monkeypatch.setattr(mushaf_fetch_tool, "get_page_data", _fake_get_page_data)

        async with Client(mcp) as client:
            result = await client.call_tool("fetch_mushaf", {"page": 7})

        payload = result.structured_content
        assert payload["page_number"] == 7
        assert payload["interactive"] is False
        assert payload["warnings"] is None
        assert result.content[0].text == "Page 7 data loaded"
