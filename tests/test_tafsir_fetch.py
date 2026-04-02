from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from quran_mcp.lib.context.types import AppContext
from quran_mcp.lib.editions.errors import DataNotFoundError, DataStoreError
from quran_mcp.lib.tafsir.fetch import (
    TafsirEntry,
    TafsirFetchResult,
    fetch_tafsir,
    resolve_tafsir_edition_ids,
)


def _load_tafsir_fetch_tool_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "quran_mcp"
        / "mcp"
        / "tools"
        / "tafsir"
        / "fetch.py"
    )
    spec = importlib.util.spec_from_file_location("test_tafsir_fetch_tool_module", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_dedup_entries = _load_tafsir_fetch_tool_module()._dedup_entries


@dataclass
class MockMemory:
    content: str
    metadata: dict


def _make_ctx(memories: list[MockMemory] | None = None) -> AppContext:
    if memories is None:
        return AppContext(goodmem_cli=None)
    mock_goodmem = AsyncMock()
    mock_goodmem.search_memories = AsyncMock(return_value=memories)
    return AppContext(goodmem_cli=mock_goodmem)


def _patch_config():
    from quran_mcp.lib.editions.fetcher import EditionFetcherConfig
    return patch(
        "quran_mcp.lib.tafsir.fetch._get_config",
        return_value=EditionFetcherConfig(
            edition_type="tafsir",
            goodmem_space="tafsir",
            entry_factory=lambda ayah, text, meta: TafsirEntry(
                ayah=ayah,
                text=text,
                citation_url=meta.get("citation_url") or meta.get("url"),
                passage_ayah_range=meta.get("passage_ayah_range"),
            ),
            chunk_multiplier=50,
        ),
    )


# ---------------------------------------------------------------------------
# resolve_tafsir_edition_ids (static registry)
# ---------------------------------------------------------------------------


def test_resolve_by_exact_id():
    result = resolve_tafsir_edition_ids("en-ibn-kathir")
    assert "en-ibn-kathir" in result


def test_resolve_by_code():
    result = resolve_tafsir_edition_ids("ibn-kathir")
    assert any("ibn-kathir" in eid for eid in result)


def test_resolve_unknown_raises():
    with pytest.raises(ValueError):
        resolve_tafsir_edition_ids("nonexistent-tafsir-xyz-999")


# ---------------------------------------------------------------------------
# fetch_tafsir — happy path
# ---------------------------------------------------------------------------


async def test_fetch_single_ayah():
    memories = [
        MockMemory(
            content="Ayat al-Kursi commentary",
            metadata={
                "ayah_key": "2:255",
                "edition_id": "en-ibn-kathir",
                "edition_type": "tafsir",
                "citation_url": "https://tafsir.app/ibn-kathir/2/255",
            },
        ),
    ]
    ctx = _make_ctx(memories)
    with _patch_config():
        result = await fetch_tafsir(ctx, "2:255", "en-ibn-kathir")
    assert isinstance(result, TafsirFetchResult)
    assert "en-ibn-kathir" in result.data
    entry = result.data["en-ibn-kathir"][0]
    assert isinstance(entry, TafsirEntry)
    assert entry.ayah == "2:255"
    assert entry.text == "Ayat al-Kursi commentary"
    assert entry.citation_url == "https://tafsir.app/ibn-kathir/2/255"


async def test_fetch_range_returns_sorted_entries():
    memories = [
        MockMemory(content="v3", metadata={"ayah_key": "31:15", "edition_id": "en-ibn-kathir", "edition_type": "tafsir"}),
        MockMemory(content="v1", metadata={"ayah_key": "31:13", "edition_id": "en-ibn-kathir", "edition_type": "tafsir"}),
        MockMemory(content="v2", metadata={"ayah_key": "31:14", "edition_id": "en-ibn-kathir", "edition_type": "tafsir"}),
    ]
    ctx = _make_ctx(memories)
    with _patch_config():
        result = await fetch_tafsir(ctx, "31:13-15", "en-ibn-kathir")
    ayahs = [e.ayah for e in result.data["en-ibn-kathir"]]
    assert ayahs == ["31:13", "31:14", "31:15"]


async def test_fetch_preserves_passage_ayah_range():
    memories = [
        MockMemory(
            content="passage text",
            metadata={
                "ayah_key": "70:8",
                "edition_id": "en-ibn-kathir",
                "edition_type": "tafsir",
                "passage_ayah_range": "70:8-21",
            },
        ),
    ]
    ctx = _make_ctx(memories)
    with _patch_config():
        result = await fetch_tafsir(ctx, "70:8", "en-ibn-kathir")
    entry = result.data["en-ibn-kathir"][0]
    assert entry.passage_ayah_range == "70:8-21"


# ---------------------------------------------------------------------------
# fetch_tafsir — gaps
# ---------------------------------------------------------------------------


async def test_fetch_missing_data_returns_gaps():
    memories = [
        MockMemory(content="text", metadata={"ayah_key": "2:255", "edition_id": "en-ibn-kathir", "edition_type": "tafsir"}),
    ]
    ctx = _make_ctx(memories)
    with _patch_config():
        result = await fetch_tafsir(ctx, "2:255-256", "en-ibn-kathir")
    assert result.gaps is not None
    assert "2:256" in result.gaps[0].missing_ayahs


# ---------------------------------------------------------------------------
# fetch_tafsir — error paths
# ---------------------------------------------------------------------------


async def test_fetch_all_missing_raises_data_not_found():
    ctx = _make_ctx(memories=[])
    with _patch_config():
        with pytest.raises(DataNotFoundError):
            await fetch_tafsir(ctx, "2:255", "en-ibn-kathir")


async def test_fetch_exceeding_300_raises_value_error():
    ctx = _make_ctx(memories=[])
    ayahs = [f"2:{i}" for i in range(1, 302)]
    with _patch_config():
        with pytest.raises(ValueError, match="300"):
            await fetch_tafsir(ctx, ayahs, "en-ibn-kathir")


async def test_fetch_no_goodmem_raises_data_store_error():
    ctx = _make_ctx(None)
    with _patch_config():
        with pytest.raises(DataStoreError):
            await fetch_tafsir(ctx, "2:255", "en-ibn-kathir")


# ---------------------------------------------------------------------------
# fetch_tafsir — unresolved editions
# ---------------------------------------------------------------------------


async def test_fetch_unresolved_edition_tracked():
    memories = [
        MockMemory(content="text", metadata={"ayah_key": "2:255", "edition_id": "en-ibn-kathir", "edition_type": "tafsir"}),
    ]
    ctx = _make_ctx(memories)
    with _patch_config():
        result = await fetch_tafsir(ctx, "2:255", ["en-ibn-kathir", "nonexistent-xyz-123"])
    assert result.unresolved is not None
    assert any(u.selector == "nonexistent-xyz-123" for u in result.unresolved)


# ---------------------------------------------------------------------------
# _dedup_entries (tool-layer deduplication)
# ---------------------------------------------------------------------------


def test_dedup_empty_input():
    assert _dedup_entries([]) == []


def test_dedup_single_entry():
    result = _dedup_entries([("2:255", "commentary", None, None)])
    assert len(result) == 1
    assert result[0].ayahs == ["2:255"]
    assert result[0].text == "commentary"


def test_dedup_consecutive_identical_texts_collapse():
    raw = [
        ("31:13", "Luqman's Advice", None, None),
        ("31:14", "Luqman's Advice", None, None),
        ("31:15", "Luqman's Advice", None, None),
    ]
    result = _dedup_entries(raw)
    assert len(result) == 1
    assert result[0].ayahs == ["31:13", "31:14", "31:15"]
    assert result[0].range == "31:13-15"
    assert result[0].text == "Luqman's Advice"


def test_dedup_different_texts_stay_separate():
    raw = [
        ("2:255", "Ayat al-Kursi", None, None),
        ("2:256", "La ikraha", None, None),
    ]
    result = _dedup_entries(raw)
    assert len(result) == 2
    assert result[0].ayahs == ["2:255"]
    assert result[1].ayahs == ["2:256"]


def test_dedup_mixed_groups():
    raw = [
        ("31:13", "same text", None, None),
        ("31:14", "same text", None, None),
        ("31:15", "different text", None, None),
        ("31:16", "another same", None, None),
        ("31:17", "another same", None, None),
    ]
    result = _dedup_entries(raw)
    assert len(result) == 3
    assert result[0].ayahs == ["31:13", "31:14"]
    assert result[1].ayahs == ["31:15"]
    assert result[2].ayahs == ["31:16", "31:17"]


def test_dedup_preserves_citation_url():
    raw = [
        ("2:255", "text", "https://tafsir.app/ibn-kathir/2/255", None),
    ]
    result = _dedup_entries(raw)
    assert result[0].citation_url == "https://tafsir.app/ibn-kathir/2/255"


def test_dedup_preserves_passage_ayah_range():
    raw = [
        ("70:8", "text", None, "70:8-21"),
        ("70:9", "text", None, "70:8-21"),
    ]
    result = _dedup_entries(raw)
    assert len(result) == 1
    assert result[0].passage_ayah_range == "70:8-21"
