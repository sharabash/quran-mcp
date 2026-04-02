"""Tests for quran_mcp.mcp.tools.editions.list — list_editions tool logic.

Tests the business logic through FastMCP Client: type normalization,
deduplication, language filtering, sorting, and response shape.
No external services needed — load_editions_by_type reads from the
static editions.json bundled with the package.

Covers:
  - Single string edition_type normalized to list
  - List edition_type returns both types
  - Empty list raises error
  - Duplicate types deduped
  - lang filter applied to translation only
  - lang filter ignored for tafsir (all returned)
  - Response count matches len(editions)
  - Editions sorted by edition_id within each type
"""

from __future__ import annotations

import pytest

from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from quran_mcp.mcp.tools.editions.list import register


@pytest.fixture()
def mcp() -> FastMCP:
    server = FastMCP("editions-test")
    register(server)
    return server


class TestEditionTypeNormalization:
    """edition_type string → list normalization."""

    async def test_single_string_normalized_to_list(self, mcp: FastMCP):
        """Single string 'tafsir' should be treated as ['tafsir']."""
        async with Client(mcp) as client:
            result = await client.call_tool(
                "list_editions", {"edition_type": "tafsir"}
            )
        payload = result.structured_content
        assert payload["edition_types"] == ["tafsir"]
        assert payload["count"] > 0
        # All returned editions should be tafsir type
        for ed in payload["editions"]:
            assert ed["edition_type"] == "tafsir"

    async def test_list_of_two_types_returns_both(self, mcp: FastMCP):
        """edition_type=['tafsir', 'translation'] returns both types."""
        async with Client(mcp) as client:
            result = await client.call_tool(
                "list_editions",
                {"edition_type": ["tafsir", "translation"]},
            )
        payload = result.structured_content
        assert payload["edition_types"] == ["tafsir", "translation"]

        returned_types = {ed["edition_type"] for ed in payload["editions"]}
        assert "tafsir" in returned_types
        assert "translation" in returned_types


class TestEmptyAndDuplicateTypes:
    """Edge cases: empty list, duplicate types."""

    async def test_empty_list_raises_error(self, mcp: FastMCP):
        """Empty edition_type list should raise the shared invalid-request ToolError."""
        with pytest.raises(ToolError, match=r"^\[invalid_request\] edition_type must not be empty$"):
            async with Client(mcp) as client:
                await client.call_tool(
                    "list_editions", {"edition_type": []}
                )

    async def test_duplicate_types_deduped(self, mcp: FastMCP):
        """['tafsir', 'tafsir'] should deduplicate to one set of tafsir."""
        async with Client(mcp) as client:
            single_result = await client.call_tool(
                "list_editions", {"edition_type": "tafsir"}
            )
            dup_result = await client.call_tool(
                "list_editions",
                {"edition_type": ["tafsir", "tafsir"]},
            )
        single_payload = single_result.structured_content
        dup_payload = dup_result.structured_content

        # Deduped type list should have only one entry
        assert dup_payload["edition_types"] == ["tafsir"]

        # Same number of editions returned
        assert dup_payload["count"] == single_payload["count"]
        assert len(dup_payload["editions"]) == len(single_payload["editions"])


class TestLanguageFiltering:
    """lang parameter filtering behavior."""

    async def test_lang_filter_applied_to_translation(self, mcp: FastMCP):
        """lang='en' with translation type should filter to English only."""
        async with Client(mcp) as client:
            all_result = await client.call_tool(
                "list_editions", {"edition_type": "translation"}
            )
            en_result = await client.call_tool(
                "list_editions",
                {"edition_type": "translation", "lang": "en"},
            )
        all_payload = all_result.structured_content
        en_payload = en_result.structured_content

        # Filtered set should be smaller than full set
        assert en_payload["count"] < all_payload["count"]

        # All returned editions should be English
        for ed in en_payload["editions"]:
            assert ed["lang"] == "en"

        # lang_filter should be reported
        assert en_payload["lang_filter"] == "en"

    async def test_lang_filter_ignored_for_tafsir(self, mcp: FastMCP):
        """lang='en' with tafsir type should return ALL tafsir (lang ignored)."""
        async with Client(mcp) as client:
            all_result = await client.call_tool(
                "list_editions", {"edition_type": "tafsir"}
            )
            en_result = await client.call_tool(
                "list_editions",
                {"edition_type": "tafsir", "lang": "en"},
            )
        all_payload = all_result.structured_content
        en_payload = en_result.structured_content

        # Same count — lang filter has no effect on tafsir
        assert en_payload["count"] == all_payload["count"]

        # lang_filter should be None (not applied)
        assert en_payload["lang_filter"] is None

    async def test_lang_filter_active_only_when_translation_in_types(self, mcp: FastMCP):
        """lang='en' with ['tafsir', 'translation'] filters only translation."""
        async with Client(mcp) as client:
            result = await client.call_tool(
                "list_editions",
                {"edition_type": ["tafsir", "translation"], "lang": "en"},
            )
        payload = result.structured_content

        # lang_filter should be 'en' (translation is in the list)
        assert payload["lang_filter"] == "en"

        # Tafsir editions: should include non-English (Arabic) ones
        tafsir_editions = [e for e in payload["editions"] if e["edition_type"] == "tafsir"]
        tafsir_langs = {e["lang"] for e in tafsir_editions}
        assert "ar" in tafsir_langs, "Arabic tafsir should be present despite lang='en'"

        # Translation editions: should be English only
        trans_editions = [e for e in payload["editions"] if e["edition_type"] == "translation"]
        for ed in trans_editions:
            assert ed["lang"] == "en"


class TestResponseShape:
    """Response payload structure and consistency."""

    async def test_count_matches_editions_length(self, mcp: FastMCP):
        """count field should match len(editions)."""
        async with Client(mcp) as client:
            result = await client.call_tool(
                "list_editions", {"edition_type": "tafsir"}
            )
        payload = result.structured_content
        assert payload["count"] == len(payload["editions"])

    async def test_editions_sorted_by_edition_id_within_type(self, mcp: FastMCP):
        """Editions should be sorted by edition_id within each type."""
        async with Client(mcp) as client:
            result = await client.call_tool(
                "list_editions",
                {"edition_type": ["tafsir", "translation"]},
            )
        payload = result.structured_content

        # Check sorting within each type
        for edition_type in ["tafsir", "translation"]:
            type_editions = [
                e for e in payload["editions"]
                if e["edition_type"] == edition_type
            ]
            edition_ids = [e["edition_id"] for e in type_editions]
            assert edition_ids == sorted(edition_ids), (
                f"{edition_type} editions not sorted by edition_id"
            )

    async def test_edition_fields_present(self, mcp: FastMCP):
        """Each edition should have the required fields."""
        async with Client(mcp) as client:
            result = await client.call_tool(
                "list_editions", {"edition_type": "tafsir"}
            )
        payload = result.structured_content
        required_fields = {"edition_id", "edition_type", "lang", "code", "name"}

        for ed in payload["editions"]:
            for field in required_fields:
                assert field in ed, f"Missing field '{field}' in edition {ed.get('edition_id')}"
