"""
Semantic search for Quran text via GoodMem with Voyage reranking.

Architecture:
    Query → Wide Retrieval (multi-space) → Dedupe by ayah_key → Rerank → Enrich → Results

Key Design Decisions:
- AYAH is the unit of reranking, not editions
- Balanced per-space retrieval to avoid single-space dominance
- Best-matching edition per ayah in detected language for deduplication
- Voyage rerank-2.5 for semantic ranking
- Enrich with Arabic text and translations only for top-N results

Spec: codev/specs/0027-search-quran-rewrite.md
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from quran_mcp.lib.goodmem import GoodMemClient, GoodMemMemory

from pydantic import BaseModel, ConfigDict, Field

from quran_mcp.lib.config.settings import get_settings
from quran_mcp.lib.editions.registry import get_by_edition_id
from quran_mcp.lib.search.common import (
    AyahMemoryRecord,
    SearchBackendError,
    SearchEnrichmentError,
    TranslationSearchSelection,
    build_ayah_key_filter,
    build_edition_filter,
    build_surah_filter,
    combine_filters,
    detect_query_language,
    memory_to_ayah_record,
    resolve_translation_search_selection,
)

logger = logging.getLogger(__name__)

# Default retrieval limits
DEFAULT_WIDE_RETRIEVAL_LIMIT = 100  # Per space


# =============================================================================
# Response Models (Pydantic)
# =============================================================================


class EditionInfo(BaseModel):
    """Metadata about a Quran or translation edition."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Edition identifier (e.g., 'en-sahih-international')")
    author: str = Field(description="Author or translator name")
    name: str = Field(description="Edition name")
    lang: str = Field(description="2-letter language code (e.g., 'en', 'ar')")
    code: str = Field(description="Short edition code")


class TranslationSearchResult(BaseModel):
    """Translation text for a single ayah from a specific edition."""

    model_config = ConfigDict(extra="forbid")

    edition: EditionInfo = Field(description="Edition metadata")
    text: str = Field(description="Translation text for this ayah")
    url: str = Field(description="Direct link to ayah with this edition on quran.com")


class SearchResult(BaseModel):
    """A single search result representing a ranked ayah."""

    model_config = ConfigDict(extra="forbid")

    ayah_key: str = Field(description="Ayah key in S:V format (e.g., '2:255')")
    surah: int = Field(description="Surah number")
    ayah: int = Field(description="Ayah number within the surah")
    text: str = Field(description="Arabic text (ar-uthmani edition)")
    translations: list[TranslationSearchResult] = Field(
        default_factory=list,
        description="Translation results (empty if translations=None)"
    )
    url: str = Field(description="Link to this ayah on quran.com")
    relevance_score: float | None = Field(
        default=None,
        description="Relevance score from reranker or embedding similarity (higher = more relevant)"
    )
    source_space: str = Field(
        default="",
        description="Which space this result came from (quran, translation, tafsir)"
    )


class SearchQuranResult(BaseModel):
    """Result of search_quran() with warnings."""

    model_config = ConfigDict(extra="forbid")

    results: list[SearchResult] = Field(description="Ranked search results")
    unresolved_editions: list[str] = Field(
        default_factory=list,
        description="Edition selectors that couldn't be resolved"
    )
    translation_gaps: list[str] = Field(
        default_factory=list,
        description="Ayah keys where requested translations were unavailable"
    )


@dataclass(slots=True)
class _DedupedAyah:
    """Internal typed ayah aggregate used across dedupe/enrichment stages."""

    ayah_key: str
    surah: int
    ayah: int
    text: str
    url: str
    relevance_score: float | None
    source_space: str
    edition_id: str
    lang: str
    all_editions: list[AyahMemoryRecord]

# =============================================================================
# Internal Helpers (shared helpers now in lib/search/common.py)
# =============================================================================


# =============================================================================
# Pipeline Stages
# =============================================================================


async def _retrieve_wide(
    goodmem_client: GoodMemClient,
    query: str,
    space_names: list[str],
    limit_per_space: int,
    filter_expr: str | None,
    reranker_id: str | None,
) -> list[GoodMemMemory]:
    """Retrieve memories from multiple spaces with optional reranking.

    Balanced retrieval: fetches limit_per_space from each space to avoid
    single-space dominance.

    Args:
        goodmem_client: Initialized GoodMem client
        query: Search query
        space_names: List of space names to search
        limit_per_space: Max results per space
        filter_expr: Optional surah filter
        reranker_id: Optional Voyage reranker ID

    Returns:
        Combined list of memories from all spaces
    """
    # Search each space separately for balanced retrieval
    search_tasks = [
        goodmem_client.search_memories(
            query=query,
            space_names=[space_name],
            limit=limit_per_space,
            filter_expr=filter_expr,
            reranker_id=reranker_id,
        )
        for space_name in space_names
    ]

    results = await asyncio.gather(*search_tasks, return_exceptions=True)

    all_memories: list[GoodMemMemory] = []
    failures: list[tuple[str, Exception]] = []

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            failures.append((space_names[i], result))
            continue
        if isinstance(result, list):
            all_memories.extend(result)

    if failures:
        joined = ", ".join(f"{space}: {exc}" for space, exc in failures)
        raise SearchBackendError("wide_retrieval", joined)

    return all_memories


def _dedupe_by_ayah(
    memories: list[GoodMemMemory],
    detected_lang: str,
) -> dict[str, _DedupedAyah]:
    """Deduplicate memories by ayah_key, keeping best-matching edition per ayah.

    For each ayah, selects the edition with highest relevance_score in the
    detected language. Falls back to any language if none match.

    Args:
        memories: List of memories from wide retrieval
        detected_lang: Detected query language ("ar" or "en")

    Returns:
        Dict mapping ayah_key -> best typed ayah aggregate
    """
    # Group memories by ayah_key
    ayah_groups: dict[str, list[AyahMemoryRecord]] = {}
    for memory in memories:
        data = memory_to_ayah_record(memory)
        ayah_key = data.ayah_key
        if not ayah_key:
            continue

        if ayah_key not in ayah_groups:
            ayah_groups[ayah_key] = []
        ayah_groups[ayah_key].append(data)

    # For each ayah, select best edition
    deduped: dict[str, _DedupedAyah] = {}
    for ayah_key, editions in ayah_groups.items():
        # Separate by language match
        lang_matched = [e for e in editions if e.lang == detected_lang]
        other_editions = [e for e in editions if e.lang != detected_lang]

        # Pick best from language-matched, else best from others
        candidates = lang_matched if lang_matched else other_editions

        # Sort by relevance_score (highest first), handle None scores
        candidates.sort(
            key=lambda x: (x.relevance_score is not None, x.relevance_score or 0),
            reverse=True
        )

        best = candidates[0] if candidates else editions[0]

        deduped[ayah_key] = _DedupedAyah(
            ayah_key=ayah_key,
            surah=best.surah,
            ayah=best.ayah,
            text=best.text,
            url=best.url,
            relevance_score=best.relevance_score,
            source_space=best.source_space,
            edition_id=best.edition_id,
            lang=best.lang,
            all_editions=editions,
        )

    return deduped


async def _enrich_arabic_text(
    goodmem_client: GoodMemClient,
    deduped_ayat: dict[str, _DedupedAyah],
    quran_space: str,
) -> None:
    """Ensure all ayat have Arabic text (ar-uthmani edition).

    Modifies deduped_ayat in-place to add Arabic text where missing.

    Args:
        goodmem_client: GoodMem client
        deduped_ayat: Deduped ayat (modified in-place)
        quran_space: Name of quran space
    """
    # Find ayat needing Arabic text
    ayahs_needing_arabic = []
    for ayah_key, data in deduped_ayat.items():
        # Check if we already have ar-uthmani from _all_editions
        ar_uthmani = next(
            (e for e in data.all_editions if e.edition_id == "ar-uthmani"),
            None
        )
        if ar_uthmani:
            # Already have it, just update the text field
            if data.lang != "ar" or data.edition_id != "ar-uthmani":
                data.text = ar_uthmani.text
        else:
            ayahs_needing_arabic.append(ayah_key)

    if not ayahs_needing_arabic:
        return

    logger.debug(f"Fetching ar-uthmani text for {len(ayahs_needing_arabic)} ayahs")

    try:
        # Build filter for ar-uthmani edition and specific ayahs
        ayah_filter = build_ayah_key_filter(ayahs_needing_arabic)
        edition_filter = build_edition_filter(["ar-uthmani"])
        combined_filter = combine_filters(edition_filter, ayah_filter)

        arabic_memories = await goodmem_client.search_memories(
            query=" ".join(ayahs_needing_arabic),  # Use ayah keys as query (filter does the real work)
            space_names=[quran_space],
            limit=len(ayahs_needing_arabic),
            filter_expr=combined_filter,
        )

        # Update deduped_ayat with Arabic text
        for memory in arabic_memories:
            data = memory_to_ayah_record(memory)
            ak = data.ayah_key
            if ak in deduped_ayat:
                deduped_ayat[ak].text = data.text
                if not deduped_ayat[ak].url:
                    deduped_ayat[ak].url = data.url

    except Exception as e:
        raise SearchEnrichmentError("quran_arabic_text", str(e)) from e


def _build_translation_edition_metadata(resolved_ids: list[str]) -> dict[str, EditionInfo]:
    """Load translation edition metadata for resolved edition ids."""
    edition_metadata: dict[str, EditionInfo] = {}
    for eid in resolved_ids:
        ed = get_by_edition_id("translation", eid)
        if ed:
            edition_metadata[eid] = EditionInfo(
                id=eid,
                author=ed.author or "",
                name=ed.name,
                lang=ed.lang,
                code=ed.code,
            )
    return edition_metadata


async def _fetch_translations(
    goodmem_client: GoodMemClient,
    ayah_keys: list[str],
    selection: TranslationSearchSelection,
    query: str,
    translation_space: str,
) -> tuple[dict[str, list[TranslationSearchResult]], list[str], list[str]]:
    """Fetch translation text for specific ayahs.

    Args:
        goodmem_client: GoodMem client
        ayah_keys: List of ayah keys to fetch translations for
        selection: Resolved translation selection state
        query: Original query (for language detection in auto mode)
        translation_space: Name of translation space

    Returns:
        Tuple of:
        - Dict mapping ayah_key -> list of TranslationSearchResult
        - List of unresolved edition selectors
        - List of ayah_keys with missing translations (gaps)
    """
    if not ayah_keys:
        return {}, [], []

    resolved_ids = selection.selection.resolved_ids
    unresolved = selection.selection.unresolved
    single_best_match = selection.selection.single_best_match

    if not resolved_ids:
        logger.warning("No translation editions resolved from selectors: %s", unresolved)
        return {}, unresolved, []

    # Initialize result dict
    translation_data: dict[str, list[TranslationSearchResult]] = {ak: [] for ak in ayah_keys}
    gaps: list[str] = []

    try:
        edition_metadata = _build_translation_edition_metadata(resolved_ids)
        memories = await _search_translation_memories(
            goodmem_client=goodmem_client,
            query=query,
            translation_space=translation_space,
            ayah_keys=ayah_keys,
            selection=selection,
        )
        translation_data, gaps = _shape_translation_results(
            memories=memories,
            ayah_keys=ayah_keys,
            edition_metadata=edition_metadata,
            single_best_match=single_best_match,
        )

    except Exception as e:
        raise SearchEnrichmentError("quran_translations", str(e)) from e

    return translation_data, unresolved, gaps


async def _search_translation_memories(
    *,
    goodmem_client: GoodMemClient,
    query: str,
    translation_space: str,
    ayah_keys: list[str],
    selection: TranslationSearchSelection,
) -> list[GoodMemMemory]:
    """Fetch translation memories for one resolved selection."""
    combined_filter = combine_filters(
        build_ayah_key_filter(ayah_keys),
        selection.edition_filter,
    )
    return await goodmem_client.search_memories(
        query=query,
        space_names=[translation_space],
        limit=len(ayah_keys) * len(selection.selection.resolved_ids),
        filter_expr=combined_filter,
    )


def _shape_translation_results(
    *,
    memories: list[GoodMemMemory],
    ayah_keys: list[str],
    edition_metadata: dict[str, EditionInfo],
    single_best_match: bool,
) -> tuple[dict[str, list[TranslationSearchResult]], list[str]]:
    """Project translation memories into per-ayah results and gaps."""
    translation_data: dict[str, list[TranslationSearchResult]] = {ayah_key: [] for ayah_key in ayah_keys}
    best_by_ayah: dict[str, tuple[int, TranslationSearchResult]] = {}

    for idx, memory in enumerate(memories):
        data = memory_to_ayah_record(memory)
        ayah_key = data.ayah_key
        edition_id = data.edition_id

        if ayah_key not in translation_data or edition_id not in edition_metadata:
            continue

        result = TranslationSearchResult(
            edition=edition_metadata[edition_id],
            text=memory.content,
            url=data.url or f"https://quran.com/{data.surah}:{data.ayah}/{edition_id}",
        )

        if single_best_match:
            current = best_by_ayah.get(ayah_key)
            if current is None or idx < current[0]:
                best_by_ayah[ayah_key] = (idx, result)
            continue

        existing_editions = {entry.edition.id for entry in translation_data[ayah_key]}
        if edition_id not in existing_editions:
            translation_data[ayah_key].append(result)

    if single_best_match:
        for ayah_key, (_, result) in best_by_ayah.items():
            translation_data[ayah_key] = [result]

    gaps = [ayah_key for ayah_key in ayah_keys if not translation_data.get(ayah_key)]
    return translation_data, gaps


# =============================================================================
# Core Search Function
# =============================================================================


async def search_quran(
    goodmem_client: GoodMemClient,
    query: str,
    surah: int | None = None,
    results: int = 10,
    translations: str | list[str] | None = None,
    use_reranker: bool = True,
) -> SearchQuranResult:
    """
    Search Quran text semantically via GoodMem with Voyage reranking.

    Pipeline:
    1. Wide retrieval from quran + translation spaces (balanced per-space)
    2. Deduplicate by ayah_key, keeping best-matching edition per ayah
    3. Rerank deduplicated ayat using Voyage rerank-2.5
    4. Enrich top-N with Arabic text and requested translations

    Args:
        goodmem_client: Initialized GoodMem client
        query: Semantic search query (required, non-empty)
        surah: Optional surah number to filter results
        results: Maximum number of results to return (default: 10)
        translations: Translation control:
            - None: No translations in results
            - "auto": Detect query language, return single best match
            - ["en-abdel-haleem", ...]: Return all specified editions
            - "en" (2-letter code): Return single best match from that language
        use_reranker: Whether to use Voyage reranker (default: True)

    Returns:
        SearchQuranResult with ranked results and any warnings

    Raises:
        ValueError: If query is empty or whitespace-only
    """
    if not query or not query.strip():
        raise ValueError("Query cannot be empty or whitespace-only")

    query = query.strip()

    # Detect query language for text selection (used as dedup preference, not hard filter)
    detected_lang, _lang_confidence = detect_query_language(query)
    logger.debug(f"Detected query language: {detected_lang} (confidence={_lang_confidence:.3f})")

    filter_expr = build_surah_filter(surah)

    # Always search both quran + translation spaces
    settings = get_settings()
    space_mapping = {
        "quran": settings.goodmem.space.quran,
        "translation": settings.goodmem.space.translation,
    }
    spaces_to_search = [space_mapping["quran"], space_mapping["translation"]]

    logger.info(f"search_quran: query='{query[:50]}...', spaces={spaces_to_search}, reranker={use_reranker}")

    # Wide retrieval with reranking
    reranker_id = goodmem_client.default_reranker_id if use_reranker else None
    all_memories = await _retrieve_wide(
        goodmem_client=goodmem_client,
        query=query,
        space_names=spaces_to_search,
        limit_per_space=DEFAULT_WIDE_RETRIEVAL_LIMIT,
        filter_expr=filter_expr,
        reranker_id=reranker_id,
    )

    logger.debug(f"Wide retrieval returned {len(all_memories)} memories")

    deduped_ayat = _dedupe_by_ayah(all_memories, detected_lang)
    logger.debug(f"Deduplication: {len(all_memories)} memories -> {len(deduped_ayat)} unique ayat")

    sorted_ayat = sorted(
        deduped_ayat.values(),
        key=lambda x: (
            x.relevance_score is not None,
            x.relevance_score or 0,
        ),
        reverse=True
    )[:results]

    # Enrich with Arabic text (ar-uthmani)
    # Build a dict of just the top results for enrichment
    top_ayat = {a.ayah_key: a for a in sorted_ayat}
    await _enrich_arabic_text(
        goodmem_client=goodmem_client,
        deduped_ayat=top_ayat,
        quran_space=space_mapping["quran"],
    )

    unresolved_editions: list[str] = []
    translation_gaps: list[str] = []
    translation_data: dict[str, list[TranslationSearchResult]] = {}

    if translations is not None:
        selection = resolve_translation_search_selection(
            query,
            translations,
            auto_low_confidence_behavior="resolve",
        )
        translation_data, unresolved_editions, translation_gaps = await _fetch_translations(
            goodmem_client=goodmem_client,
            ayah_keys=[a.ayah_key for a in sorted_ayat],
            selection=selection,
            query=query,
            translation_space=space_mapping["translation"],
        )

    final_results: list[SearchResult] = []
    for ayah_data in sorted_ayat:
        ayah_key = ayah_data.ayah_key
        final_results.append(
            SearchResult(
                ayah_key=ayah_key,
                surah=ayah_data.surah,
                ayah=ayah_data.ayah,
                text=top_ayat.get(ayah_key, ayah_data).text,
                translations=translation_data.get(ayah_key, []),
                url=ayah_data.url or f"https://quran.com/{ayah_data.surah}:{ayah_data.ayah}",
                relevance_score=ayah_data.relevance_score,
                source_space=ayah_data.source_space,
            )
        )

    return SearchQuranResult(
        results=final_results,
        unresolved_editions=unresolved_editions,
        translation_gaps=translation_gaps,
    )
