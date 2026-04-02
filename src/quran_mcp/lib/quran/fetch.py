"""GoodMem-native Quran text fetch helpers."""
from __future__ import annotations

from quran_mcp.lib.config.settings import get_settings
from quran_mcp.lib.context.types import AppContext

from quran_mcp.lib.editions.entry import BaseFetchEntry
from quran_mcp.lib.editions.fetcher import EditionFetcherConfig
from quran_mcp.lib.editions.registry import resolve_ids
from quran_mcp.lib.editions.types import EditionFetchResult, fetch_with_config


_EDITION_TYPE = "quran"


class QuranEntry(BaseFetchEntry):
    """Single Quran text entry for one ayah."""

    __slots__ = ()

    def __repr__(self) -> str:
        return f"QuranEntry(ayah_key={self.ayah_key!r}, text={self.text[:50]!r}...)"


class QuranFetchResult(EditionFetchResult[QuranEntry]):
    """Typed Quran fetch result."""


def _get_config() -> EditionFetcherConfig:
    """Build the Quran fetcher config from current settings."""
    return EditionFetcherConfig(
        edition_type=_EDITION_TYPE,
        goodmem_space=get_settings().goodmem.space.quran,
        entry_factory=lambda ayah_key, text, meta: QuranEntry(ayah_key=ayah_key, text=text),
    )


async def fetch_quran(
    ctx: AppContext,
    ayahs: str | list[str],
    editions: str | list[str],
) -> QuranFetchResult:
    """Fetch Quran text for ayahs from one or more editions."""
    return QuranFetchResult.from_result(
        await fetch_with_config(
            ctx,
            ayahs,
            editions,
            config=_get_config(),
        )
    )


def resolve_quran_edition_ids(selector: str | list[str]) -> list[str]:
    """Resolve Quran edition selector(s) to canonical IDs."""
    return resolve_ids(_EDITION_TYPE, selector)
