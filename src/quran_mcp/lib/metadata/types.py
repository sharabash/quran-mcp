"""Pydantic response models for fetch_quran_metadata.

Fixed-shape response with full structural context chain.
Type consistency rules:
- surah: always list[SurahInfo]
- sajdah: always list[SajdahInfo] (empty if none)
- ayah ranges: always verse_key format
- numeric ranges: always {start, end}
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

QueryType = Literal["surah", "ayah", "juz", "page", "hizb", "ruku", "manzil"]
RevelationPlace = Literal["makkah", "madinah"]
SajdahType = Literal["required", "optional"]


class SurahInfo(BaseModel):
    """Chapter metadata."""

    model_config = ConfigDict(extra="forbid")

    number: int = Field(description="Surah number (1-114)")
    name_arabic: str = Field(description="Arabic name")
    name_simple: str = Field(description="Simple transliterated name")
    revelation_place: RevelationPlace = Field(description="'makkah' or 'madinah'")
    revelation_order: int = Field(description="Chronological revelation order")
    verses_count: int = Field(description="Total verses in this surah")
    bismillah_pre: bool = Field(description="Whether Bismillah precedes this surah")


class AyahPoint(BaseModel):
    """Single ayah location (point query result)."""

    model_config = ConfigDict(extra="forbid")

    verse_key: str = Field(description="Verse reference in S:V format")
    number: int = Field(description="Ayah number within surah")
    words_count: int = Field(description="Number of words in this ayah")


class AyahRange(BaseModel):
    """Ayah range (span query result). Always uses verse_key format."""

    model_config = ConfigDict(extra="forbid")

    start_verse_key: str = Field(description="First verse in range (S:V format)")
    end_verse_key: str = Field(description="Last verse in range (S:V format)")
    count: int = Field(description="Total ayat in range")


class NumericPoint(BaseModel):
    """Single numeric structural value (point query result)."""

    model_config = ConfigDict(extra="forbid")

    number: int = Field(description="The numeric value")


class NumericRange(BaseModel):
    """Numeric range (span query result)."""

    model_config = ConfigDict(extra="forbid")

    start: int = Field(description="Start of range (inclusive)")
    end: int = Field(description="End of range (inclusive)")


class RukuPoint(BaseModel):
    """Ruku with global and surah-local numbers (point query result)."""

    model_config = ConfigDict(extra="forbid")

    number: int = Field(description="Global ruku number")
    surah_ruku_number: int = Field(description="Ruku number within surah")


class SajdahInfo(BaseModel):
    """Sajdah verse metadata."""

    model_config = ConfigDict(extra="forbid")

    verse_key: str = Field(description="Verse reference in S:V format")
    type: SajdahType = Field(description="Sajdah type: 'required' or 'optional'")
    number: int = Field(description="Sajdah sequence number (1-14)")


class QuranMetadataResponse(BaseModel):
    """Fixed-shape response for fetch_quran_metadata.

    All fields are always present. Type varies by query mode:
    - Point queries: single-value fields (AyahPoint, NumericPoint, RukuPoint)
    - Span queries: range fields (AyahRange, NumericRange)
    """

    model_config = ConfigDict(extra="forbid")

    query_type: QueryType = Field(description="Query mode that produced this response")
    surah: list[SurahInfo] = Field(description="Surah(s) in scope (always a list)")
    ayah: AyahPoint | AyahRange = Field(
        description="Ayah info (point) or range (span)"
    )
    juz: NumericPoint | NumericRange = Field(description="Juz info or range")
    hizb: NumericPoint | NumericRange = Field(description="Hizb info or range")
    rub_el_hizb: NumericPoint | NumericRange = Field(
        description="Rub' al-Hizb info or range"
    )
    page: NumericPoint | NumericRange = Field(description="Page info or range")
    ruku: RukuPoint | NumericRange = Field(description="Ruku info or range")
    manzil: NumericPoint | NumericRange = Field(description="Manzil info or range")
    sajdah: list[SajdahInfo] = Field(
        description="Sajdah verses in scope (empty list if none)"
    )
