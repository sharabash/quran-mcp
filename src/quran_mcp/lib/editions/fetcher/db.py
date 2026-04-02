"""PostgreSQL fetch backend for edition content."""
from __future__ import annotations

import json
import logging

import asyncpg

from quran_mcp.lib.ayah_parsing import parse_ayah_key
from quran_mcp.lib.editions.errors import DataStoreError
from quran_mcp.lib.editions.types import EditionType

logger = logging.getLogger(__name__)


async def fetch_from_db(
    db_pool: asyncpg.Pool,
    edition_type: EditionType,
    edition_id: str,
    ayah_list: list[str],
) -> dict[str, tuple[str, dict]] | None:
    """Fetch edition content from PostgreSQL.

    Returns:
        dict mapping ayah_key -> (content, metadata_dict), or
        None if edition_content table doesn't exist or has zero rows for this edition.
    """
    try:
        # Step 1: Edition existence check.
        # Separate from ayah fetch so we can distinguish "edition not loaded"
        # (fallback to GoodMem) from "edition loaded but ayahs missing" (DataGap).
        exists = await db_pool.fetchval(
            "SELECT EXISTS ("
            "  SELECT 1 FROM quran_mcp.edition_content"
            "  WHERE edition_type = $1 AND edition_id = $2"
            "  LIMIT 1"
            ")",
            edition_type,
            edition_id,
        )
        if not exists:
            return None

        # Step 2: Ayah fetch (only if edition exists in DB).
        if edition_type == "tafsir":
            # Range-overlap query: find passages covering any requested ayah.
            surahs = []
            ayah_nums = []
            for ak in ayah_list:
                s, a = parse_ayah_key(ak)
                surahs.append(s)
                ayah_nums.append(a)
            rows = await db_pool.fetch(
                "SELECT DISTINCT ON (ayah_key)"
                "   ayah_key, content, metadata, surah, ayah_start, ayah_end"
                " FROM quran_mcp.edition_content,"
                "      unnest($3::smallint[], $4::smallint[])"
                "        AS req(req_surah, req_ayah)"
                " WHERE edition_type = $1 AND edition_id = $2"
                "   AND surah = req_surah"
                "   AND ayah_start <= req_ayah"
                "   AND ayah_end >= req_ayah",
                edition_type,
                edition_id,
                surahs,
                ayah_nums,
            )
        else:
            rows = await db_pool.fetch(
                "SELECT ayah_key, content, metadata"
                " FROM quran_mcp.edition_content"
                " WHERE edition_type = $1 AND edition_id = $2"
                " AND ayah_key = ANY($3::text[])",
                edition_type,
                edition_id,
                ayah_list,
            )
    except asyncpg.UndefinedTableError:
        logger.warning("DB fetch skipped (table missing), falling back")
        return None
    except Exception as e:
        raise DataStoreError(operation="fetch", cause=e) from e

    found: dict[str, tuple[str, dict]] = {}
    if edition_type == "tafsir":
        # Remap passage-range keys back to individual requested ayah keys.
        # A passage "2:8-9" must appear under both "2:8" and "2:9" if both
        # were requested, so _build_entries_from_found can look them up.
        for row in rows:
            raw_meta = row["metadata"]
            metadata = json.loads(raw_meta) if isinstance(raw_meta, str) else dict(raw_meta)
            content = row["content"]
            row_surah = row["surah"]
            row_start = row["ayah_start"]
            row_end = row["ayah_end"]
            for ak in ayah_list:
                s, a = parse_ayah_key(ak)
                if s == row_surah and row_start <= a <= row_end:
                    found[ak] = (content, metadata)
    else:
        for row in rows:
            raw_meta = row["metadata"]
            found[row["ayah_key"]] = (
                row["content"],
                json.loads(raw_meta) if isinstance(raw_meta, str) else dict(raw_meta),
            )

    return found
