"""Filter expression DSL helpers for GoodMem metadata queries."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

logger = logging.getLogger(__name__)

# Operator precedence for parsing (longest first to avoid partial matches)
_FILTER_OPERATORS = [">=", "<=", "!=", ">", "<", "="]

# Valid field name pattern: starts with letter/underscore, followed by
# letters, numbers, underscores, or dots (for nested JSON paths)
_FIELD_NAME_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_.]*$")

# Type mapping from Python types to SQL types
_TYPE_TO_SQL: dict[type, str] = {
    int: "INT",
    float: "NUMERIC",
    date: "DATE",
    datetime: "TIMESTAMPTZ",
    str: "TEXT",
}


@dataclass
class FilterTerm:
    """Parsed filter term from CLI input."""

    field: str
    operator: str
    value: Any
    value_type: type


def escape_literal(value: str) -> str:
    """Escape single quotes in a value for use inside SQL string literals."""
    return value.replace("'", "\\'")


def _cast_clause(field: str, python_type: type) -> str:
    """Build the CAST expression for a field."""
    sql_type = _TYPE_TO_SQL.get(python_type, "TEXT")
    return f"CAST(val('$.{field}') AS {sql_type})"


def _format_literal(value: Any, python_type: type) -> str:
    """Format a value as a SQL literal with appropriate type handling."""
    if python_type is int:
        return str(value)
    if python_type is float:
        return str(value)
    if python_type is date:
        return f"CAST('{value.isoformat()}' AS DATE)"
    if python_type is datetime:
        return f"CAST('{value.isoformat()}' AS TIMESTAMPTZ)"
    return f"'{escape_literal(str(value))}'"


def _infer_value_type(value_str: str) -> tuple[Any, type]:
    """Infer the type of a filter value and parse it.

    Intentional cascade: each ValueError falls through to the next type probe.
    """
    try:
        return int(value_str), int
    except ValueError:
        pass

    try:
        return float(value_str), float
    except ValueError:
        pass

    try:
        return date.fromisoformat(value_str), date
    except ValueError:
        pass

    try:
        return datetime.fromisoformat(value_str), datetime
    except ValueError:
        pass

    return value_str, str


def parse_filter_string(raw: str) -> FilterTerm:
    """Parse a filter string into a FilterTerm."""
    raw = raw.strip()

    operator_pos = -1
    found_operator = None
    for op in _FILTER_OPERATORS:
        pos = raw.find(op)
        if pos == -1:
            continue
        if operator_pos == -1 or pos < operator_pos:
            operator_pos = pos
            found_operator = op
        elif pos == operator_pos and len(op) > len(found_operator):
            found_operator = op

    if found_operator is None:
        raise ValueError(f"Invalid filter '{raw}': no operator found.")

    field = raw[:operator_pos].strip()
    value_str = raw[operator_pos + len(found_operator):].strip()

    if not field:
        raise ValueError(f"Invalid filter '{raw}': missing field name.")
    if not _FIELD_NAME_PATTERN.match(field):
        raise ValueError(
            f"Invalid field name '{field}'; only letters, numbers, underscores, and dots allowed."
        )
    if not value_str:
        raise ValueError(f"Invalid filter '{raw}': missing value.")

    value, value_type = _infer_value_type(value_str)
    return FilterTerm(
        field=field,
        operator=found_operator,
        value=value,
        value_type=value_type,
    )


def build_filter_expression(terms: list[FilterTerm]) -> str | None:
    """Build a GoodMem filter expression from parsed FilterTerms."""
    if not terms:
        return None

    field_groups: dict[str, list[FilterTerm]] = {}
    for term in terms:
        field_groups.setdefault(term.field, []).append(term)

    field_clauses: list[str] = []
    for field, group_terms in field_groups.items():
        equality_terms = [t for t in group_terms if t.operator == "="]
        other_terms = [t for t in group_terms if t.operator != "="]

        clauses: list[str] = []
        if len(equality_terms) == 1:
            term = equality_terms[0]
            cast = _cast_clause(term.field, term.value_type)
            literal = _format_literal(term.value, term.value_type)
            clauses.append(f"{cast} = {literal}")
        elif len(equality_terms) > 1:
            cast = _cast_clause(field, equality_terms[0].value_type)
            literals = [_format_literal(t.value, t.value_type) for t in equality_terms]
            clauses.append(f"{cast} IN ({', '.join(literals)})")

        for term in other_terms:
            cast = _cast_clause(term.field, term.value_type)
            literal = _format_literal(term.value, term.value_type)
            clauses.append(f"{cast} {term.operator} {literal}")

        if len(clauses) == 1:
            field_clauses.append(clauses[0])
        elif len(clauses) > 1:
            field_clauses.append(f"({' AND '.join(clauses)})")

    return " AND ".join(field_clauses)


def combine_filter_expressions(
    cast_expr: str | None,
    raw_exprs: list[str] | None,
) -> str | None:
    """Combine CAST-based and raw filter expressions with AND logic."""
    valid_raw = [e.strip() for e in (raw_exprs or []) if e and e.strip()]

    if len(valid_raw) > 1:
        raw_combined = " AND ".join(f"({e})" for e in valid_raw)
    elif len(valid_raw) == 1:
        raw_combined = valid_raw[0]
    else:
        raw_combined = None

    if cast_expr and raw_combined:
        return f"({cast_expr.strip()}) AND ({raw_combined})"
    if cast_expr:
        return cast_expr
    if raw_combined:
        return raw_combined
    return None


def build_metadata_filter_expression(metadata_filters: dict[str, Any]) -> str:
    """Build a CAST-based filter expression from metadata key/value pairs."""
    conditions: list[str] = []

    for key, value in metadata_filters.items():
        if isinstance(value, str):
            escaped_value = escape_literal(value)
            conditions.append(f"CAST(val('$.{key}') AS TEXT) = '{escaped_value}'")
        elif isinstance(value, int):
            conditions.append(f"CAST(val('$.{key}') AS INT) = {value}")
        elif isinstance(value, float):
            conditions.append(f"CAST(val('$.{key}') AS NUMERIC) = {value}")
        else:
            str_value = escape_literal(str(value))
            conditions.append(f"CAST(val('$.{key}') AS TEXT) = '{str_value}'")

    return " AND ".join(conditions)


__all__ = [
    "FilterTerm",
    "escape_literal",
    "_cast_clause",
    "_format_literal",
    "_infer_value_type",
    "parse_filter_string",
    "build_filter_expression",
    "combine_filter_expressions",
    "build_metadata_filter_expression",
]
