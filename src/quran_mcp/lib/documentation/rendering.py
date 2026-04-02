"""Formatting and rendering helpers for documentation payload generation."""

from __future__ import annotations

import html
import json
from typing import Any

STRUCTURED_RESPONSE_STRING_LIMIT = 256


def escape(value: Any) -> str:
    return html.escape(str(value), quote=False)


def truncate_structured_response_string(value: str) -> str:
    if len(value) <= STRUCTURED_RESPONSE_STRING_LIMIT:
        return value
    return value[: STRUCTURED_RESPONSE_STRING_LIMIT - 3] + "..."


def should_compact_object_list(value: list[Any]) -> bool:
    return len(value) > 2 and all(isinstance(item, dict) and len(item) >= 3 for item in value)


def display_structured_response_value(value: Any) -> Any:
    if isinstance(value, str):
        return truncate_structured_response_string(value)
    if isinstance(value, list):
        if should_compact_object_list(value):
            return [
                display_structured_response_value(value[0]),
                Ellipsis,
                display_structured_response_value(value[-1]),
            ]
        return [display_structured_response_value(item) for item in value]
    if isinstance(value, dict):
        return {key: display_structured_response_value(val) for key, val in value.items()}
    return value


def colorize_value_literal(value: Any) -> str:
    """Return HTML-highlighted Python literal."""
    if value is None:
        return '<span class="hl-nil">None</span>'
    if isinstance(value, bool):
        return f'<span class="hl-nil">{"True" if value else "False"}</span>'
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<span class="hl-num">{escape(str(value))}</span>'
    if isinstance(value, str):
        return f'<span class="hl-str">{escape(json.dumps(value, ensure_ascii=False))}</span>'
    if isinstance(value, list):
        if not value:
            return '<span class="hl-p">[]</span>'
        items = '<span class="hl-p">, </span>'.join(colorize_value_literal(item) for item in value)
        return f'<span class="hl-p">[</span>{items}<span class="hl-p">]</span>'
    if isinstance(value, dict):
        if not value:
            return '<span class="hl-p">{{}}</span>'
        parts = []
        for key, val in value.items():
            parts.append(
                f'<span class="hl-str">{escape(json.dumps(str(key), ensure_ascii=False))}</span>'
                f'<span class="hl-p">: </span>{colorize_value_literal(val)}'
            )
        items = '<span class="hl-p">, </span>'.join(parts)
        return f'<span class="hl-p">{{</span>{items}<span class="hl-p">}}</span>'
    return escape(str(value))


def colorize_call(tool_name: str, args: dict[str, Any]) -> str:
    """Return syntax-highlighted HTML for a Python-style tool call."""
    fn = f'<span class="hl-fn">{escape(tool_name)}</span>'
    if not args:
        return f'{fn}<span class="hl-p">()</span>'
    parts: list[str] = []
    for key, value in args.items():
        parts.append(
            f'\n    <span class="hl-kw">{escape(key)}</span>'
            f'<span class="hl-p">=</span>{colorize_value_literal(value)}'
        )
    joined = '<span class="hl-p">,</span>'.join(parts)
    return f'{fn}<span class="hl-p">(</span>{joined}\n<span class="hl-p">)</span>'


def colorize_json_value(value: Any, indent: int = 0) -> str:
    """Return syntax-highlighted HTML for a JSON value."""
    pad = "  " * indent
    pad1 = "  " * (indent + 1)
    if value is Ellipsis:
        return '<span class="json-comment">...</span>'
    if value is None:
        return '<span class="hl-nil">null</span>'
    if isinstance(value, bool):
        return f'<span class="hl-nil">{"true" if value else "false"}</span>'
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<span class="hl-num">{escape(str(value))}</span>'
    if isinstance(value, str):
        return f'<span class="hl-str">{escape(json.dumps(value, ensure_ascii=False))}</span>'
    if isinstance(value, list):
        if not value:
            return '<span class="hl-p">[]</span>'
        items: list[str] = []
        for item in value:
            items.append(f"{pad1}{colorize_json_value(item, indent + 1)}")
        joined = '<span class="hl-p">,</span>\n'.join(items)
        return f'<span class="hl-p">[</span>\n{joined}\n{pad}<span class="hl-p">]</span>'
    if isinstance(value, dict):
        if not value:
            return '<span class="hl-p">{{}}</span>'
        entries: list[str] = []
        for key, val in value.items():
            k = f'<span class="hl-key">{escape(json.dumps(str(key), ensure_ascii=False))}</span>'
            v = colorize_json_value(val, indent + 1)
            entries.append(f'{pad1}{k}<span class="hl-p">: </span>{v}')
        joined = '<span class="hl-p">,</span>\n'.join(entries)
        return f'<span class="hl-p">{{</span>\n{joined}\n{pad}<span class="hl-p">}}</span>'
    return escape(str(value))


def type_label(schema: Any) -> str:
    if not isinstance(schema, dict) or not schema:
        return "object"
    if "const" in schema:
        return json.dumps(schema["const"], ensure_ascii=False)
    if "anyOf" in schema:
        variants: list[str] = []
        for part in schema["anyOf"]:
            label = type_label(part)
            if label not in variants:
                variants.append(label)
        return " | ".join(variants) if variants else "object"
    if "enum" in schema:
        return " | ".join(json.dumps(item, ensure_ascii=False) for item in schema["enum"])
    schema_type = schema.get("type")
    if schema_type == "array":
        return f"list[{type_label(schema.get('items', {}))}]"
    if schema_type == "string":
        return "str"
    if schema_type == "integer":
        return "int"
    if schema_type == "number":
        return "float"
    if schema_type == "boolean":
        return "bool"
    if schema_type == "null":
        return "None"
    if schema_type == "object":
        return "object"
    return str(schema_type or "object")


def value_literal(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, list):
        return "[" + ", ".join(value_literal(item) for item in value) + "]"
    if isinstance(value, dict):
        items = ", ".join(f"{json.dumps(str(key), ensure_ascii=False)}: {value_literal(val)}" for key, val in value.items())
        return "{" + items + "}"
    return str(value)


def infer_value_type(value: Any) -> str:
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        if not value:
            return "list[object]"
        return f"list[{infer_value_type(value[0])}]"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


__all__ = [
    "escape",
    "truncate_structured_response_string",
    "should_compact_object_list",
    "display_structured_response_value",
    "colorize_call",
    "colorize_json_value",
    "type_label",
    "value_literal",
    "infer_value_type",
]
