"""Data types for mushaf page rendering.

These types represent the server-side data model for mushaf page data.
They mirror what the app UI expects as structured_content from tool results.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# Default mushaf: KFGQPC HAFS (edition 5) — readable Unicode Arabic text, 604 pages.
# QCF V2 mushaf: edition 1 — PUA glyph chars for QCF v2 calligraphic fonts.
# Editions 1 and 5 share identical line breaks (both 1441 Hijri print layout).
# We query edition 5 for text + layout, JOIN edition 1 for v2 glyph code points.
DEFAULT_MUSHAF_ID = 5
QCF_V2_MUSHAF_ID = 1
MAX_PAGES = {1: 604, 5: 604}  # mushaf_id → max page


@dataclass(slots=True)
class MushafWord:
    """A single word (or marker) on a mushaf page."""

    word_id: int
    verse_id: int
    text: str
    char_type_name: str  # "word", "end"
    line_number: int
    position_in_line: int
    position_in_verse: int
    glyph_text: str | None = None  # QCF V2 PUA characters (may include pause mark)


@dataclass(slots=True)
class PageLine:
    """A line of words on a mushaf page (typically 15 lines per page)."""

    line_number: int
    words: list[MushafWord] = field(default_factory=list)


@dataclass(slots=True)
class PageVerse:
    """Verse metadata for a verse appearing on this page."""

    verse_id: int
    verse_key: str  # e.g., "2:255"
    chapter_id: int
    verse_number: int


@dataclass(slots=True)
class SurahHeader:
    """A surah header that should be rendered on this page."""

    chapter_id: int
    name_arabic: str
    name_simple: str
    bismillah_pre: bool
    appears_before_line: int  # render header above this line number


@dataclass(slots=True)
class PageData:
    """Complete rendering data for a single mushaf page."""

    page_number: int
    mushaf_edition_id: int
    total_pages: int
    lines: list[PageLine] = field(default_factory=list)
    verses: list[PageVerse] = field(default_factory=list)
    surah_headers: list[SurahHeader] = field(default_factory=list)
    chapter_names: dict[int, str] = field(default_factory=dict)
    initial_selected_verse: str | None = None  # e.g. "2:255" — auto-select on load
