"""Tool for fetching tafsir data."""

from typing import Annotated

from fastmcp import Context, FastMCP
from pydantic import BaseModel, ConfigDict, Field

from quran_mcp.lib.ayah_parsing import format_ayah_range
from quran_mcp.lib.presentation.pagination import (
    ContinuationPaginationMeta,
)
from quran_mcp.lib.tafsir.fetch import TafsirEntry as FetchedTafsirEntry, fetch_tafsir
from quran_mcp.lib.presentation.warnings import (
    GROUNDING_RULES_FIELD_DESCRIPTION,
    WarningModel,
)
from quran_mcp.mcp.tools._fetch_orchestration import (
    CONTINUATION_FIELD_DESCRIPTION,
    PreparedFetchPage,
    GROUNDING_NONCE_FIELD_DESCRIPTION,
    MISSING_AYAHS_AND_EDITIONS_MESSAGE,
    VERSE_REFS_FIELD_DESCRIPTION,
    execute_fetch_tool,
    with_fetch_grounding_prerequisite,
)
from quran_mcp.mcp.tools._tool_errors import FETCH_TOOL_ERROR_CONTRACT


class TafsirEntry(BaseModel):
    """Tafsir commentary for one or more ayat.

    When a mufassir comments on a group of verses together, duplicate
    entries are collapsed: ``ayahs`` lists every covered verse and
    ``range`` gives the compact form (e.g. "31:13-15").
    """

    # Enforce strict schema (no surprise keys) for tool output contracts.
    model_config = ConfigDict(extra="forbid")

    ayahs: list[str] = Field(description="Individual ayah keys covered by this entry")
    range: str = Field(description="Compact ayah range (e.g. '31:13-15' or '2:255')")
    text: str = Field(description="Full tafsir text")
    citation_url: str | None = Field(
        default=None,
        description="Per-entry source link (e.g., 'https://tafsir.app/kashaf/2/255')"
    )
    passage_ayah_range: str | None = Field(
        default=None,
        description="Passage range from source metadata (e.g., '70:8-21') when tafsir covers multiple verses"
    )


class FetchTafsirResponse(BaseModel):
    """Response payload for the fetch tafsir tool."""

    model_config = ConfigDict(extra="forbid")

    ayahs: list[str] = Field(description="Ayah keys in this page (subset of full request)")
    results: dict[str, list[TafsirEntry]] = Field(
        description="Tafsir results keyed by edition identifier (e.g., '{lang}-{code}')"
    )
    pagination: ContinuationPaginationMeta = Field(description="Continuation metadata")
    warnings: list[WarningModel] | None = Field(
        default=None,
        description="Warnings about data gaps or unresolved edition selectors"
    )
    grounding_rules: str | None = Field(
        default=None,
        description=GROUNDING_RULES_FIELD_DESCRIPTION,
    )

def _dedup_entries(
    raw_texts: list[tuple[str, str, str | None, str | None]],
) -> list[TafsirEntry]:
    """Collapse consecutive entries with identical text into one.

    Tafsir authors often comment on groups of verses together. The upstream data
    stores the same text for each verse in the group, producing duplicates like:
        31:13 → "Luqman's Advice..."
        31:14 → "Luqman's Advice..."  (identical)
        31:15 → "Luqman's Advice..."  (identical)

    This collapses them into:
        ayahs=["31:13","31:14","31:15"], range="31:13-15", text="Luqman's Advice..."

    Args:
        raw_texts: List of (ayah_key, text, citation_url, passage_ayah_range) tuples in order.
    """
    if not raw_texts:
        return []

    result: list[TafsirEntry] = []
    group_ayahs: list[str] = [raw_texts[0][0]]
    group_text = raw_texts[0][1]
    group_citation_url = raw_texts[0][2]
    group_passage_ayah_range = raw_texts[0][3]

    for ayah_key, text, citation_url, passage_ayah_range in raw_texts[1:]:
        if text == group_text:
            group_ayahs.append(ayah_key)
        else:
            result.append(TafsirEntry(
                ayahs=group_ayahs,
                range=format_ayah_range(group_ayahs),
                text=group_text,
                citation_url=group_citation_url,
                passage_ayah_range=group_passage_ayah_range,
            ))
            group_ayahs = [ayah_key]
            group_text = text
            group_citation_url = citation_url
            group_passage_ayah_range = passage_ayah_range

    result.append(TafsirEntry(
        ayahs=group_ayahs,
        range=format_ayah_range(group_ayahs),
        text=group_text,
        citation_url=group_citation_url,
        passage_ayah_range=group_passage_ayah_range,
    ))
    return result


def _build_tafsir_results(
    raw_results: dict[str, list[FetchedTafsirEntry]],
) -> dict[str, list[TafsirEntry]]:
    """Project fetched tafsir into tool entries with duplicate passage collapse."""
    results: dict[str, list[TafsirEntry]] = {}
    for edition_id, entries in raw_results.items():
        raw_texts = [(entry.ayah, entry.text, entry.citation_url, entry.passage_ayah_range) for entry in entries]
        results[edition_id] = _dedup_entries(raw_texts)
    return results


def register(mcp: FastMCP) -> None:
    """Register tafsir fetch tool."""

    @mcp.tool(
        name="fetch_tafsir",
        title="Fetch Tafsir Commentary",
        description=with_fetch_grounding_prerequisite(
            "BEST PRACTICE: Before fetching, call list_editions(edition_type='tafsir') "
            "to review available mufassirin and their descriptions. Choose the tafsirs "
            "best suited to the question rather than defaulting reflexively. "
            "Do not limit yourself to the user's language — Arabic tafsir editions often contain "
            "richer scholarship. Fetch the most authoritative source regardless of language and "
            "translate the result yourself. "
            "Retrieve full canonical tafsir text for one or more ayat. "
            "Use when the user asks for tafsir, explanation, commentary, "
            "interpretation, or context and the requested canonical tafsir text for an ayah or ayat "
            f"is not already in your context via dynamic context or prior tool calls. {FETCH_TOOL_ERROR_CONTRACT}"
        ),
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
        output_schema=FetchTafsirResponse.model_json_schema(),
        version="0.1.1",
        tags={"ga"},
    )
    async def fetch_tafsir_tool(
        ayahs: Annotated[
            str | list[str] | None,
            Field(description=VERSE_REFS_FIELD_DESCRIPTION),
        ] = None,
        editions: Annotated[
            str | list[str] | None,
            Field(
                description=(
                    "Edition identifier(s): required. Accept a single string or list; values may be full "
                    "identifiers ('{lang}-{code}'), short codes ('{code}'), 2-letter language codes "
                    "('en', 'ar'), or ≥4 character fuzzy matches across name/author/code/id. "
                    "Call list_editions(edition_type='tafsir') first to discover available editions "
                    "and choose the source best suited to the question. Required unless continuation is provided."
                )
            ),
        ] = None,
        continuation: Annotated[
            str | None,
            Field(description=CONTINUATION_FIELD_DESCRIPTION),
        ] = None,
        grounding_nonce: Annotated[
            str | None,
            Field(description=GROUNDING_NONCE_FIELD_DESCRIPTION),
        ] = None,
        ctx: Context | None = None,
    ) -> FetchTafsirResponse:
        """Fetch tafsir data for every requested edition."""
        page: PreparedFetchPage[TafsirEntry] = await execute_fetch_tool(
            ctx=ctx,
            tool_name="fetch_tafsir",
            continuation=continuation,
            ayahs=ayahs,
            editions=editions,
            default_editions=None,
            missing_inputs_message=MISSING_AYAHS_AND_EDITIONS_MESSAGE,
            fetch_entries=fetch_tafsir,
            build_results=_build_tafsir_results,
            entry_ayahs=lambda entry: entry.ayahs,
        )

        return FetchTafsirResponse(
            ayahs=page.ayahs,
            results=page.results,
            pagination=page.pagination,
            warnings=page.warnings,
        )
