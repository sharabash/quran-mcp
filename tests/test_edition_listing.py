from __future__ import annotations

from quran_mcp.lib.editions.registry import (
    get_by_edition_id,
    filter_editions,
    get_edition_list,
    list_edition_summaries,
)
from quran_mcp.lib.editions.loader import load_editions_by_type
from quran_mcp.lib.editions.types import project_edition_info
from quran_mcp.mcp.tools.editions.list import EditionInfo


class TestListQuranEditions:
    def test_returns_non_empty(self):
        editions = load_editions_by_type("quran")
        assert len(editions) > 0

    def test_records_have_required_fields(self):
        for rec in load_editions_by_type("quran"):
            assert rec.edition_id
            assert rec.name
            assert rec.lang

    def test_get_by_known_id(self):
        rec = get_by_edition_id("quran", "ar-uthmani")
        assert rec is not None
        assert rec.edition_id == "ar-uthmani"

    def test_get_by_unknown_id(self):
        assert get_by_edition_id("quran", "nonexistent") is None

    def test_get_list_returns_dict(self):
        result = get_edition_list("quran")
        assert "results" in result
        assert "count" in result
        assert result["count"] == len(result["results"])

    def test_filter_by_lang(self):
        editions = filter_editions("quran", lang="ar")
        assert len(editions) > 0
        for rec in editions:
            assert rec.lang == "ar"


class TestListTafsirEditions:
    def test_returns_non_empty(self):
        editions = load_editions_by_type("tafsir")
        assert len(editions) > 0

    def test_records_have_required_fields(self):
        for rec in load_editions_by_type("tafsir"):
            assert rec.edition_id
            assert rec.name
            assert rec.lang
            assert "author" in rec

    def test_get_by_known_id(self):
        rec = get_by_edition_id("tafsir", "en-ibn-kathir")
        assert rec is not None
        assert rec.edition_id == "en-ibn-kathir"

    def test_get_by_unknown_id(self):
        assert get_by_edition_id("tafsir", "nonexistent") is None

    def test_get_list_with_lang_filter(self):
        result = get_edition_list("tafsir", lang="en")
        assert result["count"] > 0
        for rec in result["results"]:
            assert rec["lang"] == "en"

    def test_filter_by_name(self):
        editions = filter_editions("tafsir", name="kathir")
        assert len(editions) > 0


class TestListTranslationEditions:
    def test_returns_non_empty(self):
        editions = load_editions_by_type("translation")
        assert len(editions) > 0

    def test_records_have_required_fields(self):
        for rec in load_editions_by_type("translation"):
            assert rec.edition_id
            assert rec.name
            assert rec.lang

    def test_get_by_known_id(self):
        rec = get_by_edition_id("translation", "en-abdel-haleem")
        assert rec is not None
        assert rec.edition_id == "en-abdel-haleem"

    def test_get_by_unknown_id(self):
        assert get_by_edition_id("translation", "nonexistent") is None

    def test_get_list_returns_dict(self):
        result = get_edition_list("translation")
        assert "results" in result
        assert "count" in result
        assert result["count"] == len(result["results"])

    def test_filter_by_lang(self):
        editions = filter_editions("translation", lang="en")
        assert len(editions) > 0
        for rec in editions:
            assert rec.lang == "en"

    def test_filter_by_lang_case_insensitive(self):
        lower = filter_editions("translation", lang="en")
        upper = filter_editions("translation", lang="EN")
        assert len(lower) == len(upper)

    def test_filter_combined_lang_and_name(self):
        editions = filter_editions("translation", lang="en", name="haleem")
        assert len(editions) > 0
        for rec in editions:
            assert rec.lang == "en"

    def test_projected_public_shape_matches_tool_model(self):
        record = load_editions_by_type("translation")[0]
        projected = project_edition_info(record)
        model = EditionInfo(**projected)

        assert model.edition_id == record.edition_id
        assert model.edition_type == record.edition_type
        assert model.author == record.author

    def test_list_edition_summaries_uses_shared_public_shape(self):
        summary = list_edition_summaries("translation", lang="en", sort_by_edition_id=True)[0]
        model = EditionInfo(**summary)

        assert model.lang == "en"
        assert model.edition_id == summary["edition_id"]

    def test_get_list_excludes_internal_id_by_default(self):
        result = get_edition_list("translation")
        assert result["results"]
        assert "qf_resource_id" not in result["results"][0]
