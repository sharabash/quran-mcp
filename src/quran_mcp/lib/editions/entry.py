"""Base class for domain fetch entries with shared ayah_key management."""
from __future__ import annotations

from quran_mcp.lib.ayah_parsing import normalize_ayah_key


class BaseFetchEntry:
    """Common ayah_key normalization and property interface for fetch entries.

    Subclasses add domain-specific fields (e.g. citation_url for tafsir).
    The ``ayah`` property/setter pair exists for callers that use the shorter
    alias — both read and write the canonical ``ayah_key`` slot.
    """

    __slots__ = ("ayah_key", "text")

    def __init__(
        self,
        ayah_key: str | None = None,
        text: str = "",
        *,
        ayah: str | None = None,
    ) -> None:
        self.ayah_key = normalize_ayah_key(ayah_key, ayah)
        self.text = text

    @property
    def ayah(self) -> str:
        return self.ayah_key

    @ayah.setter
    def ayah(self, value: str) -> None:
        self.ayah_key = value
