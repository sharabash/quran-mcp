from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest

from quran_mcp.lib.editions.loader import (
    _project_to_schema,
    load_editions_by_type,
)


class TestProjectToSchema:
    def test_projects_known_fields(self):
        records = [{"edition_id": "ar-uthmani", "edition_type": "quran", "lang": "ar",
                     "code": "uthmani", "name": "Uthmani", "author": None, "extra_field": "dropped"}]
        result = _project_to_schema(records)
        assert len(result) == 1
        assert "extra_field" not in result[0]
        assert result[0].edition_id == "ar-uthmani"
        assert result[0].lang == "ar"

    def test_skips_records_missing_edition_id(self):
        records = [{"edition_type": "quran", "lang": "ar", "code": "x", "name": "X"}]
        result = _project_to_schema(records)
        assert result == []

    def test_skips_records_missing_edition_type(self):
        records = [{"edition_id": "ar-uthmani", "lang": "ar", "code": "x", "name": "X"}]
        result = _project_to_schema(records)
        assert result == []

    def test_skips_records_with_unknown_edition_type(self):
        records = [{
            "edition_id": "ar-uthmani",
            "edition_type": "unknown",
            "lang": "ar",
            "code": "x",
            "name": "X",
        }]
        result = _project_to_schema(records)
        assert result == []

    def test_skips_records_missing_lang(self):
        records = [{"edition_id": "ar-uthmani", "edition_type": "quran", "code": "x", "name": "X"}]
        result = _project_to_schema(records)
        assert result == []

    def test_skips_records_missing_code(self):
        records = [{"edition_id": "ar-uthmani", "edition_type": "quran", "lang": "ar", "name": "X"}]
        result = _project_to_schema(records)
        assert result == []

    def test_skips_records_missing_name(self):
        records = [{"edition_id": "ar-uthmani", "edition_type": "quran", "lang": "ar", "code": "x"}]
        result = _project_to_schema(records)
        assert result == []

    def test_skips_records_with_empty_required_strings(self):
        records = [{
            "edition_id": "ar-uthmani",
            "edition_type": "quran",
            "lang": "  ",
            "code": "x",
            "name": "X",
        }]
        result = _project_to_schema(records)
        assert result == []

    def test_resource_id_mapped_to_qf_resource_id(self):
        records = [{"edition_id": "en-x", "edition_type": "translation", "lang": "en",
                     "code": "x", "name": "X", "resource_id": 42}]
        result = _project_to_schema(records)
        assert result[0].qf_resource_id == 42

    def test_qf_resource_id_takes_precedence_over_resource_id(self):
        records = [{"edition_id": "en-x", "edition_type": "translation", "lang": "en",
                     "code": "x", "name": "X", "qf_resource_id": 99, "resource_id": 42}]
        result = _project_to_schema(records)
        assert result[0].qf_resource_id == 99


class TestLoadEditionsByType:
    def test_returns_non_empty_for_known_type(self):
        result = load_editions_by_type("translation")
        assert len(result) > 0

    def test_returns_empty_for_unknown_type(self):
        result = load_editions_by_type(cast(Any, "nonexistent_type"))
        assert result == []

    def test_all_records_have_correct_edition_type(self):
        for rec in load_editions_by_type("tafsir"):
            assert rec.edition_type == "tafsir"

    def test_required_fields_are_non_empty_strings(self):
        for rec in load_editions_by_type("translation"):
            assert isinstance(rec.edition_id, str) and rec.edition_id
            assert isinstance(rec.edition_type, str) and rec.edition_type
            assert isinstance(rec.lang, str) and rec.lang
            assert isinstance(rec.code, str) and rec.code
            assert isinstance(rec.name, str) and rec.name

    def test_no_duplicate_edition_ids(self):
        records = load_editions_by_type("translation")
        ids = [record.edition_id for record in records]
        assert len(ids) == len(set(ids))

    def test_returns_immutable_mapping_records(self):
        a = load_editions_by_type("quran")
        b = load_editions_by_type("quran")

        assert a[0] is not b[0]
        assert a[0].edition_id == a[0]["edition_id"]
        assert dict(a[0])["edition_type"] == "quran"

        with pytest.raises(FrozenInstanceError):
            cast(Any, a[0]).edition_id = "MUTATED"
