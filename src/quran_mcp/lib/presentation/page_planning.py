"""Pagination planning and token-budget utilities."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

T = TypeVar("T")

TOKEN_CAP = 25_000
ARABIC_RATIO = 1.9
DEFAULT_RATIO = 3.8


def _is_arabic_script(text: str) -> bool:
    """Check if text is predominantly Arabic/Urdu script (>30% Arabic chars)."""
    if not text:
        return False
    arabic = sum(
        1
        for c in text
        if "\u0600" <= c <= "\u06FF"
        or "\u0750" <= c <= "\u077F"
        or "\u08A0" <= c <= "\u08FF"
        or "\uFB50" <= c <= "\uFDFF"
        or "\uFE70" <= c <= "\uFEFF"
    )
    return arabic > len(text) * 0.3


def _chars_per_token(text: str) -> float:
    """Chars-per-token ratio based on script detection (Arabic/Urdu vs other)."""
    return ARABIC_RATIO if _is_arabic_script(text) else DEFAULT_RATIO


class PaginationMeta(BaseModel):
    """Pagination metadata included in paginated tool responses."""

    model_config = ConfigDict(extra="forbid")

    page: int = Field(description="Current page number (1-based)")
    page_size: int = Field(description="Maximum items per page")
    total_items: int = Field(description="Total items across all pages")
    total_pages: int = Field(description="Total number of pages")
    has_more: bool = Field(description="Whether more pages are available after this one")
    pages: list["PageEntry"] = Field(
        default_factory=list,
        description=(
            "Deterministic manifest of paginated entries across all pages. "
            "Each record identifies the page number plus the edition and ayah key "
            "represented on that page."
        ),
    )


class PageEntry(BaseModel):
    """Reference to one entry within a paginated response manifest."""

    model_config = ConfigDict(extra="forbid")

    page: int = Field(description="1-based page number containing this entry")
    edition_id: str | None = Field(
        default=None,
        description="Edition identifier for this entry, or null when the result is not tied to a single edition",
    )
    ayah_key: str = Field(
        description="Ayah key or compact ayah range for this entry (e.g. '2:255' or '2:2-3')"
    )


def paginate(items: list[T], page: int, page_size: int) -> tuple[list[T], PaginationMeta]:
    """Paginate a list of items and return (page_items, metadata)."""
    total = len(items)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(1, page)

    offset = (page - 1) * page_size
    page_items = items[offset : offset + page_size]

    meta = PaginationMeta(
        page=page,
        page_size=page_size,
        total_items=total,
        total_pages=total_pages,
        has_more=page < total_pages,
    )
    return page_items, meta


def choose_auto_page_size(tool_name: str, host: str | None = None) -> int:
    """Choose an internal page size tuned to the client host."""
    host_key = host or "unknown"
    defaults: dict[str, dict[str, int]] = {
        "search_quran": {"claude": 10, "default": 18},
        "search_translation": {"claude": 10, "default": 18},
        "search_tafsir": {"claude": 5, "default": 8},
        "fetch_quran": {"claude": 50, "default": 80},
        "fetch_translation": {"claude": 50, "default": 80},
        "fetch_tafsir": {"claude": 20, "default": 28},
    }
    tool_defaults = defaults.get(tool_name, {"claude": 10, "default": 10})
    return tool_defaults["claude"] if host_key == "claude" else tool_defaults["default"]


def estimate_tokens(obj: Any) -> int:
    """Rough token estimate for a serializable object."""
    if isinstance(obj, str):
        return int(len(obj) / _chars_per_token(obj))
    if isinstance(obj, BaseModel):
        text = obj.model_dump_json()
        return int(len(text) / _chars_per_token(text))
    if isinstance(obj, list):
        total = 1
        for item in obj:
            if isinstance(item, BaseModel):
                serialized = item.model_dump_json()
                total += int(len(serialized) / _chars_per_token(serialized))
            elif isinstance(item, str):
                total += int((len(item) + 3) / _chars_per_token(item))
            else:
                try:
                    serialized = json.dumps(item, default=str)
                    total += int(len(serialized) / _chars_per_token(serialized))
                except (TypeError, ValueError):
                    # Intentional: skip unserializable items in token estimation
                    logger.debug("Could not serialize item for token estimation", exc_info=True)
        return total
    try:
        text = json.dumps(obj, default=str)
        return int(len(text) / _chars_per_token(text))
    except (TypeError, ValueError):
        return 0


def _extract_ayah_key(entry: Any) -> str:
    """Extract the primary ayah key from an entry."""
    for attr in ("ayah_key", "ayah"):
        val = getattr(entry, attr, None)
        if val:
            return str(val)
    ayahs = getattr(entry, "ayahs", None)
    if isinstance(ayahs, list) and ayahs:
        return str(ayahs[0])
    return ""


def _entry_page_key(entry: Any) -> str:
    """Stable display key for pagination indexes and sorting."""
    range_key = getattr(entry, "range", None)
    if range_key:
        return str(range_key)
    return _extract_ayah_key(entry)


def _parse_page_key(key: str) -> tuple[int, int, str]:
    """Parse a S:V or S:V-V key for deterministic ordering."""
    if not key:
        return (10**9, 10**9, "")
    try:
        surah_part, ayah_part = key.split(":", 1)
        first_ayah = ayah_part.split("-", 1)[0]
        return (int(surah_part), int(first_ayah), key)
    except (ValueError, TypeError):
        return (10**9, 10**9, key)


def _page_items_to_results(page_items: list[tuple[str, str, T]]) -> dict[str, list[T]]:
    """Convert flattened page items back to dict-keyed results."""
    grouped: dict[str, list[T]] = {}
    for edition_id, _entry_key, entry in page_items:
        grouped.setdefault(edition_id, []).append(entry)
    return grouped


def _estimate_dict_page_tokens(page_items: list[tuple[str, str, T]]) -> int:
    """Estimate token cost for a dict-keyed page slice."""
    return estimate_tokens({"results": _page_items_to_results(page_items)})


def _estimate_list_page_tokens(page_items: list[T]) -> int:
    """Estimate token cost for a flat list page slice."""
    return estimate_tokens(page_items)


def _build_pages_manifest_dict(
    pages: list[list[tuple[str, str, T]]],
) -> list[PageEntry]:
    """Build a flat page manifest for dict-keyed page plans."""
    manifest: list[PageEntry] = []
    for page_number, page_items in enumerate(pages, start=1):
        for edition_id, entry_key, _entry in page_items:
            manifest.append(PageEntry(page=page_number, edition_id=edition_id, ayah_key=entry_key))
    return manifest


def _build_pages_manifest_list(
    pages: list[list[T]],
    page_entry_fn: Callable[[T], tuple[str | None, str]] | None,
) -> list[PageEntry]:
    """Build a flat page manifest for list-based page plans."""
    if page_entry_fn is None:
        return []

    manifest: list[PageEntry] = []
    for page_number, page_items in enumerate(pages, start=1):
        for item in page_items:
            edition_id, ayah_key = page_entry_fn(item)
            manifest.append(PageEntry(page=page_number, edition_id=edition_id, ayah_key=ayah_key))
    return manifest


def build_pages_for_list(
    items: list[T],
    page_entry_fn: Callable[[T], tuple[str | None, str]],
    page: int = 1,
) -> list[PageEntry]:
    """Build a one-page manifest for a flat list of already-selected items."""
    return [
        PageEntry(page=page, edition_id=edition_id, ayah_key=ayah_key)
        for edition_id, ayah_key in (page_entry_fn(item) for item in items)
    ]


def build_pages_for_dict_results(
    results: dict[str, list[T]],
    page: int = 1,
) -> list[PageEntry]:
    """Build a one-page manifest for dict-keyed results already selected for delivery."""
    manifest: list[PageEntry] = []
    for edition_id in sorted(results):
        entries = sorted(
            results[edition_id],
            key=lambda entry: _parse_page_key(_entry_page_key(entry)),
        )
        for entry in entries:
            manifest.append(PageEntry(page=page, edition_id=edition_id, ayah_key=_entry_page_key(entry)))
    return manifest


def _flatten_dict_results(
    results: dict[str, list[T]],
) -> list[tuple[str, str, T]]:
    """Flatten dict-keyed results into a deterministic entry sequence."""
    flat_items: list[tuple[str, str, T]] = []
    for edition_id in sorted(results):
        entries = sorted(
            results[edition_id],
            key=lambda entry: _parse_page_key(_entry_page_key(entry)),
        )
        for entry in entries:
            flat_items.append((edition_id, _entry_page_key(entry), entry))
    return flat_items


def _build_page_units(
    flat_items: list[tuple[str, str, T]],
    bundle_key_fn: Callable[[T], str] | None,
) -> list[list[tuple[str, str, T]]]:
    """Create atomic page units: either per entry or per caller-defined bundle."""
    if bundle_key_fn is None:
        return [[item] for item in flat_items]

    bundles: dict[str, list[tuple[str, str, T]]] = defaultdict(list)
    for edition_id, entry_key, entry in flat_items:
        bundles[bundle_key_fn(entry)].append((edition_id, entry_key, entry))

    sorted_keys = sorted(bundles, key=_parse_page_key)
    units: list[list[tuple[str, str, T]]] = []
    for key in sorted_keys:
        units.append(sorted(bundles[key], key=lambda item: (item[0], _parse_page_key(item[1]))))
    return units


def enforce_token_cap(
    items: list[T],
    meta: PaginationMeta,
    cap: int = TOKEN_CAP,
    page_entry_fn: Callable[[T], tuple[str | None, str]] | None = None,
) -> tuple[list[T], PaginationMeta]:
    """Paginate flat list results into full-item token-aware pages."""
    if not items:
        updated_meta = meta.model_copy(
            update={
                "page": max(1, meta.page),
                "page_size": max(1, meta.page_size),
                "total_items": 0,
                "total_pages": 1,
                "has_more": False,
                "pages": [],
            }
        )
        return items, updated_meta

    requested_page = max(1, meta.page)
    requested_page_size = max(1, meta.page_size)
    total_est = estimate_tokens(items)

    pages: list[list[T]] = []
    current_page: list[T] = []

    for item in items:
        candidate = current_page + [item]
        candidate_est = _estimate_list_page_tokens(candidate)
        exceeds_count = len(candidate) > requested_page_size
        exceeds_cap = candidate_est > cap

        if current_page and (exceeds_count or exceeds_cap):
            pages.append(current_page)
            current_page = [item]
        else:
            current_page = candidate

    if current_page:
        pages.append(current_page)

    total_pages = max(1, len(pages))
    page_items = pages[requested_page - 1] if requested_page <= total_pages else []
    delivered_est = _estimate_list_page_tokens(page_items) if page_items else 0
    page_manifest = _build_pages_manifest_list(pages, page_entry_fn)

    if total_pages > 1:
        logger.warning(
            "Token cap repagination: page=%d/%d items=%d total_items=%d (cap=%d, est_total=%d, est_page=%d)",
            requested_page,
            total_pages,
            len(page_items),
            len(items),
            cap,
            total_est,
            delivered_est,
        )

    updated_meta = meta.model_copy(
        update={
            "page": requested_page,
            "page_size": requested_page_size,
            "total_items": len(items),
            "total_pages": total_pages,
            "has_more": requested_page < total_pages,
            "pages": page_manifest,
        }
    )
    return page_items, updated_meta


def enforce_token_cap_dict(
    results: dict[str, list[T]],
    meta: PaginationMeta,
    cap: int = TOKEN_CAP,
    bundle_key_fn: Callable[[T], str] | None = None,
) -> tuple[dict[str, list[T]], PaginationMeta]:
    """Paginate dict-keyed results into full-entry token-aware pages."""
    if not results:
        return results, meta

    requested_page = max(1, meta.page)
    requested_page_size = max(1, meta.page_size)
    flat_items = _flatten_dict_results(results)

    if not flat_items:
        updated_meta = meta.model_copy(
            update={
                "page": requested_page,
                "page_size": requested_page_size,
                "total_items": 0,
                "total_pages": 1,
                "has_more": False,
                "pages": [],
            }
        )
        return {}, updated_meta

    units = _build_page_units(flat_items, bundle_key_fn)
    total_est = _estimate_dict_page_tokens(flat_items)
    pages: list[list[tuple[str, str, T]]] = []
    current_page: list[tuple[str, str, T]] = []
    current_unit_count = 0

    for unit in units:
        candidate = current_page + unit
        candidate_est = _estimate_dict_page_tokens(candidate)
        exceeds_count = current_unit_count + 1 > requested_page_size
        exceeds_cap = candidate_est > cap

        if current_page and (exceeds_count or exceeds_cap):
            pages.append(current_page)
            current_page = list(unit)
            current_unit_count = 1
        else:
            current_page = candidate
            current_unit_count += 1

    if current_page:
        pages.append(current_page)

    total_pages = max(1, len(pages))
    page_items = pages[requested_page - 1] if requested_page <= total_pages else []
    page_results = _page_items_to_results(page_items)
    pages_manifest = _build_pages_manifest_dict(pages)
    delivered_est = _estimate_dict_page_tokens(page_items) if page_items else 0

    if total_pages > 1:
        first_ref = f"{page_items[0][0]}:{page_items[0][1]}" if page_items else "-"
        logger.warning(
            "Token cap repagination: page=%d/%d items=%d total_items=%d (cap=%d, est_total=%d, est_page=%d, first=%s)",
            requested_page,
            total_pages,
            len(page_items),
            len(units),
            cap,
            total_est,
            delivered_est,
            first_ref,
        )

    updated_meta = meta.model_copy(
        update={
            "page": requested_page,
            "page_size": requested_page_size,
            "total_items": len(units),
            "total_pages": total_pages,
            "has_more": requested_page < total_pages,
            "pages": pages_manifest,
        }
    )
    return page_results, updated_meta


MAX_SEARCH_DEPTH = 200
