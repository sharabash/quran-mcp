"""
Tafsir metadata and content helpers.

Modules
-------
fetch
    GoodMem-native tafsir retrieval utilities and summarization prompt builders.
search
    Semantic search for tafsir content via GoodMem.
"""

from .fetch import (
    TafsirEntry,
    fetch_tafsir,
    infer_summary_lang,
    resolve_tafsir_edition_ids,
)
from .search import (
    SearchTafsirResult,
    TafsirCitation,
    TafsirSearchResult,
    search_tafsir,
)

__all__ = [
    # Fetch module
    "TafsirEntry",
    "fetch_tafsir",
    "resolve_tafsir_edition_ids",
    "infer_summary_lang",
    # Search module
    "TafsirCitation",
    "TafsirSearchResult",
    "SearchTafsirResult",
    "search_tafsir",
]
