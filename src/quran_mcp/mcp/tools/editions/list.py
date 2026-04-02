"""Tool for listing available editions (quran, tafsir, translation)."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from fastmcp import FastMCP

from quran_mcp.lib.editions.registry import list_edition_summaries
from quran_mcp.lib.editions.types import EditionType
from quran_mcp.lib.presentation.warnings import (
    GROUNDING_RULES_FIELD_DESCRIPTION,
    GroundingWarning,
)
from quran_mcp.mcp.tools._tool_errors import (
    STANDARD_RESOURCE_ERROR_CONTRACT,
    invalid_request_error,
)


class EditionInfo(BaseModel):
    """Single edition record."""

    model_config = ConfigDict(extra="forbid")

    edition_id: str = Field(
        description=(
            "Edition identifier, unique within its type (e.g., '{lang}-{code}') - "
            "use this when calling fetch tools"
        )
    )
    edition_type: EditionType = Field(
        description="Edition type: quran, tafsir, or translation"
    )
    lang: str = Field(description="2-letter language code (e.g., 'ar', 'en')")
    code: str = Field(
        description=(
            "Short code for the edition (e.g., '{code}') - "
            "shorter identifier without language prefix"
        )
    )
    name: str = Field(description="Human-readable name of the edition")
    author: str | None = Field(description="Author name, if applicable")
    description: str | None = Field(
        default=None,
        description="Short description of the edition's style or methodology, if available"
    )
    choose_when: str | None = Field(
        default=None,
        description="When to choose this edition — matches user intent to the edition's strengths"
    )
    avg_entry_tokens: int | None = Field(
        default=None,
        description=(
            "Average tokens per entry for this edition, rounded to the nearest whole "
            "token. Populated for profiled editions and useful for planning "
            "context-efficient retrieval."
        ),
    )
    # Note: qf_resource_id is intentionally excluded - internal use only


class ListEditionsResponse(BaseModel):
    """Response payload for list_editions tool."""

    model_config = ConfigDict(extra="forbid")

    edition_types: list[EditionType] = Field(
        description="The edition type(s) that were queried (always a list)"
    )
    lang_filter: str | None = Field(
        description="The language filter applied to translation editions, if any"
    )
    editions: list[EditionInfo] = Field(
        description="List of available editions, sorted by edition_id within each type"
    )
    count: int = Field(description="Number of editions returned")
    warnings: list[GroundingWarning] | None = Field(
        default=None,
        description="Warnings about grounding requirements for canonical Quran data",
    )
    grounding_rules: str | None = Field(
        default=None,
        description=GROUNDING_RULES_FIELD_DESCRIPTION,
    )


def register(mcp: FastMCP) -> None:
    """Register list_editions tool."""

    @mcp.tool(
        name="list_editions",
        title="List Available Editions",
        description=(
            "List all available editions of a specific type (quran, tafsir, or translation). "
            "Use this tool to discover what editions are available before calling fetch tools. "
            "Returns edition IDs, names, authors, language codes, description fields, and "
            "average entry token counts. Use descriptions to match editions to the user's "
            "question — each mufassir has distinct strengths (legal, linguistic, hadith-critical, "
            "rhetorical, structural, practical). Use token counts to plan context-efficient "
            "multi-source retrieval. "
            "Accepts a single type or a list of types to fetch multiple in one call "
            "(e.g., edition_type=[\"tafsir\", \"translation\"]). "
            "Use the lang parameter to filter translation editions by language. "
            "Ignored for quran and tafsir types — all tafsir editions are always returned "
            f"because Arabic tafsir is valuable regardless of the user's language. {STANDARD_RESOURCE_ERROR_CONTRACT}"
        ),
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
        output_schema=ListEditionsResponse.model_json_schema(),
        version="0.1.1",
        tags={"ga"},
    )
    def list_editions(
        edition_type: Annotated[
            EditionType | list[EditionType],
            Field(
                description=(
                    "Type of editions to list. Must be one of: "
                    "'quran' (Quran text editions), "
                    "'tafsir' (Quranic commentary editions), "
                    "'translation' (Quran translation editions). "
                    "Accepts a single type or a list of types "
                    "(e.g., [\"tafsir\", \"translation\"])."
                )
            ),
        ],
        lang: Annotated[
            str | None,
            Field(
                description=(
                    "Optional 2-letter language code to filter editions (e.g., 'en', 'ur'). "
                    "Only respected for edition_type='translation'. Ignored for 'quran' and "
                    "'tafsir' types; the complete tafsir corpus is always returned because the "
                    "diversity of Arabic tafsir offers insights that may not be present in the "
                    "limited set directly available in the user's language. LLMs are multilingual."
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
    ) -> ListEditionsResponse:
        """List available editions for given type(s) with optional language filtering."""

        # Normalize single string to list (avoids iterating over characters)
        types: list[EditionType] = (
            [edition_type] if isinstance(edition_type, str) else list(edition_type)
        )

        # Reject empty list
        if not types:
            raise invalid_request_error("edition_type must not be empty")

        # Deduplicate preserving request order (NOT set() — unordered)
        types = list(dict.fromkeys(types))

        # Only translation requests honor lang filtering
        effective_lang_filter = lang if lang and "translation" in types else None

        # Iterate per type: load, filter, sort within type, extend
        all_editions: list[EditionInfo] = []
        for t in types:
            summaries = list_edition_summaries(
                t,
                lang=effective_lang_filter if t == "translation" else None,
                sort_by_edition_id=True,
            )
            all_editions.extend(EditionInfo(**summary) for summary in summaries)

        return ListEditionsResponse(
            edition_types=types,
            lang_filter=effective_lang_filter,
            editions=all_editions,
            count=len(all_editions),
            warnings=None,
        )
