"""SQL queries specific to the fetch_word_paradigm tool.

Paradigm queries that are not shared with other morphology tools.
Shared queries (resolve_verse_by_key, get_words_for_verse, etc.)
live in query.py.
"""

from __future__ import annotations

import asyncpg

from quran_mcp.lib.morphology.arabic_normalize import normalize_arabic


# ---------------------------------------------------------------------------
# Lemma / root resolution for a word
# ---------------------------------------------------------------------------

_LEMMA_FOR_WORD_SQL = """
SELECT dl.dict_lemma_id, dl.value AS lemma_value, dl.clean
FROM quran_com.word_lemma wl
JOIN quran_com.dict_lemma dl ON dl.dict_lemma_id = wl.dict_lemma_id
WHERE wl.word_id = $1
ORDER BY wl.position
LIMIT 1
"""

_ROOT_FOR_WORD_SQL = """
SELECT dr.dict_root_id, dr.value AS root_value
FROM quran_com.word_root wr
JOIN quran_com.dict_root dr ON dr.dict_root_id = wr.dict_root_id
WHERE wr.word_id = $1
ORDER BY wr.position
LIMIT 1
"""


async def resolve_lemma_for_word(
    pool: asyncpg.Pool, word_id: int
) -> asyncpg.Record | None:
    """Get the primary lemma for a word. Returns None if no lemma."""
    return await pool.fetchrow(_LEMMA_FOR_WORD_SQL, word_id)


async def resolve_root_for_word(
    pool: asyncpg.Pool, word_id: int
) -> asyncpg.Record | None:
    """Get the primary root for a word. Returns None if no root."""
    return await pool.fetchrow(_ROOT_FOR_WORD_SQL, word_id)


# ---------------------------------------------------------------------------
# Word segments (for paradigm availability check)
# ---------------------------------------------------------------------------

_WORD_SEGMENTS_SQL = """
SELECT part_of_speech_key, part_of_speech_name, pos_tags, verb_form
FROM quran_com.morph_word_segment
WHERE word_id = $1 AND (hidden IS NULL OR hidden = false)
ORDER BY position
"""


async def get_word_visible_segments(
    pool: asyncpg.Pool, word_id: int
) -> list[asyncpg.Record]:
    """Fetch all visible morph segments for a word (ordered by position).

    Returns all segments so the caller can check if *any* is a verb,
    rather than assuming the first segment determines the POS
    (which fails for prefixed verbs like wa-qala).
    """
    return await pool.fetch(_WORD_SEGMENTS_SQL, word_id)


# ---------------------------------------------------------------------------
# Lemma resolution by text
# ---------------------------------------------------------------------------

_RESOLVE_LEMMA_SQL = """
SELECT dict_lemma_id, value, clean, gloss_en
FROM quran_com.dict_lemma
WHERE value = $1 OR clean = $1
ORDER BY dict_lemma_id
LIMIT 1
"""


async def resolve_lemma_by_text(
    pool: asyncpg.Pool, lemma_text: str
) -> asyncpg.Record:
    """Resolve lemma text to a dict_lemma record. Tries exact then normalized."""
    row = await pool.fetchrow(_RESOLVE_LEMMA_SQL, lemma_text)
    if row is not None:
        return row

    normalized = normalize_arabic(lemma_text)
    if normalized != lemma_text:
        row = await pool.fetchrow(_RESOLVE_LEMMA_SQL, normalized)
        if row is not None:
            return row

    raise ValueError(f"Lemma not found: {lemma_text!r}")


# ---------------------------------------------------------------------------
# Root resolution by text (or by lemma)
# ---------------------------------------------------------------------------

_RESOLVE_ROOT_SQL = """
SELECT dict_root_id, value AS root_value
FROM quran_com.dict_root
WHERE value = $1
LIMIT 1
"""

_ROOT_FROM_LEMMA_SQL = """
SELECT DISTINCT dr.dict_root_id, dr.value AS root_value
FROM quran_com.word_lemma wl
JOIN quran_com.word_root wr ON wr.word_id = wl.word_id
JOIN quran_com.dict_root dr ON dr.dict_root_id = wr.dict_root_id
WHERE wl.dict_lemma_id = $1
LIMIT 1
"""


async def resolve_root_by_text(
    pool: asyncpg.Pool,
    root_text: str | None = None,
    dict_lemma_id: int | None = None,
) -> asyncpg.Record | None:
    """Resolve root text to dict_root record.

    If root_text is given, look up directly.
    If dict_lemma_id is given, find root via word_root JOIN.
    Accepts both spaced ("ع ل م") and unspaced ("علم") root formats.
    """
    if root_text:
        # Strip spaces so spaced roots like "ع ل م" match DB value "علم"
        root_text = root_text.replace(" ", "")
        row = await pool.fetchrow(_RESOLVE_ROOT_SQL, root_text)
        if row is not None:
            return row

        # Try normalized
        normalized = normalize_arabic(root_text)
        if normalized != root_text:
            row = await pool.fetchrow(_RESOLVE_ROOT_SQL, normalized)
            if row is not None:
                return row

        raise ValueError(f"Root not found: {root_text!r}")

    if dict_lemma_id is not None:
        return await pool.fetchrow(_ROOT_FROM_LEMMA_SQL, dict_lemma_id)

    return None


# ---------------------------------------------------------------------------
# Stems for a lemma (the actual paradigm data)
# ---------------------------------------------------------------------------

_STEMS_FOR_LEMMA_SQL = """
SELECT DISTINCT ON (ds.dict_stem_id)
    ds.dict_stem_id, ds.value, ds.clean,
    mws.pos_tags, mws.grammar_term_desc_english,
    (SELECT COUNT(*) FROM quran_com.word_stem ws2
     WHERE ws2.dict_stem_id = ds.dict_stem_id) AS word_count
FROM quran_com.word_lemma wl
JOIN quran_com.word_stem ws ON ws.word_id = wl.word_id
JOIN quran_com.dict_stem ds ON ds.dict_stem_id = ws.dict_stem_id
LEFT JOIN quran_com.morph_word_segment mws
    ON mws.word_id = wl.word_id AND mws.part_of_speech_key = 'V'
    AND (mws.hidden IS NULL OR mws.hidden = false)
WHERE wl.dict_lemma_id = $1
ORDER BY ds.dict_stem_id, mws.position
"""


async def get_stems_for_lemma(
    pool: asyncpg.Pool, dict_lemma_id: int
) -> list[asyncpg.Record]:
    """Fetch all distinct stems under a lemma with aspect tags and counts."""
    return await pool.fetch(_STEMS_FOR_LEMMA_SQL, dict_lemma_id)


# ---------------------------------------------------------------------------
# Candidate lemmas for a root
# ---------------------------------------------------------------------------

_CANDIDATE_LEMMAS_SQL = """
SELECT dl.dict_lemma_id, dl.value, dl.clean, dl.gloss_en,
       MAX(mws.verb_form) AS verb_form,
       COUNT(DISTINCT wr.word_id) AS frequency
FROM quran_com.word_root wr
JOIN quran_com.word_lemma wl ON wl.word_id = wr.word_id
JOIN quran_com.dict_lemma dl ON dl.dict_lemma_id = wl.dict_lemma_id
LEFT JOIN quran_com.morph_word_segment mws
    ON mws.word_id = wr.word_id AND mws.part_of_speech_key = 'V'
    AND (mws.hidden IS NULL OR mws.hidden = false)
WHERE wr.dict_root_id = $1
GROUP BY dl.dict_lemma_id, dl.value, dl.clean, dl.gloss_en
ORDER BY frequency DESC
"""


async def get_candidate_lemmas(
    pool: asyncpg.Pool, dict_root_id: int
) -> list[asyncpg.Record]:
    """Fetch all lemmas under a root with frequency and verb form."""
    return await pool.fetch(_CANDIDATE_LEMMAS_SQL, dict_root_id)


# ---------------------------------------------------------------------------
# Gloss fallback (when gloss_en is NULL)
# ---------------------------------------------------------------------------

_GLOSS_FALLBACK_SQL = """
SELECT wt.value, COUNT(*) AS freq
FROM quran_com.word_lemma wl
JOIN quran_com.word_translation wt ON wt.word_id = wl.word_id
WHERE wl.dict_lemma_id = $1 AND wt.language_code = 'en'
GROUP BY wt.value
ORDER BY freq DESC
LIMIT 1
"""


async def get_gloss_fallback(
    pool: asyncpg.Pool, dict_lemma_id: int
) -> str | None:
    """Get English gloss by aggregating word translations (fallback for NULL gloss_en)."""
    row = await pool.fetchrow(_GLOSS_FALLBACK_SQL, dict_lemma_id)
    if row:
        return row["value"]
    return None


_GLOSS_FALLBACK_BATCH_SQL = """
SELECT DISTINCT ON (wl.dict_lemma_id)
    wl.dict_lemma_id, wt.value
FROM quran_com.word_lemma wl
JOIN quran_com.word_translation wt ON wt.word_id = wl.word_id
WHERE wl.dict_lemma_id = ANY($1) AND wt.language_code = 'en'
GROUP BY wl.dict_lemma_id, wt.value
ORDER BY wl.dict_lemma_id, COUNT(*) DESC
"""


async def get_gloss_fallback_batch(
    pool: asyncpg.Pool, dict_lemma_ids: list[int]
) -> dict[int, str]:
    """Batch gloss fallback: fetch most-frequent English translation for multiple lemmas.

    Returns {dict_lemma_id: gloss_text} for lemmas that have translations.
    """
    if not dict_lemma_ids:
        return {}
    rows = await pool.fetch(_GLOSS_FALLBACK_BATCH_SQL, dict_lemma_ids)
    return {row["dict_lemma_id"]: row["value"] for row in rows}
