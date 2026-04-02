"""Shared types and utilities for edition fetching."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from quran_mcp.lib.ayah_parsing import parse_ayah_key
from quran_mcp.lib.editions.errors import DataGap, UnresolvedEdition
from quran_mcp.lib.editions.types import EditionType

# Maximum ayahs per query to prevent memory exhaustion and GoodMem timeouts
# Per multi-agent review recommendation
MAX_AYAHS_PER_QUERY = 300


@dataclass
class EditionFetcherConfig:
    """Configuration for EditionFetcher."""

    edition_type: EditionType
    goodmem_space: str
    entry_factory: Callable[[str, str, dict], Any]
    chunk_multiplier: int = 2  # Default for unchunked content


@dataclass
class FetchResult:
    """Fetch result with graceful gap handling.

    Returns available data and reports gaps/unresolved editions
    instead of failing on partial misses.
    """

    data: dict[str, list[Any]]
    gaps: list[DataGap] | None = None
    unresolved: list[UnresolvedEdition] | None = None


def _validate_range_count(ayah_count: int) -> None:
    """Raise ValueError if ayah_count exceeds MAX_AYAHS_PER_QUERY."""
    if ayah_count > MAX_AYAHS_PER_QUERY:
        raise ValueError(
            f"Range exceeds maximum of {MAX_AYAHS_PER_QUERY} ayahs. "
            f"Requested {ayah_count}. Split into smaller ranges."
        )


def _build_ayah_conditions(ayah_list: list[str]) -> list[str]:
    """Build optimized ayah filter conditions.

    Groups consecutive ayahs in the same surah into range conditions.
    """
    if not ayah_list:
        return []

    parsed = [parse_ayah_key(ak) for ak in ayah_list]
    sorted_parsed = sorted(parsed)

    conditions = []
    i = 0
    while i < len(sorted_parsed):
        surah, start_ayah = sorted_parsed[i]
        end_ayah = start_ayah

        # Extend range while consecutive and same surah
        while (
            i + 1 < len(sorted_parsed)
            and sorted_parsed[i + 1][0] == surah
            and sorted_parsed[i + 1][1] == end_ayah + 1
        ):
            i += 1
            end_ayah = sorted_parsed[i][1]

        if start_ayah == end_ayah:
            condition = (
                f"CAST(val('$.surah') AS INT) = {surah} AND "
                f"CAST(val('$.ayah') AS INT) = {start_ayah}"
            )
        else:
            condition = (
                f"CAST(val('$.surah') AS INT) = {surah} AND "
                f"CAST(val('$.ayah') AS INT) >= {start_ayah} AND "
                f"CAST(val('$.ayah') AS INT) <= {end_ayah}"
            )

        conditions.append(condition)
        i += 1

    return conditions
