"""Pydantic response models for the three morphology tools.

These models define the API contract for:
- fetch_word_morphology → MorphologyResponse
- fetch_word_paradigm → ParadigmResponse
- fetch_word_concordance → ConcordanceResponse
"""

from __future__ import annotations

from typing import Literal, TypedDict

from pydantic import BaseModel, Field

ConcordanceMatchBy = Literal["all", "root", "lemma", "stem"]
ConcordanceGroupBy = Literal["verse", "word"]


# --- Shared sub-models ---


class WordInfo(TypedDict):
    """Source word information returned in paradigm responses."""

    text_uthmani: str
    text_simple: str | None
    transliteration: str | None
    ayah_key: str
    position: int


class ConcordanceQueryEcho(TypedDict, total=False):
    """Echo of resolved concordance query parameters.

    Fields are populated based on input mode:
    - ayah_key mode: ayah_key, word_position, text
    - word mode: word, resolved_verse
    - root mode: root
    - lemma mode: lemma
    - stem mode: stem
    """

    ayah_key: str
    word_position: int
    text: str
    word: str
    resolved_verse: str
    root: str
    lemma: str
    stem: str


class FrequencyInfo(BaseModel):
    """Word and verse frequency counts for a linguistic unit."""

    word_count: int = Field(description="Number of word occurrences in the Quran")
    verse_count: int = Field(description="Number of distinct verses containing this unit")


class MorphemeSegment(BaseModel):
    """A single morpheme segment within a word (prefix, stem, or suffix)."""

    position: int = Field(description="Segment position (1-based)")
    text: str = Field(description="Arabic text of this segment")
    part_of_speech_key: str | None = Field(default=None, description="POS key (V, N, PRON, etc.)")
    part_of_speech_name: str | None = Field(default=None, description="Human-readable POS name")
    grammar_description: str | None = Field(default=None, description="English grammar description (HTML stripped)")
    pos_tags: str | None = Field(default=None, description="Raw pos_tags from corpus")
    root: str | None = Field(default=None, description="Root letters if present on this segment")
    lemma: str | None = Field(default=None, description="Lemma if present on this segment")
    verb_form: int | None = Field(default=None, description="Arabic verb form (1-10) if applicable")


class GrammaticalFeaturesModel(BaseModel):
    """Structured grammatical features parsed from pos_tags."""

    part_of_speech: str | None = Field(default=None, description="Part of speech (verb, noun, etc.)")
    person: str | None = Field(default=None, description="Person (1st, 2nd, 3rd)")
    gender: str | None = Field(default=None, description="Gender (masculine, feminine)")
    number: str | None = Field(default=None, description="Number (singular, dual, plural)")
    aspect: str | None = Field(default=None, description="Verbal aspect (perfect, imperfect, imperative)")
    mood: str | None = Field(default=None, description="Verbal mood (indicative, subjunctive, jussive)")
    voice: str | None = Field(default=None, description="Voice (active, passive)")
    verb_form: int | None = Field(default=None, description="Arabic verb form number (1-10)")
    definiteness: str | None = Field(default=None, description="Definiteness (definite, indefinite)")
    case: str | None = Field(default=None, description="Grammatical case (nominative, accusative, genitive)")
    features_version: str = Field(default="v1", description="Version of the features schema")
    raw_unrecognized_tags: list[str] = Field(
        default_factory=list,
        description="Tags from pos_tags that were not recognized by the parser (preserved for debugging)",
    )


# --- fetch_word_morphology models ---


class WordMorphologyEntry(BaseModel):
    """Morphological analysis for a single word."""

    word_id: int = Field(description="Internal word ID")
    position: int = Field(description="Word position within the verse (1-based)")
    text_uthmani: str = Field(description="Arabic text in Uthmani script")
    text_simple: str | None = Field(default=None, description="Arabic text in simplified script")
    transliteration: str | None = Field(default=None, description="English transliteration")
    translation: str | None = Field(default=None, description="Word-level English translation")
    root: str | None = Field(default=None, description="Triliteral root letters")
    root_frequency: FrequencyInfo | None = Field(default=None, description="Root frequency in the Quran")
    lemma: str | None = Field(default=None, description="Lemma (dictionary form)")
    lemma_frequency: FrequencyInfo | None = Field(default=None, description="Lemma frequency in the Quran")
    stem: str | None = Field(default=None, description="Morphological stem")
    stem_frequency: FrequencyInfo | None = Field(default=None, description="Stem frequency in the Quran")
    grammatical_features: GrammaticalFeaturesModel | None = Field(
        default=None, description="Structured grammatical features"
    )
    morpheme_segments: list[MorphemeSegment] = Field(
        default_factory=list, description="Morpheme-level breakdown"
    )
    description: str | None = Field(
        default=None, description="Corpus description (HTML stripped)"
    )


class MorphologyResponse(BaseModel):
    """Response from fetch_word_morphology tool."""

    ayah_key: str = Field(description="Verse reference (e.g., '2:77')")
    words: list[WordMorphologyEntry] = Field(description="Morphological entries per word")
    input_mode: str = Field(description="How input was resolved: 'ayah_key' or 'word_text'")
    other_occurrences_count: int | None = Field(
        default=None,
        description="For word_text input: total occurrences minus this one",
    )


# --- fetch_word_paradigm models ---


class ParadigmStem(BaseModel):
    """A single stem form in the paradigm."""

    stem: str = Field(description="Arabic stem text")
    description: str | None = Field(default=None, description="Grammar description")
    count: int = Field(description="Number of occurrences in the Quran")


class CandidateLemma(BaseModel):
    """A lemma derived from the same root."""

    lemma: str = Field(description="Lemma text")
    verb_form: int | None = Field(default=None, description="Verb form number (1-10)")
    count: int = Field(description="Word count in the Quran")
    gloss: str | None = Field(default=None, description="English gloss")


class ParadigmResponse(BaseModel):
    """Response from fetch_word_paradigm tool."""

    word: WordInfo | None = Field(
        default=None,
        description="Source word info (text, transliteration, ayah_key, position)",
    )
    root: str | None = Field(default=None, description="Root letters")
    lemma: str | None = Field(default=None, description="Lemma text")
    verb_form: int | None = Field(default=None, description="Verb form number")
    paradigm_available: bool = Field(
        default=True, description="Whether a verbal paradigm exists"
    )
    paradigm_unavailable_reason: str | None = Field(
        default=None,
        description="Why paradigm is unavailable (e.g., 'particle — no conjugation')",
    )
    paradigm: dict[str, list[ParadigmStem]] | None = Field(
        default=None,
        description="Stems categorized by aspect: perfect, imperfect, imperative",
    )
    candidate_lemmas: list[CandidateLemma] = Field(
        default_factory=list,
        description="All lemmas derived from the same root",
    )
    total_forms_in_quran: dict[str, int] | None = Field(
        default=None,
        description="Summary counts: root_words, lemma_words, stems_in_paradigm",
    )


# --- fetch_word_concordance models ---


class ConcordanceWord(BaseModel):
    """A matched word within a concordance verse."""

    position: int = Field(description="Word position in the verse")
    text_uthmani: str = Field(description="Arabic text")
    transliteration: str | None = Field(default=None, description="Transliteration")
    match_level: str = Field(description="How it matched: 'exact', 'lemma', or 'root'")


class ConcordanceVerse(BaseModel):
    """A verse result in concordance output."""

    ayah_key: str = Field(description="Verse reference (e.g., '2:255')")
    verse_text: str = Field(description="Full verse text (Uthmani)")
    score: float = Field(description="Tiered lexical score")
    rerank_score: float | None = Field(default=None, description="Voyage semantic rerank score (when reranking is active)")
    matched_words: list[ConcordanceWord] = Field(description="Words that matched")


class ConcordanceWordResult(BaseModel):
    """A single word result in word-grouped concordance output."""

    ayah_key: str = Field(description="Verse reference (e.g., '2:255')")
    position: int = Field(description="Word position in the verse")
    text_uthmani: str = Field(description="Arabic text")
    transliteration: str | None = Field(default=None, description="Transliteration")
    match_level: str = Field(description="How it matched: 'exact', 'lemma', or 'root'")
    verse_text: str = Field(description="Full verse text (Uthmani)")
    score: float = Field(description="Word-level score")


class ConcordanceResponse(BaseModel):
    """Response from fetch_word_concordance tool."""

    query: ConcordanceQueryEcho = Field(description="Echo of resolved query parameters")
    match_by: ConcordanceMatchBy = Field(
        default="all",
        description="Match level used: 'root', 'lemma', 'stem', or 'all'",
    )
    group_by: ConcordanceGroupBy = Field(default="verse", description="Grouping mode: 'verse' (default) or 'word'")
    total_verses: int = Field(description="Total matching verses")
    total_words: int | None = Field(default=None, description="Total matching words (populated in word mode)")
    page: int = Field(default=1, description="Current page number")
    page_size: int = Field(default=20, description="Results per page")
    results: list[ConcordanceVerse] = Field(default_factory=list, description="Verse-grouped results (populated when group_by='verse')")
    word_results: list[ConcordanceWordResult] = Field(default_factory=list, description="Word-level results (populated when group_by='word')")
    truncated: bool = Field(default=False, description="True if results were truncated to stay within token limits")
    reranker_model: str | None = Field(default=None, description="Voyage model used for reranking (when active)")
    reranked_from_pool: int | None = Field(default=None, description="Size of candidate pool that was reranked")
