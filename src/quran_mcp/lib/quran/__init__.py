"""
Quran text retrieval helpers.

Provides GoodMem-native retrieval for Quran scripture text.
No QF API fallback - all data must exist in GoodMem.
No summarization support (Quran text doesn't need AI summarization).

Modules
-------
fetch
    GoodMem-native retrieval for Quran text.
search
    Semantic search for Quran text via GoodMem.
"""
from __future__ import annotations

from .fetch import (
    QuranEntry,
    fetch_quran,
    resolve_quran_edition_ids,
)
from .search import (
    EditionInfo,
    SearchQuranResult,
    SearchResult,
    TranslationSearchResult,
    search_quran,
)

__all__ = [
    # Fetch module
    "QuranEntry",
    "fetch_quran",
    "resolve_quran_edition_ids",
    # Search module
    "EditionInfo",
    "SearchQuranResult",
    "SearchResult",
    "TranslationSearchResult",
    "search_quran",
]
