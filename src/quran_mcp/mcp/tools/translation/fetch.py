"""Tool for fetching Qur'an translations."""

from typing import Annotated

from fastmcp import Context, FastMCP
from pydantic import BaseModel, ConfigDict, Field

from quran_mcp.lib.presentation.pagination import (
    ContinuationPaginationMeta,
)
from quran_mcp.lib.translation.fetch import (
    TranslationEntry as FetchedTranslationEntry,
    fetch_translation,
)
from quran_mcp.lib.presentation.warnings import (
    GROUNDING_RULES_FIELD_DESCRIPTION,
    WarningModel,
)
from quran_mcp.mcp.tools._fetch_orchestration import (
    CONTINUATION_FIELD_DESCRIPTION,
    PreparedFetchPage,
    GROUNDING_NONCE_FIELD_DESCRIPTION,
    MISSING_AYAHS_MESSAGE,
    VERSE_REFS_FIELD_DESCRIPTION,
    build_fetch_results,
    execute_fetch_tool,
    with_fetch_grounding_prerequisite,
)
from quran_mcp.mcp.tools._tool_errors import FETCH_TOOL_ERROR_CONTRACT


class TranslationEntry(BaseModel):
    """Single translation snippet for a given ayah."""

    model_config = ConfigDict(extra="forbid")

    ayah: str = Field(description="Ayah key in S:V format")
    text: str = Field(description="Full translation text for the ayah")


class FetchTranslationResponse(BaseModel):
    """Response payload for the translation fetch tool."""

    model_config = ConfigDict(extra="forbid")

    ayahs: list[str] = Field(description="Ayah keys in this page (subset of full request)")
    results: dict[str, list[TranslationEntry]] = Field(
        description="Translation results keyed by edition identifier (e.g., 'en-abdel-haleem')"
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


def _build_translation_results(
    raw_results: dict[str, list[FetchedTranslationEntry]],
) -> dict[str, list[TranslationEntry]]:
    """Project fetched translations into the stable tool response shape."""
    return build_fetch_results(
        raw_results,
        entry_factory=lambda entry: TranslationEntry(ayah=entry.ayah, text=entry.text),
    )


def register(mcp: FastMCP) -> None:
    """Register translation fetch tool."""

    @mcp.tool(
        name="fetch_translation",
        title="Fetch Translation",
        description=with_fetch_grounding_prerequisite(
            "Retrieve canonical Quran translation text for one or more ayat. "
            "Defaults to en-abdel-haleem if no edition is provided. "
            "Use when the user requests a translation, literal meaning, or rendering "
            "of a verse and the requested canonical translation for those ayat "
            "is not already in your context via dynamic context or prior tool calls. "
            "Translations are not the same as tafsir; this returns the literal meaning of the text. "
            f"For interpretation and commentary, use fetch_tafsir instead. {FETCH_TOOL_ERROR_CONTRACT}"
        ),
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
        output_schema=FetchTranslationResponse.model_json_schema(),
        version="0.1.1",
        tags={"ga"},
    )
    async def fetch_translation_tool(
        ayahs: Annotated[
            str | list[str] | None,
            Field(description=VERSE_REFS_FIELD_DESCRIPTION),
        ] = None,
        editions: Annotated[
            str | list[str] | None,
            Field(
                description=(
                    "Edition identifier(s): accept a single string or list; values may be full identifiers "
                    "('en-abdel-haleem'), short codes, 2-letter language codes (e.g., 'en', 'es'), "
                    "or ≥4 character fuzzy matches across name/author/code/id. Defaults to "
                    "'en-abdel-haleem' when omitted on the initial call."
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
    ) -> FetchTranslationResponse:
        """Fetch translation data for every requested edition."""
        page: PreparedFetchPage[TranslationEntry] = await execute_fetch_tool(
            ctx=ctx,
            tool_name="fetch_translation",
            continuation=continuation,
            ayahs=ayahs,
            editions=editions,
            default_editions="en-abdel-haleem",
            missing_inputs_message=MISSING_AYAHS_MESSAGE,
            fetch_entries=fetch_translation,
            build_results=_build_translation_results,
            entry_ayahs=lambda entry: entry.ayah,
            bundle_key_fn=lambda entry: entry.ayah,
        )

        return FetchTranslationResponse(
            ayahs=page.ayahs,
            results=page.results,
            pagination=page.pagination,
            warnings=page.warnings,
        )
