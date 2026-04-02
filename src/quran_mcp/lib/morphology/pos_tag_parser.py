"""Deterministic parser for quran.com morphological pos_tags strings.

Maps raw pos_tags (e.g., "IMPF,VF:1,3MP,MOOD:IND") from the
morph_word_segment table into structured GrammaticalFeatures.

No NLP libraries — just static dict lookups and regex parsing.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# --- Person/Gender/Number regex ---
# Matches patterns like "3MP" (3rd person, masculine, plural)
_PGN_RE = re.compile(r"^(?P<person>[123])(?P<gender>[MF])(?P<number>[SDP])$")

# --- Static mappings ---

_PERSON_MAP = {"1": "1st", "2": "2nd", "3": "3rd"}
_GENDER_MAP = {"M": "masculine", "F": "feminine"}
_NUMBER_MAP = {"S": "singular", "D": "dual", "P": "plural"}

_ASPECT_MAP = {
    "PERF": "perfect",
    "IMPF": "imperfect",
    "IMPV": "imperative",
}

_MOOD_MAP = {
    "IND": "indicative",
    "SUBJ": "subjunctive",
    "JUS": "jussive",
}

# Part of speech keys from morph_word_segment.part_of_speech_key
_POS_KEY_MAP = {
    "V": "verb",
    "N": "noun",
    "ADJ": "adjective",
    "PN": "proper noun",
    "PRON": "pronoun",
    "DEM": "demonstrative",
    "REL": "relative",
    "INTG": "interrogative",
    "T": "time adverb",
    "LOC": "location adverb",
    "P": "preposition",
    "CONJ": "conjunction",
    "COND": "conditional",
    "ACC": "accusative particle",  # Used via part_of_speech_key (line ~152).
    # In the tag loop, ACC is shadowed by _CASE_MAP (case check runs first).
    # This is intentional: ACC in pos_tags = case marker, ACC as key = POS.
    "NEG": "negative particle",
    "CERT": "certainty particle",
    "RES": "restriction particle",
    "EXP": "explanation particle",
    "AMD": "amendment particle",
    "ANS": "answer particle",
    "AVR": "aversion particle",
    "CIRC": "circumstantial particle",
    "COM": "comitative particle",
    "EXH": "exhortation particle",
    "EXL": "exclamation particle",
    "FUT": "future particle",
    "INC": "inceptive particle",
    "INT": "interpretation particle",
    "PREV": "preventive particle",
    "PRO": "prohibition particle",
    "REM": "resumption particle",
    "RET": "retraction particle",
    "SUP": "supplementary particle",
    "SUR": "surprise particle",
    "VOC": "vocative particle",
    "INL": "interjectional particle",
}

# Tags that indicate specific features
_CASE_MAP = {
    "NOM": "nominative",
    "ACC": "accusative",
    "GEN": "genitive",
}

_DEFINITENESS_MAP = {
    "DEF": "definite",
    "INDEF": "indefinite",
}

_STATE_MAP = {
    "CNST": "construct",  # إضافة — head of idafa construction
}

# Tags to skip (they are structural, not feature-bearing)
_SKIP_TAGS = {"SUFF", "PREF", "STEM"}


@dataclass(frozen=True, slots=True)
class GrammaticalFeatures:
    """Structured grammatical features parsed from pos_tags."""

    part_of_speech: str | None = None
    person: str | None = None
    gender: str | None = None
    number: str | None = None
    aspect: str | None = None
    mood: str | None = None
    voice: str | None = None
    verb_form: int | None = None
    definiteness: str | None = None
    case: str | None = None
    state: str | None = None
    features_version: str = "v1"
    raw_unrecognized_tags: list[str] = field(default_factory=list)


class PosTagParser:
    """Parse pos_tags strings into structured GrammaticalFeatures.

    Usage:
        parser = PosTagParser()
        features = parser.parse(
            pos_tags="IMPF,VF:1,3MP,MOOD:IND",
            part_of_speech_key="V",
        )
        # GrammaticalFeatures(
        #     part_of_speech="verb", person="3rd", gender="masculine",
        #     number="plural", aspect="imperfect", mood="indicative",
        #     voice="active", verb_form=1, ...
        # )
    """

    def parse(
        self,
        pos_tags: str | None,
        part_of_speech_key: str | None = None,
        verb_form_raw: str | None = None,
    ) -> GrammaticalFeatures:
        """Parse a pos_tags string into structured features.

        Args:
            pos_tags: Comma-separated tags from morph_word_segment.pos_tags.
                      e.g., "IMPF,VF:1,3MP,MOOD:IND"
            part_of_speech_key: From morph_word_segment.part_of_speech_key.
                                e.g., "V", "N", "PRON"
            verb_form_raw: From morph_word_segment.verb_form.
                           e.g., "1", "2", "5"

        Returns:
            GrammaticalFeatures with all recognized features set.
        """
        kwargs: dict[str, Any] = {}
        unrecognized: list[str] = []

        # Part of speech from key
        if part_of_speech_key:
            kwargs["part_of_speech"] = _POS_KEY_MAP.get(
                part_of_speech_key, part_of_speech_key.lower()
            )

        # Verb form from dedicated column
        if verb_form_raw is not None:
            try:
                kwargs["verb_form"] = int(verb_form_raw)
            except (ValueError, TypeError):
                # Intentional: verb_form is optional, continue without it
                logger.debug("Could not parse verb_form as int: %r", verb_form_raw, exc_info=True)

        if not pos_tags:
            return GrammaticalFeatures(**kwargs)

        has_passive = False
        has_aspect = False

        for token in pos_tags.split(","):
            token = token.strip()
            if not token:
                continue

            # Check for key:value tokens
            if ":" in token:
                key, _, value = token.partition(":")

                if key == "MOOD":
                    mood = _MOOD_MAP.get(value)
                    if mood:
                        kwargs["mood"] = mood
                    else:
                        unrecognized.append(token)
                    continue

                if key == "VF":
                    # Verb form — already handled from column, but parse as fallback
                    if "verb_form" not in kwargs:
                        try:
                            kwargs["verb_form"] = int(value)
                        except (ValueError, TypeError):
                            unrecognized.append(token)
                    continue

                # Unknown key:value — record it
                unrecognized.append(token)
                continue

            # Aspect tags
            if token in _ASPECT_MAP:
                kwargs["aspect"] = _ASPECT_MAP[token]
                has_aspect = True
                continue

            # Person/Gender/Number (e.g., "3MP", "2FS", "1S")
            # Handle "1S", "1P" (first person without explicit gender)
            pgn_match = _PGN_RE.match(token)
            if pgn_match:
                kwargs["person"] = _PERSON_MAP[pgn_match.group("person")]
                kwargs["gender"] = _GENDER_MAP[pgn_match.group("gender")]
                kwargs["number"] = _NUMBER_MAP[pgn_match.group("number")]
                continue

            # First person without gender: "1S", "1P", "1D"
            if len(token) == 2 and token[0] == "1" and token[1] in "SDP":
                kwargs["person"] = "1st"
                kwargs["number"] = _NUMBER_MAP[token[1]]
                continue

            # Passive voice marker
            if token == "PASS":
                has_passive = True
                continue

            # Case markers
            if token in _CASE_MAP:
                kwargs["case"] = _CASE_MAP[token]
                continue

            # Definiteness
            if token in _DEFINITENESS_MAP:
                kwargs["definiteness"] = _DEFINITENESS_MAP[token]
                continue

            # Grammatical state (construct / absolute)
            if token in _STATE_MAP:
                kwargs["state"] = _STATE_MAP[token]
                continue

            # Part of speech in tags (e.g., "PRON", "N", "V")
            if token in _POS_KEY_MAP and "part_of_speech" not in kwargs:
                kwargs["part_of_speech"] = _POS_KEY_MAP[token]
                continue

            # Structural markers — skip silently
            if token in _SKIP_TAGS:
                continue

            # Anything else is unrecognized
            unrecognized.append(token)

        # Voice inference: passive if PASS tag present, active if verb with aspect
        if has_passive:
            kwargs["voice"] = "passive"
        elif has_aspect:
            kwargs["voice"] = "active"

        if unrecognized:
            kwargs["raw_unrecognized_tags"] = unrecognized

        return GrammaticalFeatures(**kwargs)
