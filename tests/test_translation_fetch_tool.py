"""Unit tests for mcp/tools/translation/fetch.py — result projection."""
from __future__ import annotations

from dataclasses import dataclass

from quran_mcp.mcp.tools.translation.fetch import _build_translation_results


@dataclass
class FakeEntry:
    ayah: str
    text: str


def test_build_translation_results_projects_entries():
    raw = {
        "en-abdel-haleem": [
            FakeEntry(ayah="1:1", text="In the name of God"),
            FakeEntry(ayah="1:2", text="Praise be to God"),
        ],
    }
    result = _build_translation_results(raw)
    assert "en-abdel-haleem" in result
    assert len(result["en-abdel-haleem"]) == 2
    assert result["en-abdel-haleem"][0].ayah == "1:1"
    assert result["en-abdel-haleem"][0].text == "In the name of God"


def test_build_translation_results_empty():
    assert _build_translation_results({}) == {}


def test_build_translation_results_multiple_editions():
    raw = {
        "en-abdel-haleem": [FakeEntry(ayah="1:1", text="English")],
        "es-cortes": [FakeEntry(ayah="1:1", text="Spanish")],
    }
    result = _build_translation_results(raw)
    assert len(result) == 2
    assert result["en-abdel-haleem"][0].text == "English"
    assert result["es-cortes"][0].text == "Spanish"
