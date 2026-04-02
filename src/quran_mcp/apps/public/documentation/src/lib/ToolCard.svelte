<script lang="ts">
  import type { Tool } from "./types";

  interface Props {
    tool: Tool;
  }

  let { tool }: Props = $props();

  function copyCode(btn: HTMLButtonElement) {
    const block = btn.closest(".code-block");
    if (!block) return;
    const code = block.querySelector("code");
    if (!code) return;
    navigator.clipboard.writeText(code.textContent ?? "").then(() => {
      const prev = btn.textContent;
      btn.textContent = "copied";
      setTimeout(() => { btn.textContent = prev; }, 1500);
    });
  }
</script>

<article class="tool-ref reveal" id={tool.name} data-tool-section={tool.name}>
  <div class="tool-shell">
    <header class="tool-ref-header">
      <div class="tool-ref-title">
        <h3><a href="#{tool.name}">{tool.name}</a></h3>
        <div class="tool-stats" aria-label="Tool parameter counts">
          <span class="stat-pill">{tool.required_count} required</span>
          <span class="stat-pill">{tool.optional_count} optional</span>
        </div>
      </div>
      <p class="tool-desc">{tool.description}</p>
    </header>

    <div class="tool-panel-grid">
      <section class="panel-card">
        <h4 class="panel-heading">Parameters</h4>
        {#if tool.param_rows.length}
        <table class="field-table">
          <thead>
            <tr><th>Name</th><th>Type</th><th>Status</th><th>Description</th></tr>
          </thead>
          <tbody>
            {#each tool.param_rows as row}
            <tr>
              <td>{row.name}</td>
              <td>{row.type}</td>
              <td>
                <span class="badge {row.required ? 'badge-req' : 'badge-opt'}">
                  {row.required ? 'required' : 'optional'}
                </span>
                {#if row.has_default}
                <span class="default-val">{row.default_display}</span>
                {/if}
              </td>
              <td>{row.description || '\u2014'}</td>
            </tr>
            {/each}
          </tbody>
        </table>
        {:else}
        <p class="empty-state">None.</p>
        {/if}
      </section>

      <section class="panel-card" data-tool-output={tool.name}>
        <h4 class="panel-heading">Response shape</h4>
        <table class="field-table">
          <thead>
            <tr><th>Field</th><th>Type</th><th>Description</th></tr>
          </thead>
          <tbody>
            {#each tool.output_rows as row}
            <tr>
              <td>{row.name}</td>
              <td>{row.type}</td>
              <td>{row.description || '\u2014'}</td>
            </tr>
            {/each}
          </tbody>
        </table>
      </section>
    </div>

    <details class="example" data-tool-example={tool.name}>
      <summary>Example</summary>
      <div class="example-body">
        {#if tool.example_layout === 'apps'}
        <div class="example-panels example-panels-rich">
          <section class="panel-card example-panel-static">
            <h4 class="panel-heading">Example call</h4>
            <div class="code-block">
              <div class="code-label example-prompt">Example call</div>
              <pre><code>{@html tool.call_html}</code></pre>
              <button class="copy-btn" type="button" onclick={(e) => copyCode(e.currentTarget)}>copy</button>
            </div>
          </section>

          <details class="example-panel-detail">
            <summary>Structured response</summary>
            <div class="example-panel-body">
              <div class="code-block">
                <div class="code-label">Structured response</div>
                <pre><code>{@html tool.response_html}</code></pre>
                <button class="copy-btn" type="button" onclick={(e) => copyCode(e.currentTarget)}>copy</button>
              </div>
            </div>
          </details>

          {#if tool.example_screenshot}
          <details class="example-panel-detail">
            <summary>In-app screenshot</summary>
            <div class="example-panel-body example-panel-visual">
              <p class="example-visual-caption">{tool.example_screenshot.caption}</p>
              <img
                class="example-screenshot"
                src={tool.example_screenshot.src}
                alt={tool.example_screenshot.alt}
                loading="lazy"
              >
            </div>
          </details>
          {/if}
        </div>
        {:else}
        <div class="example-grid">
          <div class="code-block">
            <div class="code-label example-prompt">Example call</div>
            <pre><code>{@html tool.call_html}</code></pre>
            <button class="copy-btn" type="button" onclick={(e) => copyCode(e.currentTarget)}>copy</button>
          </div>
          <div class="code-block">
            <div class="code-label">Structured response</div>
            <pre><code>{@html tool.response_html}</code></pre>
            <button class="copy-btn" type="button" onclick={(e) => copyCode(e.currentTarget)}>copy</button>
          </div>
        </div>
        {/if}
        {#if tool.session_assumptions}
        <p class="example-note"><strong>Session assumption</strong> {tool.session_assumptions}</p>
        {/if}
      </div>
    </details>
  </div>
</article>
