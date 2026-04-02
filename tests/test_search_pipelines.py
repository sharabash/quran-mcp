from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import quran_mcp.mcp.tools.quran.search as quran_search_tool
import quran_mcp.mcp.tools.tafsir.search as tafsir_search_tool
import quran_mcp.mcp.tools.translation.search as translation_search_tool

from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from quran_mcp.lib.goodmem import GoodMemMemory
from quran_mcp.lib.presentation.pagination import (
    decode_continuation_request_model,
    encode_continuation_token,
)
from quran_mcp.lib.quran.search import (
    EditionInfo,
    SearchQuranResult,
    SearchResult,
    TranslationSearchResult,
    search_quran,
)
from quran_mcp.lib.editions.types import EditionRecord
from quran_mcp.lib.search.common import (
    SearchBackendError,
    SearchEditionSelection,
    SearchEnrichmentError,
    TranslationSearchSelection,
)
from quran_mcp.mcp.tools._search_orchestration import build_search_request_inputs
from quran_mcp.lib.tafsir.search import SearchTafsirResult, TafsirCitation, TafsirSearchResult, search_tafsir
from quran_mcp.lib.translation.search import SearchTranslationResult, TranslationEditionInfo, TranslationResult, search_translation


def _make_memory(
    content: str,
    metadata: dict[str, Any] | None = None,
    relevance_score: float | None = None,
    source_space_name: str | None = None,
) -> GoodMemMemory:
    return GoodMemMemory(
        content=content,
        metadata=metadata or {},
        relevance_score=relevance_score,
        source_space_name=source_space_name,
    )


def _make_goodmem_client(
    search_results: list[GoodMemMemory] | None = None,
    search_side_effect: Any = None,
) -> MagicMock:
    client = MagicMock()
    client.default_reranker_id = "reranker-uuid-123"
    if search_side_effect is not None:
        client.search_memories = AsyncMock(side_effect=search_side_effect)
    else:
        client.search_memories = AsyncMock(return_value=search_results or [])
    return client


def _mock_settings():
    settings = MagicMock()
    settings.goodmem.space.quran = "quran"
    settings.goodmem.space.translation = "translation"
    settings.goodmem.space.tafsir = "tafsir"
    return settings


QURAN_SETTINGS_PATH = "quran_mcp.lib.quran.search.get_settings"
TRANS_SETTINGS_PATH = "quran_mcp.lib.translation.search.get_settings"
TAFSIR_SETTINGS_PATH = "quran_mcp.lib.tafsir.search.get_settings"
QURAN_RESOLVE_PATH = "quran_mcp.lib.quran.search.resolve_translation_search_selection"
TRANS_RESOLVE_PATH = "quran_mcp.lib.translation.search.resolve_translation_search_selection"
TAFSIR_RESOLVE_PATH = "quran_mcp.lib.tafsir.search.resolve_ids_with_unresolved"
QURAN_GET_BY_ID_PATH = "quran_mcp.lib.editions.registry.get_by_edition_id"


# ============================================================================
# search_quran
# ============================================================================


@pytest.mark.asyncio
async def test_search_quran_empty_query_raises():
    client = _make_goodmem_client()
    with pytest.raises(ValueError, match="empty"):
        await search_quran(client, "")


@pytest.mark.asyncio
async def test_search_quran_whitespace_query_raises():
    client = _make_goodmem_client()
    with pytest.raises(ValueError, match="empty"):
        await search_quran(client, "   ")


@pytest.mark.asyncio
@patch(QURAN_SETTINGS_PATH, return_value=_mock_settings())
async def test_search_quran_basic_returns_expected_fields(mock_settings):
    memories = [
        _make_memory(
            content="bismillah",
            metadata={
                "ayah_key": "1:1",
                "surah": 1,
                "ayah": 1,
                "edition_id": "ar-uthmani",
                "lang": "ar",
                "url": "https://quran.com/1:1",
            },
            relevance_score=0.95,
            source_space_name="quran",
        ),
    ]
    client = _make_goodmem_client(search_results=memories)

    result = await search_quran(client, "bismillah")

    assert isinstance(result, SearchQuranResult)
    assert len(result.results) == 1
    r = result.results[0]
    assert r.ayah_key == "1:1"
    assert r.surah == 1
    assert r.ayah == 1
    assert r.relevance_score == 0.95
    assert r.url == "https://quran.com/1:1"


@pytest.mark.asyncio
@patch(QURAN_SETTINGS_PATH, return_value=_mock_settings())
async def test_search_quran_results_limited_by_param(mock_settings):
    memories = [
        _make_memory(
            content=f"ayah {i}",
            metadata={
                "ayah_key": f"2:{i}",
                "surah": 2,
                "ayah": i,
                "edition_id": "ar-uthmani",
                "lang": "ar",
            },
            relevance_score=1.0 - (i * 0.01),
            source_space_name="quran",
        )
        for i in range(1, 11)
    ]
    client = _make_goodmem_client(search_results=memories)

    result = await search_quran(client, "patience", results=3)

    assert len(result.results) == 3


@pytest.mark.asyncio
@patch(QURAN_SETTINGS_PATH, return_value=_mock_settings())
async def test_search_quran_dedup_keeps_highest_score(mock_settings):
    memories = [
        _make_memory(
            content="low score",
            metadata={
                "ayah_key": "2:255",
                "surah": 2,
                "ayah": 255,
                "edition_id": "en-sahih-international",
                "lang": "en",
            },
            relevance_score=0.5,
            source_space_name="translation",
        ),
        _make_memory(
            content="high score",
            metadata={
                "ayah_key": "2:255",
                "surah": 2,
                "ayah": 255,
                "edition_id": "en-abdel-haleem",
                "lang": "en",
            },
            relevance_score=0.9,
            source_space_name="translation",
        ),
    ]
    client = _make_goodmem_client(search_results=memories)

    result = await search_quran(client, "throne verse")

    assert len(result.results) == 1
    assert result.results[0].ayah_key == "2:255"
    assert result.results[0].relevance_score == 0.9


@pytest.mark.asyncio
@patch(QURAN_SETTINGS_PATH, return_value=_mock_settings())
async def test_search_quran_dedup_prefers_detected_language(mock_settings):
    ar_mem = _make_memory(
        content="arabic text",
        metadata={
            "ayah_key": "2:255",
            "surah": 2,
            "ayah": 255,
            "edition_id": "ar-uthmani",
            "lang": "ar",
        },
        relevance_score=0.7,
        source_space_name="quran",
    )
    en_mem = _make_memory(
        content="english text",
        metadata={
            "ayah_key": "2:255",
            "surah": 2,
            "ayah": 255,
            "edition_id": "en-sahih-international",
            "lang": "en",
        },
        relevance_score=0.8,
        source_space_name="translation",
    )
    client = _make_goodmem_client(search_results=[ar_mem, en_mem])

    result = await search_quran(client, "\u0622\u064a\u0629 \u0627\u0644\u0643\u0631\u0633\u064a")

    assert len(result.results) == 1
    assert result.results[0].source_space == "quran"


@pytest.mark.asyncio
@patch(QURAN_SETTINGS_PATH, return_value=_mock_settings())
async def test_search_quran_translations_none_returns_no_translations(mock_settings):
    memories = [
        _make_memory(
            content="text",
            metadata={
                "ayah_key": "1:1",
                "surah": 1,
                "ayah": 1,
                "edition_id": "ar-uthmani",
                "lang": "ar",
            },
            relevance_score=0.9,
            source_space_name="quran",
        ),
    ]
    client = _make_goodmem_client(search_results=memories)

    result = await search_quran(client, "bismillah", translations=None)

    assert result.results[0].translations == []


@pytest.mark.asyncio
@patch(QURAN_GET_BY_ID_PATH, return_value=EditionRecord(edition_id="en-sahih-international", edition_type="translation", lang="en", code="si", name="Sahih International", author="SI"))
@patch(QURAN_RESOLVE_PATH)
@patch(QURAN_SETTINGS_PATH, return_value=_mock_settings())
async def test_search_quran_translations_auto_fetches(mock_settings, mock_resolve, mock_get_by_id):
    mock_resolve.return_value = TranslationSearchSelection(
        selection=SearchEditionSelection(
            resolved_ids=["en-sahih-international"],
            unresolved=[],
            single_best_match=True,
        ),
        edition_filter="CAST(val('$.edition_id') AS TEXT) = 'en-sahih-international'",
    )

    quran_mem = _make_memory(
        content="arabic text",
        metadata={
            "ayah_key": "1:1",
            "surah": 1,
            "ayah": 1,
            "edition_id": "ar-uthmani",
            "lang": "ar",
        },
        relevance_score=0.9,
        source_space_name="quran",
    )
    trans_mem = _make_memory(
        content="In the name of God",
        metadata={
            "ayah_key": "1:1",
            "surah": 1,
            "ayah": 1,
            "edition_id": "en-sahih-international",
            "lang": "en",
            "url": "https://quran.com/1:1/en-sahih-international",
        },
        relevance_score=0.8,
        source_space_name="translation",
    )

    call_count = 0

    async def search_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return [quran_mem]
        return [trans_mem]

    client = _make_goodmem_client(search_side_effect=search_side_effect)

    result = await search_quran(client, "bismillah", translations="auto")

    assert len(result.results) == 1
    assert len(result.results[0].translations) == 1
    assert result.results[0].translations[0].text == "In the name of God"


@pytest.mark.asyncio
@patch(QURAN_SETTINGS_PATH, return_value=_mock_settings())
async def test_search_quran_surah_filter_passed(mock_settings):
    client = _make_goodmem_client(search_results=[])

    await search_quran(client, "patience", surah=2)

    call_args = client.search_memories.call_args_list[0]
    filter_expr = call_args.kwargs.get("filter_expr") or call_args[1].get("filter_expr")
    assert filter_expr is not None
    assert "surah" in filter_expr
    assert "2" in filter_expr


@pytest.mark.asyncio
@patch(QURAN_SETTINGS_PATH, return_value=_mock_settings())
async def test_search_quran_no_reranker(mock_settings):
    client = _make_goodmem_client(search_results=[])

    await search_quran(client, "patience", use_reranker=False)

    for call in client.search_memories.call_args_list:
        reranker_id = call.kwargs.get("reranker_id") or call[1].get("reranker_id", "MISSING")
        assert reranker_id is None


@pytest.mark.asyncio
@patch(QURAN_SETTINGS_PATH, return_value=_mock_settings())
async def test_search_quran_backend_failure_surfaces_explicitly(mock_settings):
    client = _make_goodmem_client(
        search_side_effect=[
            RuntimeError("quran-space down"),
            [],
        ]
    )

    with pytest.raises(SearchBackendError, match="wide_retrieval"):
        await search_quran(client, "patience")


# ============================================================================
# search_translation
# ============================================================================


@pytest.mark.asyncio
async def test_search_translation_empty_query_raises():
    client = _make_goodmem_client()
    with pytest.raises(ValueError, match="empty"):
        await search_translation(client, "")


@pytest.mark.asyncio
@patch(TRANS_SETTINGS_PATH, return_value=_mock_settings())
async def test_search_translation_editions_none_no_filter(mock_settings):
    memories = [
        _make_memory(
            content="patience text",
            metadata={
                "ayah_key": "2:153",
                "surah": 2,
                "ayah": 153,
                "edition_id": "en-sahih-international",
                "lang": "en",
            },
            relevance_score=0.9,
            source_space_name="translation",
        ),
    ]
    client = _make_goodmem_client(search_results=memories)

    result = await search_translation(client, "patience", editions=None)

    assert len(result.results) == 1
    call_args = client.search_memories.call_args
    filter_expr = call_args.kwargs.get("filter_expr") or call_args[1].get("filter_expr")
    assert filter_expr is None


@pytest.mark.asyncio
@patch(TRANS_RESOLVE_PATH)
@patch(TRANS_SETTINGS_PATH, return_value=_mock_settings())
async def test_search_translation_editions_auto_detects_language(mock_settings, mock_resolve):
    mock_resolve.return_value = TranslationSearchSelection(
        selection=SearchEditionSelection(
            resolved_ids=["en-sahih-international"],
            unresolved=[],
            single_best_match=True,
        ),
        edition_filter="CAST(val('$.edition_id') AS TEXT) = 'en-sahih-international'",
    )

    memories = [
        _make_memory(
            content="patience text",
            metadata={
                "ayah_key": "2:153",
                "surah": 2,
                "ayah": 153,
                "edition_id": "en-sahih-international",
                "lang": "en",
            },
            relevance_score=0.9,
            source_space_name="translation",
        ),
    ]
    client = _make_goodmem_client(search_results=memories)

    result = await search_translation(client, "patience", editions="auto")

    mock_resolve.assert_called_once_with("patience", "auto", auto_low_confidence_behavior="all")
    assert len(result.results) == 1


@pytest.mark.asyncio
@patch(TRANS_RESOLVE_PATH)
@patch(TRANS_SETTINGS_PATH, return_value=_mock_settings())
async def test_search_translation_editions_explicit_list_resolves(mock_settings, mock_resolve):
    mock_resolve.return_value = TranslationSearchSelection(
        selection=SearchEditionSelection(
            resolved_ids=["en-sahih-international", "en-abdel-haleem"],
            unresolved=[],
            single_best_match=False,
        ),
        edition_filter=(
            "(CAST(val('$.edition_id') AS TEXT) = 'en-sahih-international' OR "
            "CAST(val('$.edition_id') AS TEXT) = 'en-abdel-haleem')"
        ),
    )

    memories = [
        _make_memory(
            content="text",
            metadata={
                "ayah_key": "2:153",
                "surah": 2,
                "ayah": 153,
                "edition_id": "en-sahih-international",
                "lang": "en",
            },
            relevance_score=0.9,
            source_space_name="translation",
        ),
    ]
    client = _make_goodmem_client(search_results=memories)

    result = await search_translation(
        client, "patience", editions=["en-sahih-international", "en-abdel-haleem"]
    )

    mock_resolve.assert_called_once_with(
        "patience", ["en-sahih-international", "en-abdel-haleem"], auto_low_confidence_behavior="all"
    )
    assert isinstance(result, SearchTranslationResult)


@pytest.mark.asyncio
@patch(TRANS_RESOLVE_PATH)
@patch(TRANS_SETTINGS_PATH, return_value=_mock_settings())
async def test_search_translation_editions_lang_code_resolves(mock_settings, mock_resolve):
    mock_resolve.return_value = TranslationSearchSelection(
        selection=SearchEditionSelection(
            resolved_ids=["fr-hamidullah"],
            unresolved=[],
            single_best_match=True,
        ),
        edition_filter="CAST(val('$.edition_id') AS TEXT) = 'fr-hamidullah'",
    )

    client = _make_goodmem_client(search_results=[
        _make_memory(
            content="texte",
            metadata={
                "ayah_key": "1:1",
                "surah": 1,
                "ayah": 1,
                "edition_id": "fr-hamidullah",
                "lang": "fr",
            },
            relevance_score=0.8,
            source_space_name="translation",
        ),
    ])

    result = await search_translation(client, "patience", editions="fr")

    mock_resolve.assert_called_once_with("patience", "fr", auto_low_confidence_behavior="all")
    assert len(result.results) == 1


@pytest.mark.asyncio
@patch(TRANS_RESOLVE_PATH)
@patch(TRANS_SETTINGS_PATH, return_value=_mock_settings())
async def test_search_translation_unresolved_editions_returned_empty(mock_settings, mock_resolve):
    mock_resolve.return_value = TranslationSearchSelection(
        selection=SearchEditionSelection(
            resolved_ids=[],
            unresolved=["nonexistent-edition"],
            single_best_match=False,
        ),
        edition_filter=None,
    )

    client = _make_goodmem_client()

    result = await search_translation(client, "patience", editions=["nonexistent-edition"])

    assert result.results == []
    assert result.unresolved_editions == ["nonexistent-edition"]


@pytest.mark.asyncio
@patch(TRANS_SETTINGS_PATH, return_value=_mock_settings())
async def test_search_translation_overfetch_multiplier(mock_settings):
    client = _make_goodmem_client(search_results=[])

    await search_translation(client, "patience", results=5, editions=None)

    call_args = client.search_memories.call_args
    limit = call_args.kwargs.get("limit") or call_args[1].get("limit")
    assert limit == 15


@pytest.mark.asyncio
@patch(TRANS_SETTINGS_PATH, return_value=_mock_settings())
async def test_search_translation_dedup_keeps_highest_score(mock_settings):
    memories = [
        _make_memory(
            content="lower score edition",
            metadata={
                "ayah_key": "2:255",
                "surah": 2,
                "ayah": 255,
                "edition_id": "en-sahih-international",
                "lang": "en",
            },
            relevance_score=0.5,
            source_space_name="translation",
        ),
        _make_memory(
            content="higher score edition",
            metadata={
                "ayah_key": "2:255",
                "surah": 2,
                "ayah": 255,
                "edition_id": "en-abdel-haleem",
                "lang": "en",
            },
            relevance_score=0.9,
            source_space_name="translation",
        ),
    ]
    client = _make_goodmem_client(search_results=memories)

    result = await search_translation(client, "throne verse", editions=None)

    assert len(result.results) == 1
    assert result.results[0].ayah_key == "2:255"
    assert result.results[0].relevance_score == 0.9


# ============================================================================
# search_tafsir
# ============================================================================


@pytest.mark.asyncio
async def test_search_tafsir_empty_query_raises():
    client = _make_goodmem_client()
    with pytest.raises(ValueError, match="empty"):
        await search_tafsir(client, "")


@pytest.mark.asyncio
@patch(TAFSIR_SETTINGS_PATH, return_value=_mock_settings())
async def test_search_tafsir_basic_returns_cleaned_text(mock_settings):
    memories = [
        _make_memory(
            content="<p>This is <b>tafsir</b> text.</p>",
            metadata={
                "ayah_key": "2:255",
                "surah": 2,
                "ayah": 255,
                "edition_id": "en-ibn-kathir",
                "name": "Tafsir Ibn Kathir",
                "author": "Ibn Kathir",
                "lang": "en",
                "url": "https://quran.com/2:255/tafsirs/en-ibn-kathir",
            },
            relevance_score=0.85,
            source_space_name="tafsir",
        ),
    ]
    client = _make_goodmem_client(search_results=memories)

    result = await search_tafsir(client, "throne verse", include_ayah_text=False)

    assert len(result.results) == 1
    assert "<p>" not in result.results[0].tafsir_text
    assert "<b>" not in result.results[0].tafsir_text
    assert "tafsir" in result.results[0].tafsir_text


@pytest.mark.asyncio
@patch(TAFSIR_SETTINGS_PATH, return_value=_mock_settings())
async def test_search_tafsir_correct_citation_metadata(mock_settings):
    memories = [
        _make_memory(
            content="Commentary on the verse",
            metadata={
                "ayah_key": "2:255",
                "surah": 2,
                "ayah": 255,
                "edition_id": "en-ibn-kathir",
                "name": "Tafsir Ibn Kathir",
                "author": "Ibn Kathir",
                "lang": "en",
                "url": "https://quran.com/2:255/tafsirs/en-ibn-kathir",
                "citation_url": "https://example.com/source",
            },
            relevance_score=0.85,
            source_space_name="tafsir",
        ),
    ]
    client = _make_goodmem_client(search_results=memories)

    result = await search_tafsir(client, "throne verse", include_ayah_text=False)

    citation = result.results[0].citation
    assert citation.edition_id == "en-ibn-kathir"
    assert citation.edition_name == "Tafsir Ibn Kathir"
    assert citation.author == "Ibn Kathir"
    assert citation.lang == "en"
    assert citation.url == "https://quran.com/2:255/tafsirs/en-ibn-kathir"
    assert citation.citation_url == "https://example.com/source"


@pytest.mark.asyncio
@patch(TAFSIR_SETTINGS_PATH, return_value=_mock_settings())
async def test_search_tafsir_dedup_merges_identical_text(mock_settings):
    shared_text = "This passage covers multiple ayahs about patience."
    memories = [
        _make_memory(
            content=shared_text,
            metadata={
                "ayah_key": "2:153",
                "surah": 2,
                "ayah": 153,
                "edition_id": "en-ibn-kathir",
                "name": "Tafsir Ibn Kathir",
                "author": "Ibn Kathir",
                "lang": "en",
                "url": "https://quran.com/2:153/tafsirs/en-ibn-kathir",
            },
            relevance_score=0.8,
            source_space_name="tafsir",
        ),
        _make_memory(
            content=shared_text,
            metadata={
                "ayah_key": "2:154",
                "surah": 2,
                "ayah": 154,
                "edition_id": "en-ibn-kathir",
                "name": "Tafsir Ibn Kathir",
                "author": "Ibn Kathir",
                "lang": "en",
                "url": "https://quran.com/2:154/tafsirs/en-ibn-kathir",
            },
            relevance_score=0.7,
            source_space_name="tafsir",
        ),
        _make_memory(
            content=shared_text,
            metadata={
                "ayah_key": "2:155",
                "surah": 2,
                "ayah": 155,
                "edition_id": "en-ibn-kathir",
                "name": "Tafsir Ibn Kathir",
                "author": "Ibn Kathir",
                "lang": "en",
                "url": "https://quran.com/2:155/tafsirs/en-ibn-kathir",
            },
            relevance_score=0.6,
            source_space_name="tafsir",
        ),
    ]
    client = _make_goodmem_client(search_results=memories)

    result = await search_tafsir(client, "patience", include_ayah_text=False)

    assert len(result.results) == 1
    merged = result.results[0]
    assert merged.ayah_keys is not None
    assert "2:153" in merged.ayah_keys
    assert "2:154" in merged.ayah_keys
    assert "2:155" in merged.ayah_keys
    assert merged.relevance_score == 0.8


@pytest.mark.asyncio
@patch(TAFSIR_RESOLVE_PATH)
@patch(TAFSIR_SETTINGS_PATH, return_value=_mock_settings())
async def test_search_tafsir_unresolved_editions_tracked(mock_settings, mock_resolve):
    from quran_mcp.lib.editions.registry import ResolveResult
    mock_resolve.return_value = ResolveResult(resolved=[], unresolved=["nonexistent-tafsir"])

    client = _make_goodmem_client()

    result = await search_tafsir(client, "patience", editions=["nonexistent-tafsir"])

    assert result.results == []
    assert result.unresolved_editions == ["nonexistent-tafsir"]


@pytest.mark.asyncio
@patch(TAFSIR_SETTINGS_PATH, return_value=_mock_settings())
async def test_search_tafsir_enrichment_failure_is_explicit(mock_settings):
    tafsir_mem = _make_memory(
        content="Commentary",
        metadata={
            "ayah_key": "2:255",
            "surah": 2,
            "ayah": 255,
            "edition_id": "en-ibn-kathir",
            "name": "Tafsir Ibn Kathir",
            "author": "Ibn Kathir",
            "lang": "en",
            "url": "https://quran.com/2:255/tafsirs/en-ibn-kathir",
        },
        relevance_score=0.91,
        source_space_name="tafsir",
    )
    client = _make_goodmem_client(
        search_side_effect=[
            [tafsir_mem],
            RuntimeError("quran-space down"),
        ]
    )

    with pytest.raises(SearchEnrichmentError, match="tafsir_ayah_text"):
        await search_tafsir(client, "throne verse", include_ayah_text=True)


# ============================================================================
# Tool wrappers (deterministic server-level contracts)
# ============================================================================


@dataclass
class _StubSearchAppContext:
    goodmem_cli: object = True


@asynccontextmanager
async def _search_tool_lifespan(server) -> AsyncIterator[_StubSearchAppContext]:
    yield _StubSearchAppContext()


@pytest.fixture()
def search_tools_mcp() -> FastMCP:
    server = FastMCP("search-tool-test", lifespan=_search_tool_lifespan)
    quran_search_tool.register(server)
    translation_search_tool.register(server)
    tafsir_search_tool.register(server)
    return server


class TestSearchToolContracts:
    async def test_search_quran_server_contract(
        self, search_tools_mcp: FastMCP, monkeypatch: pytest.MonkeyPatch
    ):
        async def _fake_search_quran(**_: Any) -> SearchQuranResult:
            return SearchQuranResult(
                results=[
                    SearchResult(
                        ayah_key="2:255",
                        surah=2,
                        ayah=255,
                        text="اللَّهُ لَا إِلَٰهَ إِلَّا هُوَ",
                        translations=[
                            TranslationSearchResult(
                                edition=EditionInfo(
                                    id="en-sahih-international",
                                    author="Sahih International",
                                    name="Sahih International",
                                    lang="en",
                                    code="si",
                                ),
                                text="Allah - there is no deity except Him...",
                                url="https://quran.com/2:255/en-sahih-international",
                            )
                        ],
                        url="https://quran.com/2:255",
                        relevance_score=0.99,
                        source_space="quran",
                    )
                ],
                unresolved_editions=["typo-edition"],
                translation_gaps=["2:256"],
            )

        monkeypatch.setattr(quran_search_tool, "search_quran", _fake_search_quran)

        async with Client(search_tools_mcp) as client:
            result = await client.call_tool("search_quran", {"query": "throne verse"})

        payload = result.structured_content
        assert payload["query"] == "throne verse"
        assert payload["total_found"] == 1
        assert payload["results"][0]["ayah_key"] == "2:255"
        assert payload["warnings"] is not None
        warning_types = [w["type"] for w in payload["warnings"]]
        assert "unresolved_edition" in warning_types
        assert "translation_gap" in warning_types

    async def test_search_translation_server_contract(
        self, search_tools_mcp: FastMCP, monkeypatch: pytest.MonkeyPatch
    ):
        async def _fake_search_translation(
            *,
            editions: str | list[str] | None,
            **_: Any,
        ) -> SearchTranslationResult:
            assert editions == "auto"
            return SearchTranslationResult(
                results=[
                    TranslationResult(
                        ayah_key="1:1",
                        surah=1,
                        ayah=1,
                        text="In the name of Allah...",
                        edition=TranslationEditionInfo(
                            edition_id="en-sahih-international",
                            name="Sahih International",
                            author="Sahih International",
                            lang="en",
                        ),
                        url="https://quran.com/1:1/en-sahih-international",
                        relevance_score=0.8,
                    )
                ],
                unresolved_editions=["legacy-code"],
            )

        monkeypatch.setattr(translation_search_tool, "search_translation", _fake_search_translation)

        async with Client(search_tools_mcp) as client:
            result = await client.call_tool("search_translation", {"query": "patience"})

        payload = result.structured_content
        assert payload["query"] == "patience"
        assert payload["total_found"] == 1
        assert payload["results"][0]["edition"]["edition_id"] == "en-sahih-international"
        assert payload["warnings"] is not None
        assert payload["warnings"][0]["type"] == "unresolved_edition"

    async def test_search_tafsir_server_contract(
        self, search_tools_mcp: FastMCP, monkeypatch: pytest.MonkeyPatch
    ):
        async def _fake_search_tafsir(**_: Any) -> SearchTafsirResult:
            return SearchTafsirResult(
                results=[
                    TafsirSearchResult(
                        ayah_key="2:255",
                        surah=2,
                        ayah=255,
                        tafsir_text="Commentary text",
                        ayah_text="اللَّهُ لَا إِلَٰهَ إِلَّا هُوَ",
                        citation=TafsirCitation(
                            edition_id="en-ibn-kathir",
                            edition_name="Tafsir Ibn Kathir",
                            author="Ibn Kathir",
                            lang="en",
                            url="https://quran.com/2:255/tafsirs/en-ibn-kathir",
                            citation_url="https://tafsir.app/kathir/2/255",
                        ),
                        relevance_score=0.88,
                        passage_ayah_range=None,
                        ayah_keys=["2:255"],
                    )
                ],
                unresolved_editions=[],
            )

        monkeypatch.setattr(tafsir_search_tool, "search_tafsir", _fake_search_tafsir)

        async with Client(search_tools_mcp) as client:
            result = await client.call_tool("search_tafsir", {"query": "throne verse explanation"})

        payload = result.structured_content
        assert payload["query"] == "throne verse explanation"
        assert payload["total_found"] == 1
        assert payload["results"][0]["citation"]["edition_id"] == "en-ibn-kathir"
        assert payload["warnings"] is None

    async def test_search_tafsir_contract_omits_return_full_tafsir(
        self, search_tools_mcp: FastMCP
    ):
        async with Client(search_tools_mcp) as client:
            tools = await client.list_tools()

        tafsir = {tool.name: tool for tool in tools}["search_tafsir"]
        assert "return_full_tafsir" not in tafsir.inputSchema["properties"]
        assert "return_full_tafsir" not in tafsir_search_tool.SearchTafsirRequestState.model_fields

    async def test_search_tools_surface_pipeline_error_codes(
        self, search_tools_mcp: FastMCP, monkeypatch: pytest.MonkeyPatch
    ):
        async def _raise_backend(**_: Any):
            raise SearchBackendError("wide_retrieval", "backend unavailable")

        async def _raise_enrichment(**_: Any):
            raise SearchEnrichmentError("tafsir_ayah_text", "quran space timeout")

        monkeypatch.setattr(quran_search_tool, "search_quran", _raise_backend)
        monkeypatch.setattr(tafsir_search_tool, "search_tafsir", _raise_enrichment)

        with pytest.raises(ToolError, match=r"^\[search_backend_failure\] "):
            async with Client(search_tools_mcp) as client:
                await client.call_tool("search_quran", {"query": "mercy"})

        with pytest.raises(ToolError, match=r"^\[search_enrichment_failure\] "):
            async with Client(search_tools_mcp) as client:
                await client.call_tool("search_tafsir", {"query": "mercy"})


def test_search_tafsir_legacy_continuation_ignores_removed_flag():
    token = encode_continuation_token(
        tool_name="search_tafsir",
        next_page=2,
        page_size=8,
        request_state={
            "query": "throne verse explanation",
            "include_ayah_text": False,
            "return_full_tafsir": True,
        },
    )

    requested_page, page_size, request_state = decode_continuation_request_model(
        token,
        tool_name="search_tafsir",
        state_model=tafsir_search_tool.SearchTafsirRequestState,
    )

    assert requested_page == 2
    assert page_size == 8
    assert request_state.query == "throne verse explanation"
    assert request_state.include_ayah_text is False
    assert "return_full_tafsir" not in request_state.model_dump()


def test_build_search_request_inputs_applies_defaults_and_sorts_lists():
    state = build_search_request_inputs(
        translation_search_tool.SearchTranslationRequestState,
        continuation=None,
        query="patience",
        defaults={"editions": "auto"},
        surah=2,
        editions=["fr-hamidullah", "en-abdel-haleem"],
    )

    assert state.explicit_state == {
        "query": "patience",
        "surah": 2,
        "editions": ["en-abdel-haleem", "fr-hamidullah"],
    }
    assert state.initial_state is not None
    assert state.initial_state.editions == ["en-abdel-haleem", "fr-hamidullah"]


def test_build_search_request_inputs_uses_defaults_only_for_initial_state():
    state = build_search_request_inputs(
        tafsir_search_tool.SearchTafsirRequestState,
        continuation=None,
        query="throne verse",
        defaults={"include_ayah_text": True},
        editions=None,
        include_ayah_text=None,
    )

    assert state.explicit_state == {"query": "throne verse"}
    assert state.initial_state is not None
    assert state.initial_state.include_ayah_text is True
