<script lang="ts">
  import "./mushaf-theme.css";
  import { onMount } from "svelte";
  import {
    App,
    applyDocumentTheme,
    applyHostStyleVariables,
    applyHostFonts,
    type McpUiHostContext,
  } from "@modelcontextprotocol/ext-apps";
  import type { PageData } from "./lib/types";

  /** Minimal type for tool results — avoids importing from @modelcontextprotocol/sdk */
  type ToolResult = {
    structuredContent?: unknown;
    content?: Array<{ type: string; text?: string }>;
  };
  import MushafPage from "./lib/MushafPage.svelte";
  // TranslationPanel removed — replaced by ActionBar + ResultCard interaction model
  import Toolbar from "./lib/Toolbar.svelte";
  import DebugOverlay from "./lib/DebugOverlay.svelte";
  import {
    wordSelection,
    startDrag,
    extendDrag,
    endDrag,
    clearSelection,
    consumeClickDismissSuppression,
  } from "./lib/selection";
  import ActionBar, { type ActionId } from "./lib/ActionBar.svelte";
  import ResultCard from "./lib/ResultCard.svelte";
  import AskInput from "./lib/AskInput.svelte";

  // ─── QCF v2 Font Constants ─────────────────────────────
  const QCF_CDN = "https://verses.quran.foundation/fonts/quran/hafs/v2/woff2";

  // ─── State ──────────────────────────────────────────────
  let pipRequested = false;  // guard: only request PIP once on initial connect
  let app = $state<App | null>(null);
  let pageData = $state<PageData | null>(null);
  let hostContext = $state<McpUiHostContext | undefined>();
  let selectedVerseKey = $state<string | null>(null);
  let translationText = $state<string | null>(null);
  let translationFailed = $state(false);
  let translationLoading = $state(false);
  let loading = $state(true);
  let navigating = $state(false);
  let explaining = $state(false);
  let explainError = $state<string | null>(null);
  let error = $state<string | null>(null);
  let displayMode = $state<"inline" | "fullscreen" | "pip">("inline");
  let qcfFontFamily = $state<string | null>(null);

  // ─── Interaction toggle (from server config) ────────────
  let interactive = $derived(pageData?.interactive !== false);

  // ─── Word Selection (reactive subscription) ────────────
  let currentWordSelection = $state<import("./lib/selection").WordSelection | null>(null);
  wordSelection.subscribe((v) => { currentWordSelection = v; });

  // ─── Action Bar State ─────────────────────────────────
  let activeAction = $state<ActionId | null>(null);
  let actionResult = $state<{
    label: string;
    arabicText?: string;
    content: string;
    fallbackWord?: string;
  } | null>(null);
  let actionLoading = $state(false);
  let loadedFonts = $state(new Set<number>());
  let scrollEl = $state<HTMLDivElement | null>(null);
  let scrollPositions = new Map<number, number>();

  // ─── Debug Overlay ───────────────────────────────────────
  let debugMode = $state(false);
  let debugLastContext = $state<{ structuredContent?: unknown; contentBlockCount: number; tokenEstimate: number } | null>(null);
  let debugLastMessage = $state<{ role: string; text: string } | null>(null);

  // ─── Reference Data (populated once after connect, not reactive) ──
  type Edition = { edition_id: string; edition_type: string; lang: string; code: string; name: string; author: string | null };
  let quranEditions: Edition[] = [];
  let tafsirEditions: Edition[] = [];
  let translationEditions: Edition[] = [];

  // ─── Safe localStorage for page persistence ────────────
  const STORAGE_PAGE_KEY = "quran-mushaf-page";
  const STORAGE_TOOL_PAGE_KEY = "quran-mushaf-tool-page";

  function safeGetPage(): number | null {
    try {
      const v = localStorage.getItem(STORAGE_PAGE_KEY);
      if (v) { const n = parseInt(v, 10); if (n >= 1 && n <= 604) return n; }
    } catch { /* iframe sandbox — localStorage may be blocked */ }
    return null;
  }
  function safeSetPage(page: number) {
    try { localStorage.setItem(STORAGE_PAGE_KEY, String(page)); } catch { /* ignore */ }
  }
  /** Store the page from the initial show_mushaf tool result.
   *  Used to detect re-mount (e.g. ChatGPT re-delivers the same tool result
   *  after fullscreen exit, but the user has navigated to a different page). */
  function safeGetToolPage(): number | null {
    try {
      const v = localStorage.getItem(STORAGE_TOOL_PAGE_KEY);
      if (v) { const n = parseInt(v, 10); if (n >= 1 && n <= 604) return n; }
    } catch {}
    return null;
  }
  function safeSetToolPage(page: number) {
    try { localStorage.setItem(STORAGE_TOOL_PAGE_KEY, String(page)); } catch { /* ignore */ }
  }

  // ─── Client Detection (server-side, from HTTP headers + MCP handshake) ─
  import type { ClientHint } from "./lib/types";
  let clientHint = $state<ClientHint | null>(null);
  let isChatGPT = $derived(clientHint?.host === "chatgpt");
  let isMobile = $derived(clientHint?.platform === "mobile");

  // ─── Derived ────────────────────────────────────────────
  let availableModes = $derived(
    hostContext?.availableDisplayModes ?? []
  );
  let canPip = $derived(availableModes.includes("pip" as any));
  let canFullscreen = $derived(availableModes.includes("fullscreen"));
  let hasDisplayToggle = $derived(canPip || canFullscreen);

  /** Look up surah name for the selected verse */
  let selectedSurahName = $derived.by(() => {
    if (!selectedVerseKey || !pageData) return null;
    const [surahStr] = selectedVerseKey.split(":");
    return pageData.chapter_names?.[surahStr] ?? null;
  });

  // ─── Host Theming ───────────────────────────────────────
  $effect(() => {
    if (hostContext?.theme) applyDocumentTheme(hostContext.theme);
    if (hostContext?.styles?.variables) applyHostStyleVariables(hostContext.styles.variables);
    if (hostContext?.styles?.css?.fonts) applyHostFonts(hostContext.styles.css.fonts);
    if (hostContext?.safeAreaInsets) {
      const { top, right, bottom, left } = hostContext.safeAreaInsets;
      document.body.style.padding = `${top}px ${right}px ${bottom}px ${left}px`;
    }
    if (hostContext?.displayMode) {
      displayMode = hostContext.displayMode as "inline" | "fullscreen" | "pip";
    }
  });

  // ─── Dynamic classes on <html>: display mode
  $effect(() => {
    document.documentElement.classList.toggle("fullscreen-mode", displayMode === "fullscreen");
    document.documentElement.classList.toggle("pip-mode", displayMode === "pip");
  });

  // ─── Content-driven iframe height ─────────────────────
  // Measure actual content height and tell the host iframe exactly how tall
  // to be (content + 50px breathing room). Replaces the old min-height: 200vw
  // hack which grew excess bottom space proportionally with viewport width.
  function syncIframeHeight(el: HTMLElement) {
    // Sum the actual heights of children inside the scroll container,
    // not the container itself (which flex-expands to fill .main).
    let contentH = 0;
    for (const child of el.children) {
      contentH += (child as HTMLElement).offsetHeight;
    }
    // 8px for .main inset (4px top + 4px bottom), 50px breathing room
    const h = contentH + 8 + 50;
    document.documentElement.style.minHeight = h + "px";
  }

  // Re-sync when scrollEl mounts or pageData changes (page navigation).
  $effect(() => {
    const el = scrollEl;
    const _data = pageData; // track dependency — re-run on page change
    if (!el) return;
    // Immediate sync + deferred sync after DOM settles (font rendering, layout)
    syncIframeHeight(el);
    requestAnimationFrame(() => syncIframeHeight(el));
    const ro = new ResizeObserver(() => syncIframeHeight(el));
    ro.observe(el);
    return () => ro.disconnect();
  });

  // ─── App Lifecycle ──────────────────────────────────────
  onMount(async () => {
    const instance = new App({ name: "Mushaf App", version: "0.1.0" });

    // Flow 1: Receive initial page data from show_mushaf tool result
    instance.ontoolresult = (result: ToolResult) => {
      try {
        const data = result.structuredContent as unknown as PageData;
        if (!data?.lines) {
          error = "No page data received";
          loading = false;
          return;
        }

        // Re-mount detection: ChatGPT re-delivers the original tool result
        // when the iframe re-mounts (e.g. after fullscreen exit). If the user
        // navigated to a different page, skip the stale tool result and let
        // the fallback timeout restore from localStorage.
        const savedToolPage = safeGetToolPage();
        const currentPage = safeGetPage();
        if (
          savedToolPage === data.page_number &&
          currentPage && currentPage !== data.page_number &&
          !data.initial_selected_verse
        ) {
          console.debug(`[mushaf] Re-mount detected — ignoring stale tool result (page ${data.page_number}), will restore page ${currentPage}`);
          return; // Don't set pageData — fallback timeout will fetch saved page
        }

        safeSetToolPage(data.page_number);
        if (data.client_hint) clientHint = data.client_hint;
        pageData = data;
        loading = false;
        error = null;
        selectedVerseKey = null;
        translationText = null;
        safeSetPage(data.page_number);
        sendContext(data);

        // Auto-select verse if show_mushaf was called with surah+ayah
        if (data.initial_selected_verse) {
          handleVerseSelect(data.initial_selected_verse);
          // Scroll the selected verse into the center of the visible area
          requestAnimationFrame(() => {
            const el = document.querySelector(".quran-word.ayah-highlight");
            if (el) el.scrollIntoView({ block: "center", behavior: "instant" });
          });
        }
      } catch (e) {
        error = `Failed to render: ${(e as Error).message}`;
        loading = false;
      }
    };

    instance.onhostcontextchanged = (ctx) => {
      hostContext = { ...hostContext, ...ctx };
    };

    instance.onteardown = async () => ({ state: {} });

    await instance.connect();
    app = instance;
    hostContext = instance.getHostContext();

    // Default to PIP mode on hosts that support it (e.g., ChatGPT desktop).
    // ChatGPT mobile may not list PIP in availableDisplayModes — try anyway.
    console.debug("[mushaf] Available display modes:", hostContext?.availableDisplayModes);
    if (!pipRequested) {
      pipRequested = true;
      const hasPip = hostContext?.availableDisplayModes?.includes("pip" as any);
      if (hasPip) {
        try {
          const result = await instance.requestDisplayMode({ mode: "pip" });
          displayMode = result.mode as "inline" | "fullscreen" | "pip";
          console.debug("[mushaf] PIP mode activated:", result.mode);
        } catch (e) {
          console.debug("[mushaf] PIP request failed, staying inline:", e);
        }
      } else {
        console.debug("[mushaf] PIP not in availableDisplayModes — skipping auto-PIP");
      }
    }

    // Populate reference data (fire-and-forget, non-blocking)
    loadEditions(instance);

    // Fallback: ChatGPT's ext-apps bridge may not deliver ontoolresult
    // for the initial show_mushaf call. If page data hasn't arrived after
    // a short grace period, restore last page from localStorage or default to page 1.
    setTimeout(async () => {
      if (!pageData) {
        const fallbackPage = safeGetPage() ?? 1;
        console.debug(`[mushaf] ontoolresult did not fire — fetching page ${fallbackPage} as fallback`);
        try {
          const result = await instance.callServerTool({
            name: "fetch_mushaf",
            arguments: { page: fallbackPage },
          }) as ToolResult;
          const data = result.structuredContent as unknown as PageData;
          if (data?.lines && !pageData) {
            if (data.client_hint) clientHint = data.client_hint;
            pageData = data;
            loading = false;
            error = null;
            sendContext(data);
          }
        } catch (e) {
          if (!pageData) {
            error = `Failed to load page: ${(e as Error).message}`;
            loading = false;
          }
        }
      }
    }, 500);

    // Debug overlay: enable via ?debug=1 URL param
    if (new URLSearchParams(window.location.search).has("debug")) {
      debugMode = true;
    }

    // Debug overlay: toggle via Ctrl+Shift+D
    window.addEventListener("keydown", (e) => {
      if (e.ctrlKey && e.shiftKey && e.key === "D") {
        debugMode = !debugMode;
        e.preventDefault();
      }
    });
  });

  /** Fetch edition catalogs once after connect. Non-blocking — handlers
   *  degrade gracefully if editions haven't loaded yet.
   *  Uses batch list_editions (Spec 0041) to fetch all 3 types in 1 call. */
  async function loadEditions(instance: App) {
    try {
      const result = await instance.callServerTool({
        name: "list_editions",
        arguments: { edition_type: ["quran", "tafsir", "translation"], lang: "en" },
      });
      const allEditions = parseEditions(result);
      quranEditions = allEditions.filter((e: Edition) => e.edition_type === "quran");
      tafsirEditions = allEditions.filter((e: Edition) => e.edition_type === "tafsir");
      translationEditions = allEditions.filter((e: Edition) => e.edition_type === "translation");
    } catch (e) {
      console.warn("[mushaf] loadEditions failed (hardcoded defaults active):", e);
    }
  }

  function parseEditions(result: ToolResult): Edition[] {
    const block = result.content?.find(
      (c): c is { type: "text"; text: string } => c.type === "text"
    );
    if (!block?.text) return [];
    try {
      const parsed = JSON.parse(block.text);
      return parsed?.editions ?? [];
    } catch (e) {
      console.warn("[mushaf] parseEditions failed:", e);
      return [];
    }
  }

  // ─── QCF v2 Font Loading ────────────────────────────────
  async function loadQcfFont(pageNum: number) {
    const familyName = `p${pageNum}-v2`;
    if (loadedFonts.has(pageNum)) {
      qcfFontFamily = familyName;
      return;
    }
    // Reset while loading — UI shows Unicode fallback
    qcfFontFamily = null;
    try {
      const font = new FontFace(
        familyName,
        `url(${QCF_CDN}/p${pageNum}.woff2) format("woff2")`,
        { display: "block" },
      );
      document.fonts.add(font);
      await font.load();
      loadedFonts = new Set([...loadedFonts, pageNum]);
      // Guard: page may have changed while font was loading
      if (pageData?.page_number === pageNum) {
        qcfFontFamily = familyName;
      }
    } catch (e) {
      console.warn(`[mushaf] QCF font load failed for page ${pageNum}:`, e);
      // CDN unreachable or CSP blocked — stay on Unicode fallback
    }
  }

  // Load font whenever page data changes
  $effect(() => {
    if (pageData?.page_number) {
      loadQcfFont(pageData.page_number);
    }
  });

  // ─── Logging Wrappers ──────────────────────────────────
  async function loggedUpdateModelContext(payload: {
    structuredContent?: Record<string, unknown>;
    content?: Array<{ type: string; text?: string }>;
  }) {
    // Estimate tokens: chars/4 is a rough approximation
    const contentChars = (payload.content ?? []).reduce((sum, b) => sum + (b.text?.length ?? 0), 0);
    const structuredChars = payload.structuredContent ? JSON.stringify(payload.structuredContent).length : 0;
    const tokenEstimate = Math.ceil((contentChars + structuredChars) / 4);

    // Track for debug overlay
    debugLastContext = {
      structuredContent: payload.structuredContent,
      contentBlockCount: payload.content?.length ?? 0,
      tokenEstimate,
    };

    if (tokenEstimate > 3500) {
      console.warn(`[mushaf] updateModelContext: ~${tokenEstimate} tokens — approaching 4000 limit!`);
    }

    try {
      await app?.updateModelContext(payload);
    } catch (e) {
      console.warn("[mushaf] updateModelContext not supported by host:", e);
    }
    try {
      // Privacy: log shape only, not raw canonical text
      await app?.sendLog?.({
        level: "debug",
        message: `updateModelContext: ~${tokenEstimate} tokens, ${JSON.stringify({
          structuredContent: payload.structuredContent,
          contentBlockCount: payload.content?.length ?? 0,
          contentTypes: payload.content?.map(b => b.type) ?? [],
        })}`,
      });
    } catch (e) {
      console.debug("[mushaf] sendLog unavailable:", e);
    }
  }

  async function loggedSendMessage(message: {
    role: string;
    content: Array<{ type: string; text?: string }>;
  }) {
    // Track for debug overlay
    debugLastMessage = {
      role: message.role,
      text: message.content?.[0]?.text?.slice(0, 200) ?? "",
    };

    try {
      await app?.sendMessage(message);
    } catch (e) {
      console.warn("[mushaf] sendMessage not supported by host:", e);
    }
    try {
      await app?.sendLog?.({
        level: "debug",
        message: `sendMessage: role=${message.role}, blocks=${message.content?.length ?? 0}`,
      });
    } catch (e) {
      console.debug("[mushaf] sendLog unavailable:", e);
    }
  }

  /** Wrap callServerTool with console.log for tool calls and results. */
  async function loggedCallServerTool(call: { name: string; arguments: Record<string, unknown> }): Promise<ToolResult> {
    console.log("[mushaf] tool call:", call.name, call.arguments);
    const result = await app!.callServerTool(call);
    console.log("[mushaf] tool result:", call.name, result);
    return result;
  }

  // ─── Host Context Sync ──────────────────────────────────
  async function sendContext(
    data: PageData,
    verse?: string,
    canonical?: { arabic?: string | null; translation?: string | null },
  ) {
    if (!app) return;

    const verses = data.verses ?? [];
    const firstKey = verses[0]?.verse_key ?? "?";
    const lastKey = verses[verses.length - 1]?.verse_key ?? "?";
    const surahs = Object.values(data.chapter_names ?? {});

    // Build content block: metadata (duplicated from structuredContent as text,
    // in case host ignores structuredContent) + any canonical data we have.
    const content: Array<{ type: "text"; text: string }> = [];
    if (verse && (canonical?.arabic || canonical?.translation)) {
      const parts: string[] = [
        `Page ${data.page_number} of ${data.total_pages}`,
        `Surahs: ${surahs.join(", ")}`,
        `Verse range: ${firstKey}–${lastKey}`,
        `Selected ayah: ${verse}`,
      ];
      if (canonical.arabic) {
        parts.push("", "## Arabic Ayah Text", canonical.arabic);
      }
      if (canonical.translation) {
        const edName = getEditionName(getTranslationEditionId());
        parts.push("", `## Translation (${edName})`, canonical.translation);
      }
      content.push({ type: "text", text: parts.join("\n") });
    }

    await loggedUpdateModelContext({
      structuredContent: {
        context_kind: "metadata",
        page_number: data.page_number,
        total_pages: data.total_pages,
        surahs,
        visible_verse_range: `${firstKey}-${lastKey}`,
        selected_verse: verse ?? null,
        mushaf_edition_id: "qpc_uthmani",
      },
      content, // Empty on page load/nav, populated on verse select after fetches
    });
  }

  // ─── Edition helpers ────────────────────────────────────
  const QURAN_EDITION_FALLBACK = "ar-simple-clean";
  const EXPLAIN_TAFSIR_EDITION_FALLBACK = "en-ibn-kathir";
  const TRANSLATION_EDITION_FALLBACK = "en-abdel-haleem";

  function getQuranEditionId(): string {
    // Prefer ar-simple-clean (has full tashkil/diacritics); fallback if not in catalog
    const preferred = quranEditions.find(e => e.edition_id === QURAN_EDITION_FALLBACK);
    return preferred?.edition_id ?? QURAN_EDITION_FALLBACK;
  }

  function getExplainTafsirEditionIds(): string[] {
    const preferred = tafsirEditions.find(
      (e) => e.edition_id === EXPLAIN_TAFSIR_EDITION_FALLBACK
    );
    if (preferred) return [preferred.edition_id];
    if (tafsirEditions.length > 0) return [tafsirEditions[0].edition_id];
    return [EXPLAIN_TAFSIR_EDITION_FALLBACK];
  }

  function getTranslationEditionId(): string {
    // Prefer the configured fallback (en-sahih-international) from the loaded catalog;
    // mirrors getQuranEditionId pattern. Only falls back to [0] if preferred not found.
    const preferred = translationEditions.find(e => e.edition_id === TRANSLATION_EDITION_FALLBACK);
    if (preferred) return preferred.edition_id;
    return translationEditions.length > 0
      ? translationEditions[0].edition_id
      : TRANSLATION_EDITION_FALLBACK;
  }

  /** Look up display name for an edition ID across all loaded edition types. */
  function getEditionName(editionId: string): string {
    const all = [...quranEditions, ...translationEditions, ...tafsirEditions];
    const ed = all.find(e => e.edition_id === editionId);
    return ed?.name ?? editionId;
  }

  // ─── Prefetch caches + promise tracking ────────────────
  const MAX_CACHE_ENTRIES = 50;
  let arabicTextCache = $state<Record<string, string>>({});

  /** Insert into cache with size-capped eviction (oldest-first). */
  function cacheSet(cache: Record<string, string>, key: string, value: string) {
    const keys = Object.keys(cache);
    if (keys.length >= MAX_CACHE_ENTRIES) {
      delete cache[keys[0]];
    }
    cache[key] = value;
  }

  // Track in-flight arabic prefetch so handleExplain can wait if needed
  let arabicPrefetchPromise: Promise<void> | null = null;
  let arabicPrefetchSettled = false;

  // ─── Word-level selection handlers ─────────────────────
  function handleWordDown(surah: number, ayah: number, verseKey: string, wordPosition: number) {
    startDrag(surah, ayah, verseKey, wordPosition);
  }

  function handleWordEnter(verseKey: string, wordPosition: number) {
    extendDrag(verseKey, wordPosition);
  }

  // ─── Overlay Positioning ────────────────────────────────
  let overlayTop = $state(0);
  let overlayLeft = $state(0);
  let overlayPosition = $state<"above" | "below">("above");
  let mainEl = $state<HTMLElement | null>(null);
  let overlayEl = $state<HTMLElement | null>(null);

  /** Measure selected words and position the overlay.
   *  Caret centers above/below the FIRST selected word.
   *  Above/below decision based on available space using actual overlay height. */
  function updateOverlayPosition() {
    if (!mainEl || !currentWordSelection) return;
    const selected = mainEl.querySelectorAll(".word-selected");
    if (selected.length === 0) return;

    const mainRect = mainEl.getBoundingClientRect();

    // Find bounding rect of ALL selected words (for vertical positioning)
    let minTop = Infinity;
    let maxBottom = -Infinity;
    for (const el of selected) {
      const r = el.getBoundingClientRect();
      minTop = Math.min(minTop, r.top - mainRect.top);
      maxBottom = Math.max(maxBottom, r.bottom - mainRect.top);
    }

    // Center horizontally on the FIRST selected word
    const firstWord = selected[0];
    const firstRect = firstWord.getBoundingClientRect();
    overlayLeft = firstRect.left - mainRect.left + firstRect.width / 2;

    // Use actual overlay height if available, else estimate.
    // Add headroom for the ResultCard that may appear opposite the ActionBar
    // (it renders on the far side of the caret from the selection).
    const actualHeight = overlayEl?.getBoundingClientRect().height ?? 80;
    const resultCardAllowance = 100; // room for ResultCard above ActionBar
    const spaceAbove = minTop;
    const spaceBelow = mainRect.height - maxBottom;

    if (spaceAbove > actualHeight + resultCardAllowance + 16) {
      overlayPosition = "above";
      overlayTop = minTop;
    } else {
      overlayPosition = "below";
      overlayTop = maxBottom;
    }
  }

  // Re-measure when selection changes
  $effect(() => {
    if (currentWordSelection) {
      requestAnimationFrame(() => updateOverlayPosition());
    }
  });

  /** Dismiss selection when clicking outside interactive elements. */
  function handleDismiss(e: MouseEvent) {
    // After a real drag, the browser fires a synthetic click on the common
    // ancestor of pointerdown/pointerup targets. That click isn't on a
    // .quran-word, so it would incorrectly clear the selection. The one-shot
    // flag from endDrag suppresses exactly that one dismiss.
    if (consumeClickDismissSuppression()) return;
    const target = e.target as HTMLElement;
    if (target.closest(".quran-word, .action-bar, .result-card, .ask-input-row, .interaction-float")) return;
    clearSelection();
    selectedVerseKey = null;
    translationText = null;
    activeAction = null;
    actionResult = null;
  }

  // ─── Action Bar Handlers ──────────────────────────────
  async function handleAction(id: ActionId) {
    if (!currentWordSelection || !app) return;
    // Toggle off if clicking the already-active action
    if (activeAction === id) {
      activeAction = null;
      actionResult = null;
      return;
    }
    activeAction = id;
    actionResult = null;

    const sel = currentWordSelection;
    const selectedWords = [...sel.words].sort((a, b) => a - b);
    const isPhrase = selectedWords.length > 1;
    const firstWordPos = selectedWords[0];

    switch (id) {
      case "ask":
        // AskInput handles submission
        break;

      case "analyze": {
        actionLoading = true;
        try {
          const result = await app.callServerTool({
            name: "fetch_word_morphology",
            arguments: { surah: sel.surah, ayah: sel.ayah, word_position: firstWordPos },
          }) as { content?: Array<{ type: string; text?: string }> };
          const text = result.content?.find((c) => c.type === "text")?.text ?? "No data";
          actionResult = {
            label: "Analysis",
            content: text,
            fallbackWord: isPhrase ? `word ${firstWordPos}` : undefined,
          };
        } catch (e) {
          actionResult = { label: "Analysis", content: `Error: ${(e as Error).message}` };
        }
        actionLoading = false;
        break;
      }

      case "translate":
        actionResult = {
          label: "Translation",
          content: "Phrase translation coming soon",
        };
        break;

      case "similar": {
        actionLoading = true;
        try {
          const result = await app.callServerTool({
            name: "fetch_word_concordance",
            arguments: { surah: sel.surah, ayah: sel.ayah, word_position: firstWordPos },
          }) as { content?: Array<{ type: string; text?: string }> };
          const text = result.content?.find((c) => c.type === "text")?.text ?? "No data";
          actionResult = {
            label: "Concordance",
            content: text,
            fallbackWord: isPhrase ? `word ${firstWordPos}` : undefined,
          };
        } catch (e) {
          actionResult = { label: "Concordance", content: `Error: ${(e as Error).message}` };
        }
        actionLoading = false;
        break;
      }

      case "listen":
        break;
    }
  }

  async function handleAskSubmit(question: string) {
    if (!currentWordSelection || !app || !pageData) return;
    const sel = currentWordSelection;

    const phraseWords: string[] = [];
    const vl = Object.fromEntries(
      pageData.verses.map((v) => [v.verse_id, v.verse_key])
    ) as Record<number, string>;
    for (const line of pageData.lines) {
      for (const word of line.words) {
        if (
          word.char_type_name === "word" &&
          vl[word.verse_id] === sel.verseKey &&
          sel.words.has(word.position_in_verse)
        ) {
          phraseWords.push(word.text);
        }
      }
    }
    const phraseText = phraseWords.join(" ");

    const cachedArabic = arabicTextCache[sel.verseKey] ?? null;
    const cachedTranslation = selectedVerseKey === sel.verseKey ? translationText : null;
    await sendContext(pageData, sel.verseKey, {
      arabic: cachedArabic,
      translation: cachedTranslation,
    });

    const message = [
      `The user is reading the mushaf and selected the phrase "${phraseText}" from verse ${sel.verseKey}.`,
      `Their question: ${question}`,
      "",
      `After responding, call show_mushaf(surah=${sel.surah}, ayah=${sel.ayah}) to return the user to their mushaf reading position.`,
    ].join("\n");

    try {
      await app.sendMessage({ content: [{ type: "text", text: message }] });
    } catch (e) {
      console.warn("[mushaf] sendMessage failed:", e);
    }

    clearSelection();
    activeAction = null;
    actionResult = null;
  }

  // Clear action state when selection clears
  $effect(() => {
    if (!currentWordSelection) {
      activeAction = null;
      actionResult = null;
    }
  });

  // ─── Flow 2: Verse Selection → Translation + Quran Pre-fetch
  async function handleVerseSelect(verseKey: string) {
    selectedVerseKey = verseKey;

    // When word selection is active, just set the verse key for context
    // without triggering translation fetches (the action bar handles interaction)
    if (currentWordSelection) {
      if (pageData) sendContext(pageData, verseKey);
      return;
    }

    translationLoading = true;
    translationText = null;
    translationFailed = false;
    explainError = null;

    if (pageData) sendContext(pageData, verseKey);
    if (!app) return;

    // Fetch Arabic text and translation in parallel
    const translationPromise = loggedCallServerTool({
      name: "fetch_translation",
      arguments: { ayahs: verseKey, editions: [getTranslationEditionId()] },
    });

    // Fetch Arabic text with tashkil (for context injection + copy support)
    if (!arabicTextCache[verseKey]) {
      arabicPrefetchSettled = false;
      arabicPrefetchPromise = loggedCallServerTool({
        name: "fetch_quran",
        arguments: { ayahs: verseKey, editions: [getQuranEditionId()] },
      }).then((result) => {
        if (selectedVerseKey !== verseKey) return;
        const block = result.content?.find(
          (c): c is { type: "text"; text: string } => c.type === "text"
        );
        if (block?.text) {
          try {
            const parsed = JSON.parse(block.text);
            const editions = Object.values(parsed?.results ?? {}) as Array<Array<{ ayah: string; text: string }>>;
            const allTexts = editions.flat().map((e) => e.text);
            const arabicText = allTexts.join(" ");
            if (arabicText) cacheSet(arabicTextCache, verseKey, arabicText);
          } catch (e) {
            console.warn("[mushaf] Arabic text JSON parse failed, using raw text:", e);
            cacheSet(arabicTextCache, verseKey, block.text);
          }
        }
      }).catch((e) => { console.warn("[mushaf] fetch_quran failed:", e); })
        .finally(() => { arabicPrefetchSettled = true; });
    }

    try {
      const result = await translationPromise;
      // Guard against stale response from rapid tapping
      if (selectedVerseKey !== verseKey) return;
      translationText = extractTranslationText(result);
    } catch (e) {
      console.warn("[mushaf] fetch_translation failed:", e);
      if (selectedVerseKey !== verseKey) return;
      translationText = "Translation unavailable";
      translationFailed = true;
    } finally {
      if (selectedVerseKey === verseKey) {
        translationLoading = false;
        // Re-send context with whatever canonical data we now have
        if (pageData) {
          sendContext(pageData, verseKey, {
            arabic: arabicTextCache[verseKey] ?? null,
            translation: translationFailed ? null : translationText,
          });
        }
      }
    }
  }

  /** Strip HTML tags and decode common entities from quran.com text. */
  function stripHtml(html: string): string {
    return html
      .replace(/<[^>]*>/g, "")
      .replace(/&amp;/g, "&")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'")
      .replace(/&nbsp;/g, " ")
      .trim();
  }

  /** Parse the structured JSON response from fetch_translation into clean text. */
  function extractTranslationText(result: ToolResult): string | null {
    const textBlock = result.content?.find(
      (c): c is { type: "text"; text: string } => c.type === "text"
    );
    if (!textBlock?.text) return null;

    try {
      const parsed = JSON.parse(textBlock.text);
      if (parsed?.results) {
        const lines: string[] = [];
        for (const [, entries] of Object.entries(parsed.results)) {
          for (const entry of entries as Array<{ ayah: string; text: string }>) {
            if (entry.text) lines.push(stripHtml(entry.text));
          }
        }
        return lines.join("\n\n") || null;
      }
    } catch (e) {
      console.warn("[mushaf] extractTranslationText JSON parse failed, using raw text:", e);
    }
    return stripHtml(textBlock.text);
  }

  /** Look up display name for a tafsir edition ID. Falls back to the raw ID. */
  function getTafsirEditionName(editionId: string): string {
    const ed = tafsirEditions.find(e => e.edition_id === editionId);
    return ed?.name ?? editionId;
  }

  /** Parse fetch_tafsir JSON into per-edition sections with proper headers. */
  function extractTafsirText(result: ToolResult): string | null {
    const textBlock = result.content?.find(
      (c): c is { type: "text"; text: string } => c.type === "text"
    );
    if (!textBlock?.text) return null;

    try {
      const parsed = JSON.parse(textBlock.text);
      if (parsed?.results) {
        const sections: string[] = [];
        for (const [editionId, entries] of Object.entries(parsed.results)) {
          const name = getTafsirEditionName(editionId);
          for (const entry of entries as Array<{ ayah: string; text: string }>) {
            if (entry.text) {
              sections.push(`### ${name} (${editionId}), ayah ${entry.ayah}\n\n${stripHtml(entry.text)}`);
            }
          }
        }
        return sections.join("\n\n") || null;
      }
    } catch (e) {
      console.warn("[mushaf] extractTafsirText JSON parse failed, using raw text:", e);
    }
    return stripHtml(textBlock.text);
  }

  // ─── Canonical Content Builder (unified frontmatter) ───
  /**
   * Build ContentBlock[] for canonical data injection.
   *
   * Block 1: Single YAML frontmatter listing all editions, then markdown
   *          sections with # headers for each data type.
   * Block 2: Prompt/instructions with # section headers.
   *
   * Uses one frontmatter per document (the standard), not stacked frontmatters.
   */
  function buildCanonicalContent(
    verseKey: string,
    arabic: string | null,
    translation: string | null,
    tafsir: string | null,
    tafsirEditionIds: string[] = [],
  ): Array<{ type: "text"; text: string }> {
    const blocks: Array<{ type: "text"; text: string }> = [];

    const hasAnyCanonical = arabic || translation || tafsir;
    if (hasAnyCanonical) {
      const quranEdId = getQuranEditionId();
      const transEdId = getTranslationEditionId();

      const fmLines = [
        "---",
        "source: mushaf-app",
        `ayahs: "${verseKey}"`,
      ];
      if (arabic)      fmLines.push(`quran_edition: ${quranEdId}`);
      if (translation)  fmLines.push(`translation_edition: ${transEdId}`);
      if (tafsir && tafsirEditionIds.length > 0) {
        fmLines.push(`tafsir_editions: ${tafsirEditionIds.join(", ")}`);
      }
      fmLines.push("---");

      const bodyParts: string[] = ["# CANONICAL TEXT"];

      if (arabic) {
        const quranName = getEditionName(quranEdId);
        bodyParts.push(
          "",
          `## Arabic Ayah Text`,
          `### ${quranName} (${quranEdId}), ayah ${verseKey}`,
          "",
          arabic,
        );
      }

      if (translation) {
        const transName = getEditionName(transEdId);
        bodyParts.push(
          "",
          `## Translation`,
          `### ${transName} (${transEdId}), ayah ${verseKey}`,
          "",
          translation,
        );
      }

      if (tafsir) {
        bodyParts.push("", `## Tafsir`, "", tafsir);
      }

      blocks.push({
        type: "text",
        text: fmLines.join("\n") + "\n\n" + bodyParts.join("\n"),
      });
    }

    return blocks;
  }

  // ─── Flow 3: Explain ──────────────────────────────────
  async function handleExplain(verseKey: string, focusText: string) {
    if (!app || explaining) return;
    explaining = true;
    explainError = null;

    try {
      // Wait for arabic prefetch if still in-flight
      if (!arabicTextCache[verseKey] && !arabicPrefetchSettled && arabicPrefetchPromise) {
        await arabicPrefetchPromise;
      }

      const arabic = arabicTextCache[verseKey] ?? null;
      const translation = translationFailed ? null : translationText;
      const tafsirEditionIds = getExplainTafsirEditionIds();
      const tafsirResult = await loggedCallServerTool({
        name: "fetch_tafsir",
        arguments: { ayahs: verseKey, editions: tafsirEditionIds },
      });
      const tafsir = extractTafsirText(tafsirResult);
      const content = buildCanonicalContent(
        verseKey,
        arabic,
        translation,
        tafsir,
        tafsirEditionIds,
      );

      await loggedUpdateModelContext({
        structuredContent: {
          context_kind: "explain",
          selected_verse: verseKey,
          page_number: pageData?.page_number,
        },
        content,
      });

      const focus = focusText.trim();
      const prompt = focus
        ? `[${verseKey}] ${focus}`
        : `[${verseKey}] Explain this ayah.`;

      await loggedSendMessage({
        role: "user",
        content: [{ type: "text", text: prompt }],
      });
    } catch (e) {
      console.warn("Explain failed:", e);
      explainError = "Failed to load explanation. Please try again.";
    } finally {
      explaining = false;
    }
  }

  // ─── Scroll Position Memory ────────────────────────────
  function saveScrollPosition() {
    if (scrollEl && pageData) {
      scrollPositions.set(pageData.page_number, scrollEl.scrollTop);
    }
  }

  function restoreScrollPosition(page: number) {
    // Defer to next tick so DOM has rendered the new page
    requestAnimationFrame(() => {
      if (!scrollEl) return;
      const saved = scrollPositions.get(page);
      scrollEl.scrollTop = saved ?? 0;
    });
  }

  // ─── Flow 4: Page Navigation ───────────────────────────
  async function handleNavigate(page: number) {
    if (!app) return;
    saveScrollPosition();
    navigating = true;
    clearSelection();
    activeAction = null;
    actionResult = null;
    try {
      const result = await loggedCallServerTool({
        name: "fetch_mushaf",
        arguments: { page },
      });
      const data = result.structuredContent as unknown as PageData;
      if (!data?.lines) throw new Error("Invalid page data");
      if (data.client_hint) clientHint = data.client_hint;
      pageData = data;
      error = null;
      selectedVerseKey = null;
      translationText = null;
      safeSetPage(page);
      sendContext(data);
      restoreScrollPosition(page);
    } catch (e) {
      error = `Navigation failed: ${(e as Error).message}`;
    } finally {
      navigating = false;
    }
  }

  // ─── UI Handlers ────────────────────────────────────────
  function handleClosePanel() {
    selectedVerseKey = null;
    translationText = null;
    if (pageData) sendContext(pageData);
  }

  /** Cycle display modes:
   *  - If host supports PiP (ChatGPT): pip → inline → fullscreen → pip
   *  - If host only supports fullscreen (Claude): inline → fullscreen → inline */
  async function cycleDisplayMode() {
    if (!app) return;
    let nextMode: "inline" | "fullscreen" | "pip";
    if (canPip) {
      // ChatGPT cycle: pip → inline → fullscreen → pip
      if (displayMode === "pip") nextMode = "inline";
      else if (displayMode === "inline") nextMode = "fullscreen";
      else nextMode = "pip";
    } else {
      // Claude cycle: inline → fullscreen → inline
      nextMode = displayMode === "fullscreen" ? "inline" : "fullscreen";
    }
    try {
      const result = await app.requestDisplayMode({ mode: nextMode });
      displayMode = result.mode as "inline" | "fullscreen" | "pip";
    } catch (e) {
      console.warn("[mushaf] requestDisplayMode not supported by host:", e);
    }
  }

  /** Display mode icon: indicates next mode in cycle */
  let displayModeIcon = $derived(
    displayMode === "fullscreen" ? "\u2715" :     // ✕ → back to pip (or inline)
    displayMode === "pip" ? "\u25F0" :             // ◰ → expand to inline
    "\u26F6"                                       // ⛶ → go fullscreen
  );
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<svelte:window onpointerup={() => { if (interactive) endDrag(); }} />
<main class="main" class:fullscreen={displayMode === "fullscreen"} class:panel-open={!!selectedVerseKey} bind:this={mainEl} onclick={interactive ? handleDismiss : undefined}>
  {#if hasDisplayToggle}
    <button
      class="display-mode-btn"
      class:left-position={isChatGPT && isMobile && displayMode === "fullscreen"}
      onclick={cycleDisplayMode}
      title="Toggle display mode"
    >
      {displayModeIcon}
    </button>
  {/if}
  {#if interactive && currentWordSelection}
    <!-- Word-level interaction: floating action bar near selection.
         DOM order swaps based on position so result card is always
         on the opposite side of the caret from the selection. -->
    <div
      bind:this={overlayEl}
      class="interaction-float"
      class:above={overlayPosition === "above"}
      class:below={overlayPosition === "below"}
      style="top: {overlayTop}px; left: {overlayLeft}px;"
    >
      {#if overlayPosition === "above"}
        <!-- Above: result card first (furthest from selection), then action bar -->
        {#if activeAction === "ask"}
          <AskInput onsubmit={handleAskSubmit} />
        {:else if actionLoading}
          <div class="action-loading">Loading...</div>
        {:else if actionResult}
          <ResultCard
            label={actionResult.label}
            arabicText={actionResult.arabicText}
            content={actionResult.content}
            fallbackWord={actionResult.fallbackWord}
          />
        {/if}
        <ActionBar {activeAction} position="above" onaction={handleAction} />
      {:else}
        <!-- Below: action bar first (closest to selection), then result card -->
        <ActionBar {activeAction} position="below" onaction={handleAction} />
        {#if activeAction === "ask"}
          <AskInput onsubmit={handleAskSubmit} />
        {:else if actionLoading}
          <div class="action-loading">Loading...</div>
        {:else if actionResult}
          <ResultCard
            label={actionResult.label}
            arabicText={actionResult.arabicText}
            content={actionResult.content}
            fallbackWord={actionResult.fallbackWord}
          />
        {/if}
      {/if}
    </div>
  {/if}
  <div class="scroll-inner" bind:this={scrollEl} onscroll={() => currentWordSelection && updateOverlayPosition()}>
    {#if loading}
      <div class="loading">Mushaf App loading...</div>
    {:else if error}
      <div class="error">{error}</div>
    {:else if pageData}
      <MushafPage
        data={pageData}
        {interactive}
        {selectedVerseKey}
        wordSelection={currentWordSelection}
        {qcfFontFamily}
        onverseselect={handleVerseSelect}
        onworddown={handleWordDown}
        onwordenter={handleWordEnter}
      />
    {/if}
  </div>
  {#if pageData}
    <Toolbar
      pageNumber={pageData.page_number}
      totalPages={pageData.total_pages}
      loading={navigating}
      onnavigate={handleNavigate}
    />
  {/if}
  {#if debugMode}
    <DebugOverlay
      lastContext={debugLastContext}
      lastMessage={debugLastMessage}
      cacheStats={{ arabic: Object.keys(arabicTextCache).length, maxEntries: MAX_CACHE_ENTRIES }}
    />
  {/if}
</main>

<style>
  @font-face {
    font-family: "Amiri Quran";
    src: url("./assets/AmiriQuran.woff2") format("woff2");
    font-weight: normal;
    font-style: normal;
    font-display: swap;
  }
  @font-face {
    font-family: "surahnames";
    src: url("https://verses.quran.foundation/fonts/quran/surah-names/v1/sura_names.woff2") format("woff2");
    font-weight: normal;
    font-style: normal;
    font-display: swap;
  }
  :global(*) {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }
  /* Navy mushaf theme — always dark.
     Palette tokens defined in mushaf-theme.css (--m-* prefix).
     Legacy aliases kept for components not yet migrated. */
  :global(:root) {
    color-scheme: dark;
    --color-background-primary: var(--m-surface-1);
    --color-background-secondary: var(--m-surface-2);
    --color-background-tertiary: var(--m-surface-3);
    --color-text-primary: var(--m-text-1);
    --color-text-secondary: var(--m-text-2);
    --color-text-tertiary: var(--m-text-3);
    --color-border-primary: var(--m-border);
    --color-success-medium: var(--m-green);
  }
  :global(html) {
    /* min-height is set dynamically by ResizeObserver (content + 50px) */
  }
  :global(html.panel-open) {
    /* min-height is set dynamically by ResizeObserver (content + 50px) */
  }
  /* In PIP/fullscreen the outer document should not scroll — only .scroll-inner scrolls */
  :global(html.pip-mode),
  :global(html.fullscreen-mode) {
    overflow: hidden;
  }
  /* Mobile: min-height handled by ResizeObserver, no media-query overrides needed */
  :global(body) {
    font-family: var(--font-sans, system-ui, -apple-system, sans-serif);
    background: transparent;
    color: var(--color-text-primary);
    margin: 0;
    min-height: inherit;
  }
  /* Outer shell: fills iframe viewport, clips to rounded corners.
     position:fixed inside an iframe is relative to the iframe viewport,
     so inset:0 fills exactly the space the host gives us. */
  .main {
    position: fixed;
    top: 4px;
    right: 4px;
    bottom: 4px;
    left: 4px;
    border-radius: 1.25rem;
    overflow: hidden;
    isolation: isolate;
    background: var(--m-surface-1);
    border: 0.25rem solid rgb(50 50 50 / 25%);
    box-shadow: 0 2px 16px var(--m-shadow);
    color: var(--m-text-1);
    display: flex;
    flex-direction: column;
  }
  .main.fullscreen {
    border-radius: 0;
  }
  /* Fullscreen: extra bottom padding so last line scrolls above host overlay */
  .main.fullscreen .scroll-inner {
    padding-bottom: 40vh;
  }
  /* Floating display-mode toggle — top-right corner */
  .display-mode-btn {
    position: absolute;
    top: .5rem;
    right: .5rem;
    z-index: 10;
    width: 2rem;
    height: 2rem;
    border: none;
    border-radius: 3px 15px 3px 3px;
    background: #3d558938;
    color: #b1dee06b;
    font-size: 1rem;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background .15s;
    text-shadow: -1px 1px 1px #000000, -1px 1px 2px #666;
  }
  /* ChatGPT mobile fullscreen: native circular X is top-right — move ours to top-left */
  .display-mode-btn.left-position {
    left: .5rem;
    right: auto;
    border-radius: 15px 3px 3px 3px;
  }
  .display-mode-btn:hover {
    background: #3d558958;
  }
  /* Inner scroll surface: all content lives here.
     Scrollbar is clipped by .main's rounded overflow:hidden. */
  .scroll-inner {
    flex: 1;
    min-height: 0;
    width: 100%;
    overflow-y: auto;
    overflow-x: hidden;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding-bottom: 0;
    /* Themed scrollbar — standard properties commented out;
       they override ::-webkit-scrollbar pseudoelements in Chromium/Edge */
    /* scrollbar-width: auto; */
    /* scrollbar-color: rgba(168, 160, 145, 0.3) transparent; */
  }
  .scroll-inner::-webkit-scrollbar {
    width: 20px;
  }
  .scroll-inner::-webkit-scrollbar-track {
    background: transparent;
  }
  .scroll-inner::-webkit-scrollbar-thumb {
    background: rgba(168, 160, 145, 0.15);
    border-radius: 3px;
  }
  .scroll-inner::-webkit-scrollbar-thumb:hover {
    background: rgba(168, 160, 145, 0.3);
  }
  .loading {
    display: flex;
    align-items: center;
    justify-content: center;
    flex: 1;
    width: 100%;
    font-size: var(--font-text-lg-size, 1.125rem);
    color: var(--m-text-2);
  }
  .error {
    color: var(--m-error);
    text-align: center;
    padding: 2rem;
  }
  .interaction-float {
    position: absolute;
    z-index: 30;
    /* left is set dynamically to center on first selected word */
    transform: translateX(-50%);
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    max-width: calc(100% - 1rem);
  }
  /* When above: bottom edge meets selection top */
  .interaction-float.above {
    transform: translateX(-50%) translateY(-100%);
    padding-bottom: 15px;
  }
  /* When below: top edge meets selection bottom */
  .interaction-float.below {
    padding-top: 10px;
  }
  .action-loading {
    font-family: 'Varela Round', sans-serif;
    font-size: 12px;
    color: var(--m-text-3);
    margin-top: 8px;
  }
</style>
