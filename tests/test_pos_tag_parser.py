from __future__ import annotations

from quran_mcp.lib.morphology.pos_tag_parser import (
    GrammaticalFeatures,
    PosTagParser,
    _POS_KEY_MAP,
)

parser = PosTagParser()


class TestPartOfSpeech:
    def test_verb(self):
        result = parser.parse(pos_tags=None, part_of_speech_key="V")
        assert result.part_of_speech == "verb"

    def test_noun(self):
        result = parser.parse(pos_tags=None, part_of_speech_key="N")
        assert result.part_of_speech == "noun"

    def test_proper_noun(self):
        result = parser.parse(pos_tags=None, part_of_speech_key="PN")
        assert result.part_of_speech == "proper noun"

    def test_adjective(self):
        result = parser.parse(pos_tags=None, part_of_speech_key="ADJ")
        assert result.part_of_speech == "adjective"

    def test_pronoun(self):
        result = parser.parse(pos_tags=None, part_of_speech_key="PRON")
        assert result.part_of_speech == "pronoun"

    def test_preposition(self):
        result = parser.parse(pos_tags=None, part_of_speech_key="P")
        assert result.part_of_speech == "preposition"

    def test_conjunction(self):
        result = parser.parse(pos_tags=None, part_of_speech_key="CONJ")
        assert result.part_of_speech == "conjunction"

    def test_unknown_key_lowered(self):
        result = parser.parse(pos_tags=None, part_of_speech_key="XYZZY")
        assert result.part_of_speech == "xyzzy"

    def test_pos_in_tags_when_no_key(self):
        result = parser.parse(pos_tags="PRON", part_of_speech_key=None)
        assert result.part_of_speech == "pronoun"


class TestPersonExtraction:
    def test_first_person(self):
        result = parser.parse(pos_tags="1MS")
        assert result.person == "1st"

    def test_second_person(self):
        result = parser.parse(pos_tags="2MS")
        assert result.person == "2nd"

    def test_third_person(self):
        result = parser.parse(pos_tags="3MS")
        assert result.person == "3rd"

    def test_first_person_no_gender_singular(self):
        result = parser.parse(pos_tags="1S")
        assert result.person == "1st"
        assert result.number == "singular"
        assert result.gender is None

    def test_first_person_no_gender_plural(self):
        result = parser.parse(pos_tags="1P")
        assert result.person == "1st"
        assert result.number == "plural"
        assert result.gender is None

    def test_first_person_no_gender_dual(self):
        result = parser.parse(pos_tags="1D")
        assert result.person == "1st"
        assert result.number == "dual"
        assert result.gender is None


class TestGenderExtraction:
    def test_masculine(self):
        result = parser.parse(pos_tags="3MS")
        assert result.gender == "masculine"

    def test_feminine(self):
        result = parser.parse(pos_tags="3FS")
        assert result.gender == "feminine"


class TestNumberExtraction:
    def test_singular(self):
        result = parser.parse(pos_tags="3MS")
        assert result.number == "singular"

    def test_dual(self):
        result = parser.parse(pos_tags="3MD")
        assert result.number == "dual"

    def test_plural(self):
        result = parser.parse(pos_tags="3MP")
        assert result.number == "plural"


class TestCombinedPersonGenderNumber:
    def test_third_masculine_singular(self):
        result = parser.parse(pos_tags="3MS")
        assert result.person == "3rd"
        assert result.gender == "masculine"
        assert result.number == "singular"

    def test_second_feminine_plural(self):
        result = parser.parse(pos_tags="2FP")
        assert result.person == "2nd"
        assert result.gender == "feminine"
        assert result.number == "plural"

    def test_third_masculine_dual(self):
        result = parser.parse(pos_tags="3MD")
        assert result.person == "3rd"
        assert result.gender == "masculine"
        assert result.number == "dual"


class TestAspect:
    def test_perfect(self):
        result = parser.parse(pos_tags="PERF")
        assert result.aspect == "perfect"

    def test_imperfect(self):
        result = parser.parse(pos_tags="IMPF")
        assert result.aspect == "imperfect"

    def test_imperative(self):
        result = parser.parse(pos_tags="IMPV")
        assert result.aspect == "imperative"


class TestMood:
    def test_indicative(self):
        result = parser.parse(pos_tags="MOOD:IND")
        assert result.mood == "indicative"

    def test_subjunctive(self):
        result = parser.parse(pos_tags="MOOD:SUBJ")
        assert result.mood == "subjunctive"

    def test_jussive(self):
        result = parser.parse(pos_tags="MOOD:JUS")
        assert result.mood == "jussive"

    def test_unknown_mood_unrecognized(self):
        result = parser.parse(pos_tags="MOOD:UNKNOWN")
        assert result.mood is None
        assert "MOOD:UNKNOWN" in result.raw_unrecognized_tags


class TestCase:
    def test_nominative(self):
        result = parser.parse(pos_tags="NOM")
        assert result.case == "nominative"

    def test_accusative(self):
        result = parser.parse(pos_tags="ACC")
        assert result.case == "accusative"

    def test_genitive(self):
        result = parser.parse(pos_tags="GEN")
        assert result.case == "genitive"


class TestDefiniteness:
    def test_definite(self):
        result = parser.parse(pos_tags="DEF")
        assert result.definiteness == "definite"

    def test_indefinite(self):
        result = parser.parse(pos_tags="INDEF")
        assert result.definiteness == "indefinite"


class TestVoice:
    def test_passive(self):
        result = parser.parse(pos_tags="PERF,PASS,3MS")
        assert result.voice == "passive"

    def test_active_inferred_from_aspect(self):
        result = parser.parse(pos_tags="PERF,3MS")
        assert result.voice == "active"

    def test_no_voice_without_aspect_or_passive(self):
        result = parser.parse(pos_tags="NOM,DEF")
        assert result.voice is None


class TestVerbForm:
    def test_verb_form_from_raw(self):
        result = parser.parse(pos_tags=None, verb_form_raw="1")
        assert result.verb_form == 1

    def test_verb_form_from_tag(self):
        result = parser.parse(pos_tags="VF:4")
        assert result.verb_form == 4

    def test_verb_form_raw_takes_precedence(self):
        result = parser.parse(pos_tags="VF:4", verb_form_raw="2")
        assert result.verb_form == 2

    def test_verb_form_invalid_raw(self):
        result = parser.parse(pos_tags=None, verb_form_raw="abc")
        assert result.verb_form is None

    def test_verb_form_none_raw(self):
        result = parser.parse(pos_tags=None, verb_form_raw=None)
        assert result.verb_form is None


class TestState:
    def test_construct(self):
        result = parser.parse(pos_tags="CNST")
        assert result.state == "construct"


class TestSkipTags:
    def test_suff_skipped(self):
        result = parser.parse(pos_tags="SUFF")
        assert result.raw_unrecognized_tags == []

    def test_pref_skipped(self):
        result = parser.parse(pos_tags="PREF")
        assert result.raw_unrecognized_tags == []

    def test_stem_skipped(self):
        result = parser.parse(pos_tags="STEM")
        assert result.raw_unrecognized_tags == []


class TestFullTagParsing:
    def test_full_verb_tag(self):
        result = parser.parse(
            pos_tags="IMPF,VF:1,3MP,MOOD:IND",
            part_of_speech_key="V",
        )
        assert result.part_of_speech == "verb"
        assert result.aspect == "imperfect"
        assert result.person == "3rd"
        assert result.gender == "masculine"
        assert result.number == "plural"
        assert result.mood == "indicative"
        assert result.verb_form == 1
        assert result.voice == "active"

    def test_noun_tag(self):
        result = parser.parse(
            pos_tags="ACC,INDEF",
            part_of_speech_key="N",
        )
        assert result.part_of_speech == "noun"
        assert result.case == "accusative"
        assert result.definiteness == "indefinite"

    def test_passive_verb(self):
        result = parser.parse(
            pos_tags="PERF,PASS,3MS",
            part_of_speech_key="V",
            verb_form_raw="1",
        )
        assert result.voice == "passive"
        assert result.aspect == "perfect"
        assert result.verb_form == 1


class TestEmptyAndUnknownTags:
    def test_none_pos_tags(self):
        result = parser.parse(pos_tags=None)
        assert result == GrammaticalFeatures()

    def test_empty_pos_tags(self):
        result = parser.parse(pos_tags="")
        assert result == GrammaticalFeatures()

    def test_unknown_tag_recorded(self):
        result = parser.parse(pos_tags="XYZZY")
        assert "XYZZY" in result.raw_unrecognized_tags

    def test_unknown_key_value_recorded(self):
        result = parser.parse(pos_tags="FOO:BAR")
        assert "FOO:BAR" in result.raw_unrecognized_tags

    def test_whitespace_in_tokens(self):
        result = parser.parse(pos_tags=" PERF , 3MS ")
        assert result.aspect == "perfect"
        assert result.person == "3rd"


class TestPosKeyMap:
    def test_all_keys_present(self):
        expected = {
            "V", "N", "ADJ", "PN", "PRON", "DEM", "REL", "INTG", "T", "LOC",
            "P", "CONJ", "COND", "ACC", "NEG", "CERT", "RES", "EXP", "AMD",
            "ANS", "AVR", "CIRC", "COM", "EXH", "EXL", "FUT", "INC", "INT",
            "PREV", "PRO", "REM", "RET", "SUP", "SUR", "VOC", "INL",
        }
        assert set(_POS_KEY_MAP.keys()) == expected

    def test_demonstrative(self):
        assert _POS_KEY_MAP["DEM"] == "demonstrative"

    def test_relative(self):
        assert _POS_KEY_MAP["REL"] == "relative"

    def test_time_adverb(self):
        assert _POS_KEY_MAP["T"] == "time adverb"

    def test_location_adverb(self):
        assert _POS_KEY_MAP["LOC"] == "location adverb"

    def test_vocative_particle(self):
        assert _POS_KEY_MAP["VOC"] == "vocative particle"
