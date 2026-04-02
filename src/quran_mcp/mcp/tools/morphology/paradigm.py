"""Tool: fetch_word_paradigm — conjugation/derivation paradigm."""

from typing import Annotated

from pydantic import Field

from fastmcp import Context, FastMCP

from quran_mcp.lib.morphology.fetch_paradigm import fetch_word_paradigm
from quran_mcp.lib.morphology.types import ParadigmResponse
from quran_mcp.mcp.tools._tool_errors import (
    STANDARD_RESOURCE_ERROR_CONTRACT,
    invalid_request_error,
    require_db_pool,
)


def register(mcp: FastMCP) -> None:
    """Register the fetch_word_paradigm tool."""

    @mcp.tool(
        name="fetch_word_paradigm",
        title="Fetch Word Paradigm",
        description=(
            "Fetch conjugation/derivation paradigm for a Quranic word. Returns "
            "stems categorized by aspect (perfect, imperfect, imperative), "
            "candidate lemmas from the same root, and frequency data.\n\n"
            "Input modes:\n"
            "- ayah_key + word_text (e.g., '2:77', 'يَعْلَمُونَ') → word by text\n"
            "- ayah_key + word_position → resolve word to lemma → paradigm\n"
            "- lemma (Arabic text, e.g., 'عَلِمَ') → direct lookup\n"
            "- root (Arabic text, e.g., 'ع ل م') → most-frequent lemma\n\n"
            "Examples:\n"
            "- fetch_word_paradigm(ayah_key='2:77', word_text='يَعْلَمُونَ') → paradigm "
            "of يَعْلَمُونَ\n"
            "- fetch_word_paradigm(ayah_key='2:77', word_position=2) → same word by position\n"
            "- fetch_word_paradigm(lemma='عَلِمَ') → paradigm by lemma\n"
            "- fetch_word_paradigm(root='ع ل م') → paradigm for root\n\n"
            "Prefer fetching paradigm data over recalling it from memory. "
            "Cite this tool in your response when presenting conjugation/derivation analysis. "
            f"{STANDARD_RESOURCE_ERROR_CONTRACT}"
        ),
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
        output_schema=ParadigmResponse.model_json_schema(),
        version="0.1.1",
        tags={"ga", "quran", "morphology"},
    )
    async def tool_fetch_word_paradigm(
        ayah_key: Annotated[
            str | None,
            Field(
                default=None,
                description="Verse reference (e.g., '2:77'). Resolves word "
                "at word_position to its lemma, then shows paradigm.",
            ),
        ] = None,
        word_position: Annotated[
            int | None,
            Field(
                default=None,
                description="1-based word position within the verse. "
                "Requires ayah_key. Mutually exclusive with word_text. "
                "If omitted, uses the first word.",
            ),
        ] = None,
        word_text: Annotated[
            str | None,
            Field(
                default=None,
                description="Arabic word text to find within the verse "
                "(e.g., 'يَعْلَمُونَ'). Matches against exact text or "
                "diacritics-insensitive. Requires ayah_key. "
                "Mutually exclusive with word_position.",
            ),
        ] = None,
        lemma: Annotated[
            str | None,
            Field(
                default=None,
                description="Arabic lemma text to look up (e.g., 'عَلِمَ'). "
                "Mutually exclusive with ayah_key and root.",
            ),
        ] = None,
        root: Annotated[
            str | None,
            Field(
                default=None,
                description="Arabic root letters (e.g., 'ع ل م'). "
                "Shows paradigm for the most frequent lemma under this root. "
                "Mutually exclusive with ayah_key and lemma.",
            ),
        ] = None,
        ctx: Context | None = None,
    ) -> ParadigmResponse:
        db_pool = require_db_pool(ctx)

        try:
            return await fetch_word_paradigm(
                pool=db_pool,
                ayah_key=ayah_key,
                word_position=word_position,
                word_text=word_text,
                lemma=lemma,
                root=root,
            )
        except ValueError as exc:
            raise invalid_request_error(str(exc)) from exc
