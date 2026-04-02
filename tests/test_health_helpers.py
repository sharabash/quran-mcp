from __future__ import annotations

import time

import pytest

from quran_mcp.lib.site.health import (
    _extract_grounding_nonce,
    _first_text_block,
    _get_cached,
    _grounding_suppressed,
    _set_cache,
    build_health_runtime_state,
    clear_cache,
)


@pytest.fixture(autouse=True)
def _clean_cache():
    runtime_state = build_health_runtime_state()
    yield runtime_state
    clear_cache(runtime_state=runtime_state)


class TestExtractGroundingNonce:
    def test_key_value_format(self):
        text = "some text\nGROUNDING_NONCE: gnd-abc123\nmore text"
        assert _extract_grounding_nonce(text) == "gnd-abc123"

    def test_xml_tag_format(self):
        text = "some text\n<grounding_nonce>gnd-def456</grounding_nonce>\nmore"
        assert _extract_grounding_nonce(text) == "gnd-def456"

    def test_key_value_preferred_over_xml(self):
        text = "GROUNDING_NONCE: gnd-first\n<grounding_nonce>gnd-second</grounding_nonce>"
        assert _extract_grounding_nonce(text) == "gnd-first"

    def test_no_match_returns_none(self):
        assert _extract_grounding_nonce("no nonce here") is None

    def test_empty_string(self):
        assert _extract_grounding_nonce("") is None


class TestFirstTextBlock:
    def test_extracts_text(self):
        class Block:
            text = "hello"
        class Result:
            content = [Block()]
        assert _first_text_block(Result()) == "hello"

    def test_no_content_returns_empty(self):
        class Result:
            content = None
        assert _first_text_block(Result()) == ""

    def test_empty_content_returns_empty(self):
        class Result:
            content = []
        assert _first_text_block(Result()) == ""

    def test_non_text_block_skipped(self):
        class ImageBlock:
            pass
        class TextBlock:
            text = "found"
        class Result:
            content = [ImageBlock(), TextBlock()]
        assert _first_text_block(Result()) == "found"


class TestGroundingSuppressed:
    def test_both_none_means_suppressed(self):
        assert _grounding_suppressed({"grounding_rules": None, "warnings": None}) is True

    def test_grounding_rules_present_means_not_suppressed(self):
        assert _grounding_suppressed({"grounding_rules": "rules text", "warnings": None}) is False

    def test_warnings_present_means_not_suppressed(self):
        assert _grounding_suppressed({"grounding_rules": None, "warnings": [{"type": "grounding"}]}) is False

    def test_non_dict_returns_false(self):
        assert _grounding_suppressed("not a dict") is False

    def test_missing_keys_means_suppressed(self):
        assert _grounding_suppressed({}) is True


class TestCache:
    def test_round_trip(self, _clean_cache):
        runtime_state = _clean_cache
        _set_cache("k", {"status": "healthy"}, ttl=60.0, runtime_state=runtime_state)
        assert _get_cached("k", runtime_state=runtime_state) == {"status": "healthy"}

    def test_expired_returns_none(self, _clean_cache):
        runtime_state = _clean_cache
        _set_cache("k", {"status": "healthy"}, ttl=0.0, runtime_state=runtime_state)
        time.sleep(0.01)
        assert _get_cached("k", runtime_state=runtime_state) is None

    def test_missing_key_returns_none(self, _clean_cache):
        runtime_state = _clean_cache
        assert _get_cached("nonexistent", runtime_state=runtime_state) is None

    def test_clear_cache_removes_all(self, _clean_cache):
        runtime_state = _clean_cache
        _set_cache("k", {"status": "healthy"}, ttl=60.0, runtime_state=runtime_state)
        clear_cache(runtime_state=runtime_state)
        assert _get_cached("k", runtime_state=runtime_state) is None
