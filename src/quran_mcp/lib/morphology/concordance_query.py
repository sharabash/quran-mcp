"""SQL queries specific to the fetch_word_concordance tool.

The concordance uses a CTE-based approach with pre-aggregated GROUP BY
to avoid correlated subquery performance traps. Tiered scoring:
  exact (stem match) = 5, lemma match = 3, root match = 1.

Provides two query interfaces:
- query_concordance() — original, returns all rows (no SQL pagination)
- query_concordance_paginated() — SQL-level pagination with DENSE_RANK
"""

from __future__ import annotations

import asyncpg

from quran_mcp.lib.morphology.arabic_normalize import normalize_arabic


# ---------------------------------------------------------------------------
# Resolve root/lemma/stem IDs from a word
# ---------------------------------------------------------------------------

_WORD_LINGUISTIC_IDS_SQL = """
SELECT
    (SELECT dr.dict_root_id
     FROM quran_com.word_root wr
     JOIN quran_com.dict_root dr ON dr.dict_root_id = wr.dict_root_id
     WHERE wr.word_id = $1 ORDER BY wr.position LIMIT 1) AS dict_root_id,
    (SELECT dl.dict_lemma_id
     FROM quran_com.word_lemma wl
     JOIN quran_com.dict_lemma dl ON dl.dict_lemma_id = wl.dict_lemma_id
     WHERE wl.word_id = $1 ORDER BY wl.position LIMIT 1) AS dict_lemma_id,
    (SELECT ds.dict_stem_id
     FROM quran_com.word_stem ws
     JOIN quran_com.dict_stem ds ON ds.dict_stem_id = ws.dict_stem_id
     WHERE ws.word_id = $1 ORDER BY ws.position LIMIT 1) AS dict_stem_id
"""


async def get_word_linguistic_ids(
    pool: asyncpg.Pool, word_id: int
) -> dict[str, int | None]:
    """Get root/lemma/stem IDs for a word. Returns dict with nullable IDs."""
    row = await pool.fetchrow(_WORD_LINGUISTIC_IDS_SQL, word_id)
    return {
        "dict_root_id": row["dict_root_id"] if row else None,
        "dict_lemma_id": row["dict_lemma_id"] if row else None,
        "dict_stem_id": row["dict_stem_id"] if row else None,
    }


# ---------------------------------------------------------------------------
# Direct text lookups for root/lemma/stem
# ---------------------------------------------------------------------------

_RESOLVE_ROOT_ID_SQL = """
SELECT dict_root_id FROM quran_com.dict_root WHERE value = $1 LIMIT 1
"""

_RESOLVE_LEMMA_ID_SQL = """
SELECT dict_lemma_id FROM quran_com.dict_lemma
WHERE value = $1 OR clean = $1
ORDER BY dict_lemma_id LIMIT 1
"""

_RESOLVE_STEM_ID_SQL = """
SELECT dict_stem_id FROM quran_com.dict_stem
WHERE value = $1 OR clean = $1
ORDER BY dict_stem_id LIMIT 1
"""


async def _resolve_dict_id(
    pool: asyncpg.Pool, sql: str, id_column: str, text: str, label: str,
) -> int:
    """Resolve Arabic text → dictionary ID with normalization fallback."""
    row = await pool.fetchrow(sql, text)
    if row is None:
        normalized = normalize_arabic(text)
        if normalized != text:
            row = await pool.fetchrow(sql, normalized)
    if row is None:
        raise ValueError(f"{label} not found: {text!r}")
    return row[id_column]


async def resolve_root_id(pool: asyncpg.Pool, text: str) -> int:
    """Resolve root text → dict_root_id. Raises ValueError if not found.

    Handles both spaced ("ع ل م") and unspaced ("علم") root format.
    """
    return await _resolve_dict_id(
        pool, _RESOLVE_ROOT_ID_SQL, "dict_root_id", text.replace(" ", ""), "Root",
    )


async def resolve_lemma_id(pool: asyncpg.Pool, text: str) -> int:
    """Resolve lemma text → dict_lemma_id. Raises ValueError if not found."""
    return await _resolve_dict_id(
        pool, _RESOLVE_LEMMA_ID_SQL, "dict_lemma_id", text, "Lemma",
    )


async def resolve_stem_id(pool: asyncpg.Pool, text: str) -> int:
    """Resolve stem text → dict_stem_id. Raises ValueError if not found."""
    return await _resolve_dict_id(
        pool, _RESOLVE_STEM_ID_SQL, "dict_stem_id", text, "Stem",
    )


# ---------------------------------------------------------------------------
# Core concordance query — tiered scoring with pre-aggregated GROUP BY
# (original interface — returns ALL rows, no pagination)
# ---------------------------------------------------------------------------

_CONCORDANCE_ALL_SQL = """
WITH matched_words AS (
    SELECT w.word_id, w.verse_id, w.position,
           w.text_uthmani, w.en_transliteration,
           CASE
               WHEN ws.word_id IS NOT NULL THEN 'exact'
               WHEN wl.word_id IS NOT NULL THEN 'lemma'
               ELSE 'root'
           END AS match_level,
           CASE
               WHEN ws.word_id IS NOT NULL THEN 5
               WHEN wl.word_id IS NOT NULL THEN 3
               ELSE 1
           END AS word_score
    FROM quran_com.word_root wr
    JOIN quran_com.word w ON w.word_id = wr.word_id
    LEFT JOIN quran_com.word_lemma wl
        ON wl.word_id = w.word_id AND wl.dict_lemma_id = $2
    LEFT JOIN quran_com.word_stem ws
        ON ws.word_id = w.word_id AND ws.dict_stem_id = $3
    WHERE wr.dict_root_id = $1
)
SELECT mw.verse_id, mw.word_id, mw.position,
       mw.text_uthmani, mw.en_transliteration, mw.match_level,
       v.verse_key, v.text_uthmani AS verse_text,
       SUM(mw.word_score) OVER (PARTITION BY mw.verse_id) AS verse_score,
       COUNT(*) OVER (PARTITION BY mw.verse_id) AS match_count
FROM matched_words mw
JOIN quran_com.verse v ON v.verse_id = mw.verse_id
ORDER BY verse_score DESC, mw.verse_id ASC, mw.position ASC
"""

_CONCORDANCE_LEMMA_SQL = """
WITH matched AS (
    SELECT w.word_id, w.verse_id, w.position,
           w.text_uthmani, w.en_transliteration,
           CASE
               WHEN ws.word_id IS NOT NULL THEN 'exact'
               ELSE 'lemma'
           END AS match_level,
           CASE WHEN ws.word_id IS NOT NULL THEN 5 ELSE 3 END AS word_score
    FROM quran_com.word_lemma wl
    JOIN quran_com.word w ON w.word_id = wl.word_id
    LEFT JOIN quran_com.word_stem ws
        ON ws.word_id = w.word_id AND ws.dict_stem_id = $2
    WHERE wl.dict_lemma_id = $1
)
SELECT m.verse_id, m.word_id, m.position,
       m.text_uthmani, m.en_transliteration, m.match_level,
       v.verse_key, v.text_uthmani AS verse_text,
       SUM(m.word_score) OVER (PARTITION BY m.verse_id) AS verse_score,
       COUNT(*) OVER (PARTITION BY m.verse_id) AS match_count
FROM matched m
JOIN quran_com.verse v ON v.verse_id = m.verse_id
ORDER BY verse_score DESC, m.verse_id ASC, m.position ASC
"""

_CONCORDANCE_ROOT_SQL = """
SELECT w.word_id, w.verse_id, w.position,
       w.text_uthmani, w.en_transliteration,
       'root' AS match_level,
       v.verse_key, v.text_uthmani AS verse_text
FROM quran_com.word_root wr
JOIN quran_com.word w ON w.word_id = wr.word_id
JOIN quran_com.verse v ON v.verse_id = w.verse_id
WHERE wr.dict_root_id = $1
ORDER BY w.verse_id ASC, w.position ASC
"""

_CONCORDANCE_STEM_SQL = """
SELECT w.word_id, w.verse_id, w.position,
       w.text_uthmani, w.en_transliteration,
       'exact' AS match_level,
       v.verse_key, v.text_uthmani AS verse_text
FROM quran_com.word_stem ws
JOIN quran_com.word w ON w.word_id = ws.word_id
JOIN quran_com.verse v ON v.verse_id = w.verse_id
WHERE ws.dict_stem_id = $1
ORDER BY w.verse_id ASC, w.position ASC
"""


async def query_concordance(
    pool: asyncpg.Pool,
    match_by: str,
    dict_root_id: int | None,
    dict_lemma_id: int | None,
    dict_stem_id: int | None,
) -> list[asyncpg.Record]:
    """Execute the appropriate concordance query based on match_by level.

    Returns raw rows — caller handles pagination and grouping.
    """
    if match_by == "all":
        if dict_root_id is None:
            raise ValueError("match_by='all' requires a root ID")
        return await pool.fetch(
            _CONCORDANCE_ALL_SQL,
            dict_root_id,
            dict_lemma_id or 0,  # 0 won't match any real lemma
            dict_stem_id or 0,
        )
    elif match_by == "lemma":
        if dict_lemma_id is None:
            raise ValueError("match_by='lemma' requires a lemma ID")
        return await pool.fetch(
            _CONCORDANCE_LEMMA_SQL,
            dict_lemma_id,
            dict_stem_id or 0,
        )
    elif match_by == "root":
        if dict_root_id is None:
            raise ValueError("match_by='root' requires a root ID")
        return await pool.fetch(_CONCORDANCE_ROOT_SQL, dict_root_id)
    elif match_by == "stem":
        if dict_stem_id is None:
            raise ValueError("match_by='stem' requires a stem ID")
        return await pool.fetch(_CONCORDANCE_STEM_SQL, dict_stem_id)
    else:
        raise ValueError(f"Invalid match_by: {match_by!r}")


# ---------------------------------------------------------------------------
# Paginated concordance queries — SQL-level DENSE_RANK pagination
# ---------------------------------------------------------------------------

# match_by='all': tiered scoring with DENSE_RANK verse pagination
_PAGINATED_ALL_VERSE_SQL = """
WITH matched_words AS (
    SELECT w.word_id, w.verse_id, w.position,
           w.text_uthmani, w.en_transliteration,
           CASE
               WHEN ws.word_id IS NOT NULL THEN 'exact'
               WHEN wl.word_id IS NOT NULL THEN 'lemma'
               ELSE 'root'
           END AS match_level,
           CASE
               WHEN ws.word_id IS NOT NULL THEN 5
               WHEN wl.word_id IS NOT NULL THEN 3
               ELSE 1
           END AS word_score
    FROM quran_com.word_root wr
    JOIN quran_com.word w ON w.word_id = wr.word_id
    LEFT JOIN quran_com.word_lemma wl
        ON wl.word_id = w.word_id AND wl.dict_lemma_id = $2
    LEFT JOIN quran_com.word_stem ws
        ON ws.word_id = w.word_id AND ws.dict_stem_id = $3
    WHERE wr.dict_root_id = $1
),
verse_scores AS (
    SELECT verse_id, SUM(word_score) AS verse_score, COUNT(*) AS match_count
    FROM matched_words GROUP BY verse_id
),
verse_ranked AS (
    SELECT *, DENSE_RANK() OVER (ORDER BY verse_score DESC, verse_id ASC) AS verse_rank
    FROM verse_scores
),
totals AS (
    SELECT COUNT(*) AS total_verses,
           (SELECT COUNT(*) FROM matched_words) AS total_words
    FROM verse_ranked
)
SELECT mw.verse_id, mw.word_id, mw.position,
       mw.text_uthmani, mw.en_transliteration, mw.match_level, mw.word_score,
       v.verse_key, v.text_uthmani AS verse_text,
       vr.verse_score, vr.match_count,
       t.total_verses::int, t.total_words::int
FROM verse_ranked vr
CROSS JOIN totals t
JOIN matched_words mw ON mw.verse_id = vr.verse_id
JOIN quran_com.verse v ON v.verse_id = vr.verse_id
WHERE vr.verse_rank > $4 AND vr.verse_rank <= $4 + $5
ORDER BY vr.verse_score DESC, vr.verse_id ASC, mw.position ASC
"""

# match_by='all': word-level pagination
_PAGINATED_ALL_WORD_SQL = """
WITH matched_words AS (
    SELECT w.word_id, w.verse_id, w.position,
           w.text_uthmani, w.en_transliteration,
           CASE
               WHEN ws.word_id IS NOT NULL THEN 'exact'
               WHEN wl.word_id IS NOT NULL THEN 'lemma'
               ELSE 'root'
           END AS match_level,
           CASE
               WHEN ws.word_id IS NOT NULL THEN 5
               WHEN wl.word_id IS NOT NULL THEN 3
               ELSE 1
           END AS word_score
    FROM quran_com.word_root wr
    JOIN quran_com.word w ON w.word_id = wr.word_id
    LEFT JOIN quran_com.word_lemma wl
        ON wl.word_id = w.word_id AND wl.dict_lemma_id = $2
    LEFT JOIN quran_com.word_stem ws
        ON ws.word_id = w.word_id AND ws.dict_stem_id = $3
    WHERE wr.dict_root_id = $1
)
SELECT mw.word_id, mw.verse_id, mw.position,
       mw.text_uthmani, mw.en_transliteration, mw.match_level, mw.word_score,
       v.verse_key, v.text_uthmani AS verse_text,
       SUM(mw.word_score) OVER (PARTITION BY mw.verse_id) AS verse_score,
       COUNT(*) OVER () AS total_words,
       (SELECT COUNT(DISTINCT mw2.verse_id) FROM matched_words mw2) AS total_verses
FROM matched_words mw
JOIN quran_com.verse v ON v.verse_id = mw.verse_id
ORDER BY mw.word_score DESC, mw.verse_id ASC, mw.position ASC
LIMIT $5 OFFSET $4
"""

# match_by='lemma': verse pagination
_PAGINATED_LEMMA_VERSE_SQL = """
WITH matched AS (
    SELECT w.word_id, w.verse_id, w.position,
           w.text_uthmani, w.en_transliteration,
           CASE
               WHEN ws.word_id IS NOT NULL THEN 'exact'
               ELSE 'lemma'
           END AS match_level,
           CASE WHEN ws.word_id IS NOT NULL THEN 5 ELSE 3 END AS word_score
    FROM quran_com.word_lemma wl
    JOIN quran_com.word w ON w.word_id = wl.word_id
    LEFT JOIN quran_com.word_stem ws
        ON ws.word_id = w.word_id AND ws.dict_stem_id = $2
    WHERE wl.dict_lemma_id = $1
),
verse_scores AS (
    SELECT verse_id, SUM(word_score) AS verse_score, COUNT(*) AS match_count
    FROM matched GROUP BY verse_id
),
verse_ranked AS (
    SELECT *, DENSE_RANK() OVER (ORDER BY verse_score DESC, verse_id ASC) AS verse_rank
    FROM verse_scores
),
totals AS (
    SELECT COUNT(*) AS total_verses,
           (SELECT COUNT(*) FROM matched) AS total_words
    FROM verse_ranked
)
SELECT m.verse_id, m.word_id, m.position,
       m.text_uthmani, m.en_transliteration, m.match_level, m.word_score,
       v.verse_key, v.text_uthmani AS verse_text,
       vr.verse_score, vr.match_count,
       t.total_verses::int, t.total_words::int
FROM verse_ranked vr
CROSS JOIN totals t
JOIN matched m ON m.verse_id = vr.verse_id
JOIN quran_com.verse v ON v.verse_id = vr.verse_id
WHERE vr.verse_rank > $3 AND vr.verse_rank <= $3 + $4
ORDER BY vr.verse_score DESC, vr.verse_id ASC, m.position ASC
"""

# match_by='lemma': word-level pagination
_PAGINATED_LEMMA_WORD_SQL = """
WITH matched AS (
    SELECT w.word_id, w.verse_id, w.position,
           w.text_uthmani, w.en_transliteration,
           CASE
               WHEN ws.word_id IS NOT NULL THEN 'exact'
               ELSE 'lemma'
           END AS match_level,
           CASE WHEN ws.word_id IS NOT NULL THEN 5 ELSE 3 END AS word_score
    FROM quran_com.word_lemma wl
    JOIN quran_com.word w ON w.word_id = wl.word_id
    LEFT JOIN quran_com.word_stem ws
        ON ws.word_id = w.word_id AND ws.dict_stem_id = $2
    WHERE wl.dict_lemma_id = $1
)
SELECT m.word_id, m.verse_id, m.position,
       m.text_uthmani, m.en_transliteration, m.match_level, m.word_score,
       v.verse_key, v.text_uthmani AS verse_text,
       SUM(m.word_score) OVER (PARTITION BY m.verse_id) AS verse_score,
       COUNT(*) OVER () AS total_words,
       (SELECT COUNT(DISTINCT m2.verse_id) FROM matched m2) AS total_verses
FROM matched m
JOIN quran_com.verse v ON v.verse_id = m.verse_id
ORDER BY m.word_score DESC, m.verse_id ASC, m.position ASC
LIMIT $4 OFFSET $3
"""

# match_by='root': verse pagination (all words score 1, verse_score = count)
_PAGINATED_ROOT_VERSE_SQL = """
WITH matched_words AS (
    SELECT w.word_id, w.verse_id, w.position,
           w.text_uthmani, w.en_transliteration,
           'root' AS match_level,
           1 AS word_score
    FROM quran_com.word_root wr
    JOIN quran_com.word w ON w.word_id = wr.word_id
    WHERE wr.dict_root_id = $1
),
verse_scores AS (
    SELECT verse_id, COUNT(*) AS verse_score, COUNT(*) AS match_count
    FROM matched_words GROUP BY verse_id
),
verse_ranked AS (
    SELECT *, DENSE_RANK() OVER (ORDER BY verse_score DESC, verse_id ASC) AS verse_rank
    FROM verse_scores
),
totals AS (
    SELECT COUNT(*) AS total_verses,
           (SELECT COUNT(*) FROM matched_words) AS total_words
    FROM verse_ranked
)
SELECT mw.verse_id, mw.word_id, mw.position,
       mw.text_uthmani, mw.en_transliteration, mw.match_level, mw.word_score,
       v.verse_key, v.text_uthmani AS verse_text,
       vr.verse_score, vr.match_count,
       t.total_verses::int, t.total_words::int
FROM verse_ranked vr
CROSS JOIN totals t
JOIN matched_words mw ON mw.verse_id = vr.verse_id
JOIN quran_com.verse v ON v.verse_id = vr.verse_id
WHERE vr.verse_rank > $2 AND vr.verse_rank <= $2 + $3
ORDER BY vr.verse_score DESC, vr.verse_id ASC, mw.position ASC
"""

# match_by='root': word-level pagination
_PAGINATED_ROOT_WORD_SQL = """
WITH matched_words AS (
    SELECT w.word_id, w.verse_id, w.position,
           w.text_uthmani, w.en_transliteration,
           'root' AS match_level,
           1 AS word_score
    FROM quran_com.word_root wr
    JOIN quran_com.word w ON w.word_id = wr.word_id
    WHERE wr.dict_root_id = $1
)
SELECT mw.word_id, mw.verse_id, mw.position,
       mw.text_uthmani, mw.en_transliteration, mw.match_level, mw.word_score,
       v.verse_key, v.text_uthmani AS verse_text,
       1 AS verse_score,
       COUNT(*) OVER () AS total_words,
       (SELECT COUNT(DISTINCT mw2.verse_id) FROM matched_words mw2) AS total_verses
FROM matched_words mw
JOIN quran_com.verse v ON v.verse_id = mw.verse_id
ORDER BY mw.verse_id ASC, mw.position ASC
LIMIT $3 OFFSET $2
"""

# match_by='stem': verse pagination (all words score 5)
_PAGINATED_STEM_VERSE_SQL = """
WITH matched_words AS (
    SELECT w.word_id, w.verse_id, w.position,
           w.text_uthmani, w.en_transliteration,
           'exact' AS match_level,
           5 AS word_score
    FROM quran_com.word_stem ws
    JOIN quran_com.word w ON w.word_id = ws.word_id
    WHERE ws.dict_stem_id = $1
),
verse_scores AS (
    SELECT verse_id, SUM(word_score) AS verse_score, COUNT(*) AS match_count
    FROM matched_words GROUP BY verse_id
),
verse_ranked AS (
    SELECT *, DENSE_RANK() OVER (ORDER BY verse_score DESC, verse_id ASC) AS verse_rank
    FROM verse_scores
),
totals AS (
    SELECT COUNT(*) AS total_verses,
           (SELECT COUNT(*) FROM matched_words) AS total_words
    FROM verse_ranked
)
SELECT mw.verse_id, mw.word_id, mw.position,
       mw.text_uthmani, mw.en_transliteration, mw.match_level, mw.word_score,
       v.verse_key, v.text_uthmani AS verse_text,
       vr.verse_score, vr.match_count,
       t.total_verses::int, t.total_words::int
FROM verse_ranked vr
CROSS JOIN totals t
JOIN matched_words mw ON mw.verse_id = vr.verse_id
JOIN quran_com.verse v ON v.verse_id = vr.verse_id
WHERE vr.verse_rank > $2 AND vr.verse_rank <= $2 + $3
ORDER BY vr.verse_score DESC, vr.verse_id ASC, mw.position ASC
"""

# match_by='stem': word-level pagination
_PAGINATED_STEM_WORD_SQL = """
WITH matched_words AS (
    SELECT w.word_id, w.verse_id, w.position,
           w.text_uthmani, w.en_transliteration,
           'exact' AS match_level,
           5 AS word_score
    FROM quran_com.word_stem ws
    JOIN quran_com.word w ON w.word_id = ws.word_id
    WHERE ws.dict_stem_id = $1
)
SELECT mw.word_id, mw.verse_id, mw.position,
       mw.text_uthmani, mw.en_transliteration, mw.match_level, mw.word_score,
       v.verse_key, v.text_uthmani AS verse_text,
       5 AS verse_score,
       COUNT(*) OVER () AS total_words,
       (SELECT COUNT(DISTINCT mw2.verse_id) FROM matched_words mw2) AS total_verses
FROM matched_words mw
JOIN quran_com.verse v ON v.verse_id = mw.verse_id
ORDER BY mw.verse_id ASC, mw.position ASC
LIMIT $3 OFFSET $2
"""


async def query_concordance_paginated(
    pool: asyncpg.Pool,
    match_by: str,
    dict_root_id: int | None,
    dict_lemma_id: int | None,
    dict_stem_id: int | None,
    group_by: str = "verse",
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[asyncpg.Record], int, int]:
    """Execute paginated concordance query.

    Returns (rows, total_verses, total_words).
    Pagination is done in SQL via DENSE_RANK for verse mode, LIMIT/OFFSET for word mode.
    """
    offset = (page - 1) * page_size

    if match_by == "all":
        if dict_root_id is None:
            raise ValueError("match_by='all' requires a root ID")
        if group_by == "word":
            rows = await pool.fetch(
                _PAGINATED_ALL_WORD_SQL,
                dict_root_id, dict_lemma_id or 0, dict_stem_id or 0,
                offset, page_size,
            )
        else:
            rows = await pool.fetch(
                _PAGINATED_ALL_VERSE_SQL,
                dict_root_id, dict_lemma_id or 0, dict_stem_id or 0,
                offset, page_size,
            )
    elif match_by == "lemma":
        if dict_lemma_id is None:
            raise ValueError("match_by='lemma' requires a lemma ID")
        if group_by == "word":
            rows = await pool.fetch(
                _PAGINATED_LEMMA_WORD_SQL,
                dict_lemma_id, dict_stem_id or 0,
                offset, page_size,
            )
        else:
            rows = await pool.fetch(
                _PAGINATED_LEMMA_VERSE_SQL,
                dict_lemma_id, dict_stem_id or 0,
                offset, page_size,
            )
    elif match_by == "root":
        if dict_root_id is None:
            raise ValueError("match_by='root' requires a root ID")
        if group_by == "word":
            rows = await pool.fetch(
                _PAGINATED_ROOT_WORD_SQL,
                dict_root_id, offset, page_size,
            )
        else:
            rows = await pool.fetch(
                _PAGINATED_ROOT_VERSE_SQL,
                dict_root_id, offset, page_size,
            )
    elif match_by == "stem":
        if dict_stem_id is None:
            raise ValueError("match_by='stem' requires a stem ID")
        if group_by == "word":
            rows = await pool.fetch(
                _PAGINATED_STEM_WORD_SQL,
                dict_stem_id, offset, page_size,
            )
        else:
            rows = await pool.fetch(
                _PAGINATED_STEM_VERSE_SQL,
                dict_stem_id, offset, page_size,
            )
    else:
        raise ValueError(f"Invalid match_by: {match_by!r}")

    if not rows:
        return [], 0, 0

    total_verses = int(rows[0]["total_verses"])
    total_words = int(rows[0]["total_words"])
    return list(rows), total_verses, total_words
