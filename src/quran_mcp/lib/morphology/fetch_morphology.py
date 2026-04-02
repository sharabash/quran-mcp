"""Library function for fetch_word_morphology tool.

Orchestrates query layer calls and assembles MorphologyResponse.
"""

from __future__ import annotations

import asyncio

import asyncpg

from quran_mcp.lib.morphology.html_strip import strip_html
from quran_mcp.lib.morphology.pos_tag_parser import PosTagParser
from quran_mcp.lib.morphology.query import (
    get_frequency_counts,
    get_lemmas_for_words,
    get_roots_for_words,
    get_segments_for_words,
    get_stems_for_words,
    get_translations_for_words,
    get_words_for_verse,
    resolve_verse_by_key,
    resolve_word_by_text,
    resolve_word_in_verse,
)
from quran_mcp.lib.morphology.types import (
    FrequencyInfo,
    GrammaticalFeaturesModel,
    MorphemeSegment,
    MorphologyResponse,
    WordMorphologyEntry,
)

_parser = PosTagParser()


async def fetch_word_morphology(
    pool: asyncpg.Pool,
    ayah_key: str | None = None,
    word_position: int | None = None,
    word_text: str | None = None,
    word: str | None = None,
) -> MorphologyResponse:
    """Fetch word-level morphological analysis.

    Input modes:
    1. ayah_key (+ optional word_position or word_text) → specific or all words
    2. word (Arabic text) → first occurrence across entire Quran

    Pipeline:
    1. Resolve input → verse_id + optional position
    2. Fetch word records
    3. Batch-fetch root/lemma/stem/translation/segments
    4. Batch-fetch frequency counts
    5. Parse grammatical features
    6. Assemble response
    """
    # --- Input validation ---
    if ayah_key and word:
        raise ValueError("Provide either ayah_key or word, not both")
    if word_position is not None and not ayah_key:
        raise ValueError("word_position requires ayah_key")
    if word_text is not None and not ayah_key:
        raise ValueError("word_text requires ayah_key")
    if word_position is not None and word_text is not None:
        raise ValueError("Provide either word_position or word_text, not both")
    if not ayah_key and not word:
        raise ValueError("Provide either ayah_key or word")

    other_occurrences_count: int | None = None
    input_mode: str

    # --- Step 1: Resolve input ---
    if ayah_key:
        input_mode = "ayah_key"
        verse = await resolve_verse_by_key(pool, ayah_key)
        verse_id = verse["verse_id"]
        resolved_key = verse["verse_key"]
        # Resolve word_text to word_position if provided
        if word_text is not None:
            word_position = await resolve_word_in_verse(
                pool, verse_id, word_text, resolved_key
            )
    else:
        input_mode = "word_text"
        assert word is not None  # guaranteed by validation above
        word_record, total_occurrences = await resolve_word_by_text(pool, word)
        verse_id = word_record["verse_id"]
        word_position = word_record["position"]
        resolved_key = word_record["verse_key"]
        other_occurrences_count = max(0, total_occurrences - 1)

    # --- Step 2: Fetch words ---
    word_rows = await get_words_for_verse(pool, verse_id, word_position)
    if not word_rows:
        if word_position is not None:
            raise ValueError(
                f"No word at position {word_position} in verse {resolved_key}"
            )
        raise ValueError(f"No words found for verse {resolved_key}")

    word_ids = [r["word_id"] for r in word_rows]

    # --- Step 3: Batch-fetch dimensions (concurrent — no data dependencies) ---
    (
        roots_map,
        lemmas_map,
        stems_map,
        translations_map,
        segments_map,
    ) = await asyncio.gather(
        get_roots_for_words(pool, word_ids),
        get_lemmas_for_words(pool, word_ids),
        get_stems_for_words(pool, word_ids),
        get_translations_for_words(pool, word_ids),
        get_segments_for_words(pool, word_ids),
    )

    # --- Step 4: Collect unique IDs and batch-fetch frequencies ---
    all_root_ids = list({
        r["dict_root_id"]
        for recs in roots_map.values()
        for r in recs
    })
    all_lemma_ids = list({
        r["dict_lemma_id"]
        for recs in lemmas_map.values()
        for r in recs
    })
    all_stem_ids = list({
        r["dict_stem_id"]
        for recs in stems_map.values()
        for r in recs
    })

    freq = await get_frequency_counts(pool, all_root_ids, all_lemma_ids, all_stem_ids)

    # --- Step 5: Assemble per-word entries ---
    entries: list[WordMorphologyEntry] = []

    for w in word_rows:
        wid = w["word_id"]

        # Root (first if multiple)
        word_roots = roots_map.get(wid, [])
        root_text = word_roots[0]["root_value"] if word_roots else None
        root_freq = None
        if word_roots:
            rid = word_roots[0]["dict_root_id"]
            f = freq["root"].get(rid)
            if f:
                root_freq = FrequencyInfo(**f)

        # Lemma (first if multiple)
        word_lemmas = lemmas_map.get(wid, [])
        lemma_text = word_lemmas[0]["lemma_value"] if word_lemmas else None
        lemma_freq = None
        if word_lemmas:
            lid = word_lemmas[0]["dict_lemma_id"]
            f = freq["lemma"].get(lid)
            if f:
                lemma_freq = FrequencyInfo(**f)

        # Stem (first if multiple)
        word_stems = stems_map.get(wid, [])
        stem_text = word_stems[0]["stem_value"] if word_stems else None
        stem_freq = None
        if word_stems:
            sid = word_stems[0]["dict_stem_id"]
            f = freq["stem"].get(sid)
            if f:
                stem_freq = FrequencyInfo(**f)

        # Translation
        translation = translations_map.get(wid)

        # Morpheme segments + grammatical features
        raw_segments = segments_map.get(wid, [])
        segments: list[MorphemeSegment] = []
        # Two-pass: prefer verb segment for word-level features (fixes
        # prefixed verbs like wa-qala where position 1 is a conjunction).
        # Fall back to first segment with any POS.
        verb_features: GrammaticalFeaturesModel | None = None
        first_pos_features: GrammaticalFeaturesModel | None = None

        for seg in raw_segments:
            features = _parser.parse(
                pos_tags=seg["pos_tags"],
                part_of_speech_key=seg["part_of_speech_key"],
                verb_form_raw=seg["verb_form"],
            )

            seg_model = MorphemeSegment(
                position=seg["position"],
                text=seg["text_uthmani"] or "",
                part_of_speech_key=seg["part_of_speech_key"],
                part_of_speech_name=seg["part_of_speech_name"],
                grammar_description=strip_html(seg["grammar_term_desc_english"]),
                pos_tags=seg["pos_tags"],
                root=seg["root_name"],
                lemma=seg["lemma_name"],
                verb_form=features.verb_form,
            )
            segments.append(seg_model)

            if features.part_of_speech:
                feat_model = GrammaticalFeaturesModel(
                    part_of_speech=features.part_of_speech,
                    person=features.person,
                    gender=features.gender,
                    number=features.number,
                    aspect=features.aspect,
                    mood=features.mood,
                    voice=features.voice,
                    verb_form=features.verb_form,
                    definiteness=features.definiteness,
                    case=features.case,
                    features_version=features.features_version,
                    raw_unrecognized_tags=list(features.raw_unrecognized_tags),
                )
                # Prefer verb segment for word-level features
                if seg["part_of_speech_key"] == "V" and verb_features is None:
                    verb_features = feat_model
                elif first_pos_features is None:
                    first_pos_features = feat_model

        grammatical_features = verb_features or first_pos_features

        entry = WordMorphologyEntry(
            word_id=wid,
            position=w["position"],
            text_uthmani=w["text_uthmani"] or "",
            text_simple=w["text_imlaei_simple"],
            transliteration=w["en_transliteration"],
            translation=translation,
            root=root_text,
            root_frequency=root_freq,
            lemma=lemma_text,
            lemma_frequency=lemma_freq,
            stem=stem_text,
            stem_frequency=stem_freq,
            grammatical_features=grammatical_features,
            morpheme_segments=segments,
            description=strip_html(w["morph_description"]),
        )
        entries.append(entry)

    return MorphologyResponse(
        ayah_key=resolved_key,
        words=entries,
        input_mode=input_mode,
        other_occurrences_count=other_occurrences_count,
    )
