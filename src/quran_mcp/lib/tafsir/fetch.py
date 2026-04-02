"""GoodMem-native tafsir fetch helpers."""
from __future__ import annotations

from typing import Mapping

from quran_mcp.lib.config.settings import get_settings
from quran_mcp.lib.context.types import AppContext

from quran_mcp.lib.editions.entry import BaseFetchEntry
from quran_mcp.lib.editions.fetcher import EditionFetcherConfig
from quran_mcp.lib.editions.registry import resolve_ids
from quran_mcp.lib.editions.types import (
    EditionFetchResult,
    SummaryPromptConfig,
    fetch_with_config,
)
from quran_mcp.lib.presentation.summary import infer_summary_lang


class TafsirEntry(BaseFetchEntry):
    """Single tafsir entry for one ayah."""

    __slots__ = ("citation_url", "passage_ayah_range")

    def __init__(
        self,
        ayah_key: str | None = None,
        text: str = "",
        citation_url: str | None = None,
        passage_ayah_range: str | None = None,
        *,
        ayah: str | None = None,
    ) -> None:
        super().__init__(ayah_key=ayah_key, text=text, ayah=ayah)
        self.citation_url = citation_url
        self.passage_ayah_range = passage_ayah_range


class TafsirFetchResult(EditionFetchResult[TafsirEntry]):
    """Typed tafsir fetch result."""


TAFSIR_SUMMARY_PROMPTS = SummaryPromptConfig(
    sampling_system_template=(
        "You are a meticulous Qurʾān tafsīr summarizer. Produce faithful, neutral summaries "
        "from the supplied tafsīr text only.\n\n"
        "Requirements:\n"
        "- Respect mode:\n"
        "  • aggregate → unified digest; reconcile sources; note disagreements.\n"
        "  • separate → separate sections per source edition.\n"
        "  • compare  → emphasize similarities/differences between sources.\n"
        "- Respect length: short (3–5 bullets), medium (6–10), detailed (≥12 bullets/paragraphs).\n"
        "- Respect language (lang = ar|en) for summary prose.\n"
        "- If focus is provided, spotlight material answering it.\n\n"
        "Citations:\n"
        "- If a source_legend is provided in the options, use the human-readable source names "
        "for citations instead of raw edition_ids. For example, cite as [Ibn Kathir] or "
        "[Al-Jalalayn § 2:255], not [en-ibn-kathir].\n"
        "- If no source_legend is provided, fall back to [edition_id] or [edition_id § 2:255].\n"
        "- Use multiple citations when combining viewpoints.\n"
        "- Finish with a 'Works Cited' footer listing each source once with its full name.\n"
        "- If source markers appear (e.g. '--- SOURCE: … ---'), rely on them for attribution.\n\n"
        "Style:\n"
        "- Faithful, concise, jargon-aware. Quote brief key phrases when clarifying meaning.\n"
        "- Highlight uncertainties; never fabricate information."
    ),
    sampling_user_template=(
        "Summarize the following tafsīr.\n\n"
        "Options:\n"
        "{options}\n\n"
        "Text:\n"
        "---------------- BEGIN TAFSIR ----------------\n"
        "{text}\n"
        "----------------- END TAFSIR -----------------\n\n"
        "Output format:\n"
        "- mode = aggregate → unified list/paragraphs with inline citations.\n"
        "- mode = separate  → section per source edition, each with bullets + citations.\n"
        "- mode = compare   → bullets highlighting agreements/disagreements with citations.\n"
        "- End with 'Works Cited:' listing each source with its full name."
    ),
    prompt_assistant_template=(
        "I'm ready to summarize tafsīr text according to these guidelines:\n\n"
        "• Mode: aggregate (unified), separate (per-source), or compare (similarities/differences)\n"
        "• Length: short (3-5 bullets), medium (6-10), detailed (12+ bullets/paragraphs)\n"
        "• Language: ar (Arabic) or en (English)\n"
        "• Citations: Inline [source name] or [source name § ayah] format, with Works Cited footer\n"
        "• Style: Faithful to sources, concise, with proper attribution\n\n"
        "What would you like me to summarize?"
    ),
    prompt_user_template=(
        "Summarize the following tafsīr.\n\n"
        "Options:\n"
        "{options}\n\n"
        "Text:\n"
        "---------------- BEGIN TAFSIR ----------------\n"
        "{text}\n"
        "----------------- END TAFSIR -----------------\n\n"
        "Requirements:\n"
        "- Respect the specified mode, length, and language\n"
        "- Use source display names from source_legend (if provided) for inline citations\n"
        "- If focus is provided, emphasize that aspect\n"
        "- End with 'Works Cited:' section listing all referenced sources by full name\n"
        "- Be faithful to the source material; don't fabricate information"
    ),
)


def _build_tafsir_entry(ayah: str, text: str, meta: Mapping[str, object]) -> TafsirEntry:
    """Build one tafsir entry from EditionFetcher inputs."""
    citation_url = meta.get("citation_url") or meta.get("url")
    return TafsirEntry(
        ayah_key=ayah,
        text=text,
        citation_url=str(citation_url) if citation_url is not None else None,
        passage_ayah_range=(
            str(meta["passage_ayah_range"])
            if meta.get("passage_ayah_range") is not None
            else None
        ),
    )


def _get_config() -> EditionFetcherConfig:
    """Build the tafsir fetcher config from current settings."""
    return EditionFetcherConfig(
        edition_type="tafsir",
        goodmem_space=get_settings().goodmem.space.tafsir,
        entry_factory=_build_tafsir_entry,
        chunk_multiplier=50,  # Tafsir is chunked; each memory can have many chunks
    )


async def fetch_tafsir(
    ctx: AppContext,
    ayahs: str | list[str],
    editions: str | list[str],
) -> TafsirFetchResult:
    """Fetch tafsir for ayahs from one or more editions."""
    return TafsirFetchResult.from_result(
        await fetch_with_config(
            ctx,
            ayahs,
            editions,
            config=_get_config(),
        )
    )


def resolve_tafsir_edition_ids(edition_selector: str | list[str]) -> list[str]:
    """Resolve tafsir edition selector(s) to canonical IDs."""
    return resolve_ids("tafsir", edition_selector)




__all__ = [
    "fetch_tafsir",
    "resolve_tafsir_edition_ids",
    "TafsirEntry",
    "TafsirFetchResult",
    "infer_summary_lang",
    "TAFSIR_SUMMARY_PROMPTS",
]
