"""
Edition registry operations: list, filter, get, and resolve.

Provides a unified API for querying and resolving edition identifiers,
parameterized by edition_type. Consolidates functionality previously
spread across editions_loader.py and ayah_parsing.py.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from re import Pattern

from .loader import load_editions_by_type
from .types import EditionInfoRecord, EditionListRecord, EditionRecord, EditionType, project_edition_info

# ---------------------------------------------------------------------------
# Text-matching utilities for fuzzy search
# ---------------------------------------------------------------------------


def normalize_text(value: str) -> str:
    """Case-fold and strip non-word/non-space characters for fuzzy matching."""
    return re.sub(r"[^\w\s]+", "", value.casefold())


@lru_cache(maxsize=32)
def build_fallback_pattern(query: str) -> Pattern[str] | None:
    """
    Build a tolerant regex for fuzzy matching (words separated by whitespace).
    Only generated for queries with 4+ non-space characters.

    Cached to avoid re-compiling the same regex when filtering multiple records.
    """
    cleaned = query.strip()
    if len(cleaned) < 4:
        return None
    parts = re.split(r"\s+", cleaned.casefold())
    return re.compile(r".*" + r"\W+".join(map(re.escape, parts)) + r".*", re.IGNORECASE)


def matches_name_fields(rec: EditionRecord, term: str) -> bool:
    """Exact (case-insensitive) match across name-like fields or tolerant regex if eligible."""
    if not term:
        return True
    candidates = (rec.name, rec.author, rec.code, rec.edition_id)
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.casefold() == term.casefold():
            return True
    pat = build_fallback_pattern(term)
    if not pat:
        return False
    for candidate in candidates:
        target = normalize_text(candidate) if isinstance(candidate, str) else ""
        if pat.search(target):
            return True
    return False


# ---------------------------------------------------------------------------
# Core registry operations (parameterized by edition_type)
# ---------------------------------------------------------------------------


def get_by_edition_id(edition_type: EditionType, edition_id: str) -> EditionRecord | None:
    """Look up an edition by its edition_id."""
    for rec in load_editions_by_type(edition_type):
        if rec.edition_id.casefold() == edition_id.casefold():
            return rec
    return None


def list_editions(edition_type: EditionType) -> list[EditionRecord]:
    """List all editions of a given type."""
    return load_editions_by_type(edition_type)


def filter_editions(
    edition_type: EditionType,
    lang: str | None = None,
    name: str | None = None,
) -> list[EditionRecord]:
    """Filter editions by language and/or name (exact + fuzzy, intersected)."""
    records = load_editions_by_type(edition_type)
    out: list[EditionRecord] = []
    for rec in records:
        if lang and rec.lang.casefold() != lang.casefold():
            continue
        if name and not matches_name_fields(rec, name):
            continue
        out.append(rec)
    return out


def get_edition_list(
    edition_type: EditionType,
    lang: str | None = None,
    name: str | None = None,
    include_internal_id: bool = False,
) -> EditionListRecord:
    """List editions with optional filtering, returning a dict of filters/results/count."""
    result_payloads: list[EditionInfoRecord]
    if not include_internal_id:
        result_payloads = list(
            list_edition_summaries(
                edition_type,
                lang=lang,
                name=name,
            )
        )
    else:
        results = filter_editions(edition_type, lang=lang, name=name)
        result_payloads = [ed.as_public_dict() for ed in results]

    filters: dict[str, str] = {}
    if lang is not None:
        filters["lang"] = lang
    if name is not None:
        filters["name"] = name

    return {
        "filters": filters,
        "results": result_payloads,
        "count": len(result_payloads),
    }


def list_edition_summaries(
    edition_type: EditionType,
    *,
    lang: str | None = None,
    name: str | None = None,
    sort_by_edition_id: bool = False,
) -> list[EditionInfoRecord]:
    """Return the shared public summary view for one edition type."""
    records = filter_editions(edition_type, lang=lang, name=name)
    if sort_by_edition_id:
        records = sorted(records, key=lambda record: record.edition_id)
    return [project_edition_info(record) for record in records]


# ---------------------------------------------------------------------------
# Edition ID resolution
# ---------------------------------------------------------------------------


def _tokenize_multi_value(value: str | list[str]) -> list[str]:
    """Split a comma/whitespace-separated string or pass through a list of strings."""
    if isinstance(value, str):
        return [t for t in re.split(r"[\s,]+", value.strip()) if t]
    return list(value)


@dataclass(frozen=True, slots=True)
class ResolveResult:
    """Result of resolving edition selectors with unresolved tracking."""

    resolved: list[str]
    unresolved: list[str]


def resolve_ids(edition_type: EditionType, edition_selector: str | list[str]) -> list[str]:
    """Resolve selector tokens to edition IDs (exact > code > lang > fuzzy)."""
    result = resolve_ids_with_unresolved(edition_type, edition_selector)
    if not result.resolved:
        editions = list_editions(edition_type)
        examples = ", ".join(ed.edition_id for ed in editions[:10])
        raise ValueError(
            f"No {edition_type} editions matched '{edition_selector}'. Known examples: {examples}"
        )
    return result.resolved


def resolve_ids_with_unresolved(
    edition_type: EditionType, edition_selector: str | list[str]
) -> ResolveResult:
    """Like resolve_ids() but returns unresolved tokens instead of raising."""
    tokens = _tokenize_multi_value(edition_selector)
    editions = list_editions(edition_type)

    # Build lookup indices
    identifiers_by_id: dict[str, str] = {}
    identifiers_by_code: dict[str, list[str]] = {}
    lang_to_identifiers: dict[str, list[str]] = {}

    for ed in editions:
        identifier = ed.edition_id
        if identifier:
            identifiers_by_id[identifier.casefold()] = identifier
        code_key = ed.code.casefold()
        if code_key and identifier:
            identifiers_by_code.setdefault(code_key, []).append(identifier)
        lang_key = ed.lang.casefold()
        if lang_key and identifier:
            lang_to_identifiers.setdefault(lang_key, []).append(identifier)

    resolved: list[str] = []
    unresolved: list[str] = []
    seen: set[str] = set()

    for tok in tokens:
        t = tok.casefold()
        matched = False

        # Exact identifier
        if t in identifiers_by_id:
            identifier = identifiers_by_id[t]
            if identifier and identifier not in seen:
                resolved.append(identifier)
                seen.add(identifier)
            matched = True
        # Exact code
        elif t in identifiers_by_code:
            for identifier in identifiers_by_code[t]:
                if identifier and identifier not in seen:
                    resolved.append(identifier)
                    seen.add(identifier)
            matched = True
        # Language (2 letters)
        elif len(t) == 2 and t in lang_to_identifiers:
            for identifier in lang_to_identifiers[t]:
                if identifier and identifier not in seen:
                    resolved.append(identifier)
                    seen.add(identifier)
            matched = True
        # Fuzzy across name/author/code/id if long enough
        elif len(t) >= 4:
            fuzzy = filter_editions(edition_type, name=tok)
            if fuzzy:
                for ed in fuzzy:
                    identifier = ed.edition_id
                    if identifier and identifier not in seen:
                        resolved.append(identifier)
                        seen.add(identifier)
                matched = True

        if not matched:
            unresolved.append(tok)

    return ResolveResult(resolved=resolved, unresolved=unresolved)
