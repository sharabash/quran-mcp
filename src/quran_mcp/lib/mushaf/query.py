"""Query layer for mushaf page data from quran_com schema.

All queries use explicit quran_com. schema qualification to avoid
name collisions with the quran_mcp schema.
"""

from __future__ import annotations

import asyncpg

from quran_mcp.lib.mushaf.types import (
    DEFAULT_MUSHAF_ID,
    MAX_PAGES,
    MushafWord,
    PageData,
    PageLine,
    PageVerse,
    QCF_V2_MUSHAF_ID,
    SurahHeader,
)

# Single query fetches all word + verse + chapter data for a page.
# Uses idx_mushaf_word_page covering index for fast lookups.
# LEFT JOIN edition 1 (QCF V2) to extract v2 glyph code points from its PUA text.
# Editions 1 and 5 share line breaks (both 1441 Hijri layout), so edition 5's
# line_number is correct for QCF v2 fonts loaded from CDN.
_PAGE_DATA_SQL = """
SELECT
    mw.word_id,
    mw.verse_id,
    mw.text,
    mw.char_type_name,
    mw.line_number,
    mw.position_in_line,
    mw.position_in_verse,
    mw_v2.text AS glyph_text,
    v.verse_key,
    v.chapter_id,
    v.verse_number,
    c.name_arabic,
    c.name_simple,
    c.bismillah_pre
FROM quran_com.mushaf_word mw
LEFT JOIN quran_com.mushaf_word mw_v2
    ON mw_v2.word_id = mw.word_id
   AND mw_v2.mushaf_edition_id = $3
JOIN quran_com.verse v ON v.verse_id = mw.verse_id
JOIN quran_com.chapter c ON c.chapter_id = v.chapter_id
WHERE mw.mushaf_edition_id = $1 AND mw.page_number = $2
ORDER BY mw.line_number, mw.word_id
"""

# Resolve surah+ayah → page number via authoritative mapping table.
_RESOLVE_VERSE_SQL = """
SELECT mvp.page_number
FROM quran_com.mushaf_verse_page mvp
JOIN quran_com.verse v ON v.verse_id = mvp.verse_id
WHERE mvp.mushaf_edition_id = $1
  AND v.chapter_id = $2
  AND v.verse_number = $3
LIMIT 1
"""

# Resolve surah (alone) → page of its first verse.
_RESOLVE_SURAH_SQL = """
SELECT mvp.page_number
FROM quran_com.mushaf_verse_page mvp
JOIN quran_com.verse v ON v.verse_id = mvp.verse_id
WHERE mvp.mushaf_edition_id = $1
  AND v.chapter_id = $2
  AND v.verse_number = 1
LIMIT 1
"""

# Resolve juz → page of its first verse.
_RESOLVE_JUZ_SQL = """
SELECT mvp.page_number
FROM quran_com.mushaf_verse_page mvp
JOIN quran_com.division_juz dj ON dj.first_verse_id = mvp.verse_id
WHERE mvp.mushaf_edition_id = $1
  AND dj.juz_number = $2
LIMIT 1
"""


async def get_page_data(
    pool: asyncpg.Pool,
    page_number: int,
    mushaf_id: int = DEFAULT_MUSHAF_ID,
) -> PageData:
    """Fetch all words for a mushaf page, grouped by line and verse.

    Returns a PageData with lines (words per line), verse metadata,
    surah headers for chapters starting on this page, and chapter names.
    """
    max_page = MAX_PAGES.get(mushaf_id, 604)
    if not 1 <= page_number <= max_page:
        raise ValueError(
            f"Page number must be 1-{max_page} for mushaf {mushaf_id}, "
            f"got {page_number}"
        )

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            _PAGE_DATA_SQL, mushaf_id, page_number, QCF_V2_MUSHAF_ID,
        )

    if not rows:
        raise ValueError(
            f"No data found for mushaf {mushaf_id}, page {page_number}"
        )

    # Group words into lines
    lines_map: dict[int, list[MushafWord]] = {}
    seen_verses: dict[int, PageVerse] = {}
    chapter_names: dict[int, str] = {}
    # Track chapters whose verse 1 appears on this page (surah headers)
    surah_starts: dict[int, dict] = {}

    for row in rows:
        word = MushafWord(
            word_id=row["word_id"],
            verse_id=row["verse_id"],
            text=row["text"],
            char_type_name=row["char_type_name"],
            line_number=row["line_number"],
            position_in_line=row["position_in_line"],
            position_in_verse=row["position_in_verse"],
            glyph_text=row["glyph_text"],
        )

        lines_map.setdefault(row["line_number"], []).append(word)

        verse_id = row["verse_id"]
        if verse_id not in seen_verses:
            seen_verses[verse_id] = PageVerse(
                verse_id=verse_id,
                verse_key=row["verse_key"],
                chapter_id=row["chapter_id"],
                verse_number=row["verse_number"],
            )

        chapter_id = row["chapter_id"]
        if chapter_id not in chapter_names:
            chapter_names[chapter_id] = row["name_simple"]

        # Detect surah headers: first occurrence of verse_number=1 for a chapter
        if row["verse_number"] == 1 and chapter_id not in surah_starts:
            surah_starts[chapter_id] = {
                "name_arabic": row["name_arabic"],
                "name_simple": row["name_simple"],
                "bismillah_pre": row["bismillah_pre"],
                "first_line": row["line_number"],
            }

    lines = [
        PageLine(line_number=ln, words=words)
        for ln, words in sorted(lines_map.items())
    ]

    verses = sorted(seen_verses.values(), key=lambda v: v.verse_id)

    surah_headers = [
        SurahHeader(
            chapter_id=ch_id,
            name_arabic=info["name_arabic"],
            name_simple=info["name_simple"],
            bismillah_pre=info["bismillah_pre"],
            appears_before_line=info["first_line"],
        )
        for ch_id, info in sorted(surah_starts.items(), key=lambda x: x[1]["first_line"])
    ]

    return PageData(
        page_number=page_number,
        mushaf_edition_id=mushaf_id,
        total_pages=max_page,
        lines=lines,
        verses=verses,
        surah_headers=surah_headers,
        chapter_names=chapter_names,
    )


async def resolve_page(
    pool: asyncpg.Pool,
    *,
    page: int | None = None,
    surah: int | None = None,
    ayah: int | None = None,
    juz: int | None = None,
    mushaf_id: int = DEFAULT_MUSHAF_ID,
) -> int:
    """Resolve entry point parameters to a mushaf page number.

    Exactly one parameter group must be provided:
    - page: direct page number
    - surah + ayah: verse reference
    - surah (alone): first verse of chapter
    - juz: first verse of juz
    - (none): defaults to page 1

    Raises ValueError for invalid params or mutual exclusivity violations.
    """
    max_page = MAX_PAGES.get(mushaf_id, 604)

    # Count how many parameter groups are set
    groups = [
        page is not None,
        surah is not None,
        juz is not None,
    ]
    active = sum(groups)

    if active > 1 and juz is not None:
        raise ValueError(
            "Parameters are mutually exclusive: "
            "use page, surah[+ayah], or juz — not combinations"
        )

    # Direct page number
    if page is not None:
        if surah is not None or juz is not None:
            raise ValueError(
                "Parameters are mutually exclusive: "
                "use page, surah[+ayah], or juz — not combinations"
            )
        if not 1 <= page <= max_page:
            raise ValueError(f"Page must be 1-{max_page}, got {page}")
        return page

    # Surah + optional ayah
    if surah is not None:
        if not 1 <= surah <= 114:
            raise ValueError(f"Surah must be 1-114, got {surah}")

        async with pool.acquire() as conn:
            if ayah is not None:
                if ayah < 1:
                    raise ValueError(f"Ayah must be >= 1, got {ayah}")
                row = await conn.fetchrow(
                    _RESOLVE_VERSE_SQL, mushaf_id, surah, ayah,
                )
                if not row:
                    raise ValueError(
                        f"Verse {surah}:{ayah} not found in mushaf {mushaf_id}"
                    )
            else:
                row = await conn.fetchrow(
                    _RESOLVE_SURAH_SQL, mushaf_id, surah,
                )
                if not row:
                    raise ValueError(
                        f"Surah {surah} not found in mushaf {mushaf_id}"
                    )

        return row["page_number"]

    # Juz
    if juz is not None:
        if not 1 <= juz <= 30:
            raise ValueError(f"Juz must be 1-30, got {juz}")

        async with pool.acquire() as conn:
            row = await conn.fetchrow(_RESOLVE_JUZ_SQL, mushaf_id, juz)

        if not row:
            raise ValueError(
                f"Juz {juz} not found in mushaf {mushaf_id}"
            )
        return row["page_number"]

    # Default: page 1
    return 1
