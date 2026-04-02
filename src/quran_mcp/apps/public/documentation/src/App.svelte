<script lang="ts">
  import type { DocsData } from "./lib/types";
  import Sidebar from "./lib/Sidebar.svelte";
  import ToolCard from "./lib/ToolCard.svelte";
  import EditionTable from "./lib/EditionTable.svelte";
  let data: DocsData | null = $state(null);
  let error: string | null = $state(null);
  let activeId = $state("top");

  // ── Data loading ──
  async function loadData() {
    try {
      const res = await fetch("/documentation/data.json");
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      data = await res.json();
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
  }

  loadData();

  // ── Mobile menu ──
  function toggleMobileMenu() {
    document.getElementById("sidebar")?.classList.toggle("open");
  }
  function initSidebarClose(node: HTMLElement) {
    const sidebar = document.getElementById("sidebar");
    function handleClick(event: MouseEvent) {
      if ((event.target as HTMLElement).tagName === "A") {
        sidebar?.classList.remove("open");
      }
    }
    sidebar?.addEventListener("click", handleClick);
    return { destroy() { sidebar?.removeEventListener("click", handleClick); } };
  }

  // ── Reveal observer ──
  function initRevealObserver(node: HTMLElement) {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) entry.target.classList.add("visible");
        }
      },
      { threshold: 0.08, rootMargin: "0px 0px -36px 0px" }
    );
    node.querySelectorAll(".reveal").forEach((el) => observer.observe(el));
    return { destroy() { observer.disconnect(); } };
  }

  // ── Scroll-spy ──
  //
  // Visible content window (document coords):
  //   firstVisibleY = scrollY + navHeight
  //   lastVisibleY  = scrollY + innerHeight
  //
  // "Current section" = last section (by viewport Y) whose top edge
  // is at or above the bottom of the fixed nav.
  //
  // Element list cached; rebuilt on sidebar DOM changes (async data).
  // Positions via getBoundingClientRect (viewport-relative, immune to
  // positioned ancestors / sticky / transforms).
  function initScrollSpy(_node: HTMLElement) {
    type SectionEl = { id: string; el: HTMLElement };
    let sectionEls: SectionEl[] = [];

    function rebuildElements() {
      const links = Array.from(
        document.querySelectorAll<HTMLAnchorElement>('.sidebar-nav a[href^="#"]')
      );
      sectionEls = links
        .map((link) => {
          const id = link.getAttribute("href")!.slice(1);
          if (id === "top") return null;
          const el = document.getElementById(id);
          return el ? { id, el } : null;
        })
        .filter((s): s is SectionEl => s !== null);
    }

    function update() {
      if (window.scrollY < 10) {
        activeId = "top";
        return;
      }

      const navEl = document.getElementById("top");
      const navHeight = navEl ? navEl.getBoundingClientRect().height : 69;
      // Activation line: 20% into the visible content area, not the exact
      // nav bottom. This prevents a section staying "active" when only a
      // tiny sliver of it remains visible above the next section.
      const visibleHeight = window.innerHeight - navHeight;
      const activationLine = navHeight + visibleHeight * 0.2;

      // Sort by actual viewport Y.
      const positioned = sectionEls
        .map((s) => ({ id: s.id, vTop: s.el.getBoundingClientRect().top }))
        .sort((a, b) => a.vTop - b.vTop);

      // Last section whose top has scrolled to or past the activation line.
      let active = "top";
      for (let i = positioned.length - 1; i >= 0; i--) {
        if (positioned[i].vTop <= activationLine) {
          active = positioned[i].id;
          break;
        }
      }
      activeId = active;
    }

    rebuildElements();

    const sidebarNav = document.querySelector(".sidebar-nav");
    const observer = sidebarNav
      ? new MutationObserver(() => rebuildElements())
      : null;
    observer?.observe(sidebarNav!, { childList: true, subtree: true });

    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    update();

    return {
      destroy() {
        window.removeEventListener("scroll", update);
        window.removeEventListener("resize", update);
        observer?.disconnect();
      },
    };
  }

  // ── Collapsible system ──
  function initCollapsibles(node: HTMLElement) {
    const reduceMotion =
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    function getButton(root: HTMLElement): HTMLButtonElement | null {
      return document.querySelector(
        `[data-collapsible-toggle][data-target="${root.id}"]:not(.collapse-top-toggle)`
      );
    }

    function resolveCollapsedMax(root: HTMLElement): number {
      const value =
        root.getAttribute("data-collapsed-max") ||
        getComputedStyle(root).getPropertyValue("--collapsed-max") ||
        "31rem";
      const probe = document.createElement("div");
      probe.style.position = "absolute";
      probe.style.visibility = "hidden";
      probe.style.pointerEvents = "none";
      probe.style.height = value;
      root.appendChild(probe);
      const pixels = probe.getBoundingClientRect().height;
      probe.remove();
      return pixels;
    }

    function shouldCollapse(root: HTMLElement, collapsedMax: number): boolean {
      const rule = root.getAttribute("data-auto-collapse") || "off";
      if (rule === "off") return false;
      if (rule === "always") return true;
      const match = rule.match(/^([0-9.]+)x$/);
      const multiplier = match ? parseFloat(match[1]) : 3;
      return root.scrollHeight > collapsedMax * multiplier;
    }

    function syncButton(root: HTMLElement, button: HTMLButtonElement | null) {
      if (!button) return;
      const expanded =
        root.getAttribute("data-collapsible-state") === "expanded";
      button.hidden =
        root.getAttribute("data-collapsible-eligible") !== "true";
      button.textContent = expanded
        ? button.dataset.hideLabel || "Collapse"
        : button.dataset.showLabel || "Show more";
      button.setAttribute("aria-expanded", expanded ? "true" : "false");
    }

    function evaluate(root: HTMLElement) {
      if (!root.id) return;
      const button = getButton(root);
      const collapsedMax = resolveCollapsedMax(root);
      root.style.setProperty(
        "--collapsed-max",
        root.getAttribute("data-collapsed-max") || "31rem"
      );
      const eligible = shouldCollapse(root, collapsedMax);
      root.setAttribute(
        "data-collapsible-eligible",
        eligible ? "true" : "false"
      );
      if (!eligible) {
        root.setAttribute("data-collapsible-state", "expanded");
      } else if (!root.hasAttribute("data-collapsible-state")) {
        root.setAttribute(
          "data-collapsible-state",
          root.getAttribute("data-default-state") || "collapsed"
        );
      }
      syncButton(root, button);
      syncTopToggle(root);
    }

    function syncTopToggle(root: HTMLElement) {
      const btn = document.querySelector<HTMLButtonElement>(
        `.collapse-top-toggle[data-target="${root.id}"]`
      );
      if (!btn) return;
      const expanded = root.getAttribute("data-collapsible-state") === "expanded";
      const eligible = root.getAttribute("data-collapsible-eligible") === "true";
      btn.hidden = !(expanded && eligible);
    }

    function promoteImages(root: HTMLElement, maxY?: number) {
      for (const img of root.querySelectorAll<HTMLImageElement>("img[data-deferred-src]")) {
        if (maxY != null && img.offsetTop > maxY) continue;
        img.src = img.dataset.deferredSrc!;
        img.removeAttribute("data-deferred-src");
      }
    }

    function toggle(root: HTMLElement, scrollOnCollapse = true) {
      const nextState =
        root.getAttribute("data-collapsible-state") === "expanded"
          ? "collapsed"
          : "expanded";
      root.setAttribute("data-collapsible-state", nextState);
      syncButton(root, getButton(root));
      syncTopToggle(root);
      if (nextState === "expanded") {
        promoteImages(root);
      }
      if (nextState === "collapsed" && scrollOnCollapse) {
        requestAnimationFrame(() => {
          const scrollTarget = root.getAttribute("data-scroll-target");
          const scrollEl = scrollTarget
            ? document.getElementById(scrollTarget) || root
            : root;
          scrollEl.scrollIntoView({
            behavior: reduceMotion ? "auto" : "smooth",
            block: "start",
          });
        });
      }
    }

    const collapsibles = Array.from(
      node.querySelectorAll<HTMLElement>("[data-collapsible]")
    );

    collapsibles.forEach((root) => {
      evaluate(root);
      // Force .visible on .reveal children — IO threshold math fails for
      // tall content inside overflow:hidden (ratio < 8% even when in view).
      root.querySelectorAll(".reveal").forEach((el) => el.classList.add("visible"));
      const state = root.getAttribute("data-collapsible-state");
      if (state === "expanded") {
        promoteImages(root);
      } else {
        const max = resolveCollapsedMax(root);
        promoteImages(root, max);
      }
    });

    let resizeObserver: ResizeObserver | null = null;
    if ("ResizeObserver" in window) {
      resizeObserver = new ResizeObserver((entries) => {
        for (const entry of entries) {
          const root =
            (entry.target as HTMLElement).closest<HTMLElement>(
              "[data-collapsible]"
            ) || (entry.target as HTMLElement);
          if (root.hasAttribute("data-collapsible")) evaluate(root);
        }
      });
      collapsibles.forEach((root) => {
        resizeObserver!.observe(root.firstElementChild as HTMLElement || root);
      });
    }

    function onLoad() { collapsibles.forEach(evaluate); }
    function onResize() { collapsibles.forEach(evaluate); }
    function onClick(event: MouseEvent) {
      const button = (event.target as HTMLElement).closest<HTMLButtonElement>(
        "[data-collapsible-toggle]"
      );
      if (!button) return;
      const root = document.getElementById(
        button.getAttribute("data-target")!
      );
      if (
        !root ||
        root.getAttribute("data-collapsible-eligible") !== "true"
      )
        return;
      toggle(root, !button.classList.contains("collapse-top-toggle"));
    }

    window.addEventListener("load", onLoad);
    window.addEventListener("resize", onResize);
    document.addEventListener("click", onClick);

    return {
      destroy() {
        window.removeEventListener("load", onLoad);
        window.removeEventListener("resize", onResize);
        document.removeEventListener("click", onClick);
        resizeObserver?.disconnect();
      },
    };
  }

  // ── Copy helpers (attached to window for onclick attributes) ──
  if (typeof window !== "undefined") {
    (window as any).__copyCode = function (button: HTMLButtonElement) {
      const code = button.closest(".code-block")?.querySelector("code");
      if (!code) return;
      navigator.clipboard.writeText(code.textContent || "").then(() => {
        button.textContent = "copied";
        button.classList.add("copied");
        setTimeout(() => {
          button.textContent = "copy";
          button.classList.remove("copied");
        }, 1400);
      });
    };
    (window as any).__copyText = function (button: HTMLButtonElement) {
      const value = button.getAttribute("data-copy") || button.textContent || "";
      navigator.clipboard.writeText(value).then(() => {
        button.classList.add("copied");
        setTimeout(() => {
          button.classList.remove("copied");
        }, 900);
      });
    };
  }

  // ── Copy helpers for inline use ──
  function copyCode(btn: HTMLButtonElement) {
    (window as any).__copyCode?.(btn);
  }

</script>

{#if data}
  <Sidebar groups={data.groups} showcases={data.usage_examples.showcases} {activeId} />

  <div class="layout" use:initRevealObserver use:initScrollSpy use:initCollapsibles use:initSidebarClose>
    <main class="main">
      <div class="main-inner">
        <!-- ══════════════════════════════════════════════════════════════
             TOP NAV
             ══════════════════════════════════════════════════════════════ -->
        <nav class="top-nav" id="top">
          <a href="https://mcp.quran.ai" class="nav-home">Quran MCP</a>
          <div class="nav-links">
            <a href="/documentation" style="color:var(--green)">Documentation</a>
            <span class="nav-sep">&middot;</span>
            <a href="/support">Support</a>
            <span class="nav-sep">&middot;</span>
            <a href="/privacy">Privacy</a>
          </div>
          <div class="nav-spacer"></div>
          <div class="nav-meta">by <a href="https://quran.foundation">quran.foundation</a></div>
          <a href="https://github.com/quran/quran-mcp" class="nav-github" title="View on GitHub" target="_blank" rel="noopener">
            <svg viewBox="0 0 98 96" fill="currentColor" aria-hidden="true"><path d="M41.44 69.38C28.81 67.85 19.91 58.76 19.91 46.99c0-4.79 1.72-9.95 4.59-13.4-1.24-3.16-1.05-9.86.39-12.63 3.83-.48 8.99 1.53 12.06 4.3 3.63-1.15 7.46-1.72 12.15-1.72s8.52.57 11.96 1.63c2.97-2.68 8.23-4.69 12.06-4.21 1.34 2.58 1.53 9.28.29 12.54 3.06 3.64 4.69 8.52 4.69 13.5 0 11.77-8.9 20.67-21.72 22.3 3.25 2.1 5.45 6.7 5.45 11.96v9.95c0 2.87 2.39 4.5 5.26 3.35C84.41 87.95 98 70.63 98 49.19 98 22.11 75.99 0 48.9 0 21.82 0 0 22.11 0 49.19c0 21.25 13.49 38.86 31.68 45.46 2.58.96 5.07-.76 5.07-3.35v-7.66a18 18 0 0 1-4.59.96c-6.32 0-10.05-3.44-12.73-9.86-1.05-2.58-2.2-4.11-4.4-4.4-1.15-.1-1.53-.57-1.53-1.15 0-1.15 1.91-1.97 3.83-1.97 2.77 0 5.17 1.72 7.66 5.26 1.91 2.78 3.92 4.02 6.31 4.02s3.92-.86 6.12-3.06c1.63-1.63 2.87-3.06 4.02-4.02Z"/></svg>
          </a>
          <button class="mobile-menu-btn" id="mobileMenuBtn" type="button" aria-label="Toggle documentation navigation" onclick={toggleMobileMenu}>
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round">
              <path d="M2 4.5h12M2 8h12M2 11.5h12"/>
            </svg>
          </button>
        </nav>

        <!-- ══════════════════════════════════════════════════════════════
             HERO
             ══════════════════════════════════════════════════════════════ -->
        <section class="hero reveal" id="hero">
          <div class="hero-kicker">Public reference surface</div>
          <h1>Documentation</h1>
          <p class="tagline">Canonical Quran text, translations, and tafsir commentary, exposed through a read-only MCP server with grounded workflows, edition discovery, and word-level study tools.</p>
          <div class="hero-meta" aria-label="Documentation summary">
            <span>Scholar-grade depth</span>
            <span>{data.tafsir_count} Tafsir editions</span>
            <span>Grounded and cited</span>
            <span>Word study tools</span>
            <span>Zero config</span>
          </div>
        </section>

        <!-- ══════════════════════════════════════════════════════════════
             SETUP AND CONNECT
             ══════════════════════════════════════════════════════════════ -->
        <section class="section reveal" id="setup-and-connect">
          <h2 class="section-heading">Setup and connect <a href="#setup-and-connect" class="anchor" aria-hidden="true">#</a></h2>
          <p class="section-blurb">Connect the Quran MCP server in under a minute. The information architecture stays simple on purpose: a fast overview first, then expandable client walkthroughs when you need screenshots and exact click paths.</p>

          <!-- At a glance -->
          <h3 class="cards-subheading" id="setup-at-a-glance">At a glance <a href="#setup-at-a-glance" class="anchor" aria-hidden="true">#</a></h3>
          <div class="install-grid">
            <div class="card install-card">
              <h3>Claude</h3>
              <p><strong>Settings</strong> &rarr; <strong>Connectors</strong> &rarr; <strong>Add custom connector</strong></p>
              <p>Name: <code>quran</code><br>URL: <code>https://mcp.quran.ai</code></p>
            </div>
            <div class="card install-card">
              <h3>ChatGPT</h3>
              <p><strong>Settings</strong> &rarr; <strong>Apps</strong> &rarr; <strong>Advanced</strong> &rarr; Developer mode &rarr; <strong>Create app</strong></p>
              <p>Name: <code>quran</code><br>URL: <code>https://mcp.quran.ai</code><br>Auth: none</p>
              <p>Invoke with <code>@quran</code> in chat.</p>
            </div>
            <div class="card install-card">
              <h3>Other MCP clients</h3>
              <p>Look for MCP, app, or connector settings. Use the server name <code>quran</code>, point it at <code>https://mcp.quran.ai/</code>, and keep transport on <code>streamable-http</code>. If your client expects a JSON connection object, start from this shape:</p>
              <div class="code-block" style="margin-top:12px">
                <div class="code-label">Connection object</div>
                <pre><code>{@html data.quickstart_config_html}</code></pre>
                <button class="copy-btn" type="button" onclick={(e) => copyCode(e.currentTarget as HTMLButtonElement)}>copy</button>
              </div>
            </div>
          </div>
          <p class="section-blurb" style="margin-top:14px">Naming the server <code>quran</code> makes it easier for clients to discover and invoke the right tool surface. The public endpoint uses Streamable HTTP and does not require an API key.</p>

          <!-- Claude setup guide -->
          <h3 class="cards-subheading setup-heading-sticky" id="setup-claude">Claude <span class="platform-tags"><span>Web</span> <span>Desktop</span></span><button class="collapse-top-toggle" type="button" hidden data-collapsible-toggle data-target="claude-setup-collapsible">Collapse guide</button><a href="#setup-claude" class="anchor" aria-hidden="true">#</a></h3>
          <div class="setup-collapsible docs-collapsible" id="claude-setup-collapsible" data-collapsible data-collapsed-max="31rem" data-auto-collapse="always">
            <div class="setup-guide reveal">
              <p class="setup-intro">Available on all plans including <a href="https://claude.ai" style="color:var(--link)">Claude Free</a>. Free accounts are limited to one custom connector.</p>

              <p class="setup-phase">One-time setup</p>
              <div class="setup-steps">
                <div class="setup-step">
                  <span class="step-num">1</span>
                  <div class="step-body">
                    <h4>Open Connectors</h4>
                    <p>Go to <strong>Settings &rarr; Connectors</strong>. You'll see a banner that connectors have moved. Click <strong>Go to Customize</strong>.</p>
                    <img class="setup-screenshot" data-deferred-src="/screenshots/new/claude1.png" alt="Claude Settings showing the Connectors page with a Go to Customize banner" loading="lazy">
                  </div>
                </div>
                <div class="setup-step">
                  <span class="step-num">2</span>
                  <div class="step-body">
                    <h4>Add custom connector</h4>
                    <p>In the Customize panel, click the <strong>+</strong> button next to Connectors, then select <strong>Add custom connector</strong>.</p>
                    <img class="setup-screenshot" data-deferred-src="/screenshots/new/claude2.png" alt="Customize panel showing the Add custom connector option in the dropdown" loading="lazy">
                  </div>
                </div>
                <div class="setup-step">
                  <span class="step-num">3</span>
                  <div class="step-body">
                    <h4>Configure the server</h4>
                    <p>Set <strong>Name</strong> to <code>quran</code> and paste the server URL into <strong>Remote MCP server URL</strong>, then click <strong>Add</strong>.</p>
                    <div class="code-block" style="margin-top:12px">
                      <div class="code-label">Remote MCP server URL</div>
                      <pre><code>https://mcp.quran.ai</code></pre>
                      <button class="copy-btn" type="button" onclick={(e) => copyCode(e.currentTarget as HTMLButtonElement)}>copy</button>
                    </div>
                    <img class="setup-screenshot" data-deferred-src="/screenshots/new/claude3.png" alt="Add custom connector dialog with name and URL filled in" loading="lazy">
                  </div>
                </div>
                <div class="setup-step">
                  <span class="step-num">4</span>
                  <div class="step-body">
                    <h4>Allow all tools</h4>
                    <p>Open the connector you just added and set every tool to <strong>Always allow</strong>. They're all read-only.</p>
                    <img class="setup-screenshot" data-deferred-src="/screenshots/new/claude4.png" alt="Tool permissions showing Always allow selected for all read-only tools" loading="lazy">
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
                    <img class="setup-screenshot" data-deferred-src="/screenshots/new/claude5.png" alt="New chat with Connectors menu showing quran toggle enabled" loading="lazy">
                  </div>
                </div>
                <div class="setup-step">
                  <span class="step-num">6</span>
                  <div class="step-body">
                    <h4>Check for tool calls</h4>
                    <p>Look for tool-call indicators in the response. That is the fast sanity check that Claude fetched canonical data instead of free-styling from memory.</p>
                    <img class="setup-screenshot" data-deferred-src="/screenshots/new/claude6.png" alt="Claude response showing tool calls to the Quran MCP server" loading="lazy">
                  </div>
                </div>
                <div class="setup-step">
                  <span class="step-num">7</span>
                  <div class="step-body">
                    <h4>Verify citations</h4>
                    <p>Look for inline citations and summary attribution. Those are the visible signals that the answer stayed grounded in fetched sources.</p>
                    <img class="setup-screenshot" data-deferred-src="/screenshots/new/claude7.png" alt="Claude response with inline citations and source attribution" loading="lazy">
                  </div>
                </div>
              </div>
            </div>
          </div>
          <button class="collapse-toggle" type="button" hidden data-collapsible-toggle data-target="claude-setup-collapsible" data-show-label="Show full guide" data-hide-label="Collapse guide">Show full guide</button>

          <!-- ChatGPT setup guide -->
          <h3 class="cards-subheading setup-heading-sticky" id="setup-chatgpt">ChatGPT <span class="platform-tags"><span>Web</span> <span>Desktop</span> <span>Mobile</span></span><button class="collapse-top-toggle" type="button" hidden data-collapsible-toggle data-target="chatgpt-setup-collapsible">Collapse guide</button><a href="#setup-chatgpt" class="anchor" aria-hidden="true">#</a></h3>
          <div class="setup-collapsible docs-collapsible" id="chatgpt-setup-collapsible" data-collapsible data-collapsed-max="31rem" data-auto-collapse="always">
            <div class="setup-guide reveal">
              <p class="setup-intro">Requires a <a href="https://chatgpt.com" style="color:var(--link)">ChatGPT subscription</a>. Set up on Web or Desktop once and it syncs to Mobile automatically.</p>

              <p class="setup-phase">One-time setup</p>
              <div class="setup-steps">
                <div class="setup-step">
                  <span class="step-num">1</span>
                  <div class="step-body">
                    <h4>Open app settings</h4>
                    <p>Go to <strong>Settings &rarr; Apps</strong>, then open <strong>Advanced settings</strong> at the bottom.</p>
                    <img class="setup-screenshot" data-deferred-src="/screenshots/new/chatgpt-1-apps.png" alt="ChatGPT Settings showing Apps tab with Advanced settings at the bottom" loading="lazy">
                  </div>
                </div>
                <div class="setup-step">
                  <span class="step-num">2</span>
                  <div class="step-body">
                    <h4>Enable developer mode</h4>
                    <p>Turn on <strong>Developer mode</strong>. A <strong>Create app</strong> button appears in the top-right corner.</p>
                    <img class="setup-screenshot" data-deferred-src="/screenshots/new/chatgpt-2-devmode.png" alt="Developer mode toggled on with ELEVATED RISK badge, Create app button visible" loading="lazy">
                  </div>
                </div>
                <div class="setup-step">
                  <span class="step-num">3</span>
                  <div class="step-body">
                    <h4>Create the app</h4>
                    <p>Set <strong>Name</strong> to <code>quran</code>, paste the server URL into <strong>MCP Server URL</strong>, leave authentication on <strong>No Auth</strong>, then click <strong>Create</strong>.</p>
                    <div class="code-block" style="margin-top:12px">
                      <div class="code-label">MCP server URL</div>
                      <pre><code>https://mcp.quran.ai</code></pre>
                      <button class="copy-btn" type="button" onclick={(e) => copyCode(e.currentTarget as HTMLButtonElement)}>copy</button>
                    </div>
                    <img class="setup-screenshot" data-deferred-src="/screenshots/new/chatgpt-3-form.png" alt="New App form with name quran, MCP Server URL filled in, No Auth selected, acknowledgment checked" loading="lazy">
                  </div>
                </div>
                <div class="setup-step">
                  <span class="step-num">4</span>
                  <div class="step-body">
                    <h4>Verify it connected</h4>
                    <p>You'll land back on the Apps page. <strong>quran</strong> should appear under <strong>Enabled apps</strong> with the <strong>DEV</strong> badge.</p>
                    <img class="setup-screenshot" data-deferred-src="/screenshots/new/chatgpt-4-enabled-apps.png" alt="Apps page showing quran listed under Enabled apps with DEV badge" loading="lazy">
                  </div>
                </div>
                <div class="setup-step">
                  <span class="step-num">5</span>
                  <div class="step-body">
                    <h4>Check app details</h4>
                    <p>Open the <strong>quran</strong> entry and enable <strong>Reference memories and chats</strong> so the app can reason with conversation context while still grounding on canonical data.</p>
                    <img class="setup-screenshot" data-deferred-src="/screenshots/new/chatgpt-5-memory-on.png" alt="App details showing Reference memories toggle, connection URL, and tool list" loading="lazy">
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
                    <img class="setup-screenshot" data-deferred-src="/screenshots/new/chatgpt-6-use-app.png" alt="Chat input plus menu expanded, showing quran app at the bottom of the More submenu" loading="lazy">
                  </div>
                </div>
                <div class="setup-step">
                  <span class="step-num">7</span>
                  <div class="step-body">
                    <h4>Ask your question</h4>
                    <p>Ask naturally. The app decides whether it needs exact text, translations, tafsir, or search based on the question itself.</p>
                    <img class="setup-screenshot" data-deferred-src="/screenshots/new/chatgpt-7-just-ask.png" alt="Chat input with a multi-part question about the quran app's purpose and capabilities" loading="lazy">
                  </div>
                </div>
                <div class="setup-step">
                  <span class="step-num">8</span>
                  <div class="step-body">
                    <h4>Read the grounded response</h4>
                    <p>Look for the <strong>Called tool</strong> indicators. That is the evidence path that the response is using server data rather than memory alone.</p>
                    <img class="setup-screenshot" data-deferred-src="/screenshots/new/chatgpt-8-response.png" alt="ChatGPT response explaining the quran app as a scholarly research tool, with Called tool indicator" loading="lazy">
                  </div>
                </div>
              </div>

              <p class="setup-phase">Getting better results</p>
              <div class="setup-steps">
                <div class="setup-step">
                  <span class="step-num">9</span>
                  <div class="step-body">
                    <h4>Turn on Thinking mode</h4>
                    <p>Use <strong>Thinking</strong> for multi-step or comparative questions. It helps ChatGPT choose editions more deliberately and sequence tool calls with fewer shortcuts.</p>
                    <img class="setup-screenshot" data-deferred-src="/screenshots/new/chatgpt-9-turn-on-thinking.png" alt="ChatGPT model picker showing Thinking mode selected" loading="lazy">
                  </div>
                </div>
                <div class="setup-step">
                  <span class="step-num">10</span>
                  <div class="step-body">
                    <h4>Ask deeper questions</h4>
                    <p>With Thinking mode enabled, ChatGPT is more likely to compare available mufassirin and choose editions that match the question rather than defaulting to the first available source.</p>
                    <img class="setup-screenshot" data-deferred-src="/screenshots/new/chatgpt-10-list-editions.png" alt="Prompt asking about available tafsir and their strengths, with Extended thinking and quran badges" loading="lazy">
                  </div>
                </div>
                <div class="setup-step">
                  <span class="step-num">11</span>
                  <div class="step-body">
                    <h4>Inspect tool calls</h4>
                    <p>Expand each tool call to see which verses, parameters, and editions were used. Multiple calls usually means the answer is doing real synthesis.</p>
                    <img class="setup-screenshot" data-deferred-src="/screenshots/new/chatgpt-11-look-for-tool-calls.png" alt="Response showing multiple Called tool indicators with fetch_translation and fetch_tafsir requests visible" loading="lazy">
                  </div>
                </div>
                <div class="setup-step">
                  <span class="step-num">12</span>
                  <div class="step-body">
                    <h4>Check the citation line</h4>
                    <p>Look for the <strong>Grounded with quran.ai</strong> line at the bottom. That gives you the exact trail of tool calls and editions used in the answer.</p>
                    <img class="setup-screenshot" data-deferred-src="/screenshots/new/chatgpt-12-look-for-citation.png" alt="Citation line reading Grounded with quran.ai followed by a list of fetch_quran, fetch_translation, and fetch_tafsir calls" loading="lazy">
                  </div>
                </div>
              </div>
            </div>
          </div>
          <button class="collapse-toggle" type="button" hidden data-collapsible-toggle data-target="chatgpt-setup-collapsible" data-show-label="Show full guide" data-hide-label="Collapse guide">Show full guide</button>

          <!-- Other MCP clients -->
          <h3 class="cards-subheading" id="setup-other-clients">Other MCP clients <a href="#setup-other-clients" class="anchor" aria-hidden="true">#</a></h3>
          <div class="card install-card reveal">
            <h4>Generic MCP connection</h4>
            <p>Any MCP-compatible client can connect over Streamable HTTP. Use the server name <code>quran</code>, point it at <code>https://mcp.quran.ai/</code>, and pass the same JSON object shown above when the client wants structured configuration instead of form fields.</p>
          </div>
        </section>

        <!-- ══════════════════════════════════════════════════════════════
             USAGE EXAMPLES
             ══════════════════════════════════════════════════════════════ -->
        <section class="section reveal" id="usage-examples">
          <h2 class="section-heading">Usage examples <a href="#usage-examples" class="anchor" aria-hidden="true">#</a></h2>

          <!-- Showcases with full curated responses -->
          {#each data.usage_examples.showcases as showcase}
            <section class="usage-showcase reveal" id={showcase.id}>
              <div class="usage-showcase-head">
                <div class="usage-showcase-copy">
                  <h3>{showcase.category || showcase.title}</h3>
                </div>
                <div class="usage-tools" aria-label="Tools used in this example">
                  {#if showcase.prerequisite_tools}
                    {#each showcase.prerequisite_tools as tool}
                      <span class="tool-badge tool-badge-prerequisite">{tool}</span>
                    {/each}
                  {/if}
                  {#each showcase.tools as tool}
                    <span class="tool-badge">{tool}</span>
                  {/each}
                </div>
              </div>

              <article class="response-card">
                <div class="response-prompt">
                  <span class="prompt-label">Prompt</span>
                  <span class="prompt-text">{@html showcase.prompt_html}</span>
                </div>

                <div
                  class="docs-collapsible showcase-response-shell"
                  id="{showcase.id}-response"
                  data-collapsible
                  data-collapsed-max="45rem"
                  data-auto-collapse="always"
                  data-scroll-target={showcase.id}
                >
                  <div class="response-body resp">
                    {#if showcase.model || showcase.date}
                      <p class="response-attribution">Response from {showcase.model}{#if showcase.date}, {showcase.date}{/if}</p>
                    {/if}
                    {@html showcase.response_html}
                  </div>
                </div>

                <div class="showcase-toggle-row">
                  <button
                    class="collapse-toggle showcase-toggle"
                    type="button"
                    hidden
                    data-collapsible-toggle
                    data-target="{showcase.id}-response"
                    data-show-label="Show full response"
                    data-hide-label="Collapse response"
                  >Show full response</button>
                </div>
              </article>
            </section>
          {/each}

        </section>

        <!-- ══════════════════════════════════════════════════════════════
             TOOL INDEX
             ══════════════════════════════════════════════════════════════ -->
        <section class="section reveal" id="available-tools">
          <h2 class="section-heading">Tool reference <a href="#available-tools" class="anchor" aria-hidden="true">#</a></h2>
          <p class="section-blurb">{data.tool_count} public tools across {data.group_count} ordered groups. The index is quick-scan; the full sections below carry the actual parameter, output, and example contracts.</p>
          <div class="tool-grid">
            {#each data.flat_tools as tool}
              <a href="#{tool.name}" class="tool-index-card">
                <span class="tool-name">{tool.name}</span>
                <span class="tool-summary">{tool.summary}</span>
                <span class="tool-meta">{tool.required_count} required &middot; {tool.optional_count} optional</span>
              </a>
            {/each}
          </div>
        </section>

        <!-- ══════════════════════════════════════════════════════════════
             TOOL REFERENCE SECTIONS
             ══════════════════════════════════════════════════════════════ -->
        {#each data.groups as group}
          <section class="section tool-group" id={group.id}>
            <h2 class="group-heading reveal">{group.label} <a href="#{group.id}" class="anchor" aria-hidden="true">#</a></h2>
            <p class="group-blurb reveal">{group.blurb}</p>
            {#each group.subgroups as subgroup}
              {#if subgroup.label}
                <h3 class="tool-subgroup-heading reveal">{subgroup.label}</h3>
              {/if}
              {#each subgroup.tools as tool}
                <ToolCard {tool} />
              {/each}
            {/each}
          </section>
        {/each}

        <!-- ══════════════════════════════════════════════════════════════
             EDITIONS
             ══════════════════════════════════════════════════════════════ -->
        <section class="section reveal section-transition" id="editions">
          <h2 class="section-heading">Supported editions <a href="#editions" class="anchor" aria-hidden="true">#</a></h2>
          <p class="section-blurb">The edition table is intentionally literal. Use the exact <code>edition_id</code> values below when you want deterministic control over translation or tafsir selection.</p>

          {#each data.edition_groups as editionGroup}
            <EditionTable group={editionGroup} />
            <button
              class="collapse-toggle"
              type="button"
              hidden
              data-collapsible-toggle
              data-target="editions-{editionGroup.id}"
              data-show-label="Show full list"
              data-hide-label="Collapse list"
            >Show full list</button>
          {/each}
        </section>

        <!-- ══════════════════════════════════════════════════════════════
             TROUBLESHOOTING
             ══════════════════════════════════════════════════════════════ -->
        <section class="section reveal" id="troubleshooting">
          <h2 class="section-heading">Troubleshooting <a href="#troubleshooting" class="anchor" aria-hidden="true">#</a></h2>
          <div class="troubleshoot-grid">
            <div class="troubleshoot-card">
              <h4>Server naming and invocation</h4>
              <p>Use <code>quran</code> as the server name. In ChatGPT, invoke with <code>@quran</code>. In Claude, enable it from the Connectors menu before you send the prompt.</p>
            </div>
            <div class="troubleshoot-card">
              <h4>Did it actually call the tools?</h4>
              <p>Look for explicit tool calls like <code>fetch_quran</code> or <code>search_tafsir</code>. If you do not see calls, the answer may be running from model memory instead of fetched data.</p>
            </div>
            <div class="troubleshoot-card">
              <h4>Did it stay inside the sources?</h4>
              <p>The server is a study surface, not a replacement for independent scholarly judgment. If the answer makes a strong claim, ask it to point back to the exact fetched text.</p>
            </div>
            <div class="troubleshoot-card">
              <h4>Does it cite what it used?</h4>
              <p>Grounded responses should expose the trail of tool calls and editions. Missing attribution is often the first sign that the client is answering too loosely.</p>
            </div>
            <div class="troubleshoot-card">
              <h4>Grounding rules bloat</h4>
              <p>Call <code>fetch_grounding_rules()</code> once per session. That suppresses repeated grounding payloads in later canonical responses and saves tokens.</p>
            </div>
            <div class="troubleshoot-card">
              <h4>Edition ID not found</h4>
              <p>Call <code>list_editions()</code> first to get exact selectors. Edition matching supports full IDs, short codes, language codes, and fuzzy matches, but exact IDs are safest.</p>
            </div>
          </div>
        </section>

        <!-- ══════════════════════════════════════════════════════════════
             NOTES
             ══════════════════════════════════════════════════════════════ -->
        <section class="section reveal" id="notes">
          <h2 class="section-heading">Notes <a href="#notes" class="anchor" aria-hidden="true">#</a></h2>
          <ul class="notes-list">
            <li><strong>Example convention</strong> Examples show the exact <code>structuredContent</code> payload shape for the checked-in fixture call. The repeated <code>grounding_rules</code> field is typically null because <code>fetch_grounding_rules()</code> was already called earlier in the session.</li>
            <li><strong>Required vs optional</strong> Required fields are marked directly in the parameter table. Nullable types such as <code>string | null</code> still accept null to skip or defer to defaults.</li>
            <li><strong>Display trimming</strong> Long string fields are shortened after 256 characters, and long lists of rich objects are shown as first item, ellipsis, last item, so the response examples stay readable without pretending to be the full payload.</li>
            <li><strong>Mushaf coupling</strong> <code>show_mushaf</code> is the human-facing tool. <code>fetch_mushaf</code> exposes the rendering payload that hosts use to power the same surface behind the scenes.</li>
            <li><strong>Production surface</strong> This page reflects the public server profile at <a href="https://mcp.quran.ai/" style="color:var(--link);text-decoration:none">mcp.quran.ai</a>. In-development tools are excluded from the public docs.</li>
          </ul>
        </section>

        <!-- ══════════════════════════════════════════════════════════════
             FOOTER
             ══════════════════════════════════════════════════════════════ -->
        <footer class="footer">
          <p>
            <a href="/">Quran MCP</a>
            <span>&middot;</span>
            <a href="/documentation">Documentation</a>
            <span>&middot;</span>
            <a href="/support">Support</a>
            <span>&middot;</span>
            <a href="/privacy">Privacy</a>
            <span>&middot;</span>
            <a href="https://quran.foundation">by quran.foundation</a>
          </p>
        </footer>
      </div>
    </main>
  </div>

{:else if error}
  <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:60vh;text-align:center;font-family:'JetBrains Mono',monospace;color:var(--muted)">
    <h1 style="font-size:1.2rem;margin-bottom:12px;color:var(--text)">Failed to load documentation</h1>
    <p>{error}</p>
    <p><a href="/docs" style="color:var(--green)">View static documentation</a></p>
  </div>
{:else}
  <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:60vh;text-align:center;font-family:'JetBrains Mono',monospace;color:var(--muted)">
    <p>Loading documentation...</p>
  </div>
{/if}
