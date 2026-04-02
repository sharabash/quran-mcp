"""
Semantic search over tafsir content via GoodMem.

Provides search_tafsir() for discovering tafsir passages by topic/concept
without requiring a known ayah_key.

Spec: codev/specs/0026-search-tafsir.md
"""
from __future__ import annotations

import html
import logging
import re
from quran_mcp.lib.goodmem import GoodMemClient, GoodMemMemory

from pydantic import BaseModel, ConfigDict, Field

from quran_mcp.lib.ayah_parsing import format_ayah_range
from quran_mcp.lib.editions.registry import resolve_ids_with_unresolved
from quran_mcp.lib.search.common import (
    SearchBackendError,
    SearchEnrichmentError,
    build_ayah_key_filter,
    build_edition_filter,
    combine_filters,
)
from quran_mcp.lib.config.settings import get_settings

logger = logging.getLogger(__name__)

# Over-fetch multiplier to compensate for content duplicates that will be deduped.
# Empirical: 18-50% of results can be duplicates, so 3x provides headroom.
_OVERFETCH_MULTIPLIER = 3


# =============================================================================
# Data Structures
# =============================================================================


class TafsirCitation(BaseModel):
    """Citation metadata for a tafsir search result."""

    model_config = ConfigDict(extra="forbid")

    edition_id: str = Field(description="Edition identifier (e.g., 'en-ibn-kathir')")
    edition_name: str = Field(description="Edition name (e.g., 'Tafsir Ibn Kathir')")
    author: str = Field(description="Author name (e.g., 'Ibn Kathir')")
    lang: str = Field(description="2-letter language code")
    url: str = Field(description="Link to tafsir on quran.com")
    citation_url: str | None = Field(
        default=None,
        description="Per-entry source link (e.g., 'https://tafsir.app/kashaf/2/255')",
    )


class TafsirSearchResult(BaseModel):
    """A single tafsir search result."""

    model_config = ConfigDict(extra="forbid")

    ayah_key: str = Field(
        description=(
            "Ayah key — single (e.g., '2:255') or merged range "
            "(e.g., '2:153-155') when duplicate tafsir entries were collapsed"
        )
    )
    surah: int = Field(description="Surah number (of first ayah in range)")
    ayah: int = Field(description="Ayah number within the surah (of first ayah in range)")
    tafsir_text: str = Field(description="Cleaned tafsir text (HTML stripped)")
    ayah_text: str | None = Field(
        default=None,
        description="Arabic ayah text for the first ayah in the range",
    )
    citation: TafsirCitation = Field(description="Citation metadata")
    relevance_score: float | None = Field(
        default=None,
        description="Relevance score from reranker (higher = more relevant)",
    )
    passage_ayah_range: str | None = Field(
        default=None,
        description=(
            "Passage range from source metadata (e.g., '70:8-21') "
            "when tafsir covers multiple verses"
        ),
    )
    ayah_keys: list[str] | None = Field(
        default=None,
        description=(
            "Individual ayah keys when multiple were merged "
            "(e.g., ['2:153', '2:154', '2:155'])"
        ),
    )


class SearchTafsirResult(BaseModel):
    """Result of search_tafsir() with warnings."""

    model_config = ConfigDict(extra="forbid")

    results: list[TafsirSearchResult] = Field(description="Ranked tafsir search results")
    unresolved_editions: list[str] = Field(
        default_factory=list,
        description="Edition selectors that could not be resolved",
    )


# =============================================================================
# HTML Cleanup
# =============================================================================


def clean_tafsir_html(text: str) -> str:
    """Strip HTML tags from tafsir content with proper spacing and normalization.

    Handles the HTML patterns found in tafsir editions:
    - <h2> headings (ibn-kathir): converted to double-newline-separated text
    - <p> paragraphs (all editions): converted to double newlines
    - <br/> tags: converted to single newlines
    - <span class="arabic ..."> (saadi): stripped, content preserved
    - <span class="footnote"> or <sup>: converted to bracketed references
    - <div> wrappers: stripped with spacing
    - HTML entities: decoded

    Args:
        text: Raw tafsir text potentially containing HTML.

    Returns:
        Cleaned plain text with proper spacing.
    """
    # Block-level elements → double newlines (headings, paragraphs, divs)
    # Insert newlines BEFORE closing+opening boundaries to avoid concatenation
    text = re.sub(r"</h2>\s*", "\n\n", text)
    text = re.sub(r"<h2[^>]*>", "", text)
    text = re.sub(r"</p>\s*<p[^>]*>", "\n\n", text)
    text = re.sub(r"<p[^>]*>", "", text)
    text = re.sub(r"</p>", "\n\n", text)
    text = re.sub(r"<div[^>]*>", "", text)
    text = re.sub(r"</div>", "\n\n", text)
    # Convert <br> tags to single newlines
    text = re.sub(r"<br\s*/?>", "\n", text)
    # Footnote/superscript markers → bracketed references (e.g., <sup>1</sup> → [1])
    text = re.sub(r"<sup[^>]*>(.*?)</sup>", r" [\1]", text)
    # Strip remaining inline tags (span, b, i, a, etc.) — preserve content with spacing
    # Add a space before stripping to prevent word concatenation (e.g., "word<span>x</span>next")
    # But only if there isn't already whitespace adjacent
    text = re.sub(r"(?<!\s)</(span|a|b|i|em|strong)>(?!\s)", r" ", text)
    text = re.sub(r"<[^>]+>", "", text)
    # Decode HTML entities (&amp; → &, &nbsp; → space, etc.)
    text = html.unescape(text)
    # Normalize multiple spaces (but not newlines) to single space
    text = re.sub(r"[^\S\n]+", " ", text)
    # Normalize excessive newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Clean up space before newline
    text = re.sub(r" +\n", "\n", text)
    return text.strip()




def _dedupe_results(
    results: list["TafsirSearchResult"],
) -> list["TafsirSearchResult"]:
    """Deduplicate search results by content hash within the same edition.

    When a tafsir author wrote one commentary spanning multiple ayahs,
    the ingestion pipeline stored that identical text for each ayah.
    This merges those duplicates into a single result with a merged
    ayah_key range (e.g., "2:153-155") and keeps the best relevance score.

    Args:
        results: List of search results, potentially with duplicates.

    Returns:
        Deduplicated list preserving original ordering by first occurrence.
    """
    # Key: (content_hash, edition_id) → first result seen
    seen: dict[tuple[int, str], TafsirSearchResult] = {}
    order: list[tuple[int, str]] = []

    for r in results:
        content_hash = hash(r.tafsir_text)
        key = (content_hash, r.citation.edition_id)

        if key not in seen:
            # First occurrence — initialize with ayah_keys list
            r.ayah_keys = [r.ayah_key]
            seen[key] = r
            order.append(key)
        else:
            # Duplicate — merge ayah_key into existing result
            existing = seen[key]
            if existing.ayah_keys is None:
                existing.ayah_keys = [existing.ayah_key]
            if r.ayah_key not in existing.ayah_keys:
                existing.ayah_keys.append(r.ayah_key)
            # Keep the best relevance score
            if r.relevance_score is not None and (
                existing.relevance_score is None
                or r.relevance_score > existing.relevance_score
            ):
                existing.relevance_score = r.relevance_score

    # Update ayah_key to formatted range for merged results
    deduped: list[TafsirSearchResult] = []
    for key in order:
        r = seen[key]
        if r.ayah_keys and len(r.ayah_keys) > 1:
            r.ayah_key = format_ayah_range(r.ayah_keys)
        deduped.append(r)

    return deduped


def _memory_to_search_result(
    memory: "GoodMemMemory",
    ayah_text: str | None = None,
) -> TafsirSearchResult | None:
    """Convert a GoodMem memory to a TafsirSearchResult.

    Args:
        memory: GoodMem memory with tafsir content and metadata.
        ayah_text: Optional ayah text to include.

    Returns:
        TafsirSearchResult, or None if required metadata is missing.
    """
    metadata = memory.metadata or {}

    ayah_key = metadata.get("ayah_key", "")
    if not ayah_key:
        logger.debug("Skipping memory without ayah_key")
        return None

    try:
        surah = int(metadata.get("surah") or 0)
        ayah = int(metadata.get("ayah_start") or metadata.get("ayah") or 0)
    except (TypeError, ValueError):
        logger.debug("Skipping memory with invalid surah/ayah metadata")
        return None

    edition_id = metadata.get("edition_id", "")
    edition_name = metadata.get("name", "")
    author = metadata.get("author", "")
    lang = metadata.get("lang", "")
    url = metadata.get("url", "")
    citation_url = metadata.get("citation_url") or None

    ayah_start = metadata.get("ayah_start")
    ayah_end = metadata.get("ayah_end")
    if ayah_start is not None and ayah_end is not None:
        s, e = int(ayah_start), int(ayah_end)
        passage_ayah_range = f"{surah}:{s}-{e}" if s != e else None
    else:
        passage_ayah_range = metadata.get("passage_ayah_range") or None

    # Clean HTML from tafsir text
    tafsir_text = clean_tafsir_html(memory.content)

    citation = TafsirCitation(
        edition_id=edition_id,
        edition_name=edition_name,
        author=author,
        lang=lang,
        url=url,
        citation_url=citation_url,
    )

    return TafsirSearchResult(
        ayah_key=ayah_key,
        surah=surah,
        ayah=ayah,
        tafsir_text=tafsir_text,
        ayah_text=ayah_text,
        citation=citation,
        relevance_score=memory.relevance_score,
        passage_ayah_range=passage_ayah_range,
    )


async def _fetch_ayah_texts(
    goodmem_client: "GoodMemClient",
    ayah_keys: list[str],
    quran_space: str,
) -> dict[str, str]:
    """Fetch Arabic text for a set of ayah keys from the quran space.

    Args:
        goodmem_client: GoodMem client.
        ayah_keys: List of ayah keys to fetch.
        quran_space: Name of the quran GoodMem space.

    Returns:
        Dict mapping ayah_key -> Arabic text.
    """
    if not ayah_keys:
        return {}

    # Build filter for ar-uthmani edition and specific ayahs
    ayah_filter = build_ayah_key_filter(ayah_keys)
    edition_filter = build_edition_filter(["ar-uthmani"])
    combined_filter = combine_filters(edition_filter, ayah_filter)

    try:
        memories = await goodmem_client.search_memories(
            query=" ".join(ayah_keys),
            space_names=[quran_space],
            limit=len(ayah_keys),
            filter_expr=combined_filter,
        )
    except Exception as e:
        raise SearchEnrichmentError("tafsir_ayah_text", str(e)) from e

    result: dict[str, str] = {}
    for mem in memories:
        ak = (mem.metadata or {}).get("ayah_key", "")
        if ak:
            result[ak] = mem.content
    return result


# =============================================================================
# Core Search Function
# =============================================================================


async def search_tafsir(
    goodmem_client: "GoodMemClient",
    query: str,
    editions: str | list[str] | None = None,
    results: int = 10,
    include_ayah_text: bool = True,
    use_reranker: bool = True,
) -> SearchTafsirResult:
    """
    Search tafsir content semantically via GoodMem.

    Args:
        goodmem_client: Initialized GoodMem client.
        query: Semantic search query (required, non-empty).
        editions: Optional edition selector or selectors to filter by.
            Supports full IDs, codes, language codes, fuzzy matching.
        results: Maximum number of results to return (default: 10).
        include_ayah_text: Whether to include the ayah Arabic text (default: True).
        use_reranker: Whether to use Voyage reranker for better relevance (default: True).

    Returns:
        SearchTafsirResult with ranked results and any warnings.

    Raises:
        ValueError: If query is empty or whitespace-only.
    """
    if not query or not query.strip():
        raise ValueError("Query cannot be empty or whitespace-only")

    query = query.strip()

    # Resolve edition filters
    resolved_ids: list[str] = []
    unresolved: list[str] = []

    if editions is not None:
        result = resolve_ids_with_unresolved("tafsir", editions)
        resolved_ids = result.resolved
        unresolved = result.unresolved

        # If editions were specified but none resolved, return empty with warnings
        if not resolved_ids:
            return SearchTafsirResult(results=[], unresolved_editions=unresolved)

    filter_expr = build_edition_filter(resolved_ids)

    settings = get_settings()
    tafsir_space = settings.goodmem.space.tafsir
    reranker_id = goodmem_client.default_reranker_id if use_reranker else None

    logger.info(
        f"search_tafsir: query='{query[:50]}...', editions={resolved_ids or 'all'}, "
        f"space={tafsir_space}, reranker={use_reranker}"
    )

    # Over-fetch to compensate for duplicates that will be deduped
    fetch_limit = results * _OVERFETCH_MULTIPLIER

    try:
        memories = await goodmem_client.search_memories(
            query=query,
            space_names=[tafsir_space],
            limit=fetch_limit,
            filter_expr=filter_expr,
            reranker_id=reranker_id,
        )
    except Exception as e:
        raise SearchBackendError("tafsir_search", str(e)) from e

    logger.debug(f"Tafsir search returned {len(memories)} results (fetched {fetch_limit})")

    raw_results: list[TafsirSearchResult] = []
    for memory in memories:
        result = _memory_to_search_result(memory)
        if result is not None:
            raw_results.append(result)

    # Deduplicate by content hash within same edition, merge ayah ranges
    deduped = _dedupe_results(raw_results)

    if len(deduped) < len(raw_results):
        logger.info(
            f"Dedup: {len(raw_results)} -> {len(deduped)} "
            f"({len(raw_results) - len(deduped)} duplicates removed)"
        )

    deduped = deduped[:results]

    # Optionally fetch ayah text (use first ayah_key from each result)
    ayah_keys_for_text: list[str] = []
    if include_ayah_text:
        for r in deduped:
            # For merged results, fetch text for the first ayah in the range
            first_key = r.ayah_keys[0] if r.ayah_keys else r.ayah_key
            if first_key not in ayah_keys_for_text:
                ayah_keys_for_text.append(first_key)

    if include_ayah_text and ayah_keys_for_text:
        quran_space = settings.goodmem.space.quran
        ayah_texts = await _fetch_ayah_texts(
            goodmem_client, ayah_keys_for_text, quran_space
        )
        for result in deduped:
            first_key = result.ayah_keys[0] if result.ayah_keys else result.ayah_key
            result.ayah_text = ayah_texts.get(first_key)

    return SearchTafsirResult(
        results=deduped,
        unresolved_editions=unresolved,
    )
