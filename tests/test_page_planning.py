"""Unit tests for lib/presentation/page_planning.py — token estimation and page sizing."""
from __future__ import annotations

from quran_mcp.lib.presentation.page_planning import (
    _is_arabic_script,
    _chars_per_token,
    choose_auto_page_size,
    estimate_tokens,
    ARABIC_RATIO,
    DEFAULT_RATIO,
)


def test_is_arabic_script_arabic_text():
    assert _is_arabic_script("بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ") is True


def test_is_arabic_script_english_text():
    assert _is_arabic_script("In the name of God") is False


def test_is_arabic_script_empty():
    assert _is_arabic_script("") is False


def test_chars_per_token_arabic():
    assert _chars_per_token("بسم الله") == ARABIC_RATIO


def test_chars_per_token_english():
    assert _chars_per_token("hello world") == DEFAULT_RATIO


def test_choose_auto_page_size_claude():
    assert choose_auto_page_size("fetch_quran", "claude") == 50


def test_choose_auto_page_size_default():
    assert choose_auto_page_size("fetch_quran", "chatgpt") == 80


def test_choose_auto_page_size_unknown_tool():
    assert choose_auto_page_size("unknown_tool") == 10


def test_estimate_tokens_string():
    tokens = estimate_tokens("hello world test string")
    assert tokens > 0


def test_estimate_tokens_empty_string():
    assert estimate_tokens("") == 0
