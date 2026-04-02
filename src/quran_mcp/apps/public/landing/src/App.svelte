<script lang="ts">
  import { onMount } from "svelte";

  interface UsageShowcase {
    id: string;
    title: string;
    category?: string;
    prompt_html: string;
    model?: string;
    date?: string;
    prerequisite_tools?: string[];
    tools: string[];
    response_html: string;
  }

  let showcase: UsageShowcase | null = $state(null);
  let showcaseCount = $state(0);
  let toolCount = $state(0);
  let copied = $state(false);
  let showcaseExpanded = $state(false);
  let quickstartConfigHtml = $state('');

  onMount(async () => {
    try {
      const res = await fetch("/documentation/data.json");
      const data = await res.json();
      toolCount = data.tool_count || 0;
      quickstartConfigHtml = data.quickstart_config_html || '';
      const showcases = data.usage_examples?.showcases || [];
      showcaseCount = showcases.length;
      if (showcases.length > 0) {
        showcase = showcases[0];
      }
    } catch {
      // Data fetch failed — showcase teaser won't show, but page still works.
    }
  });

  function copyUrl() {
    navigator.clipboard.writeText("https://mcp.quran.ai/");
    copied = true;
    setTimeout(() => { copied = false; }, 1500);
  }

  function copyCode(btn: HTMLButtonElement) {
    const block = btn.closest('.code-block');
    if (!block) return;
    const code = block.querySelector('code');
    if (!code) return;
    navigator.clipboard.writeText(code.textContent || '');
    btn.textContent = 'copied!';
    setTimeout(() => { btn.textContent = 'copy'; }, 1500);
  }

  // ── Collapsible system (matches documentation page exactly) ──
  function initCollapsibles(_node: HTMLElement) {
    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

    function getButton(root: HTMLElement): HTMLButtonElement | null {
      return document.querySelector(`[data-collapsible-toggle][data-target="${root.id}"]`);
    }

    function syncButton(root: HTMLElement, button: HTMLButtonElement | null) {
      if (!button) return;
      const expanded = root.getAttribute('data-collapsible-state') === 'expanded';
      button.hidden = root.getAttribute('data-collapsible-eligible') !== 'true';
      button.textContent = expanded
        ? button.dataset.hideLabel || 'Collapse'
        : button.dataset.showLabel || 'Show more';
      button.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    }

    function evaluate(root: HTMLElement) {
      if (!root.id) return;
      const button = getButton(root);
      root.style.setProperty('--collapsed-max', root.getAttribute('data-collapsed-max') || '31rem');
      const rule = root.getAttribute('data-auto-collapse') || 'off';
      const eligible = rule === 'always';
      root.setAttribute('data-collapsible-eligible', eligible ? 'true' : 'false');
      if (!eligible) {
        root.setAttribute('data-collapsible-state', 'expanded');
      } else if (!root.hasAttribute('data-collapsible-state')) {
        root.setAttribute('data-collapsible-state', 'collapsed');
      }
      syncButton(root, button);
    }

    function toggle(root: HTMLElement) {
      const nextState = root.getAttribute('data-collapsible-state') === 'expanded' ? 'collapsed' : 'expanded';
      root.setAttribute('data-collapsible-state', nextState);
      syncButton(root, getButton(root));
      if (nextState === 'collapsed') {
        requestAnimationFrame(() => {
          const scrollTarget = root.getAttribute('data-scroll-target');
          const scrollEl = scrollTarget ? document.getElementById(scrollTarget) || root : root;
          scrollEl.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
        });
      }
    }

    const collapsibles = Array.from(_node.querySelectorAll<HTMLElement>('[data-collapsible]'));
    collapsibles.forEach(evaluate);

    function onClick(event: MouseEvent) {
      const button = (event.target as HTMLElement).closest<HTMLButtonElement>('[data-collapsible-toggle]');
      if (!button) return;
      const root = document.getElementById(button.getAttribute('data-target')!);
      if (!root || root.getAttribute('data-collapsible-eligible') !== 'true') return;
      toggle(root);
    }

    document.addEventListener('click', onClick);
    return { destroy() { document.removeEventListener('click', onClick); } };
  }
</script>

<div class="container" use:initCollapsibles>
  <!-- ═══ Nav ═══ -->
  <nav class="top-nav">
    <div class="logo">quran<span class="ai">.ai</span></div>
    <a href="https://mcp.quran.ai" class="nav-home">Quran MCP</a>
    <div class="nav-links">
      <a href="/documentation">Documentation</a>
      <span class="nav-sep">&middot;</span>
      <a href="/support">Support</a>
      <span class="nav-sep">&middot;</span>
      <a href="/privacy">Privacy</a>
    </div>
    <div class="nav-spacer"></div>
    <div class="nav-meta">by <a href="https://quran.foundation">quran.foundation</a>
      <a href="https://github.com/quran/quran-mcp" class="nav-github" title="View on GitHub" target="_blank" rel="noopener">view on GitHub &nbsp;<svg viewBox="0 0 98 96" fill="currentColor" aria-hidden="true"><path d="M41.44 69.38C28.81 67.85 19.91 58.76 19.91 46.99c0-4.79 1.72-9.95 4.59-13.4-1.24-3.16-1.05-9.86.39-12.63 3.83-.48 8.99 1.53 12.06 4.3 3.63-1.15 7.46-1.72 12.15-1.72s8.52.57 11.96 1.63c2.97-2.68 8.23-4.69 12.06-4.21 1.34 2.58 1.53 9.28.29 12.54 3.06 3.64 4.69 8.52 4.69 13.5 0 11.77-8.9 20.67-21.72 22.3 3.25 2.1 5.45 6.7 5.45 11.96v9.95c0 2.87 2.39 4.5 5.26 3.35C84.41 87.95 98 70.63 98 49.19 98 22.11 75.99 0 48.9 0 21.82 0 0 22.11 0 49.19c0 21.25 13.49 38.86 31.68 45.46 2.58.96 5.07-.76 5.07-3.35v-7.66a18 18 0 0 1-4.59.96c-6.32 0-10.05-3.44-12.73-9.86-1.05-2.58-2.2-4.11-4.4-4.4-1.15-.1-1.53-.57-1.53-1.15 0-1.15 1.91-1.97 3.83-1.97 2.77 0 5.17 1.72 7.66 5.26 1.91 2.78 3.92 4.02 6.31 4.02s3.92-.86 6.12-3.06c1.63-1.63 2.87-3.06 4.02-4.02Z"/></svg></a>
    </div>
    <div class="nav-status">
      <span class="status-dot"></span>
      live
    </div>
  </nav>

  <!-- ═══ Hero ═══ -->
  <div class="header">
    <img src="/screenshots/header-icon.png" alt="quran.ai icon" class="header-icon">
    <h1>Qur'an + AI &mdash;<br><em>grounded, not guesswork.</em></h1>
  </div>

  <!-- ═══ Contrast ═══ -->
  <div class="contrast">
    <div class="contrast-box before">
      <span class="contrast-label">Without grounding</span>
      <span>Uncertain training data, paraphrased verses, hallucinated references</span>
    </div>
    <div class="contrast-arrow">&rarr;</div>
    <div class="contrast-box after">
      <span class="contrast-label">With quran.ai</span>
      Grounded answers backed by verified text, tafsir, and translations from quran.com
    </div>
  </div>

  <!-- ═══ Server URL ═══ -->
  <div class="card url-card">
    <h2>Server URL</h2>
    <div class="url-bar">
      <code>https://mcp.quran.ai/</code>
      <button onclick={copyUrl} title="Copy to clipboard">
        {#if copied}
          Copied!
        {:else}
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
        {/if}
      </button>
    </div>
    <p>
      Connect this MCP server to <a href="#setup-claude">Claude</a> or <a href="#setup-chatgpt">ChatGPT</a>, or any AI client that supports MCP.
      When the AI calls our server, responses are grounded in verified data from
      <a href="https://quran.com">quran.com</a>, <b>not</b> hallucinated, <em class="inshallah">insha'Allah.</em>
    </p>
  </div>

  <!-- ═══ How It Works ═══ -->
  <div class="card">
    <h2>How It Works</h2>
    <div class="how-steps">
      <div class="how-step">
        <span class="how-step-num">1</span>
        <div class="how-step-text">
          <strong>You ask the AI about the Quran.</strong> A focused tafsir deep-dive, a verse lookup, a thematic search &mdash; anything.
        </div>
      </div>
      <div class="how-step">
        <span class="how-step-num">2</span>
        <div class="how-step-text">
          <strong>The AI calls quran.ai to retrieve verified sources</strong> &mdash; classical tafsir commentary, canonical Arabic text, and translations all sourced from <a href="https://quran.com">quran.com</a>.
        </div>
      </div>
      <div class="how-step">
        <span class="how-step-num">3</span>
        <div class="how-step-text">
          <strong>The AI grounds its response strictly in the retrieved content.</strong> The source data is verified and canonical. The AI is instructed to stay within what the sources say, and <a href="#setup-claude">Claude</a> does so reliably &mdash; from quick verse lookups to deep scholarly study, but <a href="#disclaimer">read the fine print</a> to know how to spot if the AI isn't doing its job.
        </div>
      </div>
    </div>
  </div>

  <!-- ═══ Setup at a Glance ═══ -->
  <section id="setup-glance">
    <hr class="section-rule">
    <h2 class="section-heading">Setup at a glance</h2>
    <div class="install-grid">
      <div class="card install-card">
        <h3><a href="#setup-claude">Claude</a></h3>
        <p><strong>Settings</strong> &rarr; <strong>Connectors</strong> &rarr; <strong>Add custom connector</strong></p>
        <dl class="field-list">
          <dt>Name</dt><dd><code>quran</code></dd>
          <dt>URL</dt><dd><code>https://mcp.quran.ai</code></dd>
        </dl>
      </div>
      <div class="card install-card">
        <h3><a href="#setup-chatgpt">ChatGPT</a></h3>
        <p><strong>Settings</strong> &rarr; <strong>Apps</strong>, then<br><strong>Advanced</strong> &rarr; Developer mode &rarr; <strong>Create app</strong></p>
        <dl class="field-list">
          <dt>Name</dt><dd><code>quran</code></dd>
          <dt>URL</dt><dd><code>https://mcp.quran.ai</code></dd>
          <dt>Auth</dt><dd><code>none</code></dd>
        </dl>
        <p class="invoke-hint">Invoke with <code>@quran</code> in chat.</p>
      </div>
      <div class="card install-card install-card-generic">
        <h3>Other MCP clients</h3>
        <p>Use the server name <code>quran</code>, point it at <code>https://mcp.quran.ai/</code>, and keep transport on <code>streamable-http</code>. If your client expects a JSON connection object, start from this shape:</p>
        {#if quickstartConfigHtml}
          <div class="code-block" style="margin-top:12px">
            <div class="code-label">Connection object</div>
            <pre><code>{@html quickstartConfigHtml}</code></pre>
            <button class="copy-btn" type="button" onclick={(e) => copyCode(e.currentTarget as HTMLButtonElement)}>copy</button>
          </div>
        {/if}
      </div>
    </div>
  </section>

  <!-- ═══ Setup Guides ═══ -->
  <section id="setup">
    <p class="section-blurb" style="margin-bottom:16px">Need the full walkthrough with screenshots? Pick your client below. <a href="#setup-claude">Claude</a> or <a href="#setup-chatgpt">ChatGPT</a>.</p>

    <!-- Claude full guide -->
    <div class="card setup-card" id="setup-claude">
    <h3 class="setup-platform-heading">
      Claude
      <span class="platform-tags"><span>Web</span> <span>Desktop</span></span>
    </h3>
    <p class="setup-intro">Available on all plans including <a href="https://claude.ai">Claude Free</a>. Free accounts are limited to one custom connector.</p>
    <div class="docs-collapsible" id="claude-setup-collapsible" data-collapsible data-collapsed-max="31rem" data-auto-collapse="always" data-scroll-target="setup-claude">

    <p class="setup-phase">One-time setup</p>
    <div class="setup-steps">
      <div class="setup-step">
        <span class="step-num">1</span>
        <div class="step-body">
          <h4>Open Connectors</h4>
          <p>Go to <strong>Settings &rarr; Connectors</strong>. You'll see a banner that connectors have moved. Click <strong>Go to Customize</strong>.</p>
          <img class="setup-screenshot" src="/screenshots/new/claude1.png" alt="Claude Settings showing the Connectors page with a Go to Customize banner" loading="lazy">
        </div>
      </div>
      <div class="setup-step">
        <span class="step-num">2</span>
        <div class="step-body">
          <h4>Add custom connector</h4>
          <p>In the Customize panel, click the <strong>+</strong> button next to Connectors, then select <strong>Add custom connector</strong>.</p>
          <img class="setup-screenshot" src="/screenshots/new/claude2.png" alt="Customize panel showing the Add custom connector option in the dropdown" loading="lazy">
        </div>
      </div>
      <div class="setup-step">
        <span class="step-num">3</span>
        <div class="step-body">
          <h4>Configure the server</h4>
          <p>Set <strong>Name</strong> to <code>quran</code> and paste the server URL into <strong>Remote MCP server URL</strong>, then click <strong>Add</strong>.</p>
          <div class="code-block">
            <div class="code-label">Remote MCP server URL</div>
            <pre><code>https://mcp.quran.ai</code></pre>
          </div>
          <img class="setup-screenshot" src="/screenshots/new/claude3.png" alt="Add custom connector dialog with name and URL filled in" loading="lazy">
        </div>
      </div>
      <div class="setup-step">
        <span class="step-num">4</span>
        <div class="step-body">
          <h4>Allow all tools</h4>
          <p>Open the connector you just added and set every tool to <strong>Always allow</strong>. They're all read-only.</p>
          <img class="setup-screenshot" src="/screenshots/new/claude4.png" alt="Tool permissions showing Always allow selected for all read-only tools" loading="lazy">
        </div>
      </div>
    </div>

    <p class="setup-phase">Every conversation</p>
    <div class="setup-steps">
      <div class="setup-step">
        <span class="step-num">5</span>
        <div class="step-body">
          <h4>Start a conversation</h4>
          <p>Open a new chat. Click <strong>+</strong> &rarr; <strong>Connectors</strong> and make sure <strong>quran</strong> is enabled before sending your question.</p>
          <img class="setup-screenshot" src="/screenshots/new/claude5.png" alt="New chat with Connectors menu showing quran toggle enabled" loading="lazy">
        </div>
      </div>
      <div class="setup-step">
        <span class="step-num">6</span>
        <div class="step-body">
          <h4>Check for tool calls</h4>
          <p>Look for tool-call indicators in the response. That is the fast sanity check that Claude fetched canonical data instead of free-styling from memory.</p>
          <img class="setup-screenshot" src="/screenshots/new/claude6.png" alt="Claude response showing tool calls to the Quran MCP server" loading="lazy">
        </div>
      </div>
      <div class="setup-step">
        <span class="step-num">7</span>
        <div class="step-body">
          <h4>Verify citations</h4>
          <p>Look for inline citations and summary attribution. Those are the visible signals that the answer stayed grounded in fetched sources.</p>
          <img class="setup-screenshot" src="/screenshots/new/claude7.png" alt="Claude response with inline citations and source attribution" loading="lazy">
        </div>
      </div>
    </div>
    </div>
    <button class="collapse-toggle" aria-label="Show full Claude guide" data-collapsible-toggle data-target="claude-setup-collapsible" data-show-label="Show full Claude guide" data-hide-label="Collapse guide"></button>
    </div>

    <!-- ChatGPT full guide -->
    <div class="card setup-card" id="setup-chatgpt">
    <h3 class="setup-platform-heading">
      ChatGPT
      <span class="platform-tags"><span>Web</span> <span>Desktop</span> <span>Mobile</span></span>
    </h3>
    <p class="setup-intro">Requires a <a href="https://chatgpt.com">ChatGPT subscription</a>. Set up on Web or Desktop once and it syncs to Mobile automatically.</p>
    <div class="docs-collapsible" id="chatgpt-setup-collapsible" data-collapsible data-collapsed-max="31rem" data-auto-collapse="always" data-scroll-target="setup-chatgpt">

    <p class="setup-phase">One-time setup</p>
    <div class="setup-steps">
      <div class="setup-step">
        <span class="step-num">1</span>
        <div class="step-body">
          <h4>Open app settings</h4>
          <p>Go to <strong>Settings &rarr; Apps</strong>, then open <strong>Advanced settings</strong> at the bottom.</p>
          <img class="setup-screenshot" src="/screenshots/new/chatgpt-1-apps.png" alt="ChatGPT Settings showing Apps tab with Advanced settings at the bottom" loading="lazy">
        </div>
      </div>
      <div class="setup-step">
        <span class="step-num">2</span>
        <div class="step-body">
          <h4>Enable developer mode</h4>
          <p>Turn on <strong>Developer mode</strong>. A <strong>Create app</strong> button appears in the top-right corner.</p>
          <img class="setup-screenshot" src="/screenshots/new/chatgpt-2-devmode.png" alt="Developer mode toggled on with Create app button visible" loading="lazy">
        </div>
      </div>
      <div class="setup-step">
        <span class="step-num">3</span>
        <div class="step-body">
          <h4>Create the app</h4>
          <p>Set <strong>Name</strong> to <code>quran</code>, paste the server URL into <strong>MCP Server URL</strong>, leave authentication on <strong>No Auth</strong>, then click <strong>Create</strong>.</p>
          <div class="code-block">
            <div class="code-label">MCP server URL</div>
            <pre><code>https://mcp.quran.ai</code></pre>
          </div>
          <img class="setup-screenshot" src="/screenshots/new/chatgpt-3-form.png" alt="New App form with name quran, MCP Server URL filled in, No Auth selected" loading="lazy">
        </div>
      </div>
      <div class="setup-step">
        <span class="step-num">4</span>
        <div class="step-body">
          <h4>Verify it connected</h4>
          <p>You'll land back on the Apps page. <strong>quran</strong> should appear under <strong>Enabled apps</strong> with the <strong>DEV</strong> badge.</p>
          <img class="setup-screenshot" src="/screenshots/new/chatgpt-4-enabled-apps.png" alt="Apps page showing quran listed under Enabled apps with DEV badge" loading="lazy">
        </div>
      </div>
      <div class="setup-step">
        <span class="step-num">5</span>
        <div class="step-body">
          <h4>Check app details</h4>
          <p>Open the <strong>quran</strong> entry and enable <strong>Reference memories and chats</strong> so the app can reason with conversation context while still grounding on canonical data.</p>
          <img class="setup-screenshot" src="/screenshots/new/chatgpt-5-memory-on.png" alt="App details showing Reference memories toggle and tool list" loading="lazy">
        </div>
      </div>
    </div>

    <p class="setup-phase">Every conversation</p>
    <div class="setup-steps">
      <div class="setup-step">
        <span class="step-num">6</span>
        <div class="step-body">
          <h4>Attach the app</h4>
          <p>In any chat, click <strong>+</strong> &rarr; <strong>More</strong> and select <strong>quran</strong>. The badge appears in the input bar.</p>
          <img class="setup-screenshot" src="/screenshots/new/chatgpt-6-use-app.png" alt="Chat input plus menu showing quran app" loading="lazy">
        </div>
      </div>
      <div class="setup-step">
        <span class="step-num">7</span>
        <div class="step-body">
          <h4>Ask your question</h4>
          <p>Ask naturally. The app decides whether it needs exact text, translations, tafsir, or search based on the question itself.</p>
          <img class="setup-screenshot" src="/screenshots/new/chatgpt-7-just-ask.png" alt="Chat input with a question about the Quran" loading="lazy">
        </div>
      </div>
      <div class="setup-step">
        <span class="step-num">8</span>
        <div class="step-body">
          <h4>Read the grounded response</h4>
          <p>Look for the <strong>Called tool</strong> indicators. That is the evidence path that the response is using server data rather than memory alone.</p>
          <img class="setup-screenshot" src="/screenshots/new/chatgpt-8-response.png" alt="ChatGPT response with Called tool indicator" loading="lazy">
        </div>
      </div>
    </div>

    </div>
    <button class="collapse-toggle" aria-label="Show full ChatGPT guide" data-collapsible-toggle data-target="chatgpt-setup-collapsible" data-show-label="Show full ChatGPT guide" data-hide-label="Collapse guide"></button>
    </div>

    <p class="setup-done">
      That's it. You're connected. <a href="/documentation">Explore the full tool reference and showcases &rarr;</a>
    </p>
  </section>

  <!-- ═══ Showcase Teaser ═══ -->
  {#if showcase}
    <section class="card showcase-teaser" id="showcase">
      <h2>See It In Action</h2>
      <p class="section-blurb">Real output from a live conversation. Not a template &mdash; not filler &mdash; not made up. The AI fetched canonical sources from quran.com and grounded its entire response in them.</p>

      <div class="showcase-head">
        <div class="showcase-category">{showcase.category || showcase.title}</div>
        <div class="showcase-tools">
          {#if showcase.prerequisite_tools}
            {#each showcase.prerequisite_tools as tool}
              <span class="tool-badge tool-badge-prereq">{tool}</span>
            {/each}
          {/if}
          <span class="tool-badge-break"></span>
          {#each showcase.tools as tool}
            <span class="tool-badge">{tool}</span>
          {/each}
        </div>
      </div>

      <div class="response-card">
        <div class="response-prompt">
          <span class="prompt-label">Prompt</span>
          <span class="prompt-text">{@html showcase.prompt_html}</span>
        </div>

        <div class="response-body resp" class:collapsed={!showcaseExpanded}>
          {#if showcase.model || showcase.date}
            <p class="response-attribution">Response from {showcase.model}{#if showcase.date}, {showcase.date}{/if}</p>
          {/if}
          {@html showcase.response_html}
        </div>

        <div class="showcase-toggle-row">
          <button class="toggle-btn" onclick={() => showcaseExpanded = !showcaseExpanded}>
            {showcaseExpanded ? "Collapse response \u2191" : "Show full response \u2193"}
          </button>
        </div>
      </div>

      {#if showcaseCount > 1}
        <p class="showcase-more">
          This is 1 of {showcaseCount} showcases. <a href="/documentation#usage-examples">See them all &rarr;</a>
        </p>
      {/if}
    </section>
  {/if}

  <!-- ═══ Disclaimer ═══ -->
  <div class="card disclaimer" id="disclaimer">
    <h2>Disclaimer <span class="disclaimer-subtitle">(the fine print)</span></h2>
    <p>
      When the AI calls our tools, the data is verified and canonical. Two things to watch for:
    </p>
    <p>
      <strong>Did it actually call the tools?</strong><br>
      Look for tool calls like <em class="disclaimer-em">fetch_quran</em> or <em class="disclaimer-em">search_tafsir</em> before the response. No tool calls = not grounded. On ChatGPT, start your conversations by explicitly invoking the app using the @ prefix, e.g. <strong><code class="mention-white">@quran</code></strong>.
    </p>
    <p>
      <strong>Did it stay within the sources?</strong><br>
      The AI is instructed to ground strictly in Quran text, tafsir, and translation data. If you push into personal rulings or gray-area fiqh beyond what the sources cover, the AI may overstep. <strong>It's a study tool, not a mufti.</strong>
    </p>
    <p>
      <strong>Does it cite its sources?</strong><br>
      Every grounded response ends with a citation line like <em class="disclaimer-em">Grounded in quran.ai: fetch_quran(2:255), fetch_tafsir(2:255, en-ibn-kathir)</em>. If you don't see one, the AI may be working from memory &mdash; ask it to fetch the sources explicitly.
    </p>
    <p>
      <strong>Always verify with trusted scholars. Starting point, not final authority.</strong>
    </p>
  </div>

  <!-- ═══ Footer ═══ -->
  <div class="footer">
    <p>
      <a href="https://quran.ai">quran.ai</a> mcp &mdash; an AI grounding service from <a href="https://quran.com">quran.com</a> &middot; a <a href="https://quran.foundation">quran.foundation</a> project
      <br>
      <a href="/privacy">Privacy Policy</a> &middot; <a href="/support">Support</a> &middot; <a href="/documentation">Explore Tools &amp; Showcases</a> &middot; <a href="https://github.com/quran/quran-mcp" target="_blank" rel="noopener">GitHub</a>
    </p>
  </div>
</div>
