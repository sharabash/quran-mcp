<script lang="ts">
  let {
    pageNumber,
    totalPages,
    loading,
    onnavigate,
  }: {
    pageNumber: number;
    totalPages: number;
    loading: boolean;
    onnavigate: (page: number) => void;
  } = $props();

  let canGoNext = $derived(pageNumber < totalPages && !loading);
  let canGoPrev = $derived(pageNumber > 1 && !loading);

  let inputEl = $state<HTMLInputElement | null>(null);
  let editValue = $state("");

  // Sync display value when page changes externally (navigation)
  $effect(() => {
    if (document.activeElement !== inputEl) {
      editValue = String(pageNumber);
    }
  });

  function handleFocus() {
    editValue = String(pageNumber);
    inputEl?.select();
  }

  function commitEdit() {
    const num = parseInt(editValue);
    if (!isNaN(num) && num >= 1 && num <= totalPages && num !== pageNumber) {
      onnavigate(num);
    } else {
      editValue = String(pageNumber);
    }
  }

  function handleKey(e: KeyboardEvent) {
    if (e.key === "Enter") {
      commitEdit();
      inputEl?.blur();
    }
    if (e.key === "Escape") {
      editValue = String(pageNumber);
      inputEl?.blur();
    }
  }
</script>

<div class="toolbar">
  <button class="nav-btn" disabled={!canGoNext} onclick={() => onnavigate(pageNumber + 1)}>
    <span class="caret">&lsaquo;</span>
  </button>
  <div class="page-center">
    <span class="page-label">Page</span>
    <input
      class="page-input"
      type="number"
      min="1"
      max={totalPages}
      bind:value={editValue}
      bind:this={inputEl}
      onfocus={handleFocus}
      onblur={commitEdit}
      onkeydown={handleKey}
      disabled={loading}
    />
    <span class="page-total">/ {totalPages}</span>
  </div>
  <button class="nav-btn" disabled={!canGoPrev} onclick={() => onnavigate(pageNumber - 1)}>
    <span class="caret">&rsaquo;</span>
  </button>
</div>

<style>
  .toolbar {
    display: flex;
    align-items: stretch;
    width: 100%;
    flex-shrink: 0;
    direction: ltr;
    font-family: var(--font-sans, system-ui, -apple-system, sans-serif);
    border-top: 1px solid var(--m-border-subtle);
  }
  .nav-btn {
    padding: 0.35rem 1.2rem;
    border: none;
    background: linear-gradient(180deg, var(--m-surface-3) 0%, var(--m-surface-2) 100%);
    color: var(--m-text-1);
    cursor: pointer;
    font-size: 1.3rem;
    font-weight: bold;
    line-height: 1;
    transition: background 0.15s;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
  }
  .nav-btn:hover:not(:disabled) {
    background: linear-gradient(180deg, var(--m-surface-4) 0%, var(--m-surface-3) 100%);
  }
  .nav-btn:active:not(:disabled) {
    background: linear-gradient(180deg, var(--m-surface-1) 0%, #091020 100%);
    box-shadow: inset 0 2px 3px rgba(0, 0, 0, 0.3);
  }
  .nav-btn:disabled {
    opacity: 0.2;
    cursor: not-allowed;
  }
  .caret {
    text-shadow: 0 1px 3px rgba(0, 0, 0, 0.5);
    display: inline-block;
  }
  .page-center {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.25rem;
    background: rgba(15, 29, 53, 0.3);
    font-size: 0.8rem;
    color: var(--m-text-2);
    border-left: 1px solid var(--m-border-subtle);
    border-right: 1px solid var(--m-border-subtle);
  }
  .page-label {
    opacity: 0.5;
  }
  .page-input {
    width: 3.2rem;
    padding: 0.1rem 0.35rem 0.1rem 0.15rem;
    border: none;
    border-bottom: 1px solid rgba(255, 255, 255, 0.15);
    border-right: 1px solid rgba(255, 255, 255, 0.1);
    border-bottom-right-radius: 2px;
    background: transparent;
    color: var(--m-text-1);
    font-size: 0.85rem;
    font-weight: 600;
    font-family: inherit;
    text-align: right;
    -moz-appearance: textfield;
    transition: border-color 0.2s;
  }
  .page-input::-webkit-inner-spin-button,
  .page-input::-webkit-outer-spin-button {
    -webkit-appearance: none;
    margin: 0;
  }
  .page-input:hover:not(:focus):not(:disabled) {
    border-bottom-color: rgba(255, 255, 255, 0.3);
    border-right-color: rgba(255, 255, 255, 0.2);
  }
  .page-input:focus {
    outline: none;
    border-bottom-color: rgba(107, 193, 122, 0.5);
    border-right-color: rgba(107, 193, 122, 0.35);
  }
  .page-input:disabled {
    opacity: 0.3;
    cursor: not-allowed;
  }
  .page-total {
    opacity: 0.4;
  }
</style>
