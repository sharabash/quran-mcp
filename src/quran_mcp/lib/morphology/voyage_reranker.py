"""Voyage AI reranker for concordance results.

Standalone module — uses httpx directly, no AppContext/GoodMem dependency.
On any Voyage error, callers should fall back to tiered scoring (not a hard error).
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    import asyncpg

logger = logging.getLogger(__name__)

VOYAGE_RERANK_URL = "https://api.voyageai.com/v1/rerank"


async def rerank_verses(
    query_text: str,
    documents: list[str],
    api_key: str,
    model: str = "rerank-2",
    timeout: float = 10.0,
) -> list[dict[str, Any]]:
    """Call Voyage rerank API and return results sorted by relevance_score.

    Args:
        query_text: The source verse/word text to rank against.
        documents: List of candidate verse texts to rerank.
        api_key: Voyage API key.
        model: Voyage model name (default: rerank-2).
        timeout: HTTP timeout in seconds.

    Returns:
        List of dicts with 'index' (original position) and 'relevance_score'.
        Sorted by relevance_score descending.

    Raises:
        VoyageRerankerError: On any API or network error.
    """
    if not api_key:
        raise VoyageRerankerError("Voyage API key not configured")
    if not documents:
        return []

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            VOYAGE_RERANK_URL,
            json={
                "query": query_text,
                "documents": documents,
                "model": model,
            },
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        if response.status_code != 200:
            raise VoyageRerankerError(
                f"Voyage API returned {response.status_code}: {response.text[:200]}"
            )
        data = response.json()

    results = data.get("data", [])
    # Sort by relevance_score descending
    results.sort(key=lambda r: r.get("relevance_score", 0), reverse=True)
    return results


class VoyageRerankerError(Exception):
    """Raised when Voyage reranking fails. Callers should fall back gracefully."""


# ---------------------------------------------------------------------------
# DB helper: fetch English word glosses for verse keys
# ---------------------------------------------------------------------------

_VERSE_GLOSSES_SQL = """
SELECT v.verse_key,
       string_agg(wt.value, ' ' ORDER BY w.position) AS gloss
FROM quran_com.verse v
JOIN quran_com.word w ON w.verse_id = v.verse_id AND w.char_type_name = 'word'
JOIN quran_com.word_translation wt ON wt.word_id = w.word_id AND wt.language_code = 'en'
WHERE v.verse_key = ANY($1)
GROUP BY v.verse_key
"""


async def fetch_verse_glosses(
    pool: "asyncpg.Pool",
    verse_keys: list[str],
) -> dict[str, str]:
    """Fetch concatenated English word glosses for a list of verse keys.

    Returns dict mapping verse_key → gloss text.
    Verses without word translations are omitted from the result.
    """
    rows = await pool.fetch(_VERSE_GLOSSES_SQL, verse_keys)
    return {r["verse_key"]: r["gloss"] for r in rows}
