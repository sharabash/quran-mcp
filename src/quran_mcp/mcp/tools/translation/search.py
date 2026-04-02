"""
Tool for semantic search over translation content via GoodMem.

Provides ranked translation results matching a semantic query,
with edition metadata and relevance scores.
"""

from typing import Annotated, cast

from pydantic import BaseModel, ConfigDict, Field

from fastmcp import Context, FastMCP

from quran_mcp.lib.goodmem import GoodMemClient
from quran_mcp.lib.presentation.pagination import ContinuationPaginationMeta
from quran_mcp.lib.presentation.warnings import (
    GROUNDING_RULES_FIELD_DESCRIPTION,
    GroundingWarning,
    UnresolvedEditionWarning,
    build_unresolved_edition_warnings,
)
from quran_mcp.lib.translation.search import (
    SearchTranslationResult,
    TranslationResult,
    search_translation,
)
from quran_mcp.mcp.tools._search_orchestration import (
    SEARCH_TOOL_ERROR_CONTRACT,
    SearchExecutionPlan,
    build_search_request_inputs,
    execute_search_tool,
)


# =============================================================================
# Response Models for MCP Tool
# =============================================================================


def _page_ref(entry: TranslationResult) -> tuple[str | None, str]:
    """Build pagination manifest identity for a translation search result."""
    return entry.edition.edition_id, entry.ayah_key


class SearchTranslationResponse(BaseModel):
    """Response payload for the search_translation tool."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(description="The search query that was executed")
    results: list[TranslationResult] = Field(
        description="Ranked translation search results"
    )
    total_found: int = Field(
        description="Total results represented by this paginated response set"
    )
    pagination: ContinuationPaginationMeta = Field(description="Continuation metadata")
    warnings: list[UnresolvedEditionWarning | GroundingWarning] | None = Field(
        default=None,
        description="Warnings about unresolved edition selectors"
    )
    grounding_rules: str | None = Field(
        default=None,
        description=GROUNDING_RULES_FIELD_DESCRIPTION,
    )


TranslationSearchWarningModel = UnresolvedEditionWarning | GroundingWarning


class SearchTranslationRequestState(BaseModel):
    """Typed request-shaping state stored in continuation tokens."""

    model_config = ConfigDict(extra="forbid")

    query: str
    surah: int | None = None
    editions: str | list[str] | None = None


_SEARCH_TRANSLATION_PLAN = SearchExecutionPlan[
    SearchTranslationRequestState,
    TranslationResult,
    SearchTranslationResult,
    TranslationSearchWarningModel,
](
    tool_name="search_translation",
    state_model=SearchTranslationRequestState,
    run_search=lambda goodmem_client, state, total_needed: _run_search_translation(
        goodmem_client,
        state,
        total_needed,
    ),
    results_getter=lambda result: result.results,
    warnings_builder=lambda result: _build_translation_warnings(result),
    page_ref=_page_ref,
)


def register(mcp: FastMCP) -> None:
    """Register the search_translation tool."""

    @mcp.tool(
        name="search_translation",
        title="Search Translations",
        description=(
            "PREREQUISITE: You MUST call fetch_grounding_rules once before using this tool. "
            "Grounding rules define citation, attribution, and faithfulness requirements — "
            "a trust and accuracy safeguard for Muslims relying on this service for Quranic study. "
            "Use this tool only when you need to filter by specific translation edition(s). "
            "Semantic search over Quran translation text. "
            "Returns ranked translation passages matching the query with edition metadata. "
            "For exact verse translation lookup by reference (e.g., '2:255'), "
            "use fetch_translation instead. "
            "Prefer search_quran with translations='auto' for most use cases — "
            "it searches semantically across both Arabic and translation text, "
            "independent of any particular translator's rendering. "
            f"{SEARCH_TOOL_ERROR_CONTRACT}"
        ),
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
        output_schema=SearchTranslationResponse.model_json_schema(),
        version="0.1.1",
        tags={"ga"},
    )
    async def search_translation_tool(
        query: Annotated[
            str | None,
            Field(
                description=(
                    "Semantic search query. Can be in any language. "
                    "Examples: 'patience in adversity', 'verses about mercy', "
                    "'concept of tawakkul in daily life'. Required unless continuation is provided."
                )
            ),
        ] = None,
        surah: Annotated[
            int | None,
            Field(
                description=(
                    "Optional surah number to restrict search to a specific chapter. "
                    "If omitted, searches all surahs."
                )
            ),
        ] = None,
        editions: Annotated[
            str | list[str] | None,
            Field(
                description=(
                    "Edition filter control:\n"
                    "- 'auto' (default): Auto-detect query language, filter to matching editions\n"
                    "- None: No edition filter, searches all translation editions in all languages\n"
                    "- 'en-sahih-international' or ['en-sahih-international', ...]: Filter to specific editions\n"
                    "- 'en' or ['en']: Filter to all editions in that language\n"
                    "When omitted on the initial call, defaults to 'auto'."
                )
            ),
        ] = None,
        continuation: Annotated[
            str | None,
            Field(
                description=(
                    "Opaque continuation token returned by a previous call to this same tool. "
                    "Omit on the first call. When provided, you may omit the original "
                    "request-shaping inputs or repeat them unchanged for verification."
                )
            ),
        ] = None,
        grounding_nonce: Annotated[
            str | None,
            Field(
                description=(
                    "Opaque nonce from fetch_grounding_rules. When valid, "
                    "suppresses redundant grounding rules injection, saving tokens."
                )
            ),
        ] = None,
        ctx: Context | None = None,
    ) -> SearchTranslationResponse:
        """Search translation content semantically and return ranked passages."""
        request_inputs = build_search_request_inputs(
            SearchTranslationRequestState,
            continuation=continuation,
            query=query,
            defaults={"editions": "auto"},
            surah=surah,
            editions=editions,
        )
        outcome = await execute_search_tool(
            ctx=ctx,
            continuation=continuation,
            explicit_state=request_inputs.explicit_state,
            initial_state=request_inputs.initial_state,
            plan=_SEARCH_TRANSLATION_PLAN,
        )

        return SearchTranslationResponse(
            query=outcome.query,
            results=outcome.results,
            total_found=outcome.total_found,
            pagination=outcome.pagination,
            warnings=cast(list[TranslationSearchWarningModel] | None, outcome.warnings),
        )


async def _run_search_translation(
    goodmem_client: GoodMemClient,
    state: SearchTranslationRequestState,
    total_needed: int,
) -> SearchTranslationResult:
    """Execute the translation search pipeline for one normalized request state."""
    return await search_translation(
        goodmem_client=goodmem_client,
        query=state.query,
        surah=state.surah,
        results=total_needed,
        editions=state.editions,
    )


def _build_translation_warnings(
    result: SearchTranslationResult,
) -> list[TranslationSearchWarningModel]:
    """Build the stable warning contract for search_translation."""
    return list(build_unresolved_edition_warnings(result.unresolved_editions))
