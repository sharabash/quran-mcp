"""Edition fetcher — retrieves Quran/tafsir/translation text from DB or GoodMem.

Tries PostgreSQL first (sub-millisecond), falls back to GoodMem if the edition
is not loaded locally. Returns partial results with gap info on misses.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from quran_mcp.lib.context.types import AppContext

from quran_mcp.lib.ayah_parsing import parse_ayah_input
from quran_mcp.lib.editions.errors import DataGap, DataNotFoundError, DataStoreError, UnresolvedEdition
from quran_mcp.lib.editions.registry import resolve_ids_with_unresolved

from .base import (
    EditionFetcherConfig,
    FetchResult,
    MAX_AYAHS_PER_QUERY,
    _validate_range_count as _do_validate_range_count,
)
from .goodmem import fetch_from_goodmem

__all__ = ["EditionFetcher", "EditionFetcherConfig", "FetchResult", "MAX_AYAHS_PER_QUERY"]

logger = logging.getLogger(__name__)


class EditionFetcher:
    """Fetches edition text from DB or GoodMem with automatic fallback."""

    __slots__ = ("config",)

    def __init__(self, config: EditionFetcherConfig) -> None:
        self.config = config

    async def fetch(
        self,
        ctx: AppContext,
        ayahs: str | list[str],
        editions: str | list[str],
    ) -> FetchResult:
        """Fetch edition text for ayahs, with graceful degradation on partial misses."""
        ayah_list = parse_ayah_input(ayahs)
        self._validate_range_count(len(ayah_list))

        resolve_result = resolve_ids_with_unresolved(self.config.edition_type, editions)
        edition_ids = resolve_result.resolved

        unresolved: list[UnresolvedEdition] | None = None
        if resolve_result.unresolved:
            unresolved = [
                UnresolvedEdition(
                    selector=sel,
                    edition_type=self.config.edition_type,
                    suggestion=f"Edition '{sel}' not found. Use list_editions(type='{self.config.edition_type}') to see available editions.",
                )
                for sel in resolve_result.unresolved
            ]
            logger.warning(
                f"Unresolved edition selectors for {self.config.edition_type}: {resolve_result.unresolved}"
            )

        if not edition_ids:
            return FetchResult(data={}, gaps=None, unresolved=unresolved)

        results: dict[str, list[Any]] = {}
        gaps: list[DataGap] = []

        fetch_outputs = await asyncio.gather(
            *(self._fetch_for_edition(ctx, ayah_list, eid) for eid in edition_ids)
        )
        for edition_id, (entries, gap) in zip(edition_ids, fetch_outputs):
            if entries:
                results[edition_id] = entries
            if gap:
                gaps.append(gap)

        if not results and gaps:
            # Aggregate all missing info into a single error
            all_missing = []
            for gap in gaps:
                all_missing.extend(gap.missing_ayahs)
            raise DataNotFoundError(
                edition_id=", ".join(g.edition_id for g in gaps),
                edition_type=self.config.edition_type,
                missing_ayahs=list(dict.fromkeys(all_missing)),
            )

        return FetchResult(
            data=results,
            gaps=gaps if gaps else None,
            unresolved=unresolved,
        )

    async def _fetch_for_edition(
        self,
        ctx: AppContext,
        ayah_list: list[str],
        edition_id: str,
    ) -> tuple[list[Any], DataGap | None]:
        """Fetch all ayahs for a single edition, returning partial results with gap info."""
        # 1. Try DB if pool available
        if ctx.db_pool is not None:
            from .db import fetch_from_db

            db_result = await fetch_from_db(
                ctx.db_pool, self.config.edition_type, edition_id, ayah_list
            )
            if db_result is not None:
                logger.info(
                    "DB fetch: %s/%s, %d entries",
                    self.config.edition_type, edition_id, len(db_result),
                )
                entries = self._build_entries_from_found(db_result, ayah_list)
                missing = [ak for ak in ayah_list if ak not in db_result]
                gap = DataGap(edition_id=edition_id, missing_ayahs=missing) if missing else None
                if gap:
                    logger.warning(
                        "DB fetch partial: %s/%s, found %d/%d ayahs, missing %d",
                        self.config.edition_type, edition_id,
                        len(db_result), len(ayah_list), len(missing),
                    )
                return entries, gap
            else:
                logger.warning(
                    "DB fetch skipped (no data): %s/%s, falling back",
                    self.config.edition_type, edition_id,
                )

        # 2. GoodMem fallback
        if ctx.goodmem_cli is not None:
            return await self._fetch_from_goodmem(ctx, ayah_list, edition_id)

        # 3. Neither
        raise DataStoreError(
            operation="fetch",
            cause=RuntimeError("No data backend available (neither DB nor GoodMem)"),
        )

    async def _fetch_from_goodmem(
        self,
        ctx: AppContext,
        ayah_list: list[str],
        edition_id: str,
    ) -> tuple[list[Any], DataGap | None]:
        """Fetch from GoodMem and build entries."""
        found, gap = await fetch_from_goodmem(
            ctx.goodmem_cli, self.config, ayah_list, edition_id
        )

        entries = self._build_entries_from_found(found, ayah_list)

        if entries:
            logger.info(
                "GoodMem fetch complete: %s/%s, %d entries",
                self.config.edition_type, edition_id, len(entries),
            )

        return entries, gap

    def _build_entries_from_found(
        self,
        found: dict[str, tuple[str, dict]],
        ayah_list: list[str],
    ) -> list[Any]:
        """Convert found dict to entry list via config.entry_factory."""
        entries = []
        for ayah_key in ayah_list:
            if ayah_key in found:
                text, metadata = found[ayah_key]
                entry = self.config.entry_factory(ayah_key, text, metadata)
                entries.append(entry)
        return entries

    def _validate_range_count(self, ayah_count: int) -> None:
        """Raise ValueError if ayah_count exceeds MAX_AYAHS_PER_QUERY."""
        _do_validate_range_count(ayah_count)
