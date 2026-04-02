"""SQL queries for word morphology tools.

Central query layer used by fetch_word_morphology, fetch_word_paradigm,
and fetch_word_concordance.  Each function returns raw asyncpg Records;
the caller (library functions) converts them to Pydantic models.

Key design choice: root, lemma, and stem are fetched in SEPARATE queries
to avoid Cartesian blow-up (a word with 2 roots × 2 lemmas × 2 stems
would produce 8 rows from a single JOIN).
"""

from __future__ import annotations

import asyncio

import asyncpg

from quran_mcp.lib.morphology.arabic_normalize import normalize_arabic


# ---------------------------------------------------------------------------
# Verse resolution
# ---------------------------------------------------------------------------

_RESOLVE_VERSE_SQL = """
SELECT verse_id, chapter_id, verse_number, verse_key,
       text_uthmani, text_imlaei_simple
FROM quran_com.verse
WHERE chapter_id = $1 AND verse_number = $2
"""


async def resolve_verse_by_key(
    pool: asyncpg.Pool, ayah_key: str
) -> asyncpg.Record:
    """Parse '2:77' → verse record.  Raises ValueError if not found."""
    parts = ayah_key.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid ayah_key format: {ayah_key!r} (expected 'surah:ayah')")
    try:
        chapter_id, verse_number = int(parts[0]), int(parts[1])
    except ValueError:
        raise ValueError(f"Invalid ayah_key format: {ayah_key!r} (non-numeric)")

    row = await pool.fetchrow(_RESOLVE_VERSE_SQL, chapter_id, verse_number)
    if row is None:
        raise ValueError(f"Verse not found: {ayah_key}")
    return row


# ---------------------------------------------------------------------------
# Word resolution by text
# ---------------------------------------------------------------------------

_RESOLVE_WORD_BY_TEXT_SQL = """
SELECT w.word_id, w.verse_id, w.position, w.text_uthmani,
       w.text_imlaei_simple, w.en_transliteration, w.verse_key
FROM quran_com.word w
WHERE w.text_uthmani = $1 OR w.text_imlaei_simple = $1
ORDER BY w.verse_id, w.position
LIMIT 1
"""

_COUNT_WORD_OCCURRENCES_SQL = """
SELECT COUNT(*) AS cnt
FROM quran_com.word
WHERE text_uthmani = $1 OR text_imlaei_simple = $1
"""


async def resolve_word_by_text(
    pool: asyncpg.Pool, word_text: str
) -> tuple[asyncpg.Record, int]:
    """Find first occurrence of an Arabic word by text.

    Tries exact match first, then normalized match.
    Returns (word_record, total_occurrences).
    Raises ValueError if not found.
    """
    # Try exact match first
    row = await pool.fetchrow(_RESOLVE_WORD_BY_TEXT_SQL, word_text)
    total = 0
    if row is not None:
        count_row = await pool.fetchrow(_COUNT_WORD_OCCURRENCES_SQL, word_text)
        total = count_row["cnt"] if count_row else 1
        return row, total

    # Try normalized match
    normalized = normalize_arabic(word_text)
    if normalized != word_text:
        row = await pool.fetchrow(_RESOLVE_WORD_BY_TEXT_SQL, normalized)
        if row is not None:
            count_row = await pool.fetchrow(_COUNT_WORD_OCCURRENCES_SQL, normalized)
            total = count_row["cnt"] if count_row else 1
            return row, total

    raise ValueError(f"Word not found: {word_text!r}")


# ---------------------------------------------------------------------------
# Word data for a verse
# ---------------------------------------------------------------------------

_WORDS_FOR_VERSE_SQL = """
SELECT
    w.word_id,
    w.verse_id,
    w.position,
    w.text_uthmani,
    w.text_imlaei_simple,
    w.en_transliteration,
    w.verse_key,
    w.char_type_name,
    mw.description AS morph_description
FROM quran_com.word w
LEFT JOIN quran_com.morph_word mw ON mw.word_id = w.word_id
WHERE w.verse_id = $1
ORDER BY w.position
"""

_WORDS_FOR_VERSE_POS_SQL = """
SELECT
    w.word_id,
    w.verse_id,
    w.position,
    w.text_uthmani,
    w.text_imlaei_simple,
    w.en_transliteration,
    w.verse_key,
    w.char_type_name,
    mw.description AS morph_description
FROM quran_com.word w
LEFT JOIN quran_com.morph_word mw ON mw.word_id = w.word_id
WHERE w.verse_id = $1 AND w.position = $2
ORDER BY w.position
"""


async def get_words_for_verse(
    pool: asyncpg.Pool,
    verse_id: int,
    word_position: int | None = None,
) -> list[asyncpg.Record]:
    """Fetch word(s) for a verse, optionally filtered by position."""
    if word_position is not None:
        return await pool.fetch(_WORDS_FOR_VERSE_POS_SQL, verse_id, word_position)
    return await pool.fetch(_WORDS_FOR_VERSE_SQL, verse_id)


async def resolve_word_in_verse(
    pool: asyncpg.Pool,
    verse_id: int,
    word_text: str,
    ayah_key: str,
) -> int:
    """Resolve Arabic word text to a 1-based position within a specific verse.

    Matching strategy:
    1. Exact match against text_uthmani or text_imlaei_simple
    2. Normalized match (diacritics-insensitive) via normalize_arabic
    Uses first occurrence if the word appears multiple times.

    Returns:
        1-based word position.

    Raises:
        ValueError: If the word is not found in the verse.
    """
    words = await get_words_for_verse(pool, verse_id)
    if not words:
        raise ValueError(f"No words found for verse {ayah_key}")

    # Step 1: Exact match against text_uthmani or text_imlaei_simple
    for w in words:
        if w["text_uthmani"] == word_text or w["text_imlaei_simple"] == word_text:
            return w["position"]

    # Step 2: Normalized match (diacritics-insensitive)
    normalized_input = normalize_arabic(word_text)
    for w in words:
        if (normalize_arabic(w["text_uthmani"] or "") == normalized_input
                or normalize_arabic(w["text_imlaei_simple"] or "") == normalized_input):
            return w["position"]

    # Build helpful error with available words
    available = ", ".join(
        w["text_uthmani"] for w in words if w["text_uthmani"]
    )
    raise ValueError(
        f"Word {word_text!r} not found in verse {ayah_key}. "
        f"Available words: {available}"
    )


# ---------------------------------------------------------------------------
# Root / lemma / stem lookups (separate queries to avoid Cartesian blow-up)
# ---------------------------------------------------------------------------

_ROOTS_FOR_WORDS_SQL = """
SELECT wr.word_id, dr.dict_root_id, dr.value AS root_value
FROM quran_com.word_root wr
JOIN quran_com.dict_root dr ON dr.dict_root_id = wr.dict_root_id
WHERE wr.word_id = ANY($1)
ORDER BY wr.word_id, wr.position
"""

_LEMMAS_FOR_WORDS_SQL = """
SELECT wl.word_id, dl.dict_lemma_id, dl.value AS lemma_value, dl.clean AS lemma_clean
FROM quran_com.word_lemma wl
JOIN quran_com.dict_lemma dl ON dl.dict_lemma_id = wl.dict_lemma_id
WHERE wl.word_id = ANY($1)
ORDER BY wl.word_id, wl.position
"""

_STEMS_FOR_WORDS_SQL = """
SELECT ws.word_id, ds.dict_stem_id, ds.value AS stem_value, ds.clean AS stem_clean
FROM quran_com.word_stem ws
JOIN quran_com.dict_stem ds ON ds.dict_stem_id = ws.dict_stem_id
WHERE ws.word_id = ANY($1)
ORDER BY ws.word_id, ws.position
"""


async def get_roots_for_words(
    pool: asyncpg.Pool, word_ids: list[int]
) -> dict[int, list[asyncpg.Record]]:
    """Fetch roots for multiple words.  Returns {word_id: [records]}."""
    rows = await pool.fetch(_ROOTS_FOR_WORDS_SQL, word_ids)
    result: dict[int, list[asyncpg.Record]] = {}
    for row in rows:
        result.setdefault(row["word_id"], []).append(row)
    return result


async def get_lemmas_for_words(
    pool: asyncpg.Pool, word_ids: list[int]
) -> dict[int, list[asyncpg.Record]]:
    """Fetch lemmas for multiple words.  Returns {word_id: [records]}."""
    rows = await pool.fetch(_LEMMAS_FOR_WORDS_SQL, word_ids)
    result: dict[int, list[asyncpg.Record]] = {}
    for row in rows:
        result.setdefault(row["word_id"], []).append(row)
    return result


async def get_stems_for_words(
    pool: asyncpg.Pool, word_ids: list[int]
) -> dict[int, list[asyncpg.Record]]:
    """Fetch stems for multiple words.  Returns {word_id: [records]}."""
    rows = await pool.fetch(_STEMS_FOR_WORDS_SQL, word_ids)
    result: dict[int, list[asyncpg.Record]] = {}
    for row in rows:
        result.setdefault(row["word_id"], []).append(row)
    return result


# ---------------------------------------------------------------------------
# Word translation
# ---------------------------------------------------------------------------

_TRANSLATIONS_FOR_WORDS_SQL = """
SELECT word_id, value AS translation
FROM quran_com.word_translation
WHERE word_id = ANY($1) AND language_code = 'en'
"""


async def get_translations_for_words(
    pool: asyncpg.Pool, word_ids: list[int]
) -> dict[int, str]:
    """Fetch English translations for multiple words. Returns {word_id: text}."""
    rows = await pool.fetch(_TRANSLATIONS_FOR_WORDS_SQL, word_ids)
    return {row["word_id"]: row["translation"] for row in rows}


# ---------------------------------------------------------------------------
# Morpheme segments
# ---------------------------------------------------------------------------

_SEGMENTS_FOR_WORDS_SQL = """
SELECT
    morph_word_segment_id,
    word_id,
    position,
    text_uthmani,
    part_of_speech_key,
    part_of_speech_name,
    grammar_term_desc_english,
    pos_tags,
    root_name,
    lemma_name,
    verb_form,
    hidden
FROM quran_com.morph_word_segment
WHERE word_id = ANY($1) AND (hidden IS NULL OR hidden = false)
ORDER BY word_id, position
"""


async def get_segments_for_words(
    pool: asyncpg.Pool, word_ids: list[int]
) -> dict[int, list[asyncpg.Record]]:
    """Fetch visible morpheme segments for multiple words.  Returns {word_id: [records]}."""
    rows = await pool.fetch(_SEGMENTS_FOR_WORDS_SQL, word_ids)
    result: dict[int, list[asyncpg.Record]] = {}
    for row in rows:
        result.setdefault(row["word_id"], []).append(row)
    return result


# ---------------------------------------------------------------------------
# Frequency counts (batched)
# ---------------------------------------------------------------------------

_ROOT_FREQ_SQL = """
SELECT wr.dict_root_id,
       COUNT(DISTINCT wr.word_id) AS word_count,
       COUNT(DISTINCT w.verse_id) AS verse_count
FROM quran_com.word_root wr
JOIN quran_com.word w ON w.word_id = wr.word_id
WHERE wr.dict_root_id = ANY($1)
GROUP BY wr.dict_root_id
"""

_LEMMA_FREQ_SQL = """
SELECT wl.dict_lemma_id,
       COUNT(DISTINCT wl.word_id) AS word_count,
       COUNT(DISTINCT w.verse_id) AS verse_count
FROM quran_com.word_lemma wl
JOIN quran_com.word w ON w.word_id = wl.word_id
WHERE wl.dict_lemma_id = ANY($1)
GROUP BY wl.dict_lemma_id
"""

_STEM_FREQ_SQL = """
SELECT ws.dict_stem_id,
       COUNT(DISTINCT ws.word_id) AS word_count,
       COUNT(DISTINCT w.verse_id) AS verse_count
FROM quran_com.word_stem ws
JOIN quran_com.word w ON w.word_id = ws.word_id
WHERE ws.dict_stem_id = ANY($1)
GROUP BY ws.dict_stem_id
"""


async def get_frequency_counts(
    pool: asyncpg.Pool,
    root_ids: list[int],
    lemma_ids: list[int],
    stem_ids: list[int],
) -> dict[str, dict[int, dict[str, int]]]:
    """Batch frequency counts for roots, lemmas, and stems.

    Returns:
        {
            "root": {dict_root_id: {"word_count": N, "verse_count": N}},
            "lemma": {dict_lemma_id: {"word_count": N, "verse_count": N}},
            "stem": {dict_stem_id: {"word_count": N, "verse_count": N}},
        }
    """
    result: dict[str, dict[int, dict[str, int]]] = {
        "root": {},
        "lemma": {},
        "stem": {},
    }

    # Fetch all three frequency types concurrently
    coros = []
    keys = []
    if root_ids:
        coros.append(pool.fetch(_ROOT_FREQ_SQL, root_ids))
        keys.append("root")
    if lemma_ids:
        coros.append(pool.fetch(_LEMMA_FREQ_SQL, lemma_ids))
        keys.append("lemma")
    if stem_ids:
        coros.append(pool.fetch(_STEM_FREQ_SQL, stem_ids))
        keys.append("stem")

    if coros:
        all_rows = await asyncio.gather(*coros)
        id_col = {"root": "dict_root_id", "lemma": "dict_lemma_id", "stem": "dict_stem_id"}
        for key, rows in zip(keys, all_rows):
            for r in rows:
                result[key][r[id_col[key]]] = {
                    "word_count": r["word_count"],
                    "verse_count": r["verse_count"],
                }

    return result
