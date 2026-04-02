<script lang="ts">
  let {
    verseKey,
    arabicText,
    translation,
    translationLoading,
    explaining,
    explainError,
    surahName,
    onclose,
    onexplain,
  }: {
    verseKey: string;
    arabicText: string | null;
    translation: string | null;
    translationLoading: boolean;
    explaining: boolean;
    explainError: string | null;
    surahName: string | null;
    onclose: () => void;
    onexplain: (focusText: string) => void;
  } = $props();

  let focusText = $state("");
  let lastSentText = $state("");

  /** Parse "29:64" → { surah: 29, ayah: 64 } */
  let parsed = $derived(() => {
    const [s, a] = verseKey.split(":");
    return { surah: parseInt(s), ayah: parseInt(a) };
  });

  function handleSubmit() {
    if (explaining) return;
    lastSentText = focusText.trim();
    onexplain(focusText);
  }

  /** Handle focus leaving the entire explain widget (input, buttons, etc.).
   *  Uses focusout on the container — it bubbles from any child element. */
  function handleWidgetFocusOut(e: FocusEvent) {
    const target = e.relatedTarget as HTMLElement | null;
    // If focus moved to another element within the widget, don't trigger
    if (target?.closest(".explain-widget")) return;

    // Focus left the widget entirely — submit if there's unsent text
    if (focusText.trim().length > 0 && !explaining) {
      const text = focusText.trim();
      if (text !== lastSentText) {
        lastSentText = text;
        onexplain(focusText);
      }
    }
  }
</script>

<div class="panel-row">
  <button class="close-col" onclick={onclose}>&times;</button>
  <div class="panel">
    <div class="panel-header">
      <span class="verse-ref">Ayah {verseKey}</span>
      {#if surahName}
        <span class="verse-detail">Surat {surahName}, verse {parsed().ayah}</span>
      {/if}
    </div>
    {#if arabicText}
      <div class="arabic-text" dir="rtl">{arabicText}</div>
    {/if}
    <div class="panel-body">
      {#if translationLoading}
        <div class="status-text">Loading translation...</div>
      {:else if translation}
        <div class="translation-text" dir="ltr">{translation}</div>
      {:else}
        <div class="status-text">No translation available</div>
      {/if}
    </div>
    <div class="explain-widget"
         onfocusout={handleWidgetFocusOut}>
      <button
        class="explain-btn"
        onclick={handleSubmit}
        disabled={translationLoading || explaining}
      >
        {#if explaining}
          ...
        {:else}
          Explain this verse
        {/if}
      </button>
      <input
        class="focus-input"
        type="text"
        placeholder="Type your question here"
        bind:value={focusText}
        disabled={explaining}
        onkeydown={(e: KeyboardEvent) => { if (e.key === "Enter") handleSubmit(); }}
      />
      <button
        class="send-btn"
        onclick={handleSubmit}
        disabled={translationLoading || explaining}
        title="Send"
      >&#9654;</button>
    </div>
    {#if explainError}
      <div class="explain-error">{explainError}</div>
    {/if}
  </div>
</div>

<style>
  /* Outer row: close button on the left, panel content on the right */
  .panel-row {
    display: flex;
    align-items: stretch;
    width: 100%;
    direction: ltr;
    font-family: var(--font-sans, system-ui, -apple-system, sans-serif);
  }
  .close-col {
    flex-shrink: 0;
    width: 2rem;
    background: linear-gradient(to right, #0a1525, #14243d);
    border: none;
    border-right: 1px solid rgba(255, 255, 255, 0.04);
    color: var(--color-text-secondary, #a8a091);
    font-size: 1.2rem;
    cursor: pointer;
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding-top: 0.65rem;
    transition: color 0.15s, background 0.15s;
  }
  .close-col:hover {
    color: var(--color-text-primary, #ede6db);
    background: linear-gradient(to right, #0f1d35, #1a2d4a);
  }
  .panel {
    flex: 1;
    min-width: 0;
    background: linear-gradient(170deg, #14243d 0%, #0d1a2e 40%, #101828 100%);
    padding: 0.85rem 1rem 0.75rem;
    direction: ltr;
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.5);
  }
  .panel-header {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    margin-bottom: 0.6rem;
  }
  .verse-ref {
    font-weight: var(--font-weight-semibold, 600);
    color: var(--color-text-primary, #ede6db);
    font-size: 0.95rem;
  }
  .verse-detail {
    color: var(--color-text-secondary, #a8a091);
    font-size: 0.75rem;
    opacity: 0.7;
  }
  .arabic-text {
    font-family: "KFGQPC Uthmanic Script HAFS", "Amiri Quran", "Amiri", "Traditional Arabic", "Scheherazade New", serif;
    font-size: 1.4rem;
    line-height: 2;
    color: var(--color-text-primary, #ede6db);
    margin-bottom: 0.75rem;
    text-shadow: -1px 2px 1px #000000de, -1px 1px 2px #68686860;
  }
  .panel-body {
    margin-bottom: 1rem;
  }
  .translation-text {
    font-size: var(--font-text-md-size, 1rem);
    line-height: 1.6;
    color: var(--color-text-primary, #ede6db);
    white-space: pre-wrap;
  }
  .status-text {
    color: var(--color-text-secondary, #a8a091);
    font-style: italic;
  }
  /* Explain widget: button + input + send as a single joined bar */
  .explain-widget {
    display: flex;
    align-items: stretch;
    margin-top: 0.5rem;
    border-radius: 6px;
    overflow: hidden;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-bottom-color: rgba(0, 0, 0, 0.3);
    border-right-color: rgba(0, 0, 0, 0.2);
    box-shadow:
      0 3px 8px rgba(0, 0, 0, 0.4),
      0 1px 2px rgba(0, 0, 0, 0.25),
      inset 0 1px 0 rgba(255, 255, 255, 0.06);
    transition: box-shadow 0.6s ease, border-color 0.6s ease;
  }
  .explain-btn {
    padding: 0.55rem 0.85rem;
    border: none;
    background: linear-gradient(180deg, #1e3455 0%, #162544 100%);
    color: var(--color-text-primary, #ede6db);
    cursor: pointer;
    font-size: 0.8rem;
    font-family: inherit;
    white-space: nowrap;
    text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
    border-right: 1px solid rgba(255, 255, 255, 0.06);
  }
  .explain-btn:hover:not(:disabled) {
    background: linear-gradient(180deg, #243d62 0%, #1c3050 100%);
  }
  .explain-btn:active:not(:disabled) {
    background: linear-gradient(180deg, #142540 0%, #0f1d35 100%);
  }
  .explain-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  .focus-input {
    flex: 1;
    padding: 0.55rem 0.65rem;
    border: none;
    background: #060e1e;
    color: var(--color-text-primary, #ede6db);
    font-size: 0.8rem;
    font-family: inherit;
    box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.4);
  }
  .focus-input::placeholder {
    color: var(--color-text-tertiary, #706a5e);
  }
  .focus-input:focus {
    outline: none;
    background: #080f20;
  }
  .focus-input:disabled {
    opacity: 0.5;
  }
  .send-btn {
    padding: 0.55rem 0.6rem;
    border: none;
    background: linear-gradient(180deg, #1e3455 0%, #162544 100%);
    color: rgba(237, 230, 219, 0.5);
    cursor: pointer;
    font-size: 0.65rem;
    display: flex;
    align-items: center;
    justify-content: center;
    border-left: 1px solid rgba(255, 255, 255, 0.06);
    transition: color 0.15s;
  }
  .send-btn:hover:not(:disabled) {
    color: rgba(237, 230, 219, 0.85);
    background: linear-gradient(180deg, #243d62 0%, #1c3050 100%);
  }
  .send-btn:disabled {
    opacity: 0.3;
    cursor: not-allowed;
  }
  .explain-error {
    color: var(--color-text-danger, #dc2626);
    font-size: 0.75rem;
    margin-top: 0.35rem;
  }
</style>
