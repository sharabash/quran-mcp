<script lang="ts">
  import type { MushafWord } from "./types";
  import {
    type WordSelection,
    type SegmentPosition,
    getSegmentPosition,
    isDragging,
  } from "./selection";

  let {
    words,
    interactive,
    verseLookup,
    selectedVerseKey,
    wordSelection: sel,
    qcfFontFamily,
    pageNumber,
    lineNumber,
    onverseselect,
    onworddown,
    onwordenter,
  }: {
    words: MushafWord[];
    interactive: boolean;
    verseLookup: Record<number, string>;
    selectedVerseKey: string | null;
    wordSelection: WordSelection | null;
    qcfFontFamily: string | null;
    pageNumber: number;
    lineNumber: number;
    onverseselect: (key: string) => void;
    onworddown: (surah: number, ayah: number, verseKey: string, wordPosition: number) => void;
    onwordenter: (verseKey: string, wordPosition: number) => void;
  } = $props();

  /**
   * Matches quran.com's center-alignment logic for the printed Madani mushaf.
   * Pages 1-2 (Al-Fatiha, start of Al-Baqarah) are fully centered.
   * Specific last-ayah lines on other pages are also centered.
   */
  const CENTER_ALIGNED_PAGES = [1, 2];
  const CENTER_ALIGNED_LINES: Record<number, number[]> = {
    255: [2], 528: [9], 534: [6], 545: [6], 586: [1],
    593: [2], 594: [5], 600: [10], 602: [5, 15], 603: [10, 15],
    604: [4, 9, 14, 15],
  };

  let isCenterAligned = $derived(
    CENTER_ALIGNED_PAGES.includes(pageNumber) ||
    (CENTER_ALIGNED_LINES[pageNumber]?.includes(lineNumber) ?? false)
  );

  // Word positions on this line (for segment computation)
  let lineWordPositions = $derived(
    words
      .filter((w) => w.char_type_name === "word")
      .map((w) => w.position_in_verse)
  );

  function wordSegment(word: MushafWord): SegmentPosition | null {
    if (word.char_type_name !== "word") return null;
    if (!sel || verseLookup[word.verse_id] !== sel.verseKey) return null;
    return getSegmentPosition(word.position_in_verse, sel.words, lineWordPositions);
  }

  function wordInfo(word: MushafWord) {
    const key = verseLookup[word.verse_id];
    if (!key) return null;
    const [s, a] = key.split(":").map(Number);
    return { surah: s, ayah: a, verseKey: key, position: word.position_in_verse };
  }

  function handlePointerDown(e: PointerEvent, word: MushafWord) {
    if (word.char_type_name !== "word") return;
    e.preventDefault();
    const info = wordInfo(word);
    if (!info) return;
    onverseselect(info.verseKey);
    onworddown(info.surah, info.ayah, info.verseKey, info.position);
  }

  function handlePointerEnter(word: MushafWord) {
    if (word.char_type_name !== "word") return;
    if (!isDragging()) return;
    const vk = verseLookup[word.verse_id];
    if (vk) onwordenter(vk, word.position_in_verse);
  }

  /** Stop click from bubbling to <main> dismissal handler. */
  function handleClick(e: MouseEvent) {
    e.stopPropagation();
  }
</script>

<div class="line-wrapper">
  <div class="verse-text" class:center-align={isCenterAligned}>
    {#each words as word (word.word_id)}
      <!-- svelte-ignore a11y_no_static_element_interactions -->
      {#if qcfFontFamily && word.glyph_text}
        <span
          class="quran-word"
          class:interactive
          class:end-marker={word.char_type_name === "end"}
          class:ayah-highlight={word.char_type_name === "word" && verseLookup[word.verse_id] === selectedVerseKey && !sel}
          class:word-selected={wordSegment(word) !== null}
          class:seg-only={wordSegment(word) === "only"}
          class:seg-start={wordSegment(word) === "start"}
          class:seg-middle={wordSegment(word) === "middle"}
          class:seg-end={wordSegment(word) === "end"}
          data-text={word.text}
          style="font-family: '{qcfFontFamily}', 'Amiri Quran', serif"
          onpointerdown={interactive ? (e) => handlePointerDown(e, word) : undefined}
          onpointerenter={interactive ? () => handlePointerEnter(word) : undefined}
          onclick={interactive ? handleClick : undefined}
        >{word.glyph_text}</span>
      {:else if word.char_type_name === "end"}
        <span class="quran-word end-marker fallback">{word.text}</span>
      {:else if word.char_type_name === "word"}
        <span
          class="quran-word"
          class:interactive
          class:ayah-highlight={verseLookup[word.verse_id] === selectedVerseKey && !sel}
          class:word-selected={wordSegment(word) !== null}
          class:seg-only={wordSegment(word) === "only"}
          class:seg-start={wordSegment(word) === "start"}
          class:seg-middle={wordSegment(word) === "middle"}
          class:seg-end={wordSegment(word) === "end"}
          onpointerdown={interactive ? (e) => handlePointerDown(e, word) : undefined}
          onpointerenter={interactive ? () => handlePointerEnter(word) : undefined}
          onclick={interactive ? handleClick : undefined}
        >{word.text}</span>
      {/if}
    {/each}
  </div>
</div>

<style>
  .line-wrapper {
    direction: rtl;
    margin-top: 0.854em;
    margin-bottom: 0.854em;
  }

  .verse-text {
    display: flex;
    justify-content: space-between;
    gap: 0.085em;
    font-size: clamp(15px, 5.5cqi, 40px);
    line-height: var(--mushaf-line-height, 1.618em);
    text-shadow: -1px 3px 1px #000000de, -2px 2px 2px #68686880;
    touch-action: pan-y;
  }
  .verse-text.center-align {
    justify-content: center;
  }

  .quran-word {
    display: inline-block;
    white-space: nowrap;
    cursor: text;
    user-select: text;
    -webkit-user-select: text;
  }

  .quran-word.interactive {
    cursor: pointer;
    user-select: none;
    -webkit-user-select: none;
  }

  .quran-word.interactive:hover {
    color: var(--m-gold-mid);
  }

  /* Full-ayah highlight: green wash for AI re-entry "you were here" marker.
     Only shows when selectedVerseKey is set AND no word-level selection active. */
  .quran-word.ayah-highlight {
    color: var(--m-green-bright);
    background: var(--m-green-bg);
    border-radius: 4px;
  }

  /* ─── Word-level selection (burnished gold) ─── */
  .quran-word.word-selected {
    color: var(--m-gold-mid);
    background: var(--m-gold-bg);
    box-shadow: 0 0 0 1px var(--m-gold-border);
    position: relative;
    z-index: 1;
  }

  /* Bridge flex gap between adjacent selected words.
     Overlapping padding + negative margin creates continuous highlight. */
  .quran-word.seg-start {
    border-radius: 0 4px 4px 0; /* RTL: leading edge is right side */
    padding-inline-start: 0.185em;
    margin-inline-start: -0.185em;
    padding-inline-end: 0.085em;
    margin-inline-end: -0.085em;
    z-index: -1;
    box-shadow: 0 -1px 0 0 var(--m-gold-border),
                0 1px 0 0 var(--m-gold-border),
                1px 0 0 0 var(--m-gold-border);
  }
  .quran-word.seg-middle {
    border-radius: 0;
    padding-inline: 0.085em;
    margin-inline: -0.085em;
    z-index: -1;
    box-shadow: 0 -1px 0 0 var(--m-gold-border),
                0 1px 0 0 var(--m-gold-border);
  }
  .quran-word.seg-end {
    border-radius: 4px 0 0 4px; /* RTL: trailing edge is left side */
    padding-inline-end: 0.185em;
    margin-inline-end: -0.185em;
    padding-inline-start: 0.085em;
    margin-inline-start: -0.085em;
    z-index: -1;
    box-shadow: 0 -1px 0 0 var(--m-gold-border),
                0 1px 0 0 var(--m-gold-border),
                -1px 0 0 0 var(--m-gold-border);
  }
  .quran-word.seg-only {
    border-radius: 4px;
    padding-inline: 0.185em;
    margin-inline: -0.185em;
    z-index: -1;
  }

  .end-marker {
    margin-inline-end: 0.08em;
  }
  .end-marker.fallback {
    color: var(--m-text-3);
  }
</style>
