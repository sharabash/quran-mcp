<script lang="ts">
  /**
   * Debug overlay for mushaf context pipeline.
   * Shows last updateModelContext and sendMessage payloads.
   * Toggle: ?debug=1 URL param or Ctrl+Shift+D.
   */

  type Props = {
    lastContext: { structuredContent?: unknown; contentBlockCount: number; tokenEstimate: number } | null;
    lastMessage: { role: string; text: string } | null;
    cacheStats: { arabic: number; maxEntries: number };
  };

  let { lastContext, lastMessage, cacheStats }: Props = $props();

  let collapsed = $state(false);
</script>

<div class="debug-overlay" class:collapsed>
  <button class="debug-toggle" onclick={() => collapsed = !collapsed}>
    {collapsed ? "▸ Debug" : "▾ Debug"}
  </button>
  {#if !collapsed}
    <div class="debug-content">
      <section>
        <h4>Last Context</h4>
        {#if lastContext}
          <pre>{JSON.stringify(lastContext.structuredContent, null, 2)}</pre>
          <p>Content blocks: {lastContext.contentBlockCount} | <strong class:warn={lastContext.tokenEstimate > 3500}>~{lastContext.tokenEstimate} tokens</strong> (limit: 4000)</p>
        {:else}
          <p class="muted">No context sent yet</p>
        {/if}
      </section>
      <section>
        <h4>Last Message</h4>
        {#if lastMessage}
          <p><strong>{lastMessage.role}:</strong> {lastMessage.text}</p>
        {:else}
          <p class="muted">No message sent yet</p>
        {/if}
      </section>
      <section>
        <h4>Cache</h4>
        <p>Arabic: {cacheStats.arabic}/{cacheStats.maxEntries}</p>
      </section>
    </div>
  {/if}
</div>

<style>
  .debug-overlay {
    position: fixed;
    bottom: 3rem;
    left: 0.5rem;
    right: 0.5rem;
    max-height: 40vh;
    overflow-y: auto;
    background: rgba(0, 0, 0, 0.85);
    color: #0f0;
    font-family: monospace;
    font-size: 0.7rem;
    line-height: 1.3;
    border-radius: 0.5rem;
    z-index: 100;
    padding: 0.25rem 0.5rem;
  }
  .debug-overlay.collapsed {
    max-height: none;
    overflow: visible;
  }
  .debug-toggle {
    background: none;
    border: none;
    color: #0f0;
    font-family: monospace;
    font-size: 0.7rem;
    cursor: pointer;
    padding: 0;
  }
  .debug-content {
    margin-top: 0.25rem;
  }
  h4 {
    color: #0ff;
    margin: 0.25rem 0 0.1rem;
    font-size: 0.7rem;
  }
  pre {
    white-space: pre-wrap;
    word-break: break-all;
    margin: 0;
  }
  p {
    margin: 0;
  }
  .muted {
    color: var(--m-text-3);
  }
  .warn {
    color: #f80;
  }
  section {
    border-top: 1px solid #333;
    padding-top: 0.2rem;
    margin-top: 0.2rem;
  }
  section:first-child {
    border-top: none;
    margin-top: 0;
  }
</style>
