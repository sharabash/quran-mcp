"""
Semantic search over translation content via GoodMem.

Provides search_translation() for discovering translation passages by
topic/concept without requiring a known ayah_key.

Spec: codev/specs/0033-search-translation.md
"""
from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from quran_mcp.lib.config.settings import get_settings
from quran_mcp.lib.goodmem import GoodMemClient
from quran_mcp.lib.search.common import (
    AyahMemoryRecord,
    SearchBackendError,
    build_surah_filter,
    combine_filters,
    memory_to_ayah_record,
    resolve_translation_search_selection,
)

logger = logging.getLogger(__name__)

# Over-fetch multiplier to compensate for dedup loss.
# Same rationale as search_tafsir: duplicates reduce unique results.
_OVERFETCH_MULTIPLIER = 3


# =============================================================================
# Data Structures
# =============================================================================


class TranslationEditionInfo(BaseModel):
    """Edition metadata for a translation search result."""

    model_config = ConfigDict(extra="forbid")

    edition_id: str = Field(description="Edition identifier (e.g., 'en-sahih-international')")
    name: str = Field(description="Edition name (e.g., 'Sahih International')")
    author: str = Field(description="Author name")
    lang: str = Field(description="2-letter language code")


class TranslationResult(BaseModel):
    """A single translation search result."""

    model_config = ConfigDict(extra="forbid")

    ayah_key: str = Field(description="Ayah key in S:V format (e.g., '2:255')")
    surah: int = Field(description="Surah number")
    ayah: int = Field(description="Ayah number within the surah")
    text: str = Field(description="Translation text")
    edition: TranslationEditionInfo = Field(description="Edition metadata")
    url: str = Field(description="Link to this ayah on quran.com")
    relevance_score: float | None = Field(
        default=None,
        description="Relevance score from reranker (higher = more relevant)",
    )


class SearchTranslationResult(BaseModel):
    """Result of search_translation() with warnings."""

    model_config = ConfigDict(extra="forbid")

    results: list[TranslationResult] = Field(description="Ranked translation search results")
    unresolved_editions: list[str] = Field(
        default_factory=list,
        description="Edition selectors that could not be resolved",
    )


def _dedupe_best_by_ayah(records: list[AyahMemoryRecord]) -> list[AyahMemoryRecord]:
    """Keep the highest-scoring record per ayah key."""
    best_by_ayah: dict[str, AyahMemoryRecord] = {}
    for record in records:
        existing = best_by_ayah.get(record.ayah_key)
        if existing is None:
            best_by_ayah[record.ayah_key] = record
            continue
        existing_score = existing.relevance_score
        new_score = record.relevance_score
        if new_score is not None and (existing_score is None or new_score > existing_score):
            best_by_ayah[record.ayah_key] = record
    deduped = list(best_by_ayah.values())
    deduped.sort(key=lambda r: r.relevance_score or 0.0, reverse=True)
    return deduped


def _record_to_result(record: AyahMemoryRecord) -> TranslationResult:
    """Convert a typed memory record into a boundary result model."""
    return TranslationResult(
        ayah_key=record.ayah_key,
        surah=record.surah,
        ayah=record.ayah,
        text=record.text,
        edition=TranslationEditionInfo(
            edition_id=record.edition_id,
            name=record.name,
            author=record.author,
            lang=record.lang,
        ),
        url=record.url or f"https://quran.com/{record.surah}:{record.ayah}",
        relevance_score=record.relevance_score,
    )


# =============================================================================
# Core Search Function
# =============================================================================


async def search_translation(
    goodmem_client: "GoodMemClient",
    query: str,
    surah: int | None = None,
    results: int = 10,
    editions: str | list[str] | Literal["auto"] | None = "auto",
    use_reranker: bool = True,
) -> SearchTranslationResult:
    """
    Search translation content semantically via GoodMem.

    Args:
        goodmem_client: Initialized GoodMem client.
        query: Semantic search query (required, non-empty).
        surah: Optional surah number to restrict search.
        results: Maximum number of results to return (default: 10).
        editions: Edition filter:
            - "auto" (default): Auto-detect query language, filter to that language's editions.
            - None: Search all editions regardless of language.
            - str | list[str]: Specific edition selectors (IDs, codes, lang codes).
        use_reranker: Whether to use Voyage reranker (default: True).

    Returns:
        SearchTranslationResult with ranked results and any warnings.

    Raises:
        ValueError: If query is empty or whitespace-only.
    """
    # 1. Input validation
    if not query or not query.strip():
        raise ValueError("Query cannot be empty or whitespace-only")

    query = query.strip()

    # 2. Resolve edition filters
    selection = resolve_translation_search_selection(
        query,
        editions,
        auto_low_confidence_behavior="all",
    )
    resolved_ids = selection.selection.resolved_ids
    unresolved = selection.selection.unresolved

    # If edition selectors were provided but nothing matched, return empty with warnings.
    if editions is not None and not resolved_ids:
        return SearchTranslationResult(results=[], unresolved_editions=unresolved)

    # 3. Build filter expressions
    surah_filter = build_surah_filter(surah)
    combined_filter = combine_filters(surah_filter, selection.edition_filter)

    # 4. Determine translation space name from settings
    settings = get_settings()
    translation_space = settings.goodmem.space.translation

    # 5. Resolve reranker
    reranker_id = goodmem_client.default_reranker_id if use_reranker else None

    logger.info(
        "search_translation: query='%s...', editions=%s, surah=%s, space=%s, reranker=%s",
        query[:50],
        resolved_ids or "all",
        surah,
        translation_space,
        use_reranker,
    )

    # 6. Over-fetch to compensate for dedup loss
    fetch_limit = results * _OVERFETCH_MULTIPLIER

    # 7. Search GoodMem translation space
    try:
        memories = await goodmem_client.search_memories(
            query=query,
            space_names=[translation_space],
            limit=fetch_limit,
            filter_expr=combined_filter,
            reranker_id=reranker_id,
        )
    except Exception as exc:
        raise SearchBackendError("translation_search", str(exc)) from exc

    logger.debug(
        "Translation search returned %d results (fetched %d)",
        len(memories),
        fetch_limit,
    )

    # 8. Convert memories to typed ayah records
    raw_results: list[AyahMemoryRecord] = []
    for memory in memories:
        data = memory_to_ayah_record(memory)
        if data.ayah_key:
            raw_results.append(data)

    # 9. Deduplicate by ayah_key: keep highest relevance_score per ayah
    deduped = _dedupe_best_by_ayah(raw_results)

    if len(deduped) < len(raw_results):
        logger.info(
            "Dedup: %d -> %d (%d duplicates removed)",
            len(raw_results),
            len(deduped),
            len(raw_results) - len(deduped),
        )

    # 10. Trim to requested results count
    deduped = deduped[:results]

    # 11. Build TranslationResult objects
    translation_results = [_record_to_result(record) for record in deduped]

    return SearchTranslationResult(
        results=translation_results,
        unresolved_editions=unresolved,
    )
