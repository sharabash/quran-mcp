<script lang="ts">
  export type ActionId = "translate" | "ask" | "analyze" | "similar" | "listen";

  let {
    activeAction,
    position = "above" as "above" | "below",
    onaction,
  }: {
    activeAction: ActionId | null;
    position?: "above" | "below";
    onaction: (id: ActionId) => void;
  } = $props();

  const actions: { id: ActionId; icon: string; label: string; disabled?: boolean }[] = [
    { id: "translate", icon: "\u2194", label: "Translate" },
    { id: "ask", icon: "?", label: "Ask" },
    { id: "analyze", icon: "\u03B1", label: "Analyze" },
    { id: "similar", icon: "\u2261", label: "Similar" },
    { id: "listen", icon: "\u25B6", label: "Listen", disabled: true },
  ];
</script>

<div class="action-bar" class:below={position === "below"}>
  {#each actions as action (action.id)}
    <button
      class="action-btn"
      class:active={activeAction === action.id}
      class:disabled={action.disabled}
      disabled={action.disabled}
      onclick={() => !action.disabled && onaction(action.id)}
    >
      <span class="icon">{action.icon}</span>
      <span class="label">{action.label}</span>
    </button>
  {/each}
  <div class="caret"></div>
</div>

<style>
  .action-bar {
    display: inline-flex;
    gap: 2px;
    background: linear-gradient(180deg, var(--m-surface-3) 0%, var(--m-surface-2) 100%);
    border: 1px solid var(--m-border);
    border-radius: 10px;
    padding: 4px;
    box-shadow: 0 8px 24px var(--m-shadow), 0 0 0 1px var(--m-border-subtle);
    position: relative;
  }
  /* Caret: points down by default (bar above selection) */
  .caret {
    position: absolute;
    bottom: -6px;
    left: 50%;
    width: 12px;
    height: 12px;
    background: var(--m-surface-2);
    border-right: 1px solid var(--m-border);
    border-bottom: 1px solid var(--m-border);
    transform: translateX(-50%) rotate(45deg);
  }
  /* When below selection: caret points up */
  .action-bar.below .caret {
    bottom: auto;
    top: -6px;
    border-right: none;
    border-bottom: none;
    border-left: 1px solid var(--m-border);
    border-top: 1px solid var(--m-border);
  }
  .action-btn {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 3px;
    padding: 8px 14px;
    border-radius: 8px;
    cursor: pointer;
    border: none;
    background: transparent;
    font-family: 'Varela Round', sans-serif;
    font-size: 10px;
    letter-spacing: 0.02em;
    color: var(--m-gold-dim);
    transition: all 0.15s ease;
  }
  .action-btn:hover:not(.disabled) {
    color: var(--m-gold-mid);
    background: rgba(168, 128, 48, 0.08);
  }
  .action-btn.active {
    color: var(--m-gold-bright);
    background: linear-gradient(180deg, rgba(168, 128, 48, 0.18) 0%, rgba(168, 128, 48, 0.08) 100%);
    box-shadow: 0 0 0 1px var(--m-gold-border);
  }
  .action-btn.active .icon {
    text-shadow: 0 0 8px rgba(224, 192, 96, 0.3);
  }
  .action-btn.disabled {
    opacity: 0.3;
    cursor: not-allowed;
  }
  .icon {
    font-size: 18px;
    line-height: 1;
  }
</style>
