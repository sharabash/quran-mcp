"""
Edition data loading from unified editions.json registry.

Supports any edition type present in the file (tafsir, translation, quran, etc.).
This module handles the raw data loading and schema projection.
"""
from __future__ import annotations

import json
import logging
from dataclasses import replace
from functools import lru_cache
from importlib import resources
from typing import Any, cast

from .types import EDITION_TYPES, EditionRecord, EditionType

logger = logging.getLogger(__name__)

REQUIRED_EDITION_FIELDS = (
    "edition_id",
    "edition_type",
    "lang",
    "code",
    "name",
)

_VALID_EDITION_TYPES = set(EDITION_TYPES)


def _coerce_edition_type(value: object) -> EditionType | None:
    if isinstance(value, str) and value in _VALID_EDITION_TYPES:
        return cast(EditionType, value)
    return None


@lru_cache(maxsize=1)
def _load_editions_json() -> dict[str, dict[str, dict[str, Any]]]:
    """
    Load and parse editions.json from package data.
    Cached for process lifetime (static data).

    Returns:
        Dict with edition type keys (e.g. "translation", "tafsir", "quran"),
        each containing a dict of edition_id -> edition record.

        Structure: {"translation": {...}, "tafsir": {...}, "quran": {...}}

    Raises:
        FileNotFoundError: If editions.json is missing from package.
        json.JSONDecodeError: If editions.json is malformed.
    """
    try:
        raw = resources.files("quran_mcp.data").joinpath("editions.json").read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            logger.warning(
                "editions.json contains invalid UTF-8 bytes; decoding with replacement characters"
            )
            text = raw.decode("utf-8-sig", errors="replace")
        data = json.loads(text)
        return data
    except FileNotFoundError as e:
        raise FileNotFoundError(
            "editions.json not found in quran_mcp.data package. "
            "Ensure the file is included in package_data."
        ) from e
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(
            f"editions.json is malformed: {e.msg}", e.doc, e.pos
        ) from e


def _project_to_schema(records: list[dict[str, Any]]) -> list[EditionRecord]:
    """
    Project edition records to public schema (only EDITION_FIELDS).

    Handles missing fields gracefully (e.g., 'author' may be None).

    Args:
        records: List of edition dictionaries (may have extra fields).

    Returns:
        List of immutable EditionRecord objects in insertion order.
    """
    projected: list[EditionRecord] = []
    for rec in records:
        # Required fields must be non-empty strings for an honest EditionRecord contract.
        invalid_fields = [
            field
            for field in REQUIRED_EDITION_FIELDS
            if not isinstance(rec.get(field), str) or not str(rec.get(field, "")).strip()
        ]
        edition_type = _coerce_edition_type(rec.get("edition_type"))
        if edition_type is None:
            invalid_fields.append("edition_type")
        if invalid_fields:
            logger.warning(
                "Skipping record with invalid required fields %s: %s",
                invalid_fields,
                rec.get("edition_id", rec.get("code", "unknown")),
            )
            continue

        assert edition_type is not None

        proj_rec = EditionRecord(
            edition_id=rec["edition_id"],
            edition_type=edition_type,
            lang=rec["lang"],
            code=rec["code"],
            name=rec["name"],
            author=rec.get("author"),
            description=rec.get("description"),
            choose_when=rec.get("choose_when"),
            avg_entry_tokens=rec.get("avg_entry_tokens"),
            qf_resource_id=rec.get("qf_resource_id"),
        )

        # Map resource_id to qf_resource_id if needed.
        if proj_rec.qf_resource_id is None and "resource_id" in rec:
            proj_rec = replace(proj_rec, qf_resource_id=rec["resource_id"])

        projected.append(proj_rec)

    return projected


def load_editions_by_type(edition_type: EditionType) -> list[EditionRecord]:
    """
    Load editions from unified registry filtered by type.

    GENERIC: Works with any edition type present in editions.json.
    Does NOT hardcode type names - reads dynamically from file.

    Args:
        edition_type: Edition type to load (e.g., "translation", "tafsir", "quran").
                      This is the `edition_type` field value, NOT the top-level key.
                      The function handles the mapping to top-level keys.

    Returns:
        List of EditionRecord objects, in insertion order from editions.json.
        Returns empty list if type not found (graceful degradation).
    """
    data = _load_editions_json()

    # Validate top-level structure
    if not isinstance(data, dict):
        raise ValueError(f"editions.json must be a dict, got {type(data)}")

    # Find the top-level key that contains this edition_type
    # Note: After Phase 0, top-level keys match edition_type (both singular)
    # We search all top-level dicts for matching edition_type field

    all_records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()  # Deduplicate by edition_id

    for _, editions_dict in data.items():
        if not isinstance(editions_dict, dict):
            continue

        # Convert dict of dicts to list of records
        for dict_key, record in editions_dict.items():
            if isinstance(record, dict) and record.get("edition_type") == edition_type:
                # Deduplicate: skip if we've already seen this edition_id
                # CRITICAL: Track record's actual edition_id, not the dict key
                record_id = record.get("edition_id")
                if not isinstance(record_id, str) or not record_id.strip():
                    logger.warning(
                        "Skipping record missing or invalid edition_id: %s",
                        dict_key,
                    )
                    continue
                if record_id in seen_ids:
                    logger.warning("Duplicate edition_id %r found, skipping", record_id)
                    continue
                seen_ids.add(record_id)
                all_records.append(record)

    if not all_records:
        logger.warning(
            "No records found with edition_type=%r in editions.json", edition_type
        )
        return []

    # Project to public schema
    projected_records = _project_to_schema(all_records)

    # CRITICAL: Preserve insertion order from editions.json
    # Python 3.7+ dicts maintain insertion order, so iteration preserves JSON order
    # DO NOT sort - the ordering is curated/manual (not alphabetical)

    return projected_records
