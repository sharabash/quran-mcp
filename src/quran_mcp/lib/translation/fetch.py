"""GoodMem-native translation fetch helpers."""
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


class TranslationEntry(BaseFetchEntry):
    """Single translation entry for one ayah."""

    __slots__ = ()


class TranslationFetchResult(EditionFetchResult[TranslationEntry]):
    """Typed translation fetch result."""


TRANSLATION_SUMMARY_PROMPTS = SummaryPromptConfig(
    sampling_system_template=(
        "You compare Qur'an translations. Produce faithful summaries of the supplied translations only.\n\n"
        "Requirements:\n"
        "- Respect mode:\n"
        "  • aggregate → unified digest; reconcile translation differences; note disagreements.\n"
        "  • separate → separate sections per translation edition.\n"
        "  • compare  → emphasize similarities and divergences between translations.\n"
        "- Respect length: short (3–5 bullets), medium (6–10), detailed (≥12 bullets/paragraphs).\n"
        "- Respect language (lang = ar|en) for the summary prose.\n"
        "- If focus is provided, spotlight material addressing it.\n\n"
        "Citations:\n"
        "- Inline: [edition_id] or [edition_id § 2:255] at the end of each supporting clause.\n"
        "- Conclude with a 'Works Cited' footer listing each edition_id once (include language if helpful).\n\n"
        "Style:\n"
        "- Faithful, concise, attentive to nuanced wording differences.\n"
        "- Highlight uncertainties; never fabricate content."
    ),
    sampling_user_template=(
        "Summarize the following translations.\n\n"
        "Options:\n"
        "{options}\n\n"
        "Text:\n"
        "---------------- BEGIN TRANSLATIONS ----------------\n"
        "{text}\n"
        "----------------- END TRANSLATIONS -----------------\n\n"
        "Output format:\n"
        "- mode = aggregate → unified list/paragraphs with inline citations.\n"
        "- mode = separate  → section per source edition, each with bullets + citations.\n"
        "- mode = compare   → bullets highlighting agreements/disagreements with citations.\n"
        "- End with 'Works Cited:' followed by bullet list of edition_ids referenced."
    ),
    prompt_assistant_template=(
        "I'm ready to summarize Qur'an translations using these guidelines:\n\n"
        "• Mode: aggregate (unified), separate (per-source), or compare (similarities/differences)\n"
        "• Length: short (3-5 bullets), medium (6-10), detailed (12+ bullets/paragraphs)\n"
        "• Language: ar (Arabic) or en (English)\n"
        "• Citations: Inline [edition_id] or [edition_id § ayah] with Works Cited footer\n"
        "• Style: Faithful to source wording, concise, highlight distinctions\n\n"
        "What would you like me to summarize?"
    ),
    prompt_user_template=(
        "Summarize the following translations.\n\n"
        "Options:\n"
        "{options}\n\n"
        "Text:\n"
        "---------------- BEGIN TRANSLATIONS ----------------\n"
        "{text}\n"
        "----------------- END TRANSLATIONS -----------------\n\n"
        "Requirements:\n"
        "- Respect the specified mode, length, and language\n"
        "- Include inline citations [edition_id] or [edition_id § ayah_key] after each claim\n"
        "- If focus is provided, emphasize that aspect\n"
        "- End with 'Works Cited:' section listing all referenced sources\n"
        "- Be faithful to the source material; don't fabricate information"
    ),
)


def _build_translation_entry(ayah: str, text: str, _meta: Mapping[str, object]) -> TranslationEntry:
    """Build one translation entry from EditionFetcher inputs."""
    return TranslationEntry(ayah_key=ayah, text=text)


def _get_config() -> EditionFetcherConfig:
    """Build the translation fetcher config from current settings."""
    return EditionFetcherConfig(
        edition_type="translation",
        goodmem_space=get_settings().goodmem.space.translation,
        entry_factory=_build_translation_entry,
    )


async def fetch_translation(
    ctx: AppContext,
    ayahs: str | list[str],
    editions: str | list[str],
) -> TranslationFetchResult:
    """Fetch translations for ayahs from one or more editions."""
    return TranslationFetchResult.from_result(
        await fetch_with_config(
            ctx,
            ayahs,
            editions,
            config=_get_config(),
        )
    )


def resolve_translation_edition_ids(edition_selector: str | list[str]) -> list[str]:
    """Resolve translation edition selector(s) to canonical IDs."""
    return resolve_ids("translation", edition_selector)



__all__ = [
    "fetch_translation",
    "resolve_translation_edition_ids",
    "TranslationEntry",
    "TranslationFetchResult",
    "infer_summary_lang",
    "TRANSLATION_SUMMARY_PROMPTS",
]
