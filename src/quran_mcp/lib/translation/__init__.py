"""
Translation metadata and content helpers.

Modules
-------
fetch
    GoodMem-native translation retrieval utilities and summarization prompt builders.
search
    Semantic search for translation content via GoodMem.
"""

from .fetch import (
    TranslationEntry,
    fetch_translation,
    infer_summary_lang,
    resolve_translation_edition_ids,
)
from .search import (
    SearchTranslationResult,
    TranslationEditionInfo,
    TranslationResult,
    search_translation,
)

__all__ = [
    # Fetch module
    "TranslationEntry",
    "fetch_translation",
    "resolve_translation_edition_ids",
    "infer_summary_lang",
    # Search module
    "TranslationEditionInfo",
    "TranslationResult",
    "SearchTranslationResult",
    "search_translation",
]
