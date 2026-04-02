"""Tests for quran_mcp.lib.presentation.summary.

Covers:
  - format_segments: dict entries, object entries, source_names, empty
  - infer_summary_lang: all-Arabic, mixed, empty
  - build_summary_messages_for_sampling: system+user roles, options, text
  - build_summary_messages_for_prompt: assistant+user roles, no system
"""

from __future__ import annotations

from quran_mcp.lib.editions.types import SummaryPromptConfig
from quran_mcp.lib.presentation.summary import (
    build_summary_messages_for_prompt,
    build_summary_messages_for_sampling,
    format_segments,
    infer_summary_lang,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config() -> SummaryPromptConfig:
    return SummaryPromptConfig(
        sampling_system_template="You are a scholarly summarizer.",
        sampling_user_template="Summarize:\n\nOptions:\n{options}\n\nText:\n{text}",
        prompt_assistant_template="I will summarize the following text.",
        prompt_user_template="Please summarize:\n\nOptions:\n{options}\n\nText:\n{text}",
    )


class _FakeEntry:
    """Mimics a Pydantic model with .ayah and .text attributes."""

    def __init__(self, ayah: str, text: str):
        self.ayah = ayah
        self.text = text


# ---------------------------------------------------------------------------
# format_segments
# ---------------------------------------------------------------------------


class TestFormatSegments:
    def test_dict_entries(self):
        segments = {
            "en-ibn-kathir": [
                {"ayah": "2:255", "text": "Allah — there is no deity except Him."},
            ],
        }
        result = format_segments(segments)
        assert "en-ibn-kathir" in result
        assert "[2:255]" in result
        assert "Allah" in result

    def test_object_entries(self):
        segments = {
            "en-ibn-kathir": [_FakeEntry("2:255", "The Throne Verse.")],
        }
        result = format_segments(segments)
        assert "[2:255]" in result
        assert "The Throne Verse." in result

    def test_source_names_in_header(self):
        segments = {"en-ibn-kathir": [{"ayah": "2:255", "text": "..."}]}
        result = format_segments(
            segments,
            header_template="--- SOURCE: {name} [{edition_id}] ---",
            source_names={"en-ibn-kathir": "Ibn Kathir"},
        )
        assert "Ibn Kathir" in result
        assert "en-ibn-kathir" in result

    def test_multiple_editions(self):
        segments = {
            "en-ibn-kathir": [{"ayah": "2:255", "text": "text-a"}],
            "en-jalalayn": [{"ayah": "2:255", "text": "text-b"}],
        }
        result = format_segments(segments)
        assert "en-ibn-kathir" in result
        assert "en-jalalayn" in result

    def test_empty_segments(self):
        assert format_segments({}) == ""

    def test_entry_with_none_values(self):
        segments = {"ed": [{"ayah": None, "text": None}]}
        result = format_segments(segments)
        assert "[]" in result  # empty ayah renders as []


# ---------------------------------------------------------------------------
# infer_summary_lang
# ---------------------------------------------------------------------------


class TestInferSummaryLang:
    def test_all_arabic(self):
        assert infer_summary_lang(["ar-tabari", "ar-ibn-kathir"]) == "ar"

    def test_mixed(self):
        assert infer_summary_lang(["en-ibn-kathir", "ar-tabari"]) == "en"

    def test_all_english(self):
        assert infer_summary_lang(["en-ibn-kathir", "en-jalalayn"]) == "en"

    def test_empty(self):
        assert infer_summary_lang([]) == "en"

    def test_single_arabic(self):
        assert infer_summary_lang(["ar-tabari"]) == "ar"


# ---------------------------------------------------------------------------
# build_summary_messages_for_sampling
# ---------------------------------------------------------------------------


class TestBuildSamplingMessages:
    def test_returns_system_and_user_roles(self):
        segments = {"en-ibn-kathir": [{"ayah": "2:255", "text": "..."}]}
        messages = build_summary_messages_for_sampling(
            ayah_key="2:255", segments=segments, config=_config(),
        )
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_system_message_is_template(self):
        segments = {"en-ibn-kathir": [{"ayah": "2:255", "text": "..."}]}
        messages = build_summary_messages_for_sampling(
            ayah_key="2:255", segments=segments, config=_config(),
        )
        assert messages[0]["content"] == "You are a scholarly summarizer."

    def test_user_message_contains_options_and_text(self):
        segments = {"en-ibn-kathir": [{"ayah": "2:255", "text": "Throne verse."}]}
        messages = build_summary_messages_for_sampling(
            ayah_key="2:255", segments=segments, config=_config(),
            mode="compare", lang="en", length="short",
        )
        user = messages[1]["content"]
        assert "ayah_key: 2:255" in user
        assert "mode: compare" in user
        assert "length: short" in user
        assert "Throne verse." in user

    def test_focus_included_when_provided(self):
        segments = {"en-ibn-kathir": [{"ayah": "2:255", "text": "..."}]}
        messages = build_summary_messages_for_sampling(
            ayah_key="2:255", segments=segments, config=_config(),
            focus="theological implications",
        )
        assert "focus: theological implications" in messages[1]["content"]

    def test_sources_included_when_provided(self):
        segments = {"en-ibn-kathir": [{"ayah": "2:255", "text": "..."}]}
        messages = build_summary_messages_for_sampling(
            ayah_key="2:255", segments=segments, config=_config(),
            sources=["en-ibn-kathir"],
        )
        assert "sources: en-ibn-kathir" in messages[1]["content"]


# ---------------------------------------------------------------------------
# build_summary_messages_for_prompt
# ---------------------------------------------------------------------------


class TestBuildPromptMessages:
    def test_returns_assistant_and_user_roles(self):
        segments = {"en-ibn-kathir": [{"ayah": "2:255", "text": "..."}]}
        messages = build_summary_messages_for_prompt(
            ayah_key="2:255", segments=segments, config=_config(),
        )
        assert len(messages) == 2
        assert messages[0]["role"] == "assistant"
        assert messages[1]["role"] == "user"

    def test_no_system_role(self):
        segments = {"en-ibn-kathir": [{"ayah": "2:255", "text": "..."}]}
        messages = build_summary_messages_for_prompt(
            ayah_key="2:255", segments=segments, config=_config(),
        )
        roles = [m["role"] for m in messages]
        assert "system" not in roles

    def test_assistant_message_is_template(self):
        segments = {"en-ibn-kathir": [{"ayah": "2:255", "text": "..."}]}
        messages = build_summary_messages_for_prompt(
            ayah_key="2:255", segments=segments, config=_config(),
        )
        assert messages[0]["content"] == "I will summarize the following text."
