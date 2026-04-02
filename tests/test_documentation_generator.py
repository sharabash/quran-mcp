"""Tests for documentation rendering, catalog, and context helpers.

Covers:
  - type_label: JSON Schema → Python type string (12 branches)
  - truncate_structured_response_string: boundary at 256 chars
  - should_compact_object_list: compaction predicate
  - display_structured_response_value: recursive display transform
  - is_public_docs_tool: tag/prefix filtering
  - parameter_rows: schema → parameter table rows
  - colorize_call: syntax-highlighted Python call HTML
  - colorize_json_value: syntax-highlighted JSON value HTML
"""

from __future__ import annotations

from types import SimpleNamespace

from quran_mcp.lib.documentation.catalog import is_public_docs_tool
from quran_mcp.lib.documentation.context import parameter_rows
from quran_mcp.lib.documentation.rendering import (
    colorize_call,
    colorize_json_value,
    display_structured_response_value,
    should_compact_object_list,
    truncate_structured_response_string,
    type_label,
)


# ---------------------------------------------------------------------------
# type_label — JSON Schema → Python type string
# ---------------------------------------------------------------------------


class TestTypeLabel:
    def test_empty_dict(self):
        assert type_label({}) == "object"

    def test_non_dict(self):
        assert type_label("not a dict") == "object"

    def test_none_input(self):
        assert type_label(None) == "object"

    def test_const(self):
        assert type_label({"const": "foo"}) == '"foo"'

    def test_const_integer(self):
        assert type_label({"const": 42}) == "42"

    def test_anyof_deduped(self):
        schema = {"anyOf": [{"type": "string"}, {"type": "null"}, {"type": "string"}]}
        assert type_label(schema) == "str | None"

    def test_anyof_empty(self):
        assert type_label({"anyOf": []}) == "object"

    def test_enum(self):
        schema = {"enum": ["a", "b", "c"]}
        assert type_label(schema) == '"a" | "b" | "c"'

    def test_array_with_items(self):
        schema = {"type": "array", "items": {"type": "string"}}
        assert type_label(schema) == "list[str]"

    def test_array_without_items(self):
        schema = {"type": "array"}
        assert type_label(schema) == "list[object]"

    def test_string(self):
        assert type_label({"type": "string"}) == "str"

    def test_integer(self):
        assert type_label({"type": "integer"}) == "int"

    def test_number(self):
        assert type_label({"type": "number"}) == "float"

    def test_boolean(self):
        assert type_label({"type": "boolean"}) == "bool"

    def test_null(self):
        assert type_label({"type": "null"}) == "None"

    def test_object(self):
        assert type_label({"type": "object"}) == "object"

    def test_type_none_fallback(self):
        assert type_label({"type": None}) == "object"


# ---------------------------------------------------------------------------
# truncate_structured_response_string — boundary at 256 chars
# ---------------------------------------------------------------------------


class TestTruncateStructuredResponseString:
    def test_short_string_unchanged(self):
        s = "a" * 256
        assert truncate_structured_response_string(s) == s

    def test_exact_boundary_unchanged(self):
        s = "x" * 256
        assert truncate_structured_response_string(s) == s
        assert len(truncate_structured_response_string(s)) == 256

    def test_long_string_truncated(self):
        s = "y" * 257
        result = truncate_structured_response_string(s)
        assert result.endswith("...")
        assert len(result) == 256

    def test_much_longer_string(self):
        s = "z" * 1000
        result = truncate_structured_response_string(s)
        assert len(result) == 256
        assert result == "z" * 253 + "..."

    def test_empty_string(self):
        assert truncate_structured_response_string("") == ""


# ---------------------------------------------------------------------------
# should_compact_object_list — compaction predicate
# ---------------------------------------------------------------------------


class TestShouldCompactObjectList:
    def test_three_dicts_with_three_keys(self):
        items = [{"a": 1, "b": 2, "c": 3} for _ in range(3)]
        assert should_compact_object_list(items) is True

    def test_two_dicts_too_few(self):
        items = [{"a": 1, "b": 2, "c": 3} for _ in range(2)]
        assert should_compact_object_list(items) is False

    def test_dicts_with_fewer_than_three_keys(self):
        items = [{"a": 1, "b": 2} for _ in range(5)]
        assert should_compact_object_list(items) is False

    def test_mixed_types(self):
        items = [{"a": 1, "b": 2, "c": 3}, "not a dict", {"x": 1, "y": 2, "z": 3}]
        assert should_compact_object_list(items) is False

    def test_empty_list(self):
        assert should_compact_object_list([]) is False


# ---------------------------------------------------------------------------
# display_structured_response_value — recursive display transform
# ---------------------------------------------------------------------------


class TestDisplayStructuredResponseValue:
    def test_string_truncation(self):
        s = "a" * 300
        result = display_structured_response_value(s)
        assert len(result) == 256
        assert result.endswith("...")

    def test_short_string_passthrough(self):
        assert display_structured_response_value("hello") == "hello"

    def test_long_list_compaction(self):
        items = [{"a": 1, "b": 2, "c": 3} for _ in range(5)]
        result = display_structured_response_value(items)
        assert len(result) == 3
        assert result[0] == {"a": 1, "b": 2, "c": 3}
        assert result[1] is Ellipsis
        assert result[2] == {"a": 1, "b": 2, "c": 3}

    def test_short_list_passthrough(self):
        items = ["a", "b"]
        result = display_structured_response_value(items)
        assert result == ["a", "b"]

    def test_dict_recursion(self):
        data = {"key": "x" * 300}
        result = display_structured_response_value(data)
        assert result["key"].endswith("...")
        assert len(result["key"]) == 256

    def test_non_container_passthrough(self):
        assert display_structured_response_value(42) == 42
        assert display_structured_response_value(True) is True
        assert display_structured_response_value(None) is None


# ---------------------------------------------------------------------------
# is_public_docs_tool — tag/prefix filtering
# ---------------------------------------------------------------------------


def _make_tool(name: str, tags: set[str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(name=name, tags=tags)


class TestIsPublicDocsTool:
    def test_ga_tag(self):
        assert is_public_docs_tool(_make_tool("fetch_quran", {"ga"})) is True

    def test_preview_tag(self):
        assert is_public_docs_tool(_make_tool("fetch_quran", {"preview"})) is True

    def test_deprecated_tag(self):
        assert is_public_docs_tool(_make_tool("fetch_quran", {"deprecated"})) is False

    def test_excluded_takes_precedence(self):
        assert is_public_docs_tool(_make_tool("fetch_quran", {"ga", "deprecated"})) is False

    def test_relay_prefix_excluded(self):
        assert is_public_docs_tool(_make_tool("relay_foo", {"ga"})) is False

    def test_no_tags(self):
        assert is_public_docs_tool(_make_tool("fetch_quran")) is False

    def test_empty_tags(self):
        assert is_public_docs_tool(_make_tool("fetch_quran", set())) is False

    def test_internal_tag_excluded(self):
        assert is_public_docs_tool(_make_tool("fetch_quran", {"ga", "internal"})) is False

    def test_in_development_tag_excluded(self):
        assert is_public_docs_tool(_make_tool("fetch_quran", {"ga", "in-development"})) is False


# ---------------------------------------------------------------------------
# parameter_rows — schema → parameter table rows
# ---------------------------------------------------------------------------


class TestParameterRows:
    def test_required_optional_default(self):
        schema = {
            "properties": {
                "surah": {"type": "integer", "description": "Surah number"},
                "ayah": {"type": "integer", "description": "Ayah number", "default": 1},
                "lang": {"type": "string", "description": "Language code"},
            },
            "required": ["surah"],
        }
        rows = parameter_rows(schema)
        assert len(rows) == 3

        surah = rows[0]
        assert surah["name"] == "surah"
        assert surah["type"] == "int"
        assert surah["required"] is True
        assert surah["has_default"] is False

        ayah = rows[1]
        assert ayah["name"] == "ayah"
        assert ayah["required"] is False
        assert ayah["has_default"] is True
        assert ayah["default"] == 1
        assert ayah["default_display"] == "1"

        lang = rows[2]
        assert lang["name"] == "lang"
        assert lang["type"] == "str"
        assert lang["required"] is False
        assert lang["has_default"] is False
        assert lang["description"] == "Language code"

    def test_empty_schema(self):
        assert parameter_rows({}) == []


# ---------------------------------------------------------------------------
# colorize_call — syntax-highlighted Python call HTML
# ---------------------------------------------------------------------------


class TestColorizeCall:
    def test_empty_args(self):
        result = colorize_call("my_tool", {})
        assert "my_tool" in result
        assert "()" in result

    def test_string_arg(self):
        result = colorize_call("fetch", {"ref": "2:255"})
        assert "ref" in result
        assert "2:255" in result
        assert "hl-str" in result

    def test_int_arg(self):
        result = colorize_call("fetch", {"page": 5})
        assert "5" in result
        assert "hl-num" in result

    def test_list_arg(self):
        result = colorize_call("fetch", {"items": ["a", "b"]})
        assert "hl-p" in result
        assert "a" in result
        assert "b" in result

    def test_dict_arg(self):
        result = colorize_call("fetch", {"opts": {"k": "v"}})
        assert "k" in result
        assert "v" in result

    def test_none_arg(self):
        result = colorize_call("fetch", {"val": None})
        assert "None" in result
        assert "hl-nil" in result


# ---------------------------------------------------------------------------
# colorize_json_value — syntax-highlighted JSON value HTML
# ---------------------------------------------------------------------------


class TestColorizeJsonValue:
    def test_none(self):
        result = colorize_json_value(None)
        assert "null" in result
        assert "hl-nil" in result

    def test_true(self):
        result = colorize_json_value(True)
        assert "true" in result

    def test_false(self):
        result = colorize_json_value(False)
        assert "false" in result

    def test_int(self):
        result = colorize_json_value(42)
        assert "42" in result
        assert "hl-num" in result

    def test_float(self):
        result = colorize_json_value(3.14)
        assert "3.14" in result
        assert "hl-num" in result

    def test_string(self):
        result = colorize_json_value("hello")
        assert "hello" in result
        assert "hl-str" in result

    def test_empty_list(self):
        result = colorize_json_value([])
        assert "[]" in result

    def test_empty_dict(self):
        result = colorize_json_value({})
        assert "{}" in result

    def test_nested_list(self):
        result = colorize_json_value([1, "two"])
        assert "1" in result
        assert "two" in result
        assert "[" in result

    def test_nested_dict(self):
        result = colorize_json_value({"k": 99})
        assert "k" in result
        assert "99" in result
        assert "hl-key" in result

    def test_ellipsis(self):
        result = colorize_json_value(Ellipsis)
        assert "..." in result
        assert "json-comment" in result
