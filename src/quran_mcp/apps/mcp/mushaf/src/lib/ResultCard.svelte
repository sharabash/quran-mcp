<script lang="ts">
  let {
    label,
    arabicText,
    content,
    fallbackWord,
  }: {
    label: string;
    arabicText?: string;
    content: string;
    fallbackWord?: string;
  } = $props();
</script>

<div class="result-card">
  <div class="result-label">{label}</div>
  {#if fallbackWord}
    <div class="fallback-notice">Showing {label.toLowerCase()} for: {fallbackWord}</div>
  {/if}
  {#if arabicText}
    <div class="result-arabic">{arabicText}</div>
  {/if}
  <div class="result-text">{content}</div>
</div>

<style>
  .result-card {
    background: linear-gradient(170deg, var(--m-surface-3) 0%, var(--m-surface-2) 40%, var(--m-surface-2) 100%);
    border: 1px solid var(--m-border-subtle);
    border-radius: 10px;
    padding: 16px 20px;
    margin-top: 12px;
    box-shadow: 0 6px 20px var(--m-shadow);
    max-width: 420px;
    margin-left: auto;
    margin-right: auto;
    direction: ltr;
  }
  .result-label {
    font-family: 'Varela Round', sans-serif;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--m-text-3);
    margin-bottom: 8px;
  }
  .fallback-notice {
    font-family: 'Varela Round', sans-serif;
    font-size: 10px;
    color: var(--m-gold-dim);
    font-style: italic;
    margin-bottom: 6px;
  }
  .result-arabic {
    direction: rtl;
    font-family: "Amiri Quran", "Amiri", "Traditional Arabic", serif;
    font-size: 18px;
    color: var(--m-text-1);
    margin-bottom: 6px;
  }
  .result-text {
    color: var(--m-text-1);
    font-size: 14px;
    line-height: 1.6;
  }
</style>
