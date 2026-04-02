"""Tests for quran_mcp.lib.ayah_parsing.

Covers:
  - parse_ayah_key: basic parsing, error cases
  - parse_ayah_input: single keys, ranges, comma/whitespace splitting, list input
  - format_ayah_range: adjacent merge, cross-surah, single key, empty
"""

from __future__ import annotations

import pytest

from quran_mcp.lib.ayah_parsing import (
    format_ayah_range,
    parse_ayah_input,
    parse_ayah_key,
)


# ---------------------------------------------------------------------------
# parse_ayah_key
# ---------------------------------------------------------------------------


class TestParseAyahKey:
    def test_simple(self):
        assert parse_ayah_key("2:255") == (2, 255)

    def test_first_ayah(self):
        assert parse_ayah_key("1:1") == (1, 1)

    def test_last_surah(self):
        assert parse_ayah_key("114:6") == (114, 6)

    def test_invalid_no_colon(self):
        with pytest.raises(ValueError):
            parse_ayah_key("2255")

    def test_invalid_too_many_colons(self):
        with pytest.raises(ValueError):
            parse_ayah_key("2:255:1")

    def test_invalid_non_numeric(self):
        with pytest.raises(ValueError):
            parse_ayah_key("abc:def")

    def test_empty_string(self):
        with pytest.raises(ValueError):
            parse_ayah_key("")


# ---------------------------------------------------------------------------
# parse_ayah_input
# ---------------------------------------------------------------------------


class TestParseAyahInput:
    def test_single_key(self):
        assert parse_ayah_input("2:255") == ["2:255"]

    def test_range_expansion(self):
        assert parse_ayah_input("2:255-257") == ["2:255", "2:256", "2:257"]

    def test_reversed_range_auto_corrects(self):
        assert parse_ayah_input("2:257-255") == ["2:255", "2:256", "2:257"]

    def test_comma_separated(self):
        assert parse_ayah_input("2:255, 3:1") == ["2:255", "3:1"]

    def test_whitespace_separated(self):
        assert parse_ayah_input("2:255 3:1") == ["2:255", "3:1"]

    def test_mixed_keys_and_ranges(self):
        result = parse_ayah_input("2:255-256, 3:1")
        assert result == ["2:255", "2:256", "3:1"]

    def test_list_input(self):
        result = parse_ayah_input(["2:255", "3:1-3"])
        assert result == ["2:255", "3:1", "3:2", "3:3"]

    def test_extra_whitespace_stripped(self):
        result = parse_ayah_input("  2:255  ,  3:1  ")
        assert result == ["2:255", "3:1"]

    def test_empty_string(self):
        assert parse_ayah_input("") == []

    def test_single_element_range(self):
        assert parse_ayah_input("2:255-255") == ["2:255"]


# ---------------------------------------------------------------------------
# format_ayah_range
# ---------------------------------------------------------------------------


class TestFormatAyahRange:
    def test_empty_list(self):
        assert format_ayah_range([]) == ""

    def test_single_key(self):
        assert format_ayah_range(["2:255"]) == "2:255"

    def test_adjacent_merged(self):
        assert format_ayah_range(["2:153", "2:154", "2:155"]) == "2:153-155"

    def test_non_adjacent_stay_separate(self):
        assert format_ayah_range(["2:153", "2:155"]) == "2:153, 2:155"

    def test_cross_surah_separate(self):
        assert format_ayah_range(["2:286", "3:1"]) == "2:286, 3:1"

    def test_mixed_adjacent_and_gaps(self):
        result = format_ayah_range(["2:1", "2:2", "2:3", "2:10", "3:1"])
        assert result == "2:1-3, 2:10, 3:1"

    def test_unsorted_input_sorted_automatically(self):
        result = format_ayah_range(["3:1", "2:255", "2:256"])
        assert result == "2:255-256, 3:1"

    def test_invalid_key_skipped(self):
        result = format_ayah_range(["2:255", "invalid", "2:256"])
        assert result == "2:255-256"
