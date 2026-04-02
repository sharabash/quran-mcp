"""Shared helpers for semantic search tools.

Contains utility functions used across search_quran, search_tafsir,
and search_translation. Extracted from lib/quran/search.py to avoid
cross-module coupling and code duplication.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
import re
from typing import Any, Literal
from quran_mcp.lib.goodmem import GoodMemMemory
from quran_mcp.lib.goodmem.filters import (
    FilterTerm,
    build_filter_expression,
    escape_literal,
)
from quran_mcp.lib.editions.registry import resolve_ids_with_unresolved

logger = logging.getLogger(__name__)

# Arabic Unicode range — catches Arabic, Urdu, Farsi (all share the script).
# Used as a fast heuristic before the optional full language detector to avoid
# Urdu/Farsi misclassification on short queries that statistical detectors
# struggle with.
_ARABIC_SCRIPT_RE = re.compile(r"[\u0600-\u06FF]")

_ARABIC_WORD_RE = re.compile(r"[\u0600-\u06FF]+")

# Short Arabic-script queries (≤ this many Arabic words) bypass the optional
# detector
# and default to "ar". FastText cannot reliably distinguish Arabic from
# Urdu/Farsi on very short text (e.g., "صبر" → ur:0.69, wrong for Quran use).
# For longer queries (3+ Arabic words), FastText has enough signal.
_SHORT_ARABIC_WORD_THRESHOLD = 2

# Minimum confidence score for statistical language detection to be trusted.
# Below this, the language is considered ambiguous (e.g., transliterated
# Islamic terms like "sabr", "tawakkul" that FastText can't classify).
LANG_DETECT_CONFIDENCE_THRESHOLD = 0.6


@dataclass(slots=True, frozen=True)
class SearchEditionSelection:
    """Resolved edition selector state for search-boundary helpers."""

    resolved_ids: list[str]
    unresolved: list[str]
    single_best_match: bool = False


@dataclass(slots=True, frozen=True)
class TranslationSearchSelection:
    """Resolved translation selector state plus its reusable GoodMem filter."""

    selection: SearchEditionSelection
    edition_filter: str | None


def _detect_with_fast_langdetect(query: str) -> list[dict[str, Any]] | None:
    """Return raw fast-langdetect results, or ``None`` when unavailable."""
    try:
        from fast_langdetect import detect as fast_detect
    except Exception as exc:  # pragma: no cover - dependency availability varies
        logger.debug("fast-langdetect unavailable, falling back to heuristics: %s", exc)
        return None

    try:
        return fast_detect(query, model="full")
    except Exception as exc:
        logger.warning("FastText failed for query=%r: %s", query[:30], exc)
        return None


def build_edition_filter(edition_ids: list[str]) -> str | None:
    """Build a GoodMem filter expression restricting results to editions."""
    if not edition_ids:
        return None

    parts = [
        f"CAST(val('$.edition_id') AS TEXT) = '{escape_literal(eid)}'"
        for eid in edition_ids
    ]
    if len(parts) == 1:
        return parts[0]
    return f"({' OR '.join(parts)})"


def combine_filters(*filters: str | None) -> str | None:
    """Combine GoodMem filters with ``AND`` while skipping ``None`` values."""
    active = [f for f in filters if f is not None]
    if not active:
        return None
    if len(active) == 1:
        return active[0]
    return " AND ".join(active)


def build_ayah_key_filter(ayah_keys: list[str]) -> str | None:
    """Build a GoodMem filter expression restricting results to ayah keys."""
    if not ayah_keys:
        return None

    parts = [
        f"CAST(val('$.ayah_key') AS TEXT) = '{escape_literal(ayah_key)}'"
        for ayah_key in ayah_keys
    ]
    if len(parts) == 1:
        return parts[0]
    return f"({' OR '.join(parts)})"


class SearchPipelineError(RuntimeError):
    """Base error type for search pipeline failures.

    ``code`` is surfaced at tool boundaries as a bracketed error contract.
    """

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class SearchBackendError(SearchPipelineError):
    """Raised when backend search calls fail."""

    def __init__(self, stage: str, detail: str):
        super().__init__(
            "search_backend_failure",
            f"Search backend failed during {stage}: {detail}",
        )


class SearchEnrichmentError(SearchPipelineError):
    """Raised when enrichment of already-retrieved results fails."""

    def __init__(self, stage: str, detail: str):
        super().__init__(
            "search_enrichment_failure",
            f"Search enrichment failed during {stage}: {detail}",
        )


@dataclass(frozen=True, slots=True)
class AyahMemoryRecord:
    """Typed projection of a Quran-related GoodMem memory."""

    ayah_key: str
    surah: int
    ayah: int
    text: str
    edition_id: str
    lang: str
    url: str
    code: str
    author: str
    name: str
    relevance_score: float | None
    source_space: str


def detect_query_language(query: str | None) -> tuple[str, float]:
    """Detect query language → (iso_code, confidence).

    Short Arabic (≤2 words) → ("ar", 1.0) via heuristic. Longer text
    uses FastText. Falls back to ("en", 0.0) on empty input or errors.
    """
    if not query or not query.strip():
        return ("en", 0.0)

    query = query.strip()

    if _ARABIC_SCRIPT_RE.search(query):
        arabic_word_count = len(_ARABIC_WORD_RE.findall(query))

        # Stage 1: Short Arabic-script text — FastText unreliable for ar vs ur/fa
        if arabic_word_count <= _SHORT_ARABIC_WORD_THRESHOLD:
            return ("ar", 1.0)

        # Stage 2: Longer Arabic-script text — FastText can distinguish ar/ur/fa
        results = _detect_with_fast_langdetect(query)
        if results and results[0].get("lang"):
            lang = results[0]["lang"]
            score = results[0].get("score", 0.0)
            logger.debug(
                f"Arabic-script FastText: {lang} (score={score:.3f}) "
                f"for query={query[:30]!r}"
            )
            # Trust FastText only if it confidently says non-Arabic
            if lang != "ar" and score >= LANG_DETECT_CONFIDENCE_THRESHOLD:
                return (lang, score)

        # Default to Arabic for Arabic-script text when FastText is unsure
        return ("ar", 1.0)

    # Stage 3: FastText full model for non-Arabic-script queries
    results = _detect_with_fast_langdetect(query)
    if results and results[0].get("lang"):
        lang = results[0]["lang"]
        score = results[0].get("score", 0.0)
        logger.debug(f"Language detected: {lang} (score={score:.3f}) for query={query[:30]!r}")
        return (lang, score)

    return ("en", 0.0)


def resolve_translation_editions(
    query: str,
    selectors: str | list[str] | Literal["auto"] | None,
    *,
    auto_low_confidence_behavior: Literal["resolve", "all"] = "resolve",
) -> SearchEditionSelection:
    """Resolve translation selectors into edition IDs for search pipelines."""
    if selectors is None:
        return SearchEditionSelection(resolved_ids=[], unresolved=[])

    if selectors == "auto":
        detected_lang, confidence = detect_query_language(query)
        if confidence < LANG_DETECT_CONFIDENCE_THRESHOLD and auto_low_confidence_behavior == "all":
            logger.info(
                "Low confidence language detection (%s, score=%.3f), searching all editions",
                detected_lang,
                confidence,
            )
            return SearchEditionSelection(resolved_ids=[], unresolved=[])

        if detected_lang == "ar":
            result = resolve_ids_with_unresolved("translation", "ar")
            if not result.resolved:
                # No Arabic translations — fall back to English
                result = resolve_ids_with_unresolved("translation", "en")
        elif detected_lang == "en":
            result = resolve_ids_with_unresolved("translation", "en")
        else:
            result = resolve_ids_with_unresolved("translation", detected_lang)

        return SearchEditionSelection(
            resolved_ids=result.resolved,
            unresolved=result.unresolved,
            single_best_match=True,
        )

    explicit = resolve_ids_with_unresolved("translation", selectors)
    single_best_match = isinstance(selectors, str) and len(selectors) == 2
    return SearchEditionSelection(
        resolved_ids=explicit.resolved,
        unresolved=explicit.unresolved,
        single_best_match=single_best_match,
    )


def resolve_translation_search_selection(
    query: str,
    selectors: str | list[str] | Literal["auto"] | None,
    *,
    auto_low_confidence_behavior: Literal["resolve", "all"] = "resolve",
) -> TranslationSearchSelection:
    """Resolve translation selectors and prebuild the corresponding edition filter."""
    selection = resolve_translation_editions(
        query,
        selectors,
        auto_low_confidence_behavior=auto_low_confidence_behavior,
    )
    return TranslationSearchSelection(
        selection=selection,
        edition_filter=build_edition_filter(selection.resolved_ids),
    )


def build_surah_filter(surah: int | None) -> str | None:
    """Build GoodMem filter for surah constraint, or None if not filtering."""
    if surah is None:
        return None
    terms = [FilterTerm(field="surah", operator="=", value=surah, value_type=int)]
    return build_filter_expression(terms)


def parse_ayah_key(key: str) -> tuple[int, int]:
    """Parse ``S:V`` ayah key into (surah, ayah) integers."""
    parts = key.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid ayah_key format: {key}")
    return int(parts[0]), int(parts[1])


def memory_to_ayah_record(memory: "GoodMemMemory") -> AyahMemoryRecord:
    """Extract a typed ayah record from a GoodMem memory."""
    metadata = memory.metadata or {}

    ayah_key = metadata.get("ayah_key", "")
    surah = metadata.get("surah", 0)
    ayah = metadata.get("ayah", 0)

    if not ayah_key and surah and ayah:
        ayah_key = f"{surah}:{ayah}"

    if ayah_key and (not surah or not ayah):
        try:
            surah, ayah = parse_ayah_key(ayah_key)
        except ValueError:
            logger.debug("Could not parse ayah_key %r for surah/ayah extraction", ayah_key, exc_info=True)

    return AyahMemoryRecord(
        ayah_key=ayah_key,
        surah=int(surah) if surah else 0,
        ayah=int(ayah) if ayah else 0,
        text=memory.content,
        edition_id=metadata.get("edition_id", ""),
        lang=metadata.get("lang", ""),
        url=metadata.get("url", ""),
        code=metadata.get("code", ""),
        author=metadata.get("author", ""),
        name=metadata.get("name", ""),
        relevance_score=memory.relevance_score,
        source_space=memory.source_space_name or "",
    )
