from __future__ import annotations

from dataclasses import dataclass, field

import pytest

import quran_mcp.lib.search.common as search_common
from quran_mcp.lib.search.common import (
    AyahMemoryRecord,
    TranslationSearchSelection,
    build_ayah_key_filter,
    build_edition_filter,
    combine_filters,
    build_surah_filter,
    detect_query_language,
    memory_to_ayah_record,
    parse_ayah_key,
    resolve_translation_editions,
    resolve_translation_search_selection,
)


# =============================================================================
# detect_query_language
# =============================================================================


def test_detect_arabic_short_single_word():
    lang, score = detect_query_language("صبر")
    assert lang == "ar"
    assert score == 1.0


def test_detect_arabic_short_two_words():
    lang, score = detect_query_language("صبر وتوكل")
    assert lang == "ar"
    assert score == 1.0


def test_detect_arabic_longer_text():
    lang, score = detect_query_language("بسم الله الرحمن الرحيم الحمد لله رب العالمين")
    assert lang == "ar"


def test_detect_english():
    lang, score = detect_query_language("the meaning of patience in the Quran")
    assert lang == "en"
    assert score > 0.0


def test_detect_empty_string():
    lang, score = detect_query_language("")
    assert lang == "en"
    assert score == 0.0


def test_detect_whitespace_only():
    lang, score = detect_query_language("   \t\n  ")
    assert lang == "en"
    assert score == 0.0


def test_detect_none_handled():
    lang, score = detect_query_language(None)
    assert lang == "en"
    assert score == 0.0


def test_detect_returns_tuple():
    result = detect_query_language("hello")
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_detect_score_range():
    _, score = detect_query_language("some text to detect")
    assert 0.0 <= score <= 1.0


def test_detect_non_arabic_without_fast_langdetect_falls_back_to_english(monkeypatch):
    monkeypatch.setattr(search_common, "_detect_with_fast_langdetect", lambda _query: None)

    lang, score = detect_query_language("hello")
    assert lang == "en"
    assert score == 0.0


def test_detect_non_arabic_with_detector_result(monkeypatch):
    monkeypatch.setattr(
        search_common,
        "_detect_with_fast_langdetect",
        lambda _query: [{"lang": "fr", "score": 0.93}],
    )

    lang, score = detect_query_language("la signification de la patience dans le Coran")
    assert lang == "fr"
    assert score == 0.93


# =============================================================================
# parse_ayah_key
# =============================================================================


def test_parse_valid_ayah_key():
    assert parse_ayah_key("2:255") == (2, 255)


def test_parse_first_ayah():
    assert parse_ayah_key("1:1") == (1, 1)


def test_parse_large_numbers():
    assert parse_ayah_key("114:6") == (114, 6)


def test_parse_invalid_no_colon():
    with pytest.raises(ValueError):
        parse_ayah_key("2255")


def test_parse_invalid_too_many_colons():
    with pytest.raises(ValueError):
        parse_ayah_key("2:255:1")


def test_parse_invalid_non_numeric():
    with pytest.raises(ValueError):
        parse_ayah_key("abc:def")


def test_parse_empty_string():
    with pytest.raises(ValueError):
        parse_ayah_key("")


# =============================================================================
# build_surah_filter
# =============================================================================


def test_surah_filter_none():
    assert build_surah_filter(None) is None


def test_surah_filter_returns_string():
    result = build_surah_filter(2)
    assert isinstance(result, str)
    assert "2" in result


def test_surah_filter_contains_surah_field():
    result = build_surah_filter(7)
    assert "surah" in result


# =============================================================================
# _build_edition_filter (tafsir + translation)
# =============================================================================


def test_edition_filter_empty_list():
    assert build_edition_filter([]) is None


def test_edition_filter_single_id():
    result = build_edition_filter(["en-ibn-kathir"])
    assert "en-ibn-kathir" in result
    assert "OR" not in result


def test_edition_filter_multiple_ids():
    result = build_edition_filter(["en-ibn-kathir", "en-saadi"])
    assert "en-ibn-kathir" in result
    assert "en-saadi" in result
    assert "OR" in result


def test_edition_filter_special_chars_escaped():
    result = build_edition_filter(["O'Brien"])
    assert "O\\'Brien" in result


def test_edition_filter_translation_matches_tafsir():
    result = build_edition_filter(["test-edition"])
    assert result == "CAST(val('$.edition_id') AS TEXT) = 'test-edition'"


def test_ayah_key_filter_single_key():
    result = build_ayah_key_filter(["2:255"])
    assert result == "CAST(val('$.ayah_key') AS TEXT) = '2:255'"


def test_ayah_key_filter_multiple_keys():
    result = build_ayah_key_filter(["2:255", "2:256"])
    assert "OR" in result
    assert "2:255" in result
    assert "2:256" in result


# =============================================================================
# _combine_filters
# =============================================================================


def test_combine_filters_all_none():
    assert combine_filters(None, None, None) is None


def test_combine_filters_single():
    result = combine_filters("surah = 2", None)
    assert result == "surah = 2"


def test_combine_filters_multiple():
    result = combine_filters("surah = 2", "ayah = 255")
    assert "surah = 2" in result
    assert "ayah = 255" in result
    assert "AND" in result


def test_combine_filters_skips_none():
    result = combine_filters(None, "surah = 2", None, "ayah = 255", None)
    assert "surah = 2" in result
    assert "ayah = 255" in result
    assert "AND" in result


def test_combine_filters_no_args():
    assert combine_filters() is None


# =============================================================================
# resolve_translation_editions
# =============================================================================


def test_resolve_translation_editions_auto_low_confidence_searches_all(monkeypatch):
    monkeypatch.setattr(search_common, "detect_query_language", lambda _query: ("fr", 0.2))

    result = resolve_translation_editions("patience", "auto", auto_low_confidence_behavior="all")
    assert result.resolved_ids == []
    assert result.unresolved == []
    assert result.single_best_match is False


def test_resolve_translation_editions_auto_resolves_low_confidence(monkeypatch):
    monkeypatch.setattr(search_common, "detect_query_language", lambda _query: ("fr", 0.2))

    def _resolve(kind, selectors):
        assert kind == "translation"
        assert selectors == "fr"
        from quran_mcp.lib.editions.registry import ResolveResult

        return ResolveResult(resolved=["fr-hamidullah"], unresolved=[])

    monkeypatch.setattr(search_common, "resolve_ids_with_unresolved", _resolve)

    result = resolve_translation_editions("patience", "auto", auto_low_confidence_behavior="resolve")
    assert result.resolved_ids == ["fr-hamidullah"]
    assert result.unresolved == []


def test_resolve_translation_search_selection_builds_filter(monkeypatch):
    monkeypatch.setattr(
        search_common,
        "resolve_translation_editions",
        lambda *_args, **_kwargs: search_common.SearchEditionSelection(
            resolved_ids=["en-abdel-haleem", "en-sahih-international"],
            unresolved=["unknown"],
            single_best_match=False,
        ),
    )

    result = resolve_translation_search_selection("patience", ["en"])

    assert isinstance(result, TranslationSearchSelection)
    assert result.selection.resolved_ids == ["en-abdel-haleem", "en-sahih-international"]
    assert result.selection.unresolved == ["unknown"]
    assert "en-abdel-haleem" in (result.edition_filter or "")
    assert "en-sahih-international" in (result.edition_filter or "")
    assert result.selection.single_best_match is False


# =============================================================================
# memory_to_ayah_record
# =============================================================================


@dataclass
class FakeMemory:
    content: str = ""
    metadata: dict = field(default_factory=dict)
    relevance_score: float | None = None
    source_space_name: str | None = None


def test_memory_to_ayah_record_returns_typed_projection():
    mem = FakeMemory(
        content="typed",
        metadata={"ayah_key": "36:58", "edition_id": "en-abdel-haleem", "lang": "en"},
        relevance_score=0.77,
        source_space_name="translation",
    )
    result = memory_to_ayah_record(mem)
    assert isinstance(result, AyahMemoryRecord)
    assert result.ayah_key == "36:58"
    assert result.surah == 36
    assert result.ayah == 58
    assert result.edition_id == "en-abdel-haleem"
    assert result.relevance_score == 0.77
