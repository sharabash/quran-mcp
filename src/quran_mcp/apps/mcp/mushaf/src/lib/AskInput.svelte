<script lang="ts">
  let {
    onsubmit,
  }: {
    onsubmit: (question: string) => void;
  } = $props();

  let value = $state("");

  function handleSubmit() {
    const trimmed = value.trim();
    if (!trimmed) return;
    onsubmit(trimmed);
    value = "";
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }
</script>

<div class="ask-input-row">
  <input
    class="ask-input"
    type="text"
    placeholder="Ask about this phrase..."
    bind:value
    onkeydown={handleKeydown}
  />
  <button
    class="ask-submit"
    onclick={handleSubmit}
    disabled={!value.trim()}
  >&rarr;</button>
</div>

<style>
  .ask-input-row {
    display: flex;
    gap: 8px;
    margin-top: 12px;
    max-width: 420px;
    margin-left: auto;
    margin-right: auto;
    direction: ltr;
  }
  .ask-input {
    flex: 1;
    background: var(--m-surface-1);
    border: 1px solid var(--m-border);
    border-radius: 8px;
    padding: 10px 14px;
    color: var(--m-text-1);
    font-family: 'Varela Round', sans-serif;
    font-size: 13px;
    outline: none;
    transition: border-color 0.2s;
  }
  .ask-input::placeholder {
    color: var(--m-text-3);
  }
  .ask-input:focus {
    border-color: var(--m-gold-border);
  }
  .ask-submit {
    background: linear-gradient(180deg, var(--m-surface-5) 0%, var(--m-surface-3) 100%);
    border: 1px solid var(--m-border);
    border-radius: 8px;
    color: var(--m-gold-bright);
    padding: 10px 16px;
    font-size: 13px;
    cursor: pointer;
    transition: all 0.15s;
  }
  .ask-submit:hover:not(:disabled) {
    background: linear-gradient(180deg, var(--m-surface-6) 0%, var(--m-surface-4) 100%);
  }
  .ask-submit:disabled {
    opacity: 0.3;
    cursor: not-allowed;
  }
</style>
