"""Metadata package for structural Quran lookups.

Exports the public metadata response models and query helpers used by the
metadata MCP tool. Keeping the package root explicit improves navigation and
reduces the need to chase implementation modules.
"""

from __future__ import annotations

from .query import (
    query_ayah_point,
    query_hizb_span,
    query_juz_span,
    query_manzil_span,
    query_page_span,
    query_ruku_span,
    query_surah_span,
)
from .types import (
    AyahPoint,
    AyahRange,
    NumericPoint,
    NumericRange,
    QueryType,
    QuranMetadataResponse,
    RevelationPlace,
    RukuPoint,
    SajdahInfo,
    SajdahType,
    SurahInfo,
)

__all__ = [
    "query_ayah_point",
    "query_hizb_span",
    "query_juz_span",
    "query_manzil_span",
    "query_page_span",
    "query_ruku_span",
    "query_surah_span",
    "AyahPoint",
    "AyahRange",
    "NumericPoint",
    "NumericRange",
    "QueryType",
    "QuranMetadataResponse",
    "RevelationPlace",
    "RukuPoint",
    "SajdahInfo",
    "SajdahType",
    "SurahInfo",
]
