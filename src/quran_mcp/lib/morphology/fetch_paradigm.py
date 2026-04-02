"""Library function for fetch_word_paradigm tool.

Orchestrates query layer calls and assembles ParadigmResponse.
"""

from __future__ import annotations

import asyncio

import asyncpg

from quran_mcp.lib.morphology.html_strip import strip_html
from quran_mcp.lib.morphology.pos_tag_parser import PosTagParser
from quran_mcp.lib.morphology.query import (
    get_words_for_verse,
    resolve_verse_by_key,
    resolve_word_in_verse,
)
from quran_mcp.lib.morphology.paradigm_query import (
    get_candidate_lemmas,
    get_gloss_fallback_batch,
    get_stems_for_lemma,
    resolve_lemma_by_text,
    resolve_root_by_text,
    resolve_root_for_word,
    resolve_lemma_for_word,
    get_word_visible_segments,
)
from quran_mcp.lib.morphology.types import (
    CandidateLemma,
    ParadigmResponse,
    ParadigmStem,
    WordInfo,
)

_parser = PosTagParser()

# Aspect tag prefixes for stem categorization
_ASPECT_CATEGORIES = {
    "PERF": "perfect",
    "IMPF": "imperfect",
    "IMPV": "imperative",
}


def _categorize_stem(pos_tags: str | None) -> str | None:
    """Categorize a stem by aspect from its pos_tags tokens.

    Uses exact token matching (split on comma) to avoid false positives
    like "IMPERFECT" matching "PERF".
    """
    if not pos_tags:
        return None
    tags = set(pos_tags.split(","))
    for tag, aspect in _ASPECT_CATEGORIES.items():
        if tag in tags:
            return aspect
    return None


async def fetch_word_paradigm(
    pool: asyncpg.Pool,
    ayah_key: str | None = None,
    word_position: int | None = None,
    word_text: str | None = None,
    lemma: str | None = None,
    root: str | None = None,
) -> ParadigmResponse:
    """Fetch conjugation/derivation paradigm.

    Input modes:
    1. ayah_key (+ optional word_position or word_text) → resolve word → lemma → paradigm
    2. lemma (Arabic text) → direct lookup
    3. root (Arabic text) → most-frequent lemma under root

    Pipeline:
    1. Resolve input → dict_lemma_id (+ dict_root_id)
    2. Check paradigm availability (non-verbal → paradigm_available=false)
    3. Fetch stems under lemma, categorize by aspect
    4. Fetch candidate lemmas from root
    5. Apply gloss fallback where needed
    6. Assemble response
    """
    # --- Input validation ---
    provided = sum(1 for x in (ayah_key, lemma, root) if x)
    if provided > 1:
        raise ValueError("Provide only one of: ayah_key, lemma, or root")
    if word_position is not None and not ayah_key:
        raise ValueError("word_position requires ayah_key")
    if word_text is not None and not ayah_key:
        raise ValueError("word_text requires ayah_key")
    if word_position is not None and word_text is not None:
        raise ValueError("Provide either word_position or word_text, not both")
    if provided == 0:
        raise ValueError("Provide one of: ayah_key, lemma, or root")

    word_info: WordInfo | None = None
    dict_lemma_id: int | None = None
    dict_root_id: int | None = None
    lemma_text: str | None = None
    root_text: str | None = None
    verb_form_number: int | None = None

    # --- Step 1: Resolve input ---
    if ayah_key:
        verse = await resolve_verse_by_key(pool, ayah_key)
        verse_id = verse["verse_id"]
        resolved_key = verse["verse_key"]

        # Resolve word_text to word_position if provided
        if word_text is not None:
            word_position = await resolve_word_in_verse(
                pool, verse_id, word_text, resolved_key
            )

        # Get word record
        words = await get_words_for_verse(pool, verse_id, word_position)
        if not words:
            if word_position is not None:
                raise ValueError(
                    f"No word at position {word_position} in verse {resolved_key}"
                )
            raise ValueError(f"No words found for verse {resolved_key}")

        # If no position specified, use the first word
        w = words[0]
        word_info = WordInfo(
            text_uthmani=w["text_uthmani"],
            text_simple=w["text_imlaei_simple"],
            transliteration=w["en_transliteration"],
            ayah_key=w["verse_key"],
            position=w["position"],
        )

        word_id = w["word_id"]

        # Check paradigm availability — find verb segment among ALL visible segments
        # (not just position 1, which fails for prefixed verbs like wa-qala)
        segments = await get_word_visible_segments(pool, word_id)
        verb_seg = next(
            (s for s in segments if s["part_of_speech_key"] == "V"), None
        )
        if verb_seg is None:
            pos_name = segments[0]["part_of_speech_name"] if segments else "unknown"
            return ParadigmResponse(
                word=word_info,
                paradigm_available=False,
                paradigm_unavailable_reason=f"{pos_name} — no conjugation paradigm",
            )

        # Parse verb form from verb segment
        if verb_seg.get("verb_form"):
            features = _parser.parse(
                pos_tags=verb_seg["pos_tags"],
                part_of_speech_key=verb_seg["part_of_speech_key"],
                verb_form_raw=verb_seg["verb_form"],
            )
            verb_form_number = features.verb_form

        # Resolve lemma and root for this word concurrently
        lemma_rec, root_rec = await asyncio.gather(
            resolve_lemma_for_word(pool, word_id),
            resolve_root_for_word(pool, word_id),
        )
        if lemma_rec:
            dict_lemma_id = lemma_rec["dict_lemma_id"]
            lemma_text = lemma_rec["lemma_value"]
        if root_rec:
            dict_root_id = root_rec["dict_root_id"]
            root_text = root_rec["root_value"]

    elif lemma:
        lemma_rec = await resolve_lemma_by_text(pool, lemma)
        dict_lemma_id = lemma_rec["dict_lemma_id"]
        lemma_text = lemma_rec["value"]

        # Try to find the root for this lemma
        root_rec = await resolve_root_by_text(pool, None, dict_lemma_id=dict_lemma_id)
        if root_rec:
            dict_root_id = root_rec["dict_root_id"]
            root_text = root_rec["root_value"]

    elif root:
        root_rec = await resolve_root_by_text(pool, root)
        dict_root_id = root_rec["dict_root_id"]
        root_text = root_rec["root_value"]

        # Find most frequent lemma under this root
        candidates = await get_candidate_lemmas(pool, dict_root_id)
        if candidates:
            top = candidates[0]
            dict_lemma_id = top["dict_lemma_id"]
            lemma_text = top["value"]

    # If we still don't have a lemma, we can't build a paradigm
    if dict_lemma_id is None:
        return ParadigmResponse(
            word=word_info,
            root=root_text,
            paradigm_available=False,
            paradigm_unavailable_reason="No lemma found for this input",
        )

    # --- Step 2: Fetch stems and categorize ---
    stem_rows = await get_stems_for_lemma(pool, dict_lemma_id)

    paradigm: dict[str, list[ParadigmStem]] = {
        "perfect": [],
        "imperfect": [],
        "imperative": [],
    }

    for s in stem_rows:
        aspect = _categorize_stem(s["pos_tags"])
        if aspect and aspect in paradigm:
            paradigm[aspect].append(ParadigmStem(
                stem=s["value"],
                description=strip_html(s["grammar_term_desc_english"]),
                count=s["word_count"],
            ))

    # --- Step 3: Candidate lemmas from root ---
    candidate_lemmas: list[CandidateLemma] = []
    if dict_root_id:
        raw_candidates = await get_candidate_lemmas(pool, dict_root_id)

        # Batch gloss fallback: collect IDs missing gloss, fetch all at once
        missing_gloss_ids = [
            c["dict_lemma_id"] for c in raw_candidates if not c.get("gloss_en")
        ]
        gloss_map = await get_gloss_fallback_batch(pool, missing_gloss_ids)

        for c in raw_candidates:
            gloss = c.get("gloss_en") or gloss_map.get(c["dict_lemma_id"])
            candidate_lemmas.append(CandidateLemma(
                lemma=c["value"],
                verb_form=_safe_int(c.get("verb_form")),
                count=c["frequency"],
                gloss=gloss,
            ))

    # --- Step 4: Check paradigm availability based on stems ---
    stems_in_paradigm = sum(len(v) for v in paradigm.values())

    if stems_in_paradigm == 0:
        # No verbal stems found — this lemma is not a verb (or has no
        # categorizable stems). Return paradigm_available=False so the
        # caller knows there's nothing to conjugate.
        return ParadigmResponse(
            word=word_info,
            root=root_text,
            lemma=lemma_text,
            verb_form=verb_form_number,
            paradigm_available=False,
            paradigm_unavailable_reason="No verbal stems found for this lemma",
            candidate_lemmas=candidate_lemmas,
        )

    # --- Step 5: Summary stats ---
    total_forms = {
        "stems_in_paradigm": stems_in_paradigm,
        "lemma_words": sum(s["word_count"] for s in stem_rows),
    }

    return ParadigmResponse(
        word=word_info,
        root=root_text,
        lemma=lemma_text,
        verb_form=verb_form_number,
        paradigm_available=True,
        paradigm=paradigm,
        candidate_lemmas=candidate_lemmas,
        total_forms_in_quran=total_forms,
    )


def _safe_int(value) -> int | None:
    """Convert a value to int, or None if not possible."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None
