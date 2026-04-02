"""Unit tests for _fetch_orchestration.py — build_fetch_warnings and helpers."""
from __future__ import annotations

from dataclasses import dataclass

from quran_mcp.mcp.tools._fetch_orchestration import (
    build_fetch_warnings,
    recompute_page_ayahs,
    _canonicalize_editions,
)


@dataclass
class MockGap:
    edition_id: str
    missing_ayahs: list[str]


@dataclass
class MockUnresolved:
    selector: str
    suggestion: str


def test_build_fetch_warnings_with_gaps():
    warnings = build_fetch_warnings(
        gaps=[MockGap("ed-1", ["1:1", "1:2"])],
        unresolved=None,
    )
    assert warnings is not None
    assert len(warnings) == 1
    assert warnings[0].type == "data_gap"


def test_build_fetch_warnings_with_unresolved():
    warnings = build_fetch_warnings(
        gaps=None,
        unresolved=[MockUnresolved("bad-ed", "Try list_editions")],
    )
    assert warnings is not None
    assert len(warnings) == 1
    assert warnings[0].type == "unresolved_edition"


def test_build_fetch_warnings_empty_returns_none():
    assert build_fetch_warnings(gaps=None, unresolved=None) is None
    assert build_fetch_warnings(gaps=[], unresolved=[]) is None


def test_canonicalize_editions_sorts_list():
    assert _canonicalize_editions(["b", "a", "c"]) == ["a", "b", "c"]
    assert _canonicalize_editions("single") == "single"


@dataclass
class MockEntry:
    ayah: str

def test_recompute_page_ayahs_filters_to_survived():
    all_ayahs = ["1:1", "1:2", "1:3", "1:4"]
    results = {"ed": [MockEntry("1:1"), MockEntry("1:3")]}
    page = recompute_page_ayahs(all_ayahs, results, entry_ayahs=lambda e: e.ayah)
    assert page == ["1:1", "1:3"]
