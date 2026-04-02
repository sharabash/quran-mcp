"""Unit tests for lib/editions/entry.py — BaseFetchEntry ayah_key normalization."""
from __future__ import annotations

from quran_mcp.lib.editions.entry import BaseFetchEntry


def test_entry_from_ayah_key():
    entry = BaseFetchEntry(ayah_key="2:255", text="test")
    assert entry.ayah_key == "2:255"
    assert entry.ayah == "2:255"
    assert entry.text == "test"


def test_entry_from_ayah_alias():
    entry = BaseFetchEntry(ayah="2:255", text="test")
    assert entry.ayah_key == "2:255"
    assert entry.ayah == "2:255"


def test_entry_ayah_setter():
    entry = BaseFetchEntry(ayah_key="1:1", text="")
    entry.ayah = "2:255"
    assert entry.ayah_key == "2:255"


def test_entry_no_key_gives_empty_string():
    entry = BaseFetchEntry(text="no key")
    assert entry.ayah_key == ""
