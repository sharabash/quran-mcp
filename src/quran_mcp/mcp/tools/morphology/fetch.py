"""Tool: fetch_word_morphology — word-level morphological analysis."""

from typing import Annotated

from pydantic import Field

from fastmcp import Context, FastMCP

from quran_mcp.lib.morphology.fetch_morphology import fetch_word_morphology
from quran_mcp.lib.morphology.types import MorphologyResponse
from quran_mcp.mcp.tools._tool_errors import (
    STANDARD_RESOURCE_ERROR_CONTRACT,
    invalid_request_error,
    require_db_pool,
)


def register(mcp: FastMCP) -> None:
    """Register the fetch_word_morphology tool."""

    @mcp.tool(
        name="fetch_word_morphology",
        title="Fetch Word Morphology",
        description=(
            "Fetch word-level morphological analysis for Quranic text. Returns "
            "root, lemma, stem, grammatical features, morpheme segments, and "
            "frequency data (verbatim occurrence count, root occurrence count, "
            "lemma occurrence count) for each word.\n\n"
            "Input modes:\n"
            "- ayah_key (e.g., '2:77') → all words in the verse\n"
            "- ayah_key + word_text (e.g., '2:77', 'يَعْلَمُونَ') → specific word by text\n"
            "- ayah_key + word_position (e.g., '2:77', 2) → specific word by position\n"
            "- word (Arabic text, e.g., 'يَعْلَمُونَ') → first occurrence in Quran\n\n"
            "Examples:\n"
            "- fetch_word_morphology(ayah_key='2:77', word_text='يَعْلَمُونَ') → morphology "
            "of يَعْلَمُونَ\n"
            "- fetch_word_morphology(ayah_key='2:77', word_position=2) → same word by position\n"
            "- fetch_word_morphology(ayah_key='1:1') → all 4 words of Bismillah\n"
            "- fetch_word_morphology(word='يَعْلَمُونَ') → first occurrence + "
            "other_occurrences_count\n\n"
            "Prefer fetching morphology data over recalling it from memory. "
            "Cite this tool in your response when presenting morphological analysis. "
            f"{STANDARD_RESOURCE_ERROR_CONTRACT}"
        ),
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
        output_schema=MorphologyResponse.model_json_schema(),
        version="0.1.1",
        tags={"ga", "quran", "morphology"},
    )
    async def tool_fetch_word_morphology(
        ayah_key: Annotated[
            str | None,
            Field(
                default=None,
                description="Verse reference (e.g., '2:77'). Returns all words "
                "in the verse, or a specific word if word_position is also provided.",
            ),
        ] = None,
        word_position: Annotated[
            int | None,
            Field(
                default=None,
                description="1-based word position within the verse. "
                "Requires ayah_key. Mutually exclusive with word_text.",
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
        word: Annotated[
            str | None,
            Field(
                default=None,
                description="Arabic word text to look up (e.g., 'يَعْلَمُونَ'). "
                "Returns first occurrence. Mutually exclusive with ayah_key.",
            ),
        ] = None,
        ctx: Context | None = None,
    ) -> MorphologyResponse:
        db_pool = require_db_pool(ctx)

        try:
            return await fetch_word_morphology(
                pool=db_pool,
                ayah_key=ayah_key,
                word_position=word_position,
                word_text=word_text,
                word=word,
            )
        except ValueError as exc:
            raise invalid_request_error(str(exc)) from exc
