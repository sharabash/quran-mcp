from __future__ import annotations

from typing import Any, cast

import pytest

from quran_mcp.lib.editions.registry import (
    ResolveResult,
    filter_editions,
    get_by_edition_id,
    list_editions,
    list_edition_summaries,
    resolve_ids,
    resolve_ids_with_unresolved,
)


class TestResolveIds:
    def test_exact_id_resolution(self):
        result = resolve_ids("quran", "ar-uthmani")
        assert result == ["ar-uthmani"]

    def test_code_resolution(self):
        result = resolve_ids("quran", "uthmani")
        assert len(result) >= 1
        assert any("uthmani" in eid for eid in result)

    def test_language_resolution_two_char(self):
        result = resolve_ids("translation", "en")
        assert len(result) > 1
        for eid in result:
            rec = get_by_edition_id("translation", eid)
            assert rec is not None
            assert rec.lang == "en"

    def test_fuzzy_resolution(self):
        result = resolve_ids("tafsir", "kathir")
        assert any("kathir" in eid for eid in result)

    def test_unknown_selector_raises_value_error(self):
        with pytest.raises(ValueError, match="No .* editions matched"):
            resolve_ids("translation", "zzz-nonexistent-xyz")

    def test_multiple_comma_separated_selectors(self):
        result = resolve_ids("quran", "ar-uthmani, ar-simple-clean")
        assert "ar-uthmani" in result
        assert "ar-simple-clean" in result

    def test_case_insensitive_matching(self):
        result = resolve_ids("quran", "AR-UTHMANI")
        assert result == ["ar-uthmani"]


class TestResolveIdsWithUnresolved:
    def test_tracks_unresolved_selectors(self):
        result = resolve_ids_with_unresolved("translation", "en-sahih-international, zzz-fake")
        assert isinstance(result, ResolveResult)
        assert "en-sahih-international" in result.resolved
        assert "zzz-fake" in result.unresolved

    def test_all_resolved_gives_empty_unresolved(self):
        result = resolve_ids_with_unresolved("quran", "ar-uthmani")
        assert result.unresolved == []
        assert len(result.resolved) == 1


class TestGetByEditionId:
    def test_returns_record_for_known_id(self):
        rec = get_by_edition_id("quran", "ar-uthmani")
        assert rec is not None
        assert rec.edition_id == "ar-uthmani"
        assert rec.edition_id == "ar-uthmani"
        assert dict(rec)["edition_type"] == "quran"

    def test_returns_none_for_unknown_id(self):
        rec = get_by_edition_id("translation", "zzz-nonexistent")
        assert rec is None

    def test_case_insensitive(self):
        rec = get_by_edition_id("quran", "AR-UTHMANI")
        assert rec is not None
        assert rec.edition_id == "ar-uthmani"


class TestListEditions:
    def test_returns_non_empty_for_known_type(self):
        editions = list_editions("translation")
        assert len(editions) > 0

    def test_returns_non_empty_for_tafsir(self):
        editions = list_editions("tafsir")
        assert len(editions) > 0

    def test_returns_empty_for_unknown_type(self):
        editions = list_editions(cast(Any, "nonexistent_type"))
        assert editions == []


class TestFilterEditions:
    def test_filter_by_lang(self):
        results = filter_editions("translation", lang="en")
        assert len(results) > 0
        for rec in results:
            assert rec.lang == "en"

    def test_filter_by_lang_case_insensitive(self):
        lower = filter_editions("translation", lang="en")
        upper = filter_editions("translation", lang="EN")
        assert len(lower) == len(upper)

    def test_filter_by_name(self):
        results = filter_editions("tafsir", name="kathir")
        assert len(results) >= 1
        assert any("kathir" in r.edition_id.lower() for r in results)

    def test_filter_by_lang_and_name(self):
        results = filter_editions("translation", lang="en", name="sahih")
        assert len(results) >= 1
        for rec in results:
            assert rec.lang == "en"

    def test_list_edition_summaries_sorts_shared_public_projection(self):
        summaries = list_edition_summaries("translation", lang="en", sort_by_edition_id=True)
        edition_ids = [summary["edition_id"] for summary in summaries]
        assert edition_ids == sorted(edition_ids)
