"""Tool: fetch_quran_metadata — structural Quran lookups.

Returns a fixed-shape response with the full structural context chain
(surah, ayah, juz, hizb, rub_el_hizb, page, ruku, manzil, sajdah)
for any entry point: a specific ayah, an entire surah, a juz, a page,
a hizb, a ruku, or a manzil.
"""

from typing import Annotated

from pydantic import Field

from fastmcp import Context, FastMCP

from quran_mcp.lib.metadata.query import (
    query_ayah_point,
    query_hizb_span,
    query_juz_span,
    query_manzil_span,
    query_page_span,
    query_ruku_span,
    query_surah_span,
)
from quran_mcp.lib.metadata.types import QuranMetadataResponse
from quran_mcp.mcp.tools._tool_errors import (
    STANDARD_RESOURCE_ERROR_CONTRACT,
    invalid_request_error,
    require_db_pool,
)


def _require_value(name: str, value: int | None) -> int:
    """Narrow an optional validated parameter to an int."""
    if value is None:
        raise AssertionError(f"{name} was validated as required before dispatch")
    return value


def register(mcp: FastMCP) -> None:
    """Register the fetch_quran_metadata tool."""

    @mcp.tool(
        name="fetch_quran_metadata",
        title="Fetch Quran Metadata",
        description=(
            "Fetch structural Quran metadata for a surah, ayah, juz, page, hizb, "
            "ruku, or manzil. Returns a fixed-shape response with the full context "
            "chain: surah info, ayah location, juz/hizb/page/ruku/manzil placement, "
            "and sajdah info. All parameters are optional — provide one entry point.\n\n"
            "Examples:\n"
            "- fetch_quran_metadata(surah=2, ayah=255) → structural location of "
            "Ayat al-Kursi\n"
            "- fetch_quran_metadata(surah=2) → overview of Surat Al-Baqarah "
            "(verse count, page range, juz range, etc.)\n"
            "- fetch_quran_metadata(juz=1) → what surahs/pages are in Juz 1\n"
            "- fetch_quran_metadata(page=50) → what's on page 50\n\n"
            "Prefer fetching metadata over recalling it from memory. "
            "Cite this tool in your response when presenting structural Quran data. "
            f"{STANDARD_RESOURCE_ERROR_CONTRACT}"
        ),
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
        output_schema=QuranMetadataResponse.model_json_schema(),
        version="0.1.1",
        tags={"preview", "quran", "metadata", "navigation"},
    )
    async def fetch_quran_metadata(
        surah: Annotated[
            int | None,
            Field(
                default=None,
                description="Surah number (1-114). Use alone for surah overview, "
                "or with ayah for a specific verse.",
            ),
        ] = None,
        ayah: Annotated[
            int | None,
            Field(
                default=None,
                description="Ayah number within the surah. Requires surah parameter.",
            ),
        ] = None,
        juz: Annotated[
            int | None,
            Field(
                default=None,
                description="Juz number (1-30). Mutually exclusive with other "
                "span entry points.",
            ),
        ] = None,
        page: Annotated[
            int | None,
            Field(
                default=None,
                description="Mushaf page number (1-604). Mutually exclusive with "
                "other span entry points.",
            ),
        ] = None,
        hizb: Annotated[
            int | None,
            Field(
                default=None,
                description="Hizb number (1-60). Mutually exclusive with other "
                "span entry points.",
            ),
        ] = None,
        ruku: Annotated[
            int | None,
            Field(
                default=None,
                description="Ruku number (1-558). Mutually exclusive with other "
                "span entry points.",
            ),
        ] = None,
        manzil: Annotated[
            int | None,
            Field(
                default=None,
                description="Manzil number (1-7). Mutually exclusive with other "
                "span entry points.",
            ),
        ] = None,
        ctx: Context | None = None,
    ) -> QuranMetadataResponse:
        pool = require_db_pool(ctx)

        try:
            # --- Parameter validation ---

            # ayah requires surah
            if ayah is not None and surah is None:
                raise ValueError("ayah requires surah parameter")

            # Determine query mode
            is_point = surah is not None and ayah is not None
            span_params = {
                name: val
                for name, val in [
                    ("juz", juz),
                    ("page", page),
                    ("hizb", hizb),
                    ("ruku", ruku),
                    ("manzil", manzil),
                ]
                if val is not None
            }

            # surah-alone is also a span entry point
            if surah is not None and ayah is None:
                span_params["surah"] = surah

            if is_point and span_params:
                names = ", ".join(sorted(span_params.keys()))
                raise ValueError(
                    f"surah+ayah is a point query and cannot be combined with "
                    f"span parameters: {names}"
                )

            if len(span_params) > 1:
                names = ", ".join(sorted(span_params.keys()))
                raise ValueError(
                    f"Span entry points are mutually exclusive. "
                    f"Got multiple: {names}. Provide exactly one."
                )

            if not is_point and not span_params:
                raise ValueError(
                    "At least one parameter required. Provide surah, surah+ayah, "
                    "juz, page, hizb, ruku, or manzil."
                )

            # --- Dispatch to query function ---

            if is_point:
                return await query_ayah_point(
                    pool,
                    _require_value("surah", surah),
                    _require_value("ayah", ayah),
                )

            if "surah" in span_params:
                return await query_surah_span(pool, _require_value("surah", surah))

            if juz is not None:
                return await query_juz_span(pool, juz)

            if page is not None:
                return await query_page_span(pool, page)

            if hizb is not None:
                return await query_hizb_span(pool, hizb)

            if ruku is not None:
                return await query_ruku_span(pool, ruku)

            # manzil
            return await query_manzil_span(pool, _require_value("manzil", manzil))
        except ValueError as exc:
            raise invalid_request_error(str(exc)) from exc
