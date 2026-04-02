<script lang="ts">
  import type { PageData, SurahHeader as SurahHeaderType } from "./types";
  import type { WordSelection } from "./selection";
  import VerseLine from "./VerseLine.svelte";
  import SurahHeader from "./SurahHeader.svelte";

  let {
    data,
    interactive,
    selectedVerseKey,
    wordSelection: sel,
    qcfFontFamily,
    onverseselect,
    onworddown,
    onwordenter,
  }: {
    data: PageData;
    interactive: boolean;
    selectedVerseKey: string | null;
    wordSelection: WordSelection | null;
    qcfFontFamily: string | null;
    onverseselect: (key: string) => void;
    onworddown: (surah: number, ayah: number, verseKey: string, wordPosition: number) => void;
    onwordenter: (verseKey: string, wordPosition: number) => void;
  } = $props();

  // Surah header map: line_number → header
  let headerMap = $derived(
    Object.fromEntries(
      data.surah_headers.map((h) => [h.appears_before_line, h])
    ) as Record<number, SurahHeaderType>
  );

  // Verse lookup: verse_id → verse_key
  let verseLookup = $derived(
    Object.fromEntries(
      data.verses.map((v) => [v.verse_id, v.verse_key])
    ) as Record<number, string>
  );

  /** Intercept copy: replace QCF PUA glyphs with uthmani text from data-text attributes. */
  function handleCopy(e: ClipboardEvent) {
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed) return;

    // Walk all elements in the selection range and collect data-text values
    const range = selection.getRangeAt(0);
    const container = range.commonAncestorContainer instanceof Element
      ? range.commonAncestorContainer
      : range.commonAncestorContainer.parentElement;
    if (!container) return;

    const spans = container.querySelectorAll<HTMLElement>("[data-text]");
    if (spans.length === 0) return; // No QCF glyphs in selection — let default copy work

    const words: string[] = [];
    for (const span of spans) {
      if (selection.containsNode(span, true)) {
        words.push(span.dataset.text!);
      }
    }
    if (words.length === 0) return;

    e.preventDefault();
    e.clipboardData?.setData("text/plain", words.join(" "));
  }
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="page-container" oncopy={handleCopy}>
  <div class="page-content">
    {#each data.lines as line (line.line_number)}
      {#if headerMap[line.line_number]}
        <SurahHeader header={headerMap[line.line_number]} />
      {/if}
      <VerseLine
        words={line.words}
        {interactive}
        {verseLookup}
        {selectedVerseKey}
        wordSelection={sel}
        {qcfFontFamily}
        pageNumber={data.page_number}
        lineNumber={line.line_number}
        {onverseselect}
        {onworddown}
        {onwordenter}
      />
    {/each}
  </div>
</div>

<style>
  .page-container {
    direction: rtl;
    font-family: "Amiri Quran", "Amiri", "Traditional Arabic", "Scheherazade New", serif;
    max-width: 825px;
    width: 100%;
    margin: 0 auto;
    padding: 2.75rem 0 1rem;
    /* cqi container for responsive font-size in VerseLine */
    container-type: inline-size;
  }
  /* Shrink-wrap to widest line's natural content width, then center.
     All verse lines (block-level flex) stretch to this shared width,
     so space-between produces true mushaf justification — lines with
     more glyph content get tighter gaps, lines with less get wider gaps. */
  .page-content {
    width: max-content;
    max-width: 100%;
    margin-inline: auto;
    padding-inline: 1rem;
  }
</style>
