"""GoodMem fetch backend for edition content."""
from __future__ import annotations

import logging
from typing import Any

from quran_mcp.lib.editions.errors import DataGap, DataStoreError
from quran_mcp.lib.editions.fetcher.base import EditionFetcherConfig, _build_ayah_conditions
from quran_mcp.lib.goodmem.filters import build_filter_expression, parse_filter_string

logger = logging.getLogger(__name__)


async def fetch_from_goodmem(
    goodmem_cli: Any,
    config: EditionFetcherConfig,
    ayah_list: list[str],
    edition_id: str,
) -> tuple[dict[str, tuple[str, dict]], DataGap | None]:
    """Fetch edition content from GoodMem.

    Returns dict mapping ayah_key -> (content, metadata), plus optional DataGap.
    """
    filter_expr = _build_edition_filter(config, edition_id, ayah_list)

    logger.debug(
        f"GoodMem fetch: {config.edition_type}/{edition_id}, "
        f"{len(ayah_list)} ayahs, filter={filter_expr[:100]}..."
    )

    try:
        # Limit accounts for chunking: streaming API returns chunks, not memories,
        # so chunked content (like tafsir) needs a higher limit to ensure all
        # requested memories are found even when each memory has many chunks.
        limit = len(ayah_list) * config.chunk_multiplier + 10
        results = await goodmem_cli.search_memories(
            query="content",  # Required non-empty query, filter does the work
            space_names=[config.goodmem_space],
            limit=limit,
            filter_expr=filter_expr,
        )
    except Exception as e:
        raise DataStoreError(operation="search", cause=e) from e

    found: dict[str, tuple[str, dict]] = {}
    for memory in results:
        ayah_key = memory.metadata.get("ayah_key")
        if ayah_key and ayah_key in ayah_list:
            if ayah_key not in found:
                found[ayah_key] = (memory.content, memory.metadata or {})

    missing = [ak for ak in ayah_list if ak not in found]
    gap = DataGap(edition_id=edition_id, missing_ayahs=missing) if missing else None

    if gap:
        logger.warning(
            f"GoodMem fetch partial: {config.edition_type}/{edition_id}, "
            f"found {len(found)}/{len(ayah_list)} ayahs, missing {len(missing)}"
        )

    return found, gap


def _build_edition_filter(
    config: EditionFetcherConfig,
    edition_id: str,
    ayah_list: list[str],
) -> str:
    """Build GoodMem filter expression for edition and ayahs."""
    base_terms = [
        parse_filter_string(f"edition_type={config.edition_type}"),
        parse_filter_string(f"edition_id={edition_id}"),
    ]
    base_filter = build_filter_expression(base_terms)

    ayah_conditions = _build_ayah_conditions(ayah_list)

    if not ayah_conditions:
        return base_filter

    ayah_filter = " OR ".join(f"({c})" for c in ayah_conditions)
    return f"({base_filter}) AND ({ayah_filter})"
