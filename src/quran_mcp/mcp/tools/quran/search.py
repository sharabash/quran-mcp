"""
Tool for semantic search over Quran text via GoodMem.

Provides ranked ayah results matching a semantic query,
with optional translation text.
"""

from typing import Annotated, Literal

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
from quran_mcp.lib.quran.search import (
    SearchQuranResult,
    SearchResult,
    search_quran,
)
from quran_mcp.mcp.tools._search_orchestration import (
    SEARCH_TOOL_ERROR_CONTRACT,
    SearchExecutionPlan,
    build_search_request_inputs,
    execute_search_tool,
)


def _page_ref(entry: SearchResult) -> tuple[str | None, str]:
    """Build pagination manifest identity for a Quran search result."""
    if entry.translations:
        return entry.translations[0].edition.id, entry.ayah_key
    return "ar-uthmani", entry.ayah_key


class TranslationGapWarning(BaseModel):
    """Warning for ayahs where requested translations were unavailable."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["translation_gap"] = Field(
        default="translation_gap",
        description="Warning type discriminator"
    )
    ayah_keys: list[str] = Field(description="Ayah keys missing translation data")


QuranSearchWarningModel = UnresolvedEditionWarning | TranslationGapWarning | GroundingWarning


class SearchQuranResponse(BaseModel):
    """Response payload for the search_quran tool."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(description="The search query that was executed")
    results: list[SearchResult] = Field(description="Ranked search results")
    total_found: int = Field(
        description="Total results represented by this paginated response set"
    )
    pagination: ContinuationPaginationMeta = Field(description="Continuation metadata")
    warnings: list[QuranSearchWarningModel] | None = Field(
        default=None,
        description="Warnings about unresolved editions or translation gaps"
    )
    grounding_rules: str | None = Field(
        default=None,
        description=GROUNDING_RULES_FIELD_DESCRIPTION,
    )


class SearchQuranRequestState(BaseModel):
    """Typed request-shaping state stored in continuation tokens."""

    model_config = ConfigDict(extra="forbid")

    query: str
    surah: int | None = None
    translations: str | list[str] | None = None


_SEARCH_QURAN_PLAN = SearchExecutionPlan[
    SearchQuranRequestState,
    SearchResult,
    SearchQuranResult,
    QuranSearchWarningModel,
](
    tool_name="search_quran",
    state_model=SearchQuranRequestState,
    run_search=lambda goodmem_client, state, total_needed: _run_search_quran(
        goodmem_client,
        state,
        total_needed,
    ),
    results_getter=lambda result: result.results,
    warnings_builder=lambda result: _build_quran_warnings(result),
    page_ref=_page_ref,
)


def register(mcp: FastMCP) -> None:
    """Register the search_quran tool."""

    @mcp.tool(
        name="search_quran",
        title="Search Quran",
        description=(
            "PREREQUISITE: You MUST call fetch_grounding_rules once before using this tool. "
            "Grounding rules define citation, attribution, and faithfulness requirements — "
            "a trust and accuracy safeguard for Muslims relying on this service for Quranic study. "
            "Semantic search over Quran text. "
            "Returns ranked ayat matching the query with Arabic text and optional translations. "
            "Use the translations parameter ('auto' or specific editions) to include translated text "
            "in results, which covers most use cases that search_translation would handle. "
            "For exact verse lookup by reference (e.g., '2:255'), use fetch_quran instead. "
            f"{SEARCH_TOOL_ERROR_CONTRACT}"
        ),
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
        output_schema=SearchQuranResponse.model_json_schema(),
        version="0.1.1",
        tags={"ga"},
    )
    async def search_quran_tool(
        query: Annotated[
            str | None,
            Field(
                description=(
                    "Semantic search query. Can be in any language. "
                    "Examples: 'patience in adversity', 'الصبر', 'verses about mercy'. "
                    "Required unless continuation is provided."
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
        translations: Annotated[
            str | list[str] | None,
            Field(
                description=(
                    "Translation control:\n"
                    "- None (default): No translations, only Arabic text\n"
                    "- 'auto': Auto-detect query language, return single best-matching translation\n"
                    "- 'en-abdel-haleem' (or another concrete selector): Return that specific translation\n"
                    "- ['en-sahih-international', ...]: Return all specified edition translations\n"
                    "- 'en' (2-letter code): Return single best translation from that language"
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
    ) -> SearchQuranResponse:
        """Search Quran text semantically and return ranked ayat."""
        request_inputs = build_search_request_inputs(
            SearchQuranRequestState,
            continuation=continuation,
            query=query,
            surah=surah,
            translations=translations,
        )
        outcome = await execute_search_tool(
            ctx=ctx,
            continuation=continuation,
            explicit_state=request_inputs.explicit_state,
            initial_state=request_inputs.initial_state,
            plan=_SEARCH_QURAN_PLAN,
        )

        return SearchQuranResponse(
            query=outcome.query,
            results=outcome.results,
            total_found=outcome.total_found,
            pagination=outcome.pagination,
            warnings=outcome.warnings,
        )


async def _run_search_quran(
    goodmem_client: GoodMemClient,
    state: SearchQuranRequestState,
    total_needed: int,
) -> SearchQuranResult:
    """Execute the Quran search pipeline for one normalized request state."""
    return await search_quran(
        goodmem_client=goodmem_client,
        query=state.query,
        surah=state.surah,
        results=total_needed,
        translations=state.translations,
    )


def _build_quran_warnings(result: SearchQuranResult) -> list[QuranSearchWarningModel]:
    """Build the stable warning contract for search_quran."""
    warnings: list[QuranSearchWarningModel] = list(
        build_unresolved_edition_warnings(result.unresolved_editions)
    )
    if result.translation_gaps:
        warnings.append(TranslationGapWarning(ayah_keys=result.translation_gaps))
    return warnings
