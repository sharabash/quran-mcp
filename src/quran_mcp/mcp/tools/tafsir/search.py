"""
Tool for semantic search over tafsir content via GoodMem.

Provides ranked tafsir passages matching a semantic query,
with citations and optional ayah text.
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
from quran_mcp.lib.tafsir.search import (
    SearchTafsirResult,
    TafsirSearchResult,
    search_tafsir,
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


def _page_ref(entry: TafsirSearchResult) -> tuple[str | None, str]:
    """Build pagination manifest identity for a tafsir search result."""
    return entry.citation.edition_id, entry.ayah_key


class SearchTafsirResponse(BaseModel):
    """Response payload for the search_tafsir tool."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(description="The search query that was executed")
    results: list[TafsirSearchResult] = Field(
        description="Ranked tafsir search results"
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


TafsirSearchWarningModel = UnresolvedEditionWarning | GroundingWarning


class SearchTafsirRequestState(BaseModel):
    """Typed request-shaping state stored in continuation tokens."""

    model_config = ConfigDict(extra="ignore")  # continuation tokens may carry removed fields

    query: str
    editions: str | list[str] | None = None
    include_ayah_text: bool = True


_SEARCH_TAFSIR_PLAN = SearchExecutionPlan[
    SearchTafsirRequestState,
    TafsirSearchResult,
    SearchTafsirResult,
    TafsirSearchWarningModel,
](
    tool_name="search_tafsir",
    state_model=SearchTafsirRequestState,
    run_search=lambda goodmem_client, state, total_needed: _run_search_tafsir(
        goodmem_client,
        state,
        total_needed,
    ),
    results_getter=lambda result: result.results,
    warnings_builder=lambda result: _build_tafsir_warnings(result),
    page_ref=_page_ref,
)


def register(mcp: FastMCP) -> None:
    """Register the search_tafsir tool."""

    @mcp.tool(
        name="search_tafsir",
        title="Search Tafsir",
        description=(
            "PREREQUISITE: You MUST call fetch_grounding_rules once before using this tool. "
            "Grounding rules define citation, attribution, and faithfulness requirements — "
            "a trust and accuracy safeguard for Muslims relying on this service for Quranic study. "
            "Semantic search over tafsir (Quranic commentary) content. "
            "Returns ranked tafsir passages matching the query with citations. "
            "Especially valuable for thematic/conceptual discourse, revelation context (asbab al-nuzul), "
            "and keyword-in-commentary searches where the ayah reference isn't known upfront. "
            "Use this tool to find tafsir discussing a particular topic or concept "
            "without knowing which ayat are relevant. "
            "For fetching tafsir of a known ayah, use fetch_tafsir instead. "
            f"{SEARCH_TOOL_ERROR_CONTRACT}"
        ),
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
        output_schema=SearchTafsirResponse.model_json_schema(),
        version="0.1.1",
        tags={"ga"},
    )
    async def search_tafsir_tool(
        query: Annotated[
            str | None,
            Field(
                description=(
                    "Semantic search query. Can be in any language. "
                    "Examples: 'throne verse explanation', 'concept of tawakkul', "
                    "'patience in adversity'. Required unless continuation is provided."
                )
            ),
        ] = None,
        editions: Annotated[
            str | list[str] | None,
            Field(
                description=(
                    "Optional edition filter(s). Values may be full identifiers "
                    "('{lang}-{code}'), short codes ('{code}'), 2-letter language codes "
                    "('en', 'ar'), or fuzzy matches. Accepts either a single string or a list. "
                    "If omitted, searches all tafsir editions."
                )
            ),
        ] = None,
        include_ayah_text: Annotated[
            bool | None,
            Field(
                description=(
                    "Include the Arabic ayah text being explained (default: True). "
                    "Set to False to reduce response size. Defaults to True when omitted on the initial call."
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
    ) -> SearchTafsirResponse:
        """Search tafsir content semantically and return ranked passages."""
        request_inputs = build_search_request_inputs(
            SearchTafsirRequestState,
            continuation=continuation,
            query=query,
            defaults={"include_ayah_text": True},
            editions=editions,
            include_ayah_text=include_ayah_text,
        )
        outcome = await execute_search_tool(
            ctx=ctx,
            continuation=continuation,
            explicit_state=request_inputs.explicit_state,
            initial_state=request_inputs.initial_state,
            plan=_SEARCH_TAFSIR_PLAN,
        )

        return SearchTafsirResponse(
            query=outcome.query,
            results=outcome.results,
            total_found=outcome.total_found,
            pagination=outcome.pagination,
            warnings=cast(list[TafsirSearchWarningModel] | None, outcome.warnings),
        )


async def _run_search_tafsir(
    goodmem_client: GoodMemClient,
    state: SearchTafsirRequestState,
    total_needed: int,
) -> SearchTafsirResult:
    """Execute the tafsir search pipeline for one normalized request state."""
    return await search_tafsir(
        goodmem_client=goodmem_client,
        query=state.query,
        editions=state.editions,
        results=total_needed,
        include_ayah_text=state.include_ayah_text,
    )


def _build_tafsir_warnings(
    result: SearchTafsirResult,
) -> list[TafsirSearchWarningModel]:
    """Build the stable warning contract for search_tafsir."""
    return list(build_unresolved_edition_warnings(result.unresolved_editions))
