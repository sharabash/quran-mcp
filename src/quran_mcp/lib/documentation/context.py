"""Context/data assembly for the documentation JSON payload."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from quran_mcp.lib.documentation.catalog import (
    EDITION_SECTION_CONFIG,
    TOOL_EXAMPLE_CONFIG,
    TOOL_GROUPS,
    card_summary,
    short_description,
)
from quran_mcp.lib.documentation.rendering import (
    colorize_call,
    colorize_json_value,
    display_structured_response_value,
    escape,
    infer_value_type,
    type_label,
    value_literal,
)
from quran_mcp.lib.documentation.qmd_parser import build_generated_showcases
from quran_mcp.lib.editions.loader import load_editions_by_type
from quran_mcp.lib.editions.types import project_edition_info

EXAMPLE_FIXTURES_PATH = Path(__file__).resolve().parent / "data" / "tool_examples.json"


def load_example_fixtures() -> dict[str, dict[str, Any]]:
    """Load checked-in live example payloads for the public docs."""
    return _load_example_fixtures_cached()


@lru_cache(maxsize=1)
def _load_example_fixtures_cached() -> dict[str, dict[str, Any]]:
    raw = json.loads(EXAMPLE_FIXTURES_PATH.read_text(encoding="utf-8"))
    return {str(name): value for name, value in raw.items()}


def parameter_rows(parameters: dict[str, Any]) -> list[dict[str, Any]]:
    properties = parameters.get("properties", {}) if isinstance(parameters, dict) else {}
    required = set(parameters.get("required", [])) if isinstance(parameters, dict) else set()
    rows: list[dict[str, Any]] = []
    for name, schema in properties.items():
        default_val = schema.get("default") if isinstance(schema, dict) and "default" in schema else None
        has_default = isinstance(schema, dict) and "default" in schema
        rows.append(
            {
                "name": name,
                "type": type_label(schema),
                "required": name in required,
                "default": default_val,
                "has_default": has_default,
                "default_display": escape(value_literal(default_val)) if has_default else "",
                "description": " ".join(str(schema.get("description", "")).split()) if isinstance(schema, dict) else "",
            }
        )
    return rows


def output_rows(output_schema: Any, fixture_payload: dict[str, Any]) -> list[dict[str, str]]:
    if isinstance(output_schema, dict) and output_schema.get("properties"):
        rows: list[dict[str, str]] = []
        for name, schema in output_schema["properties"].items():
            rows.append(
                {
                    "name": name,
                    "type": type_label(schema),
                    "description": " ".join(str(schema.get("description", "")).split()) if isinstance(schema, dict) else "",
                }
            )
        return rows
    rows = []
    for name, value in fixture_payload.items():
        rows.append(
            {
                "name": name,
                "type": infer_value_type(value),
                "description": "Present in the exact example payload shown below.",
            }
        )
    return rows


def visible_fixture_subset(fixtures: dict[str, dict[str, Any]], visible_names: set[str]) -> dict[str, dict[str, Any]]:
    return {name: fixtures[name] for name in fixtures if name in visible_names}


def build_flat_tools_context(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [tool for group in groups for subgroup in group["subgroups"] for tool in subgroup["tools"]]


def build_usage_examples_context(include_showcase_html: bool = False) -> dict[str, Any]:
    showcases: list[dict[str, Any]] = []
    if include_showcase_html:
        showcases.extend(build_generated_showcases())

    return {
        "showcases": showcases,
        "examples": [],
    }


@lru_cache(maxsize=1)
def build_editions_context() -> list[dict[str, Any]]:
    edition_groups: list[dict[str, Any]] = []
    for section in EDITION_SECTION_CONFIG:
        raw_rows = load_editions_by_type(section["id"])
        lang_count = len({row.lang for row in raw_rows if row.lang})
        summary = f"{len(raw_rows)} editions"
        if section["id"] == "translation" and lang_count:
            summary += f" across {lang_count} languages"
        summary += f" — {section['summary_suffix']}"
        rows = [dict(project_edition_info(row)) for row in raw_rows]
        edition_groups.append(
            {
                "id": section["id"],
                "label": section["label"],
                "summary": summary,
                "columns": list(section["columns"]),
                "rows": rows,
            }
        )
    return edition_groups


def build_tool_context(tool: Any, fixtures: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Build template context dict for a single tool."""
    fixture = fixtures[tool.name]
    args = fixture["args"]
    payload = fixture["structured_content"]
    display_payload = display_structured_response_value(payload)
    param_rows = parameter_rows(getattr(tool, "parameters", {}) or {})
    out_rows = output_rows(getattr(tool, "output_schema", None), payload)
    required_count = sum(1 for row in param_rows if row["required"])
    optional_count = len(param_rows) - required_count
    example_config = TOOL_EXAMPLE_CONFIG.get(tool.name, {})
    return {
        "name": tool.name,
        "description": short_description(tool.name, tool),
        "summary": card_summary(tool.name, tool),
        "param_rows": param_rows,
        "output_rows": out_rows,
        "required_count": required_count,
        "optional_count": optional_count,
        "call_html": colorize_call(tool.name, args),
        "response_html": colorize_json_value(display_payload),
        "session_assumptions": fixture.get("session_assumptions"),
        "example_layout": example_config.get("layout", "default"),
        "example_screenshot": example_config.get("screenshot"),
    }


def build_groups_context(tools: list[Any], fixtures: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Build grouped tool context for the docs payload."""
    tool_map = {tool.name: tool for tool in tools}
    groups: list[dict[str, Any]] = []
    for group_def in TOOL_GROUPS:
        subgroups: list[dict[str, Any]] = []
        for subgroup_def in group_def["subgroups"]:
            subgroup_tools = [
                build_tool_context(tool_map[name], fixtures)
                for name in subgroup_def["tools"]
                if name in tool_map
            ]
            if subgroup_tools:
                subgroups.append({"label": subgroup_def["label"], "tools": subgroup_tools})
        if subgroups:
            groups.append(
                {
                    "id": group_def["id"],
                    "label": group_def["label"],
                    "blurb": group_def["blurb"],
                    "subgroups": subgroups,
                }
            )
    return groups


__all__ = [
    "load_example_fixtures",
    "parameter_rows",
    "output_rows",
    "visible_fixture_subset",
    "build_flat_tools_context",
    "build_usage_examples_context",
    "build_editions_context",
    "build_tool_context",
    "build_groups_context",
]
