"""Tests for morphology libraries and MCP tool wrappers.

Covers:
  - fetch_word_morphology: input validation + mock-based pipeline
  - fetch_word_paradigm: input validation + mock-based pipeline
  - fetch_word_concordance: input validation + mock-based pipeline
  - morphology MCP wrapper contract behavior
  - _categorize_stem: pure aspect categorization
  - _safe_int: pure type coercion
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, patch

import pytest
import quran_mcp.mcp.tools.morphology.concordance as concordance_tool
import quran_mcp.mcp.tools.morphology.fetch as morphology_fetch_tool
import quran_mcp.mcp.tools.morphology.paradigm as paradigm_tool

from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from quran_mcp.lib.morphology.fetch_concordance import fetch_word_concordance
from quran_mcp.lib.morphology.fetch_morphology import fetch_word_morphology
from quran_mcp.lib.morphology.fetch_paradigm import (
    _categorize_stem,
    _safe_int,
    fetch_word_paradigm,
)
from quran_mcp.lib.morphology.types import (
    CandidateLemma,
    ConcordanceResponse,
    MorphologyResponse,
    ParadigmResponse,
    ParadigmStem,
    WordMorphologyEntry,
)


# ---------------------------------------------------------------------------
# Helpers — validation fires before pool is used, so AsyncMock works
# ---------------------------------------------------------------------------


def _pool() -> AsyncMock:
    pool = AsyncMock()
    pool.fetch = AsyncMock(return_value=[])
    pool.fetchrow = AsyncMock(return_value=None)
    return pool


# ===========================================================================
# fetch_word_morphology — input validation
# ===========================================================================


class TestMorphologyValidation:
    async def test_ayah_key_and_word_mutual_exclusion(self):
        with pytest.raises(ValueError, match="not both"):
            await fetch_word_morphology(_pool(), ayah_key="1:1", word="بسم")

    async def test_word_position_requires_ayah_key(self):
        with pytest.raises(ValueError, match="word_position requires ayah_key"):
            await fetch_word_morphology(_pool(), word_position=3)

    async def test_word_text_requires_ayah_key(self):
        with pytest.raises(ValueError, match="word_text requires ayah_key"):
            await fetch_word_morphology(_pool(), word_text="بسم")

    async def test_word_position_and_word_text_mutual_exclusion(self):
        with pytest.raises(ValueError, match="word_position or word_text"):
            await fetch_word_morphology(_pool(), ayah_key="1:1", word_position=1, word_text="بسم")

    async def test_no_input_raises(self):
        with pytest.raises(ValueError, match="Provide either ayah_key or word"):
            await fetch_word_morphology(_pool())


# ===========================================================================
# fetch_word_paradigm — input validation
# ===========================================================================


class TestParadigmValidation:
    async def test_mutual_exclusivity(self):
        with pytest.raises(ValueError, match="only one of"):
            await fetch_word_paradigm(_pool(), ayah_key="1:1", lemma="قال")

    async def test_two_direct_inputs(self):
        with pytest.raises(ValueError, match="only one of"):
            await fetch_word_paradigm(_pool(), lemma="قال", root="قول")

    async def test_word_position_requires_ayah_key(self):
        with pytest.raises(ValueError, match="word_position requires ayah_key"):
            await fetch_word_paradigm(_pool(), word_position=1)

    async def test_word_text_requires_ayah_key(self):
        with pytest.raises(ValueError, match="word_text requires ayah_key"):
            await fetch_word_paradigm(_pool(), word_text="بسم")

    async def test_word_position_and_text_mutual_exclusion(self):
        with pytest.raises(ValueError, match="word_position or word_text"):
            await fetch_word_paradigm(_pool(), ayah_key="1:1", word_position=1, word_text="بسم")

    async def test_no_input_raises(self):
        with pytest.raises(ValueError, match="Provide one of"):
            await fetch_word_paradigm(_pool())


# ===========================================================================
# fetch_word_concordance — input validation
# ===========================================================================


class TestConcordanceValidation:
    async def test_word_position_requires_ayah_key(self):
        with pytest.raises(ValueError, match="word_position requires ayah_key"):
            await fetch_word_concordance(_pool(), word_position=1)

    async def test_word_text_requires_ayah_key(self):
        with pytest.raises(ValueError, match="word_text requires ayah_key"):
            await fetch_word_concordance(_pool(), word_text="بسم")

    async def test_word_position_and_text_mutual_exclusion(self):
        with pytest.raises(ValueError, match="word_position or word_text"):
            await fetch_word_concordance(_pool(), ayah_key="1:1", word_position=1, word_text="بسم")

    async def test_mutual_exclusivity_multiple_inputs(self):
        with pytest.raises(ValueError, match="only one of"):
            await fetch_word_concordance(_pool(), ayah_key="1:1", root="قول")

    async def test_mutual_exclusivity_direct_inputs(self):
        with pytest.raises(ValueError, match="only one of"):
            await fetch_word_concordance(_pool(), root="قول", lemma="قال")

    async def test_no_input_raises(self):
        with pytest.raises(ValueError, match="Provide one of"):
            await fetch_word_concordance(_pool())

    async def test_invalid_match_by(self):
        with pytest.raises(ValueError, match="Invalid match_by"):
            await fetch_word_concordance(_pool(), root="قول", match_by="invalid")

    async def test_invalid_group_by(self):
        with pytest.raises(ValueError, match="Invalid group_by"):
            await fetch_word_concordance(_pool(), root="قول", group_by="chapter")

    async def test_page_zero(self):
        with pytest.raises(ValueError, match="page must be >= 1"):
            await fetch_word_concordance(_pool(), root="قول", page=0)

    async def test_page_negative(self):
        with pytest.raises(ValueError, match="page must be >= 1"):
            await fetch_word_concordance(_pool(), root="قول", page=-1)

    async def test_page_size_zero(self):
        with pytest.raises(ValueError, match="page_size must be between 1 and 100"):
            await fetch_word_concordance(_pool(), root="قول", page_size=0)

    async def test_page_size_too_large(self):
        with pytest.raises(ValueError, match="page_size must be between 1 and 100"):
            await fetch_word_concordance(_pool(), root="قول", page_size=101)


# ===========================================================================
# _categorize_stem — pure function
# ===========================================================================


class TestCategorizeStem:
    def test_perfect(self):
        assert _categorize_stem("PERF,3MS") == "perfect"

    def test_imperfect(self):
        assert _categorize_stem("IMPF,3MP,MOOD:IND") == "imperfect"

    def test_imperative(self):
        assert _categorize_stem("IMPV,2MS") == "imperative"

    def test_no_aspect(self):
        assert _categorize_stem("NOM,DEF") is None

    def test_none(self):
        assert _categorize_stem(None) is None

    def test_empty(self):
        assert _categorize_stem("") is None


# ===========================================================================
# _safe_int — pure function
# ===========================================================================


class TestSafeInt:
    def test_normal(self):
        assert _safe_int(5) == 5

    def test_string(self):
        assert _safe_int("3") == 3

    def test_none(self):
        assert _safe_int(None) is None

    def test_garbage(self):
        assert _safe_int("abc") is None


# ===========================================================================
# Shared mock record helpers
# ===========================================================================

_FM = "quran_mcp.lib.morphology.fetch_morphology"
_FP = "quran_mcp.lib.morphology.fetch_paradigm"
_FC = "quran_mcp.lib.morphology.fetch_concordance"


def _rec(**kwargs):
    class _R(dict):
        def __getitem__(self, key):
            return dict.__getitem__(self, key)
        def get(self, key, default=None):
            return dict.get(self, key, default)
    return _R(**kwargs)


def _verse_rec(verse_id=1, chapter_id=1, verse_number=1, verse_key="1:1"):
    return _rec(
        verse_id=verse_id, chapter_id=chapter_id,
        verse_number=verse_number, verse_key=verse_key,
        text_uthmani="بِسْمِ", text_imlaei_simple="بسم",
    )


def _word_rec(word_id=100, verse_id=1, position=1, verse_key="1:1"):
    return _rec(
        word_id=word_id, verse_id=verse_id, position=position,
        text_uthmani="بِسْمِ", text_imlaei_simple="بسم",
        en_transliteration="bismi", verse_key=verse_key,
        char_type_name="word", morph_description="noun",
    )


def _segment_rec(word_id=100, position=1, pos_key="N", pos_name="noun"):
    return _rec(
        morph_word_segment_id=1, word_id=word_id, position=position,
        text_uthmani="بِسْمِ", part_of_speech_key=pos_key,
        part_of_speech_name=pos_name,
        grammar_term_desc_english="genitive noun",
        pos_tags="NOM,GEN", root_name="سمو", lemma_name="اسم",
        verb_form=None, hidden=False,
    )


def _verb_segment_rec(word_id=200, position=1):
    return _rec(
        morph_word_segment_id=2, word_id=word_id, position=position,
        text_uthmani="قَالَ", part_of_speech_key="V",
        part_of_speech_name="verb",
        grammar_term_desc_english="3rd person masculine singular perfect verb",
        pos_tags="PERF,VF:1,3MS", root_name="قول", lemma_name="قَالَ",
        verb_form="I", hidden=False,
    )


# ===========================================================================
# fetch_word_morphology — pipeline tests (mocked query layer)
# ===========================================================================


class TestMorphologyPipeline:
    @patch(f"{_FM}.get_frequency_counts")
    @patch(f"{_FM}.get_segments_for_words")
    @patch(f"{_FM}.get_translations_for_words")
    @patch(f"{_FM}.get_stems_for_words")
    @patch(f"{_FM}.get_lemmas_for_words")
    @patch(f"{_FM}.get_roots_for_words")
    @patch(f"{_FM}.get_words_for_verse")
    @patch(f"{_FM}.resolve_verse_by_key")
    async def test_ayah_key_with_position_resolves(
        self, m_verse, m_words, m_roots, m_lemmas, m_stems,
        m_trans, m_segs, m_freq,
    ):
        m_verse.return_value = _verse_rec()
        word = _word_rec(word_id=100, position=3)
        m_words.return_value = [word]
        m_roots.return_value = {}
        m_lemmas.return_value = {}
        m_stems.return_value = {}
        m_trans.return_value = {}
        m_segs.return_value = {}
        m_freq.return_value = {"root": {}, "lemma": {}, "stem": {}}

        result = await fetch_word_morphology(_pool(), ayah_key="1:1", word_position=3)

        assert result.ayah_key == "1:1"
        assert result.input_mode == "ayah_key"
        assert result.other_occurrences_count is None
        assert len(result.words) == 1
        assert result.words[0].position == 3
        assert result.words[0].word_id == 100
        m_words.assert_called_once_with(ANY, 1, 3)

    @patch(f"{_FM}.get_frequency_counts")
    @patch(f"{_FM}.get_segments_for_words")
    @patch(f"{_FM}.get_translations_for_words")
    @patch(f"{_FM}.get_stems_for_words")
    @patch(f"{_FM}.get_lemmas_for_words")
    @patch(f"{_FM}.get_roots_for_words")
    @patch(f"{_FM}.get_words_for_verse")
    @patch(f"{_FM}.resolve_verse_by_key")
    async def test_missing_word_at_position_raises(
        self, m_verse, m_words, m_roots, m_lemmas, m_stems,
        m_trans, m_segs, m_freq,
    ):
        m_verse.return_value = _verse_rec()
        m_words.return_value = []

        with pytest.raises(ValueError, match="No word at position 99"):
            await fetch_word_morphology(_pool(), ayah_key="1:1", word_position=99)

    @patch(f"{_FM}.get_frequency_counts")
    @patch(f"{_FM}.get_segments_for_words")
    @patch(f"{_FM}.get_translations_for_words")
    @patch(f"{_FM}.get_stems_for_words")
    @patch(f"{_FM}.get_lemmas_for_words")
    @patch(f"{_FM}.get_roots_for_words")
    @patch(f"{_FM}.get_words_for_verse")
    @patch(f"{_FM}.resolve_word_by_text")
    async def test_word_mode_sets_input_mode_and_occurrences(
        self, m_word_text, m_words, m_roots, m_lemmas, m_stems,
        m_trans, m_segs, m_freq,
    ):
        word = _word_rec(word_id=100, position=1)
        m_word_text.return_value = (word, 5)
        m_words.return_value = [word]
        m_roots.return_value = {}
        m_lemmas.return_value = {}
        m_stems.return_value = {}
        m_trans.return_value = {}
        m_segs.return_value = {}
        m_freq.return_value = {"root": {}, "lemma": {}, "stem": {}}

        result = await fetch_word_morphology(_pool(), word="بسم")

        assert result.input_mode == "word_text"
        assert result.other_occurrences_count == 4

    @patch(f"{_FM}.get_frequency_counts")
    @patch(f"{_FM}.get_segments_for_words")
    @patch(f"{_FM}.get_translations_for_words")
    @patch(f"{_FM}.get_stems_for_words")
    @patch(f"{_FM}.get_lemmas_for_words")
    @patch(f"{_FM}.get_roots_for_words")
    @patch(f"{_FM}.get_words_for_verse")
    @patch(f"{_FM}.resolve_verse_by_key")
    async def test_full_assembly(
        self, m_verse, m_words, m_roots, m_lemmas, m_stems,
        m_trans, m_segs, m_freq,
    ):
        m_verse.return_value = _verse_rec()
        word = _word_rec(word_id=100, position=1)
        m_words.return_value = [word]
        m_roots.return_value = {
            100: [_rec(word_id=100, dict_root_id=10, root_value="سمو")]
        }
        m_lemmas.return_value = {
            100: [_rec(word_id=100, dict_lemma_id=20, lemma_value="اسم", lemma_clean="اسم")]
        }
        m_stems.return_value = {
            100: [_rec(word_id=100, dict_stem_id=30, stem_value="بسم", stem_clean="بسم")]
        }
        m_trans.return_value = {100: "In the name"}
        m_segs.return_value = {100: [_segment_rec(word_id=100)]}
        m_freq.return_value = {
            "root": {10: {"word_count": 42, "verse_count": 38}},
            "lemma": {20: {"word_count": 19, "verse_count": 17}},
            "stem": {30: {"word_count": 5, "verse_count": 5}},
        }

        result = await fetch_word_morphology(_pool(), ayah_key="1:1", word_position=1)

        entry = result.words[0]
        assert entry.root == "سمو"
        assert entry.root_frequency.word_count == 42
        assert entry.root_frequency.verse_count == 38
        assert entry.lemma == "اسم"
        assert entry.lemma_frequency.word_count == 19
        assert entry.stem == "بسم"
        assert entry.stem_frequency.word_count == 5
        assert entry.translation == "In the name"
        assert entry.grammatical_features is not None
        assert len(entry.morpheme_segments) == 1
        assert entry.morpheme_segments[0].part_of_speech_key == "N"
        assert entry.morpheme_segments[0].root == "سمو"
        assert entry.morpheme_segments[0].lemma == "اسم"


# ===========================================================================
# fetch_word_paradigm — pipeline tests (mocked query layer)
# ===========================================================================


class TestParadigmPipeline:
    @patch(f"{_FP}.get_word_visible_segments")
    @patch(f"{_FP}.get_words_for_verse")
    @patch(f"{_FP}.resolve_verse_by_key")
    async def test_non_verbal_word_returns_unavailable(
        self, m_verse, m_words, m_segs,
    ):
        m_verse.return_value = _verse_rec()
        m_words.return_value = [_word_rec(word_id=100)]
        m_segs.return_value = [
            _rec(part_of_speech_key="N", part_of_speech_name="noun",
                 pos_tags="NOM,GEN", verb_form=None),
        ]

        result = await fetch_word_paradigm(_pool(), ayah_key="1:1", word_position=1)

        assert result.paradigm_available is False
        assert "noun" in result.paradigm_unavailable_reason

    @patch(f"{_FP}.get_gloss_fallback_batch")
    @patch(f"{_FP}.get_candidate_lemmas")
    @patch(f"{_FP}.get_stems_for_lemma")
    @patch(f"{_FP}.resolve_root_for_word")
    @patch(f"{_FP}.resolve_lemma_for_word")
    @patch(f"{_FP}.get_word_visible_segments")
    @patch(f"{_FP}.get_words_for_verse")
    @patch(f"{_FP}.resolve_verse_by_key")
    async def test_verbal_word_builds_paradigm(
        self, m_verse, m_words, m_segs, m_lemma, m_root,
        m_stems, m_candidates, m_gloss,
    ):
        m_verse.return_value = _verse_rec()
        m_words.return_value = [_word_rec(word_id=200)]
        m_segs.return_value = [
            _rec(part_of_speech_key="V", part_of_speech_name="verb",
                 pos_tags="PERF,VF:1,3MS", verb_form="I"),
        ]
        m_lemma.return_value = _rec(dict_lemma_id=20, lemma_value="قَالَ")
        m_root.return_value = _rec(dict_root_id=10, root_value="قول")
        m_stems.return_value = [
            _rec(dict_stem_id=30, value="قَالَ", clean="قال",
                 pos_tags="PERF,3MS", grammar_term_desc_english="perfect",
                 word_count=300),
            _rec(dict_stem_id=31, value="يَقُولُ", clean="يقول",
                 pos_tags="IMPF,3MS,MOOD:IND", grammar_term_desc_english="imperfect",
                 word_count=200),
            _rec(dict_stem_id=32, value="قُلْ", clean="قل",
                 pos_tags="IMPV,2MS", grammar_term_desc_english="imperative",
                 word_count=50),
        ]
        m_candidates.return_value = [
            _rec(dict_lemma_id=20, value="قَالَ", clean="قال",
                 gloss_en="to say", verb_form="I", frequency=550),
        ]
        m_gloss.return_value = {}

        result = await fetch_word_paradigm(_pool(), ayah_key="1:1", word_position=1)

        assert result.paradigm_available is True
        assert result.root == "قول"
        assert result.lemma == "قَالَ"
        assert result.verb_form == 1
        assert len(result.paradigm["perfect"]) == 1
        assert result.paradigm["perfect"][0].stem == "قَالَ"
        assert result.paradigm["perfect"][0].count == 300
        assert len(result.paradigm["imperfect"]) == 1
        assert result.paradigm["imperfect"][0].count == 200
        assert len(result.paradigm["imperative"]) == 1
        assert result.paradigm["imperative"][0].count == 50
        assert len(result.candidate_lemmas) == 1
        assert result.candidate_lemmas[0].lemma == "قَالَ"
        assert result.candidate_lemmas[0].gloss == "to say"
        assert result.total_forms_in_quran["stems_in_paradigm"] == 3
        assert result.total_forms_in_quran["lemma_words"] == 550

    @patch(f"{_FP}.get_gloss_fallback_batch")
    @patch(f"{_FP}.get_candidate_lemmas")
    @patch(f"{_FP}.get_stems_for_lemma")
    @patch(f"{_FP}.resolve_root_for_word")
    @patch(f"{_FP}.resolve_lemma_for_word")
    @patch(f"{_FP}.get_word_visible_segments")
    @patch(f"{_FP}.get_words_for_verse")
    @patch(f"{_FP}.resolve_verse_by_key")
    async def test_no_lemma_returns_unavailable(
        self, m_verse, m_words, m_segs, m_lemma, m_root,
        m_stems, m_candidates, m_gloss,
    ):
        m_verse.return_value = _verse_rec()
        m_words.return_value = [_word_rec(word_id=200)]
        m_segs.return_value = [
            _rec(part_of_speech_key="V", part_of_speech_name="verb",
                 pos_tags="PERF,3MS", verb_form=None),
        ]
        m_lemma.return_value = None
        m_root.return_value = _rec(dict_root_id=10, root_value="قول")

        result = await fetch_word_paradigm(_pool(), ayah_key="1:1", word_position=1)

        assert result.paradigm_available is False
        assert "No lemma" in result.paradigm_unavailable_reason

    @patch(f"{_FP}.get_gloss_fallback_batch")
    @patch(f"{_FP}.get_candidate_lemmas")
    @patch(f"{_FP}.get_stems_for_lemma")
    @patch(f"{_FP}.resolve_root_for_word")
    @patch(f"{_FP}.resolve_lemma_for_word")
    @patch(f"{_FP}.get_word_visible_segments")
    @patch(f"{_FP}.get_words_for_verse")
    @patch(f"{_FP}.resolve_verse_by_key")
    async def test_no_verbal_stems_returns_unavailable(
        self, m_verse, m_words, m_segs, m_lemma, m_root,
        m_stems, m_candidates, m_gloss,
    ):
        m_verse.return_value = _verse_rec()
        m_words.return_value = [_word_rec(word_id=200)]
        m_segs.return_value = [
            _rec(part_of_speech_key="V", part_of_speech_name="verb",
                 pos_tags="PERF,3MS", verb_form=None),
        ]
        m_lemma.return_value = _rec(dict_lemma_id=20, lemma_value="قَالَ")
        m_root.return_value = _rec(dict_root_id=10, root_value="قول")
        m_stems.return_value = [
            _rec(dict_stem_id=30, value="قَوْل", clean="قول",
                 pos_tags="NOM,GEN", grammar_term_desc_english="noun",
                 word_count=100),
        ]
        m_candidates.return_value = [
            _rec(dict_lemma_id=20, value="قَالَ", clean="قال",
                 gloss_en="to say", verb_form=None, frequency=100),
        ]
        m_gloss.return_value = {}

        result = await fetch_word_paradigm(_pool(), ayah_key="1:1", word_position=1)

        assert result.paradigm_available is False
        assert "No verbal stems" in result.paradigm_unavailable_reason
        assert len(result.candidate_lemmas) == 1

    @patch(f"{_FP}.get_gloss_fallback_batch")
    @patch(f"{_FP}.get_candidate_lemmas")
    @patch(f"{_FP}.resolve_root_by_text")
    async def test_root_input_populates_candidate_lemmas(
        self, m_root_text, m_candidates, m_gloss,
    ):
        m_root_text.return_value = _rec(dict_root_id=10, root_value="قول")
        m_candidates.side_effect = [
            [
                _rec(dict_lemma_id=20, value="قَالَ", clean="قال",
                     gloss_en=None, verb_form="I", frequency=550),
                _rec(dict_lemma_id=21, value="قَوْل", clean="قول",
                     gloss_en="speech", verb_form=None, frequency=200),
            ],
            [
                _rec(dict_lemma_id=20, value="قَالَ", clean="قال",
                     gloss_en=None, verb_form="I", frequency=550),
                _rec(dict_lemma_id=21, value="قَوْل", clean="قول",
                     gloss_en="speech", verb_form=None, frequency=200),
            ],
        ]
        m_gloss.return_value = {20: "to say"}

        result = await fetch_word_paradigm(_pool(), root="قول")

        assert result.root == "قول"
        assert len(result.candidate_lemmas) == 2
        assert result.candidate_lemmas[0].gloss == "to say"
        assert result.candidate_lemmas[1].gloss == "speech"


# ===========================================================================
# fetch_word_concordance — pipeline tests (mocked query layer)
# ===========================================================================


class TestConcordancePipeline:
    @patch(f"{_FC}.resolve_root_id")
    @patch(f"{_FC}.query_concordance_paginated")
    async def test_valid_match_by_values(self, m_query, m_root):
        m_root.return_value = 10
        m_query.return_value = ([], 0, 0)

        for val in ("all", "root", "lemma", "stem"):
            result = await fetch_word_concordance(
                _pool(), root="قول", match_by=val,
            )
            assert result.total_verses == 0

    @patch(f"{_FC}.resolve_root_id")
    @patch(f"{_FC}.query_concordance_paginated")
    async def test_valid_group_by_values(self, m_query, m_root):
        m_root.return_value = 10
        m_query.return_value = ([], 0, 0)

        for val in ("verse", "word"):
            result = await fetch_word_concordance(
                _pool(), root="قول", group_by=val,
            )
            assert result.group_by == val

    @patch(f"{_FC}.resolve_root_id")
    @patch(f"{_FC}.query_concordance_paginated")
    async def test_valid_page_size_boundaries(self, m_query, m_root):
        m_root.return_value = 10
        m_query.return_value = ([], 0, 0)

        for size in (1, 50, 100):
            result = await fetch_word_concordance(
                _pool(), root="قول", page_size=size,
            )
            assert result.page_size == size

    @patch(f"{_FC}.resolve_root_id")
    @patch(f"{_FC}.query_concordance_paginated")
    async def test_verse_grouping(self, m_query, m_root):
        m_root.return_value = 10
        m_query.return_value = (
            [
                _rec(verse_key="2:255", position=1, text_uthmani="اللَّهُ",
                     en_transliteration="allahu", match_level="root",
                     verse_text="اللَّهُ لَا إِلَٰهَ إِلَّا هُوَ",
                     verse_score=3, word_score=1,
                     total_verses=1, total_words=2),
                _rec(verse_key="2:255", position=3, text_uthmani="إِلَٰهَ",
                     en_transliteration="ilaha", match_level="lemma",
                     verse_text="اللَّهُ لَا إِلَٰهَ إِلَّا هُوَ",
                     verse_score=3, word_score=3,
                     total_verses=1, total_words=2),
            ],
            1, 2,
        )

        result = await fetch_word_concordance(
            _pool(), root="قول", group_by="verse",
        )

        assert result.group_by == "verse"
        assert result.total_verses == 1
        assert result.total_words == 2
        assert len(result.results) == 1
        assert result.results[0].ayah_key == "2:255"
        assert len(result.results[0].matched_words) == 2
        assert result.results[0].matched_words[0].position == 1
        assert result.results[0].matched_words[1].match_level == "lemma"

    @patch(f"{_FC}.resolve_root_id")
    @patch(f"{_FC}.query_concordance_paginated")
    async def test_word_grouping(self, m_query, m_root):
        m_root.return_value = 10
        m_query.return_value = (
            [
                _rec(verse_key="2:255", position=1, text_uthmani="اللَّهُ",
                     en_transliteration="allahu", match_level="exact",
                     verse_text="اللَّهُ لَا إِلَٰهَ",
                     word_score=5, verse_score=5,
                     total_verses=1, total_words=1),
            ],
            1, 1,
        )

        result = await fetch_word_concordance(
            _pool(), root="قول", group_by="word",
        )

        assert result.group_by == "word"
        assert len(result.word_results) == 1
        assert result.word_results[0].ayah_key == "2:255"
        assert result.word_results[0].position == 1
        assert result.word_results[0].score == 5.0

    @patch(f"{_FC}.resolve_root_id")
    @patch(f"{_FC}.query_concordance_paginated")
    async def test_empty_results(self, m_query, m_root):
        m_root.return_value = 10
        m_query.return_value = ([], 0, 0)

        result = await fetch_word_concordance(_pool(), root="قول")

        assert result.total_verses == 0
        assert result.total_words == 0
        assert result.results == []
        assert result.word_results == []


# ===========================================================================
# Morphology MCP tool wrappers — public error contract and success paths
# ===========================================================================


@dataclass
class _StubToolAppContext:
    db_pool: object | None = True


@asynccontextmanager
async def _tool_lifespan(_server) -> AsyncIterator[_StubToolAppContext]:
    yield _StubToolAppContext()


@asynccontextmanager
async def _tool_no_db_lifespan(_server) -> AsyncIterator[_StubToolAppContext]:
    yield _StubToolAppContext(db_pool=None)


@pytest.fixture()
def mcp_morphology_tools() -> FastMCP:
    server = FastMCP("morphology-tool-test", lifespan=_tool_lifespan)
    morphology_fetch_tool.register(server)
    paradigm_tool.register(server)
    concordance_tool.register(server)
    return server


@pytest.fixture()
def mcp_morphology_tools_no_db() -> FastMCP:
    server = FastMCP("morphology-tool-no-db-test", lifespan=_tool_no_db_lifespan)
    morphology_fetch_tool.register(server)
    paradigm_tool.register(server)
    concordance_tool.register(server)
    return server


def _stub_settings() -> SimpleNamespace:
    voyage = SimpleNamespace(
        api_key=SimpleNamespace(get_secret_value=lambda: ""),
        model="voyage-3.5",
        top_k=20,
        timeout_seconds=10.0,
    )
    return SimpleNamespace(voyage=voyage)


def _sample_morphology_response() -> MorphologyResponse:
    return MorphologyResponse(
        ayah_key="1:1",
        words=[
            WordMorphologyEntry(
                word_id=1,
                position=1,
                text_uthmani="بِسْمِ",
                lemma="اسم",
            )
        ],
        input_mode="ayah_key",
        other_occurrences_count=None,
    )


def _sample_paradigm_response() -> ParadigmResponse:
    return ParadigmResponse(
        word={
            "text_uthmani": "قَالَ",
            "text_simple": "قال",
            "transliteration": "qala",
            "ayah_key": "2:30",
            "position": 8,
        },
        root="قول",
        lemma="قَالَ",
        paradigm_available=True,
        paradigm={
            "perfect": [ParadigmStem(stem="قَالَ", description="perfect", count=300)],
            "imperfect": [ParadigmStem(stem="يَقُولُ", description="imperfect", count=200)],
            "imperative": [ParadigmStem(stem="قُلْ", description="imperative", count=50)],
        },
        candidate_lemmas=[
            CandidateLemma(lemma="قَالَ", verb_form=1, count=550, gloss="to say"),
        ],
        total_forms_in_quran={"stems_in_paradigm": 3, "lemma_words": 550},
    )


def _sample_concordance_response() -> ConcordanceResponse:
    return ConcordanceResponse(
        query={"root": "ع ل م"},
        match_by="all",
        group_by="word",
        total_verses=1,
        total_words=1,
        page=1,
        page_size=20,
        word_results=[],
    )


class TestMorphologyToolErrorContract:
    async def test_fetch_word_morphology_missing_db_uses_service_unavailable(
        self, mcp_morphology_tools_no_db: FastMCP
    ):
        with pytest.raises(ToolError, match=r"^\[service_unavailable\] Database not available$"):
            async with Client(mcp_morphology_tools_no_db) as client:
                await client.call_tool("fetch_word_morphology", {"ayah_key": "1:1"})

    async def test_fetch_word_paradigm_missing_db_uses_service_unavailable(
        self, mcp_morphology_tools_no_db: FastMCP
    ):
        with pytest.raises(ToolError, match=r"^\[service_unavailable\] Database not available$"):
            async with Client(mcp_morphology_tools_no_db) as client:
                await client.call_tool("fetch_word_paradigm", {"lemma": "قَالَ"})

    async def test_fetch_word_concordance_missing_db_uses_service_unavailable(
        self, mcp_morphology_tools_no_db: FastMCP
    ):
        with pytest.raises(ToolError, match=r"^\[service_unavailable\] Database not available$"):
            async with Client(mcp_morphology_tools_no_db) as client:
                await client.call_tool("fetch_word_concordance", {"root": "ع ل م"})

    async def test_fetch_word_morphology_validation_uses_invalid_request(
        self, mcp_morphology_tools: FastMCP, monkeypatch: pytest.MonkeyPatch
    ):
        async def _raise_value_error(**_kwargs) -> MorphologyResponse:
            raise ValueError("bad morphology input")

        monkeypatch.setattr(morphology_fetch_tool, "fetch_word_morphology", _raise_value_error)

        with pytest.raises(ToolError, match=r"^\[invalid_request\] bad morphology input$"):
            async with Client(mcp_morphology_tools) as client:
                await client.call_tool("fetch_word_morphology", {"ayah_key": "1:1"})

    async def test_fetch_word_paradigm_validation_uses_invalid_request(
        self, mcp_morphology_tools: FastMCP, monkeypatch: pytest.MonkeyPatch
    ):
        async def _raise_value_error(**_kwargs) -> ParadigmResponse:
            raise ValueError("bad paradigm input")

        monkeypatch.setattr(paradigm_tool, "fetch_word_paradigm", _raise_value_error)

        with pytest.raises(ToolError, match=r"^\[invalid_request\] bad paradigm input$"):
            async with Client(mcp_morphology_tools) as client:
                await client.call_tool("fetch_word_paradigm", {"lemma": "قَالَ"})

    async def test_fetch_word_concordance_validation_uses_invalid_request(
        self, mcp_morphology_tools: FastMCP, monkeypatch: pytest.MonkeyPatch
    ):
        async def _raise_value_error(**_kwargs) -> ConcordanceResponse:
            raise ValueError("bad concordance input")

        monkeypatch.setattr(concordance_tool, "get_settings", _stub_settings)
        monkeypatch.setattr(concordance_tool, "fetch_word_concordance", _raise_value_error)

        with pytest.raises(ToolError, match=r"^\[invalid_request\] bad concordance input$"):
            async with Client(mcp_morphology_tools) as client:
                await client.call_tool("fetch_word_concordance", {"root": "ع ل م", "group_by": "word"})


class TestMorphologyToolSuccess:
    async def test_fetch_word_concordance_schema_uses_literal_modes(
        self, mcp_morphology_tools: FastMCP
    ):
        async with Client(mcp_morphology_tools) as client:
            tools = await client.list_tools()

        concordance = {tool.name: tool for tool in tools}["fetch_word_concordance"]
        assert concordance.inputSchema["properties"]["match_by"]["enum"] == [
            "all",
            "root",
            "lemma",
            "stem",
        ]
        assert concordance.inputSchema["properties"]["group_by"]["enum"] == [
            "verse",
            "word",
        ]

    async def test_fetch_word_morphology_success(
        self, mcp_morphology_tools: FastMCP, monkeypatch: pytest.MonkeyPatch
    ):
        async def _ok(**_kwargs) -> MorphologyResponse:
            return _sample_morphology_response()

        monkeypatch.setattr(morphology_fetch_tool, "fetch_word_morphology", _ok)

        async with Client(mcp_morphology_tools) as client:
            result = await client.call_tool("fetch_word_morphology", {"ayah_key": "1:1"})

        assert result.structured_content["ayah_key"] == "1:1"
        assert result.structured_content["input_mode"] == "ayah_key"
        assert result.structured_content["words"][0]["lemma"] == "اسم"

    async def test_fetch_word_paradigm_success(
        self, mcp_morphology_tools: FastMCP, monkeypatch: pytest.MonkeyPatch
    ):
        async def _ok(**_kwargs) -> ParadigmResponse:
            return _sample_paradigm_response()

        monkeypatch.setattr(paradigm_tool, "fetch_word_paradigm", _ok)

        async with Client(mcp_morphology_tools) as client:
            result = await client.call_tool("fetch_word_paradigm", {"lemma": "قَالَ"})

        assert result.structured_content["paradigm_available"] is True
        assert result.structured_content["lemma"] == "قَالَ"
        assert result.structured_content["candidate_lemmas"][0]["gloss"] == "to say"

    async def test_fetch_word_concordance_success(
        self, mcp_morphology_tools: FastMCP, monkeypatch: pytest.MonkeyPatch
    ):
        async def _ok(**_kwargs) -> ConcordanceResponse:
            return _sample_concordance_response()

        monkeypatch.setattr(concordance_tool, "get_settings", _stub_settings)
        monkeypatch.setattr(concordance_tool, "fetch_word_concordance", _ok)

        async with Client(mcp_morphology_tools) as client:
            result = await client.call_tool("fetch_word_concordance", {"root": "ع ل م", "group_by": "word"})

        assert result.structured_content["group_by"] == "word"
        assert result.structured_content["total_verses"] == 1
