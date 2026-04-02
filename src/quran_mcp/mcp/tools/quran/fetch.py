"""
Tool for fetching Quran text from GoodMem.

GoodMem-native retrieval only - no QF API fallback.
No summarization support (Quran text doesn't need AI summarization).
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from fastmcp import Context, FastMCP

from quran_mcp.lib.presentation.pagination import (
    ContinuationPaginationMeta,
)
from quran_mcp.lib.quran.fetch import QuranEntry as FetchedQuranEntry, fetch_quran
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


class QuranTextEntry(BaseModel):
    """Single Quran text entry for a given ayah."""

    model_config = ConfigDict(extra="forbid")

    ayah: str = Field(description="Ayah key in S:V format")
    text: str = Field(description="Quran text for the ayah")


class FetchQuranResponse(BaseModel):
    """Response payload for the fetch quran tool."""

    model_config = ConfigDict(extra="forbid")

    ayahs: list[str] = Field(description="Ayah keys in this page (subset of full request)")
    results: dict[str, list[QuranTextEntry]] = Field(
        description="Quran text results keyed by edition identifier (e.g., 'ar-uthmani')"
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


def _build_quran_results(
    raw_results: dict[str, list[FetchedQuranEntry]],
) -> dict[str, list[QuranTextEntry]]:
    """Project fetched Quran text into the stable tool response shape."""
    return build_fetch_results(
        raw_results,
        entry_factory=lambda entry: QuranTextEntry(ayah=entry.ayah, text=entry.text),
    )


def register(mcp: FastMCP) -> None:
    """Register quran fetch tool."""

    @mcp.tool(
        name="fetch_quran",
        title="Fetch Quran Text",
        description=with_fetch_grounding_prerequisite(
            "Retrieve exact canonical Quranic text for one or more ayat. "
            "Defaults to ar-simple-clean if no edition is provided. "
            "Invoke whenever a verse reference appears and the requested canonical Quran text "
            "for those ayat is not already in your context via dynamic context or prior tool calls. "
            f"{FETCH_TOOL_ERROR_CONTRACT}"
        ),
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
        output_schema=FetchQuranResponse.model_json_schema(),
        version="0.1.1",
        tags={"ga"},
    )
    async def fetch_quran_tool(
        ayahs: Annotated[
            str | list[str] | None,
            Field(description=VERSE_REFS_FIELD_DESCRIPTION),
        ] = None,
        editions: Annotated[
            str | list[str] | None,
            Field(
                description=(
                    "Edition identifier(s): accept a single string or list; values may be "
                    "full identifiers ('ar-simple-clean'), short codes ('simple-clean'), "
                    "or 2-letter language codes ('ar'). Defaults to 'ar-simple-clean' "
                    "when omitted on the initial call."
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
    ) -> FetchQuranResponse:
        """Fetch Quran text for every requested edition."""
        page: PreparedFetchPage[QuranTextEntry] = await execute_fetch_tool(
            ctx=ctx,
            tool_name="fetch_quran",
            continuation=continuation,
            ayahs=ayahs,
            editions=editions,
            default_editions="ar-simple-clean",
            missing_inputs_message=MISSING_AYAHS_MESSAGE,
            fetch_entries=fetch_quran,
            build_results=_build_quran_results,
            entry_ayahs=lambda entry: entry.ayah,
            bundle_key_fn=lambda entry: entry.ayah,
        )

        return FetchQuranResponse(
            ayahs=page.ayahs,
            results=page.results,
            pagination=page.pagination,
            warnings=page.warnings,
        )
