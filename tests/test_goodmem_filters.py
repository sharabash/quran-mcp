"""Tests for quran_mcp.lib.goodmem — filter expression DSL and pure helpers.

The GoodMemClient class hits the GoodMem API and is not tested here.
These tests cover the pure filter parsing and SQL expression building
functions that are critical for correct metadata filtering.

Covers:
  - escape_literal: SQL literal escaping
  - _cast_clause: CAST expression building
  - _format_literal: type-aware SQL literal formatting
  - _infer_value_type: type inference (int, float, date, datetime, str)
  - parse_filter_string: operator detection, field/value splitting
  - build_filter_expression: IN clauses, range, cross-field AND
  - combine_filter_expressions: merging CAST + raw expressions
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from quran_mcp.lib.goodmem.filters import (
    FilterTerm,
    _cast_clause,
    escape_literal,
    _format_literal,
    _infer_value_type,
    build_filter_expression,
    build_metadata_filter_expression,
    combine_filter_expressions,
    parse_filter_string,
)


# ---------------------------------------------------------------------------
# escape_literal
# ---------------------------------------------------------------------------


class TestEscapeLiteral:
    def test_normal_string(self):
        assert escape_literal("normal") == "normal"

    def test_single_quote_escaped(self):
        assert escape_literal("O'Brien") == "O\\'Brien"

    def test_multiple_quotes(self):
        assert escape_literal("it's a 'test'") == "it\\'s a \\'test\\'"

    def test_empty_string(self):
        assert escape_literal("") == ""


# ---------------------------------------------------------------------------
# _cast_clause
# ---------------------------------------------------------------------------


class TestCastClause:
    def test_int_field(self):
        assert _cast_clause("surah", int) == "CAST(val('$.surah') AS INT)"

    def test_str_field(self):
        assert _cast_clause("author", str) == "CAST(val('$.author') AS TEXT)"

    def test_nested_field(self):
        assert _cast_clause("meta.author", str) == "CAST(val('$.meta.author') AS TEXT)"

    def test_float_field(self):
        assert _cast_clause("score", float) == "CAST(val('$.score') AS NUMERIC)"


# ---------------------------------------------------------------------------
# _format_literal
# ---------------------------------------------------------------------------


class TestFormatLiteral:
    def test_int(self):
        assert _format_literal(42, int) == "42"

    def test_float(self):
        assert _format_literal(3.14, float) == "3.14"

    def test_string(self):
        assert _format_literal("hello", str) == "'hello'"

    def test_string_with_quote(self):
        assert _format_literal("O'Brien", str) == "'O\\'Brien'"

    def test_date(self):
        d = date(2024, 1, 15)
        assert _format_literal(d, date) == "CAST('2024-01-15' AS DATE)"

    def test_datetime(self):
        dt = datetime(2024, 1, 15, 10, 30, 0)
        result = _format_literal(dt, datetime)
        assert result.startswith("CAST('2024-01-15")
        assert "TIMESTAMPTZ" in result


# ---------------------------------------------------------------------------
# _infer_value_type
# ---------------------------------------------------------------------------


class TestInferValueType:
    def test_integer(self):
        val, typ = _infer_value_type("42")
        assert val == 42
        assert typ is int

    def test_negative_integer(self):
        val, typ = _infer_value_type("-5")
        assert val == -5
        assert typ is int

    def test_float(self):
        val, typ = _infer_value_type("3.14")
        assert val == 3.14
        assert typ is float

    def test_date(self):
        val, typ = _infer_value_type("2024-01-15")
        assert val == date(2024, 1, 15)
        assert typ is date

    def test_string_fallback(self):
        val, typ = _infer_value_type("hello")
        assert val == "hello"
        assert typ is str

    def test_boolean_stays_string(self):
        val, typ = _infer_value_type("true")
        assert val == "true"
        assert typ is str


# ---------------------------------------------------------------------------
# parse_filter_string
# ---------------------------------------------------------------------------


class TestParseFilterString:
    def test_equality(self):
        term = parse_filter_string("surah=2")
        assert term.field == "surah"
        assert term.operator == "="
        assert term.value == 2
        assert term.value_type is int

    def test_gte(self):
        term = parse_filter_string("ayah>=255")
        assert term.operator == ">="
        assert term.value == 255

    def test_lte(self):
        term = parse_filter_string("ayah<=260")
        assert term.operator == "<="

    def test_not_equal(self):
        term = parse_filter_string("status!=draft")
        assert term.operator == "!="
        assert term.value == "draft"

    def test_string_value(self):
        term = parse_filter_string("meta.author=Nour")
        assert term.field == "meta.author"
        assert term.value == "Nour"
        assert term.value_type is str

    def test_whitespace_stripped(self):
        term = parse_filter_string("  surah = 2  ")
        assert term.field == "surah"
        assert term.value == 2

    def test_no_operator_raises(self):
        with pytest.raises(ValueError, match="no operator found"):
            parse_filter_string("no_operator_here")

    def test_missing_field_raises(self):
        with pytest.raises(ValueError, match="missing field"):
            parse_filter_string("=42")

    def test_missing_value_raises(self):
        with pytest.raises(ValueError, match="missing value"):
            parse_filter_string("field=")

    def test_invalid_field_name_raises(self):
        with pytest.raises(ValueError, match="Invalid field name"):
            parse_filter_string("invalid field=42")


# ---------------------------------------------------------------------------
# build_filter_expression
# ---------------------------------------------------------------------------


class TestBuildFilterExpression:
    def test_empty_terms(self):
        assert build_filter_expression([]) is None

    def test_single_equality(self):
        terms = [FilterTerm("surah", "=", 2, int)]
        result = build_filter_expression(terms)
        assert "CAST(val('$.surah') AS INT) = 2" == result

    def test_multiple_equality_becomes_in_clause(self):
        terms = [
            FilterTerm("surah", "=", 2, int),
            FilterTerm("surah", "=", 3, int),
        ]
        result = build_filter_expression(terms)
        assert "IN (2, 3)" in result

    def test_range_filter(self):
        terms = [
            FilterTerm("ayah", ">=", 255, int),
            FilterTerm("ayah", "<=", 260, int),
        ]
        result = build_filter_expression(terms)
        assert ">= 255" in result
        assert "<= 260" in result
        assert "AND" in result

    def test_cross_field_and(self):
        terms = [
            FilterTerm("surah", "=", 2, int),
            FilterTerm("ayah", ">=", 255, int),
        ]
        result = build_filter_expression(terms)
        assert "surah" in result
        assert "ayah" in result
        assert "AND" in result

    def test_string_value_quoted(self):
        terms = [FilterTerm("author", "=", "Ibn Kathir", str)]
        result = build_filter_expression(terms)
        assert "'Ibn Kathir'" in result


# ---------------------------------------------------------------------------
# build_metadata_filter_expression
# ---------------------------------------------------------------------------


class TestBuildMetadataFilterExpression:
    def test_mixed_scalar_types(self):
        result = build_metadata_filter_expression(
            {"edition_id": "en-ibn-kathir", "surah": 2, "score": 0.5}
        )
        assert "CAST(val('$.edition_id') AS TEXT) = 'en-ibn-kathir'" in result
        assert "CAST(val('$.surah') AS INT) = 2" in result
        assert "CAST(val('$.score') AS NUMERIC) = 0.5" in result

    def test_empty_mapping_returns_empty_string(self):
        assert build_metadata_filter_expression({}) == ""


# ---------------------------------------------------------------------------
# combine_filter_expressions
# ---------------------------------------------------------------------------


class TestCombineFilterExpressions:
    def test_cast_only(self):
        result = combine_filter_expressions("CAST(val('$.x') AS INT) = 1", None)
        assert result == "CAST(val('$.x') AS INT) = 1"

    def test_raw_only_single(self):
        result = combine_filter_expressions(None, ["exists('$.a')"])
        assert result == "exists('$.a')"

    def test_raw_only_multiple(self):
        result = combine_filter_expressions(None, ["exists('$.a')", "exists('$.b')"])
        assert "(exists('$.a'))" in result
        assert "(exists('$.b'))" in result
        assert "AND" in result

    def test_both_combined(self):
        result = combine_filter_expressions(
            "CAST(val('$.surah') AS INT) = 2",
            ["exists('$.surahs')"],
        )
        assert "CAST(val('$.surah') AS INT) = 2" in result
        assert "exists('$.surahs')" in result
        assert "AND" in result

    def test_all_none(self):
        assert combine_filter_expressions(None, None) is None

    def test_empty_raw_strings_filtered(self):
        result = combine_filter_expressions(None, ["", "  ", "exists('$.a')"])
        assert result == "exists('$.a')"
