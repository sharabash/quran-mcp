"""Tests for quran_mcp.mcp.tools.morphology.concordance — pure functions.

Tests the two private helper functions:
  - _resolve_rerank_from: 8-branch decision tree for reranking mode
  - _enforce_concordance_token_cap: binary-search truncation under token cap

No external services needed — these are pure functions operating on
in-memory data structures.

Covers:
  _resolve_rerank_from:
    - group_by="word" → None
    - voyage_key="" → None
    - rerank_from="false" → None
    - rerank_from explicit ayah_key → that key
    - ayah_key auto-set when no rerank_from
    - bare word triggers _BARE_WORD_RERANK
    - root/lemma/stem also trigger _BARE_WORD_RERANK
    - all None → None

  _enforce_concordance_token_cap:
    - Under cap → returned unchanged
    - Over cap → truncated with truncated=True
    - Empty results → returned unchanged
"""

from __future__ import annotations

from quran_mcp.mcp.tools.morphology.concordance import (
    _BARE_WORD_RERANK,
    _enforce_concordance_token_cap,
    _resolve_rerank_from,
)
from quran_mcp.lib.morphology.concordance_request import (
    ConcordanceRequest,
    build_concordance_request,
)
from quran_mcp.lib.morphology.types import (
    ConcordanceResponse,
    ConcordanceVerse,
    ConcordanceWord,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _request(**kwargs) -> ConcordanceRequest:
    """Build a normalized concordance request for tests."""
    return build_concordance_request(**kwargs)


def _make_verse(ayah_key: str, text: str = "بسم الله", score: float = 5.0) -> ConcordanceVerse:
    """Build a minimal ConcordanceVerse for testing."""
    return ConcordanceVerse(
        ayah_key=ayah_key,
        verse_text=text,
        score=score,
        matched_words=[
            ConcordanceWord(
                position=1,
                text_uthmani="بسم",
                match_level="exact",
            )
        ],
    )


def _make_response(
    n_results: int = 5,
    text_per_verse: str = "بسم الله الرحمن الرحيم",
) -> ConcordanceResponse:
    """Build a ConcordanceResponse with n verse results."""
    results = [
        _make_verse(f"1:{i+1}", text=text_per_verse)
        for i in range(n_results)
    ]
    return ConcordanceResponse(
        query={"root": "ب س م"},
        match_by="all",
        group_by="verse",
        total_verses=n_results,
        page=1,
        page_size=20,
        results=results,
    )


# ===========================================================================
# _resolve_rerank_from — 8-branch decision tree
# ===========================================================================


class TestResolveRerankFrom:
    """Tests the 8 branches of _resolve_rerank_from."""

    def test_group_by_word_returns_none(self):
        """group_by='word' → reranking disabled (only works with verse mode)."""
        result = _resolve_rerank_from(
            request=_request(ayah_key="2:255", group_by="word"),
            voyage_key="sk-test-key",
        )
        assert result is None

    def test_empty_voyage_key_returns_none(self):
        """Empty Voyage API key → can't rerank."""
        result = _resolve_rerank_from(
            request=_request(ayah_key="2:255", group_by="verse"),
            voyage_key="",
        )
        assert result is None

    def test_rerank_from_false_returns_none(self):
        """rerank_from='false' → explicit disable."""
        result = _resolve_rerank_from(
            request=_request(ayah_key="2:255", group_by="verse", rerank_from="false"),
            voyage_key="sk-test-key",
        )
        assert result is None

    def test_rerank_from_false_case_insensitive(self):
        """rerank_from='FALSE' → case-insensitive disable."""
        result = _resolve_rerank_from(
            request=_request(ayah_key="2:255", group_by="verse", rerank_from="FALSE"),
            voyage_key="sk-test-key",
        )
        assert result is None

    def test_explicit_rerank_from_ayah_key(self):
        """rerank_from='2:255' explicit → returns that key."""
        result = _resolve_rerank_from(
            request=_request(root="قول", group_by="verse", rerank_from="2:255"),
            voyage_key="sk-test-key",
        )
        assert result == "2:255"

    def test_ayah_key_auto_set(self):
        """ayah_key='2:77' with no rerank_from → auto-set to ayah_key."""
        result = _resolve_rerank_from(
            request=_request(ayah_key="2:77", group_by="verse"),
            voyage_key="sk-test-key",
        )
        assert result == "2:77"

    def test_bare_word_triggers_bare_word_rerank(self):
        """word='يَعْلَمُونَ' with no ayah_key → _BARE_WORD_RERANK."""
        result = _resolve_rerank_from(
            request=_request(word="يَعْلَمُونَ", group_by="verse"),
            voyage_key="sk-test-key",
        )
        assert result == _BARE_WORD_RERANK

    def test_root_triggers_bare_word_rerank(self):
        """root='ع ل م' with no ayah_key → _BARE_WORD_RERANK."""
        result = _resolve_rerank_from(
            request=_request(root="ع ل م", group_by="verse"),
            voyage_key="sk-test-key",
        )
        assert result == _BARE_WORD_RERANK

    def test_lemma_triggers_bare_word_rerank(self):
        """lemma='عَلِمَ' with no ayah_key → _BARE_WORD_RERANK."""
        result = _resolve_rerank_from(
            request=_request(lemma="عَلِمَ", group_by="verse"),
            voyage_key="sk-test-key",
        )
        assert result == _BARE_WORD_RERANK

    def test_stem_triggers_bare_word_rerank(self):
        """stem with no ayah_key → _BARE_WORD_RERANK."""
        result = _resolve_rerank_from(
            request=_request(stem="عَلِم", group_by="verse"),
            voyage_key="sk-test-key",
        )
        assert result == _BARE_WORD_RERANK

    def test_all_none_returns_none(self):
        """No rerank_from, no ayah_key, no word/root/lemma/stem → None."""
        result = _resolve_rerank_from(
            request=_request(group_by="verse", word=""),
            voyage_key="sk-test-key",
        )
        assert result is None


class TestConcordanceRequestBuilder:
    def test_build_request_from_ayah_key(self):
        request = _request(ayah_key="2:77", word_text="يَعْلَمُونَ", page=2, page_size=10)
        assert request.selection.kind == "ayah_key"
        assert request.selection.ayah_key == "2:77"
        assert request.selection.search_term == "يَعْلَمُونَ"
        assert request.page == 2
        assert request.page_size == 10

    def test_build_request_from_root(self):
        request = _request(root="ع ل م")
        assert request.selection.kind == "root"
        assert request.selection.root == "ع ل م"
        assert request.selection.to_query_echo() == {"root": "ع ل م"}

    def test_with_overrides(self):
        request = _request(root="ع ل م")
        updated = request.with_overrides(group_by="word", page=3, page_size=5)
        assert updated.group_by == "word"
        assert updated.page == 3
        assert updated.page_size == 5
        assert updated.selection == request.selection


def test_concordance_response_schema_uses_literal_modes():
    schema = ConcordanceResponse.model_json_schema()
    assert schema["properties"]["match_by"]["enum"] == ["all", "root", "lemma", "stem"]
    assert schema["properties"]["group_by"]["enum"] == ["verse", "word"]


# ===========================================================================
# _enforce_concordance_token_cap — truncation logic
# ===========================================================================


class TestEnforceConcordanceTokenCap:
    """Tests the binary-search truncation under token cap."""

    def test_under_cap_returned_unchanged(self):
        """Response under token cap should be returned unchanged."""
        response = _make_response(n_results=3)
        result = _enforce_concordance_token_cap(response, cap=100_000)

        assert result.truncated is False
        assert len(result.results) == 3

    def test_over_cap_truncated(self):
        """Response over token cap should be truncated with truncated=True."""
        # Build a response with enough text to exceed a tiny cap.
        # Each verse has Arabic text (~21 chars → ~11 tokens at 1.9 chars/tok).
        # With JSON overhead per verse, ~100+ tokens per verse.
        # Use a very low cap to force truncation.
        long_text = "بسم الله الرحمن الرحيم " * 50  # ~1050 chars
        response = _make_response(n_results=20, text_per_verse=long_text)

        # Set a cap low enough to force truncation but high enough to keep at least 1
        result = _enforce_concordance_token_cap(response, cap=500)

        assert result.truncated is True
        assert len(result.results) < 20
        assert len(result.results) >= 1  # Always keeps at least 1

    def test_empty_results_returned_unchanged(self):
        """Empty results should be returned unchanged (no truncation)."""
        response = ConcordanceResponse(
            query={"root": "ب س م"},
            match_by="all",
            group_by="verse",
            total_verses=0,
            page=1,
            page_size=20,
            results=[],
        )
        result = _enforce_concordance_token_cap(response, cap=100)

        assert result.truncated is False
        assert len(result.results) == 0

    def test_truncation_preserves_order(self):
        """Truncated results should preserve original ordering."""
        verses = [_make_verse(f"2:{i+1}") for i in range(30)]
        response = ConcordanceResponse(
            query={"root": "ب س م"},
            match_by="all",
            group_by="verse",
            total_verses=30,
            page=1,
            page_size=30,
            results=verses,
        )
        # Force truncation with a low cap
        result = _enforce_concordance_token_cap(response, cap=500)

        if result.truncated:
            kept_keys = [v.ayah_key for v in result.results]
            original_keys = [v.ayah_key for v in verses[:len(kept_keys)]]
            assert kept_keys == original_keys

    def test_exactly_at_cap_not_truncated(self):
        """Response exactly at the cap boundary should not be truncated."""
        response = _make_response(n_results=1)
        from quran_mcp.lib.presentation.pagination import estimate_tokens

        exact_cap = estimate_tokens(response)
        result = _enforce_concordance_token_cap(response, cap=exact_cap)

        assert result.truncated is False
        assert len(result.results) == 1
