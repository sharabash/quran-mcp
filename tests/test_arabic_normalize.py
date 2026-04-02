from __future__ import annotations

from quran_mcp.lib.morphology.arabic_normalize import (
    _DIACRITICS,
    normalize_arabic,
)


def _strip_diacritics(text: str) -> str:
    return _DIACRITICS.sub("", text)


class TestNormalizeArabic:
    def test_alif_hamza_above(self):
        assert normalize_arabic("أحمد") == "احمد"

    def test_alif_hamza_below(self):
        assert normalize_arabic("إسلام") == "اسلام"

    def test_alif_madda(self):
        assert normalize_arabic("آمن") == "امن"

    def test_alif_wasla(self):
        assert normalize_arabic("ٱلرَّحْمَـٰنِ") == "الرحمن"

    def test_multiple_alif_variants(self):
        assert normalize_arabic("أإآ") == "ااا"

    def test_ta_marbuta(self):
        assert normalize_arabic("رحمة") == "رحمه"

    def test_tatweel_removed(self):
        assert normalize_arabic("كـتـاب") == "كتاب"

    def test_alif_maqsura_to_ya(self):
        assert normalize_arabic("هدى") == "هدي"

    def test_fatha_removed(self):
        assert normalize_arabic("كَتَبَ") == "كتب"

    def test_damma_removed(self):
        assert normalize_arabic("كُتُب") == "كتب"

    def test_kasra_removed(self):
        assert normalize_arabic("بِسْمِ") == "بسم"

    def test_sukun_removed(self):
        assert normalize_arabic("مِنْ") == "من"

    def test_shadda_removed(self):
        assert normalize_arabic("رَبِّ") == "رب"

    def test_tanwin_fath_removed(self):
        assert normalize_arabic("كِتَابًا") == "كتابا"

    def test_tanwin_damm_removed(self):
        assert normalize_arabic("كِتَابٌ") == "كتاب"

    def test_tanwin_kasr_removed(self):
        assert normalize_arabic("كِتَابٍ") == "كتاب"

    def test_combined_normalization(self):
        assert normalize_arabic("بِسْمِ ٱللَّهِ ٱلرَّحْمَـٰنِ") == "بسم الله الرحمن"

    def test_empty_string(self):
        assert normalize_arabic("") == ""

    def test_already_normalized(self):
        assert normalize_arabic("كتاب") == "كتاب"

    def test_mixed_arabic_latin(self):
        result = normalize_arabic("hello أحمد world")
        assert result == "hello احمد world"

    def test_latin_only(self):
        assert normalize_arabic("hello world") == "hello world"

    def test_whitespace_stripped(self):
        assert normalize_arabic("  كتاب  ") == "كتاب"


class TestStripDiacritics:
    def test_fatha(self):
        assert _strip_diacritics("كَ") == "ك"

    def test_damma(self):
        assert _strip_diacritics("كُ") == "ك"

    def test_kasra(self):
        assert _strip_diacritics("كِ") == "ك"

    def test_sukun(self):
        assert _strip_diacritics("كْ") == "ك"

    def test_shadda(self):
        assert _strip_diacritics("كّ") == "ك"

    def test_tanwin_fath(self):
        assert _strip_diacritics("كً") == "ك"

    def test_tanwin_damm(self):
        assert _strip_diacritics("كٌ") == "ك"

    def test_tanwin_kasr(self):
        assert _strip_diacritics("كٍ") == "ك"

    def test_superscript_alef(self):
        assert _strip_diacritics("كٰ") == "ك"

    def test_multiple_diacritics(self):
        assert _strip_diacritics("بِسْمِ") == "بسم"

    def test_no_diacritics(self):
        assert _strip_diacritics("كتاب") == "كتاب"

    def test_empty_string(self):
        assert _strip_diacritics("") == ""

    def test_preserves_base_letters(self):
        assert _strip_diacritics("الرَّحْمَـٰنِ") == "الرحمـن"


class TestCombinedNormalizationAndStripping:
    def test_fully_diacritized_with_alif_variants(self):
        assert normalize_arabic("أَحْمَدُ") == "احمد"

    def test_ta_marbuta_with_diacritics(self):
        assert normalize_arabic("رَحْمَةً") == "رحمه"

    def test_tatweel_with_diacritics(self):
        assert normalize_arabic("كَـتَـابٌ") == "كتاب"

    def test_alif_maqsura_with_diacritics(self):
        assert normalize_arabic("هُدًى") == "هدي"
