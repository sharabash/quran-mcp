"""Library function for fetch_word_concordance tool.

Orchestrates concordance query, pagination, grouping, and response assembly.
The preferred entry point is a validated :class:`ConcordanceRequest`.
"""

from __future__ import annotations

import asyncpg

from quran_mcp.lib.morphology.concordance_query import (
    get_word_linguistic_ids,
    query_concordance_paginated,
    resolve_lemma_id,
    resolve_root_id,
    resolve_stem_id,
)
from quran_mcp.lib.morphology.query import (
    get_words_for_verse,
    resolve_verse_by_key,
    resolve_word_by_text,
    resolve_word_in_verse,
)
from quran_mcp.lib.morphology.concordance_request import (
    ConcordanceGroupBy,
    ConcordanceRequest,
    ConcordanceMatchBy,
    build_concordance_request,
)
from quran_mcp.lib.morphology.types import (
    ConcordanceQueryEcho,
    ConcordanceResponse,
    ConcordanceVerse,
    ConcordanceWord,
    ConcordanceWordResult,
)


async def fetch_word_concordance(
    pool: asyncpg.Pool,
    request: ConcordanceRequest | None = None,
    ayah_key: str | None = None,
    word_position: int | None = None,
    word_text: str | None = None,
    word: str | None = None,
    root: str | None = None,
    lemma: str | None = None,
    stem: str | None = None,
    match_by: ConcordanceMatchBy = "all",
    group_by: ConcordanceGroupBy = "verse",
    page: int = 1,
    page_size: int = 20,
) -> ConcordanceResponse:
    """Fetch word concordance with tiered lexical scoring.

    Input modes:
    1. ayah_key + word_position → resolve word → root/lemma/stem IDs
    2. word (Arabic text) → resolve first occurrence → IDs
    3. root/lemma/stem (Arabic text) → direct ID lookup

    Pipeline:
    1. Resolve input → dict_root_id, dict_lemma_id, dict_stem_id
    2. Execute paginated concordance query (tiered scoring, SQL-level pagination)
    3. Assemble response based on group_by mode
    """
    if request is None:
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

    dict_root_id: int | None = None
    dict_lemma_id: int | None = None
    dict_stem_id: int | None = None
    query_echo: ConcordanceQueryEcho = request.selection.to_query_echo()

    # --- Step 1: Resolve input to linguistic IDs ---
    selection = request.selection

    if selection.kind == "ayah_key":
        verse = await resolve_verse_by_key(pool, selection.ayah_key or "")
        verse_id = verse["verse_id"]
        # Resolve word_text to word_position if provided
        if selection.word_text is not None:
            word_position = await resolve_word_in_verse(
                pool, verse_id, selection.word_text, verse["verse_key"]
            )
        else:
            word_position = selection.word_position
        words = await get_words_for_verse(pool, verse_id, word_position)
        if not words:
            if word_position is not None:
                raise ValueError(f"No word at position {word_position} in verse {selection.ayah_key}")
            raise ValueError(f"No words found for verse {selection.ayah_key}")
        w = words[0]
        ids = await get_word_linguistic_ids(pool, w["word_id"])
        dict_root_id = ids["dict_root_id"]
        dict_lemma_id = ids["dict_lemma_id"]
        dict_stem_id = ids["dict_stem_id"]
        query_echo = ConcordanceQueryEcho(
            ayah_key=selection.ayah_key,
            word_position=w["position"],
            text=w["text_uthmani"],
        )

    elif selection.kind == "word":
        word_rec, _ = await resolve_word_by_text(pool, selection.word or "")
        ids = await get_word_linguistic_ids(pool, word_rec["word_id"])
        dict_root_id = ids["dict_root_id"]
        dict_lemma_id = ids["dict_lemma_id"]
        dict_stem_id = ids["dict_stem_id"]
        query_echo = ConcordanceQueryEcho(word=selection.word, resolved_verse=word_rec["verse_key"])

    elif selection.kind == "root":
        dict_root_id = await resolve_root_id(pool, selection.root or "")
        query_echo = ConcordanceQueryEcho(root=selection.root)

    elif selection.kind == "lemma":
        dict_lemma_id = await resolve_lemma_id(pool, selection.lemma or "")
        query_echo = ConcordanceQueryEcho(lemma=selection.lemma)

    elif selection.kind == "stem":
        dict_stem_id = await resolve_stem_id(pool, selection.stem or "")
        query_echo = ConcordanceQueryEcho(stem=selection.stem)

    # Determine effective match_by based on available IDs
    effective_match_by: ConcordanceMatchBy = request.match_by
    if request.match_by == "all" and dict_root_id is None:
        # Can't do "all" without a root — downgrade
        if dict_lemma_id is not None:
            effective_match_by = "lemma"
        elif dict_stem_id is not None:
            effective_match_by = "stem"
        else:
            raise ValueError("No root, lemma, or stem found for this input")

    # --- Step 2: Execute paginated concordance query ---
    rows, total_verses, total_words = await query_concordance_paginated(
        pool,
        match_by=effective_match_by,
        dict_root_id=dict_root_id,
        dict_lemma_id=dict_lemma_id,
        dict_stem_id=dict_stem_id,
        group_by=request.group_by,
        page=request.page,
        page_size=request.page_size,
    )

    # --- Step 3: Assemble response based on group_by ---
    if request.group_by == "word":
        word_results = [
            ConcordanceWordResult(
                ayah_key=r["verse_key"],
                position=r["position"],
                text_uthmani=r["text_uthmani"],
                transliteration=r.get("en_transliteration"),
                match_level=r["match_level"],
                verse_text=r["verse_text"],
                score=float(r.get("word_score", r.get("verse_score", 1))),
            )
            for r in rows
        ]
        return ConcordanceResponse(
            query=query_echo,
            match_by=effective_match_by,
            group_by="word",
            total_verses=total_verses,
            total_words=total_words,
            page=request.page,
            page_size=request.page_size,
            word_results=word_results,
        )

    # Verse mode: group rows by verse
    verse_groups: dict[str, ConcordanceVerse] = {}
    for r in rows:
        vkey = r["verse_key"]
        if vkey not in verse_groups:
            score = float(r.get("verse_score", 1))
            verse_groups[vkey] = ConcordanceVerse(
                ayah_key=vkey,
                verse_text=r["verse_text"],
                score=score,
                matched_words=[],
            )
        verse_groups[vkey].matched_words.append(ConcordanceWord(
            position=r["position"],
            text_uthmani=r["text_uthmani"],
            transliteration=r.get("en_transliteration"),
            match_level=r["match_level"],
        ))

    # Preserve SQL ordering (already sorted by score desc, verse_id asc)
    results = list(verse_groups.values())

    return ConcordanceResponse(
        query=query_echo,
        match_by=effective_match_by,
        group_by="verse",
        total_verses=total_verses,
        total_words=total_words,
        page=request.page,
        page_size=request.page_size,
        results=results,
    )
