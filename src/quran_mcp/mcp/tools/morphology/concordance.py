"""Tool: fetch_word_concordance — concordance with tiered lexical scoring.

Supports optional Voyage semantic reranking when a source verse is available.
"""

import logging
from typing import TYPE_CHECKING, Annotated

from pydantic import Field

if TYPE_CHECKING:
    from quran_mcp.lib.config.settings import VoyageSettings

from fastmcp import Context, FastMCP

from quran_mcp.lib.config.settings import get_settings
from quran_mcp.lib.morphology.concordance_request import (
    ConcordanceGroupBy,
    ConcordanceMatchBy,
    ConcordanceRequest,
    build_concordance_request,
)
from quran_mcp.lib.morphology.fetch_concordance import fetch_word_concordance
from quran_mcp.lib.morphology.types import ConcordanceResponse, ConcordanceVerse
from quran_mcp.lib.presentation.pagination import TOKEN_CAP, estimate_tokens
from quran_mcp.lib.morphology.voyage_reranker import (
    VoyageRerankerError,
    fetch_verse_glosses,
    rerank_verses,
)
from quran_mcp.mcp.tools._tool_errors import (
    STANDARD_RESOURCE_ERROR_CONTRACT,
    invalid_request_error,
    require_db_pool,
)

logger = logging.getLogger(__name__)


def register(mcp: FastMCP) -> None:
    """Register the fetch_word_concordance tool."""

    @mcp.tool(
        name="fetch_word_concordance",
        title="Fetch Word Concordance",
        description=(
            "Find all Quranic verses containing words related to a given word, "
            "root, lemma, or stem. Results are ranked by tiered lexical scoring: "
            "exact stem matches (5), lemma matches (3), root matches (1), "
            "and reranked semantically: by proximity to the source ayah when "
            "ayah_key is provided, or by the search term itself for bare "
            "word/root/lemma/stem queries — naturally similar ayat float to the top.\n\n"
            "Input modes:\n"
            "- ayah_key + word_text (e.g., '2:77', 'يَعْلَمُونَ') → word by text\n"
            "- ayah_key + word_position → concordance for that word\n"
            "- word (Arabic text) → concordance for first occurrence\n"
            "- root (Arabic text, e.g., 'ع ل م') → all words from this root\n"
            "- lemma (Arabic text) → all forms of this lemma\n"
            "- stem (Arabic text) → exact stem matches only\n\n"
            "match_by controls scope: 'all' (default), 'root', 'lemma', 'stem'\n"
            "group_by controls output: 'verse' (default) or 'word'\n"
            "rerank_from enables Voyage semantic reranking against a source verse\n\n"
            "Examples:\n"
            "- fetch_word_concordance(ayah_key='2:77', word_text='يَعْلَمُونَ') → "
            "concordance for يَعْلَمُونَ (auto-reranked if Voyage configured)\n"
            "- fetch_word_concordance(root='ع ل م', match_by='all') → "
            "all words from root ع ل م with tiered scoring\n"
            "- fetch_word_concordance(root='ع ل م', rerank_from='2:255') → "
            "root concordance reranked by proximity to Ayat al-Kursi\n\n"
            "Prefer fetching concordance data over recalling it from memory. "
            "Cite this tool in your response when presenting word occurrence data. "
            f"{STANDARD_RESOURCE_ERROR_CONTRACT}"
        ),
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
        output_schema=ConcordanceResponse.model_json_schema(),
        version="0.1.1",
        tags={"ga", "quran", "morphology"},
    )
    async def tool_fetch_word_concordance(
        ayah_key: Annotated[
            str | None,
            Field(
                default=None,
                description="Verse reference (e.g., '2:77'). Resolves word "
                "at word_position to root/lemma/stem, then finds concordance.",
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
                description="Arabic word text to look up. "
                "Mutually exclusive with ayah_key, root, lemma, stem.",
            ),
        ] = None,
        root: Annotated[
            str | None,
            Field(
                default=None,
                description="Arabic root letters (e.g., 'ع ل م'). "
                "Mutually exclusive with ayah_key, word, lemma, stem.",
            ),
        ] = None,
        lemma: Annotated[
            str | None,
            Field(
                default=None,
                description="Arabic lemma text (e.g., 'عَلِمَ'). "
                "Mutually exclusive with ayah_key, word, root, stem.",
            ),
        ] = None,
        stem: Annotated[
            str | None,
            Field(
                default=None,
                description="Arabic stem text. "
                "Mutually exclusive with ayah_key, word, root, lemma.",
            ),
        ] = None,
        match_by: Annotated[
            ConcordanceMatchBy,
            Field(
                default="all",
                description="Match scope: 'all' (default, tiered scoring), "
                "'root', 'lemma', or 'stem'.",
            ),
        ] = "all",
        group_by: Annotated[
            ConcordanceGroupBy,
            Field(
                default="verse",
                description="Grouping mode: 'verse' (default, results grouped by verse) "
                "or 'word' (flat list of individual word matches).",
            ),
        ] = "verse",
        rerank_from: Annotated[
            str | None,
            Field(
                default=None,
                description="Source verse for semantic reranking. "
                "Set to an ayah_key (e.g., '2:255') to rerank results by "
                "semantic proximity to that verse. Auto-set when ayah_key is "
                "provided (pass 'false' to disable). Only works with group_by='verse'.",
            ),
        ] = None,
        page: Annotated[
            int,
            Field(
                default=1,
                description="Page number (1-based). Default: 1.",
            ),
        ] = 1,
        page_size: Annotated[
            int,
            Field(
                default=20,
                description="Results per page (1-100). Default: 20.",
            ),
        ] = 20,
        ctx: Context | None = None,
    ) -> ConcordanceResponse:
        db_pool = require_db_pool(ctx)

        settings = get_settings()
        voyage = settings.voyage
        voyage_key = voyage.api_key.get_secret_value()

        request = build_concordance_request(
            ayah_key=ayah_key,
            word_position=word_position,
            word_text=word_text,
            word=word,
            root=root,
            lemma=lemma,
            stem=stem,
            match_by=match_by,
            group_by=group_by,
            page=page,
            page_size=page_size,
        )

        # Determine if reranking should be applied
        effective_rerank_from = _resolve_rerank_from(
            request=request,
            voyage_key=voyage_key,
        )

        try:
            if effective_rerank_from:
                response = await _fetch_with_reranking(
                    pool=db_pool,
                    request=request,
                    rerank_from=effective_rerank_from,
                    voyage_key=voyage_key,
                    voyage=voyage,
                )
            else:
                response = await fetch_word_concordance(
                    pool=db_pool,
                    request=request,
                )
            return _enforce_concordance_token_cap(response)
        except ValueError as exc:
            raise invalid_request_error(str(exc)) from exc


_BARE_WORD_RERANK = "__bare_word__"


def _enforce_concordance_token_cap(
    response: ConcordanceResponse,
    cap: int = TOKEN_CAP,
) -> ConcordanceResponse:
    """Truncate concordance results if they exceed the token cap.

    Binary-searches for the largest subset of results that fits under the cap,
    then returns a copy with truncated=True if anything was removed.
    """
    total_est = estimate_tokens(response)
    if total_est <= cap:
        return response

    # Determine which list to truncate
    items = response.results or response.word_results
    field = "results" if response.results else "word_results"
    if not items:
        return response

    # Binary search for largest fitting subset
    lo, hi = 0, len(items)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        candidate = response.model_copy(update={field: items[:mid]})
        if estimate_tokens(candidate) <= cap:
            lo = mid
        else:
            hi = mid - 1

    kept = max(1, lo)
    logger.warning(
        "Concordance token cap: %d→%d items (~%d tokens, cap=%d)",
        len(items), kept, total_est, cap,
    )
    return response.model_copy(update={field: items[:kept], "truncated": True})


def _resolve_rerank_from(
    request: ConcordanceRequest,
    voyage_key: str,
) -> str | None:
    """Determine the effective rerank_from value.

    Returns ayah_key string for reranking, _BARE_WORD_RERANK for word-based
    reranking (no source verse), or None to skip.
    """
    # Reranking only works with verse mode
    if request.group_by != "verse":
        return None

    # No Voyage key → can't rerank
    if not voyage_key:
        return None

    # Explicit disable
    if request.rerank_from is not None and request.rerank_from.lower() == "false":
        return None

    # Explicit ayah_key for reranking
    if request.rerank_from is not None:
        return request.rerank_from

    # Auto-set when ayah_key is provided (the common mushaf use case)
    if request.selection.ayah_key is not None:
        return request.selection.ayah_key

    # Auto-enable for bare word/root/lemma/stem queries
    if request.selection.search_term is not None:
        return _BARE_WORD_RERANK

    return None


async def _fetch_with_reranking(
    pool,
    request: ConcordanceRequest,
    rerank_from: str,
    voyage_key: str,
    voyage: "VoyageSettings",
) -> ConcordanceResponse:
    """Fetch concordance with Voyage semantic reranking.

    Flow:
    1. Fetch top N (voyage_top_k) results via tiered scoring
    2. Get English glosses for candidates + source verse
    3. Call Voyage rerank
    4. Re-sort by Voyage scores, paginate
    5. On ANY error → fall back to plain tiered scoring
    """
    # Step 1: Fetch candidate pool
    rerank_request = request.with_overrides(group_by="verse", page=1, page_size=voyage.top_k)
    pool_result = await fetch_word_concordance(
        pool=pool,
        request=rerank_request,
    )

    if not pool_result.results:
        return pool_result

    try:
        source_text, glosses = await _resolve_rerank_source_and_glosses(
            pool=pool,
            verses=pool_result.results,
            rerank_from=rerank_from,
            search_term=request.selection.search_term,
        )
        documents = _build_rerank_documents(pool_result.results, glosses)
        reranked_verses = await _rerank_candidate_verses(
            verses=pool_result.results,
            source_text=source_text,
            documents=documents,
            voyage_key=voyage_key,
            voyage=voyage,
        )
        return _build_reranked_response(
            pool_result=pool_result,
            reranked_verses=reranked_verses,
            page=request.page,
            page_size=request.page_size,
            voyage_model=voyage.model,
        )
    except Exception as exc:
        # Fall back to plain tiered scoring on ANY error (Voyage, network, etc.)
        logger.warning("Voyage reranking failed, falling back to tiered scoring: %s", exc)
        # Reuse the pool_result we already fetched — no need to re-query the DB
        return _build_fallback_response(
            pool_result=pool_result,
            page=request.page,
            page_size=request.page_size,
        )


async def _resolve_rerank_source_and_glosses(
    *,
    pool,
    verses: list[ConcordanceVerse],
    rerank_from: str,
    search_term: str | None,
) -> tuple[str, dict[str, str]]:
    """Resolve the source query text and gloss map for reranking."""
    candidate_keys = [verse.ayah_key for verse in verses]
    if rerank_from == _BARE_WORD_RERANK:
        if not search_term:
            raise VoyageRerankerError("No search term available for bare word reranking")
        return search_term, await fetch_verse_glosses(pool, candidate_keys)

    all_keys = list(set(candidate_keys + [rerank_from]))
    glosses = await fetch_verse_glosses(pool, all_keys)
    source_text = _resolve_source_text_from_ayah(
        verses=verses,
        glosses=glosses,
        rerank_from=rerank_from,
    )
    if search_term:
        source_text = f"{search_term} — {source_text}"
    return source_text, glosses


def _resolve_source_text_from_ayah(
    *,
    verses: list[ConcordanceVerse],
    glosses: dict[str, str],
    rerank_from: str,
) -> str:
    """Resolve source text from glosses first, then fall back to verse text."""
    source_text = glosses.get(rerank_from)
    if source_text:
        return source_text

    source_verse = next((verse for verse in verses if verse.ayah_key == rerank_from), None)
    if source_verse:
        return source_verse.verse_text
    raise VoyageRerankerError(f"Cannot resolve source text for rerank_from={rerank_from!r}")


def _build_rerank_documents(
    verses: list[ConcordanceVerse],
    glosses: dict[str, str],
) -> list[str]:
    """Build the rerank document payload in stable candidate order."""
    return [glosses.get(verse.ayah_key, verse.verse_text) for verse in verses]


async def _rerank_candidate_verses(
    *,
    verses: list[ConcordanceVerse],
    source_text: str,
    documents: list[str],
    voyage_key: str,
    voyage: "VoyageSettings",
) -> list[ConcordanceVerse]:
    """Apply Voyage reranking and return verses in reranked order."""
    rerank_results = await rerank_verses(
        query_text=source_text,
        documents=documents,
        api_key=voyage_key,
        model=voyage.model,
        timeout=voyage.timeout_seconds,
    )
    reranked_verses: list[ConcordanceVerse] = []
    for result in rerank_results:
        idx = result["index"]
        reranked_verses.append(
            verses[idx].model_copy(update={"rerank_score": result.get("relevance_score")})
        )
    return reranked_verses


def _paginate_verses(
    *,
    verses: list[ConcordanceVerse],
    page: int,
    page_size: int,
) -> list[ConcordanceVerse]:
    """Paginate a verse list with 1-based page semantics."""
    offset = (page - 1) * page_size
    return verses[offset:offset + page_size]


def _build_reranked_response(
    *,
    pool_result: ConcordanceResponse,
    reranked_verses: list[ConcordanceVerse],
    page: int,
    page_size: int,
    voyage_model: str,
) -> ConcordanceResponse:
    """Build the final reranked concordance response."""
    return ConcordanceResponse(
        query=pool_result.query,
        match_by=pool_result.match_by,
        group_by="verse",
        total_verses=len(reranked_verses),
        total_words=pool_result.total_words,
        page=page,
        page_size=page_size,
        results=_paginate_verses(
            verses=reranked_verses,
            page=page,
            page_size=page_size,
        ),
        reranker_model=voyage_model,
        reranked_from_pool=len(pool_result.results),
    )


def _build_fallback_response(
    *,
    pool_result: ConcordanceResponse,
    page: int,
    page_size: int,
) -> ConcordanceResponse:
    """Build a paginated fallback response from the original tiered pool."""
    if not pool_result.results:
        return pool_result
    return ConcordanceResponse(
        query=pool_result.query,
        match_by=pool_result.match_by,
        group_by="verse",
        total_verses=pool_result.total_verses,
        total_words=pool_result.total_words,
        page=page,
        page_size=page_size,
        results=_paginate_verses(
            verses=pool_result.results,
            page=page,
            page_size=page_size,
        ),
    )
