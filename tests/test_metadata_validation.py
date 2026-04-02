"""Tests for quran_mcp.mcp.tools.metadata.fetch — contract and validation.

Tests the validation logic in the fetch_quran_metadata tool handler
through the FastMCP Client. The handler accesses db_pool BEFORE running
validation (lines 116-119), so we provide a stub lifespan that yields
a context with a truthy sentinel pool. This lets validation run; invalid
inputs raise ToolError with the public invalid-request envelope, and valid
inputs can either reach the query layer or succeed via monkeypatched query
functions.

Covers:
  - ayah without surah raises ToolError
  - surah+ayah (point) with span param raises ToolError
  - Multiple span params raises ToolError
  - No parameters at all raises ToolError
  - Missing DB raises service_unavailable ToolError
  - Valid inputs can execute successfully
  - surah alone passes validation (hits query-level error)
  - surah+ayah passes validation (hits query-level error)
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import pytest
import quran_mcp.mcp.tools.metadata.fetch as metadata_fetch_tool
from pydantic import ValidationError

from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from quran_mcp.lib.metadata import QuranMetadataResponse as ExportedQuranMetadataResponse
from quran_mcp.lib.metadata.types import (
    AyahPoint,
    NumericPoint,
    QuranMetadataResponse,
    RukuPoint,
    SajdahInfo,
    SurahInfo,
)
from quran_mcp.mcp.tools.metadata.fetch import register


@dataclass
class _StubAppContext:
    """Minimal context with a truthy db_pool so the handler reaches validation."""

    db_pool: object | None = True  # truthy sentinel -- not a real pool


@asynccontextmanager
async def _stub_lifespan(server) -> AsyncIterator[_StubAppContext]:
    """Lifespan that provides a stub AppContext with a truthy pool."""
    yield _StubAppContext()


@asynccontextmanager
async def _no_db_lifespan(server) -> AsyncIterator[_StubAppContext]:
    """Lifespan that simulates an unavailable database."""
    yield _StubAppContext(db_pool=None)


@pytest.fixture()
def mcp() -> FastMCP:
    """FastMCP server with fetch_quran_metadata registered and stub lifespan."""
    server = FastMCP("metadata-validation-test", lifespan=_stub_lifespan)
    register(server)
    return server


@pytest.fixture()
def mcp_no_db() -> FastMCP:
    """FastMCP server with metadata tool but no DB pool."""
    server = FastMCP("metadata-no-db-test", lifespan=_no_db_lifespan)
    register(server)
    return server


def _sample_metadata_response() -> QuranMetadataResponse:
    """Build a representative successful metadata payload."""
    return QuranMetadataResponse(
        query_type="ayah",
        surah=[
            SurahInfo(
                number=2,
                name_arabic="البقرة",
                name_simple="Al-Baqarah",
                revelation_place="madinah",
                revelation_order=87,
                verses_count=286,
                bismillah_pre=True,
            )
        ],
        ayah=AyahPoint(verse_key="2:255", number=255, words_count=50),
        juz=NumericPoint(number=3),
        hizb=NumericPoint(number=5),
        rub_el_hizb=NumericPoint(number=9),
        page=NumericPoint(number=42),
        ruku=RukuPoint(number=40, surah_ruku_number=5),
        manzil=NumericPoint(number=1),
        sajdah=[],
    )


class TestAyahRequiresSurah:
    """ayah parameter requires surah."""

    async def test_ayah_without_surah_raises(self, mcp: FastMCP):
        """ayah=5 without surah should raise an invalid-request ToolError."""
        with pytest.raises(ToolError, match=r"^\[invalid_request\] ayah requires surah"):
            async with Client(mcp) as client:
                await client.call_tool(
                    "fetch_quran_metadata", {"ayah": 5}
                )


class TestPointSpanConflict:
    """Point query (surah+ayah) cannot combine with span parameters."""

    async def test_point_with_juz_raises(self, mcp: FastMCP):
        """surah+ayah+juz should raise ValueError (point + span conflict)."""
        with pytest.raises(ToolError, match="point query.*cannot be combined"):
            async with Client(mcp) as client:
                await client.call_tool(
                    "fetch_quran_metadata",
                    {"surah": 2, "ayah": 255, "juz": 1},
                )

    async def test_point_with_page_raises(self, mcp: FastMCP):
        """surah+ayah+page should raise ValueError."""
        with pytest.raises(ToolError, match="point query.*cannot be combined"):
            async with Client(mcp) as client:
                await client.call_tool(
                    "fetch_quran_metadata",
                    {"surah": 2, "ayah": 255, "page": 50},
                )

    async def test_point_with_hizb_raises(self, mcp: FastMCP):
        """surah+ayah+hizb should raise ValueError."""
        with pytest.raises(ToolError, match="point query.*cannot be combined"):
            async with Client(mcp) as client:
                await client.call_tool(
                    "fetch_quran_metadata",
                    {"surah": 2, "ayah": 255, "hizb": 1},
                )


class TestMultipleSpansConflict:
    """Multiple span entry points are mutually exclusive."""

    async def test_juz_with_page_raises(self, mcp: FastMCP):
        """juz+page should raise ValueError (multiple spans)."""
        with pytest.raises(ToolError, match="mutually exclusive"):
            async with Client(mcp) as client:
                await client.call_tool(
                    "fetch_quran_metadata", {"juz": 1, "page": 50}
                )

    async def test_surah_with_juz_raises(self, mcp: FastMCP):
        """surah (alone, as span) + juz should raise ValueError."""
        with pytest.raises(ToolError, match="mutually exclusive"):
            async with Client(mcp) as client:
                await client.call_tool(
                    "fetch_quran_metadata", {"surah": 2, "juz": 1}
                )

    async def test_hizb_with_ruku_raises(self, mcp: FastMCP):
        """hizb+ruku should raise ValueError."""
        with pytest.raises(ToolError, match="mutually exclusive"):
            async with Client(mcp) as client:
                await client.call_tool(
                    "fetch_quran_metadata", {"hizb": 1, "ruku": 10}
                )

    async def test_three_spans_raises(self, mcp: FastMCP):
        """juz+page+manzil should raise ValueError."""
        with pytest.raises(ToolError, match="mutually exclusive"):
            async with Client(mcp) as client:
                await client.call_tool(
                    "fetch_quran_metadata",
                    {"juz": 1, "page": 50, "manzil": 1},
                )


class TestNoParameters:
    """At least one parameter is required."""

    async def test_no_params_raises(self, mcp: FastMCP):
        """Calling with no parameters should raise ValueError."""
        with pytest.raises(ToolError, match="At least one parameter"):
            async with Client(mcp) as client:
                await client.call_tool("fetch_quran_metadata", {})

    async def test_all_none_raises(self, mcp: FastMCP):
        """Explicitly passing all None should raise ValueError."""
        with pytest.raises(ToolError, match="At least one parameter"):
            async with Client(mcp) as client:
                await client.call_tool(
                    "fetch_quran_metadata",
                    {
                        "surah": None,
                        "ayah": None,
                        "juz": None,
                        "page": None,
                        "hizb": None,
                        "ruku": None,
                        "manzil": None,
                    },
                )


class TestValidationPasses:
    """Queries that pass validation reach the query dispatch layer.

    These tests prove that validation logic does NOT reject valid inputs.
    The error comes from the query functions trying to use the sentinel
    pool (not a real asyncpg.Pool), proving validation succeeded.
    The ToolError message will NOT match any validation error pattern.
    """

    async def test_surah_alone_passes_validation(self, mcp: FastMCP):
        """surah=2 alone (span query) should pass validation.

        Fails at query_surah_span (sentinel pool), proving validation passed.
        """
        with pytest.raises(ToolError) as exc_info:
            async with Client(mcp) as client:
                await client.call_tool(
                    "fetch_quran_metadata", {"surah": 2}
                )
        # Must NOT be a validation error
        msg = str(exc_info.value)
        assert "ayah requires surah" not in msg
        assert "mutually exclusive" not in msg
        assert "At least one parameter" not in msg
        assert "point query" not in msg


class TestMetadataTypeConstraints:
    def test_surah_info_rejects_invalid_revelation_place(self):
        with pytest.raises(ValidationError):
            SurahInfo(
                number=1,
                name_arabic="الفاتحة",
                name_simple="Al-Fatiha",
                revelation_place="unknown",
                revelation_order=1,
                verses_count=7,
                bismillah_pre=False,
            )

    def test_sajdah_info_rejects_invalid_type(self):
        with pytest.raises(ValidationError):
            SajdahInfo(verse_key="2:255", type="mandatory", number=1)

    def test_package_root_reexports_response_model(self):
        assert ExportedQuranMetadataResponse is QuranMetadataResponse

    async def test_surah_ayah_point_passes_validation(self, mcp: FastMCP):
        """surah=2 + ayah=255 (point query) should pass validation.

        Fails at query_ayah_point (sentinel pool), proving validation passed.
        """
        with pytest.raises(ToolError) as exc_info:
            async with Client(mcp) as client:
                await client.call_tool(
                    "fetch_quran_metadata", {"surah": 2, "ayah": 255}
                )
        msg = str(exc_info.value)
        assert "ayah requires surah" not in msg
        assert "mutually exclusive" not in msg
        assert "At least one parameter" not in msg
        assert "point query" not in msg

    async def test_juz_alone_passes_validation(self, mcp: FastMCP):
        """juz=1 alone should pass validation."""
        with pytest.raises(ToolError) as exc_info:
            async with Client(mcp) as client:
                await client.call_tool(
                    "fetch_quran_metadata", {"juz": 1}
                )
        msg = str(exc_info.value)
        assert "mutually exclusive" not in msg
        assert "At least one parameter" not in msg

    async def test_page_alone_passes_validation(self, mcp: FastMCP):
        """page=50 alone should pass validation."""
        with pytest.raises(ToolError) as exc_info:
            async with Client(mcp) as client:
                await client.call_tool(
                    "fetch_quran_metadata", {"page": 50}
                )
        msg = str(exc_info.value)
        assert "mutually exclusive" not in msg
        assert "At least one parameter" not in msg


class TestToolErrorContract:
    """Public metadata errors should use stable ToolError prefixes."""

    async def test_missing_db_raises_service_unavailable(self, mcp_no_db: FastMCP):
        with pytest.raises(ToolError, match=r"^\[service_unavailable\] Database not available$"):
            async with Client(mcp_no_db) as client:
                await client.call_tool("fetch_quran_metadata", {"surah": 2})


class TestSuccessfulExecution:
    """Valid requests should be able to complete successfully."""

    async def test_surah_ayah_returns_structured_response(
        self, mcp: FastMCP, monkeypatch: pytest.MonkeyPatch
    ):
        expected = _sample_metadata_response()

        async def _fake_query(pool: object, surah: int, ayah: int) -> QuranMetadataResponse:
            assert pool is True
            assert (surah, ayah) == (2, 255)
            return expected

        monkeypatch.setattr(metadata_fetch_tool, "query_ayah_point", _fake_query)

        async with Client(mcp) as client:
            result = await client.call_tool(
                "fetch_quran_metadata", {"surah": 2, "ayah": 255}
            )

        payload = result.structured_content
        assert payload["query_type"] == "ayah"
        assert payload["ayah"]["verse_key"] == "2:255"
        assert payload["page"]["number"] == 42
        assert payload["surah"][0]["name_simple"] == "Al-Baqarah"
