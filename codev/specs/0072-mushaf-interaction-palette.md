# Specification: Mushaf Word Interaction & Theme Palette

## Metadata
- **ID**: spec-2026-03-27-mushaf-interaction-palette
- **Status**: in-progress
- **Created**: 2026-03-27
- **Bead**: quran-buz (parent epic: quran-x84)

## Clarifying Questions Asked

1. **Where should the action bar anchor?** Above the selection by default; flip below when selection is on the top 1-2 lines and there's insufficient room above.
2. **Where do results appear?** Inline overlay cards (Option A) — overlays the mushaf text temporarily. Rejected: accordion between lines (disrupts spatial memory), side panel (disconnects from selection), bottom sheet (mobile-only pattern).
3. **Should actions be visually grouped by type?** No — all actions look identical in the bar. Differentiation by icon + label only. Grouping would emerge during implementation if needed.
4. **What color for phrase selection vs ayah highlight?** Burnished gold for user phrase selection, green for system ayah highlight ("you were here"). Two colors, two semantic owners, no ambiguity.
5. **Which gold?** Burnished (#a88030) for text selection. Bright gold (#e0c060) with subtle glow for active action items (Treatment C — monochromatic warmth).
6. **Action label font?** Varela Round (Google Fonts) — rounded letterforms contrast cleanly against serif Arabic text. Requires CSP allowance or local bundling.
7. **Scope of implementation?** Full interaction UI now, stub backends where needed. Phrase-level backends deferred. Audio disabled until implemented.

## Problem Statement

The mushaf MCP app renders Quran pages but offers no way to interact with individual words or phrases. Users can only navigate pages and view text. There is no mechanism to ask questions about specific text, analyze word morphology, find concordances, or get translations for selected phrases.

Additionally, all colors are hardcoded hex values scattered across 6+ Svelte components with no token system, making theme changes error-prone and inconsistent.

## Current State

- **Word interaction**: None. Tapping a word selects the entire verse (green text highlight). No phrase-level selection. No actions beyond verse selection.
- **Color system**: ~40+ hardcoded hex values across `App.svelte`, `VerseLine.svelte`, `Toolbar.svelte`, `TranslationPanel.svelte`, `SurahHeader.svelte`, and `DebugOverlay.svelte`. No CSS custom properties. No dark/light mode support (mushaf is always dark navy). Changing a color requires grep-and-replace across multiple files.
- **AI interaction**: The app supports `sendMessage` to the AI host and `callServerTool` for MCP tools, but neither is used for word-level interaction.
- **Re-entry**: When the AI responds and the mushaf scrolls out of view, there is no mechanism to return the user to their reading position.

## Desired State

### Word-Level Interaction (Progressive Disclosure)

**Level 1 — Selection**: Two selection methods, both producing contiguous phrase selections within an ayah with burnished gold highlights:

**Drag-to-select (primary)**: `pointerdown` on a word anchors the selection. `pointermove` extends the selection to include all words between the anchor and the word currently under the pointer (determined via `document.elementFromPoint`). `pointerup` finalizes. Set `touch-action: pan-y` on the verse text container so vertical scrolling is handled by the browser and horizontal drag gestures are captured by the app. This is the natural, fast path for contiguous phrases.

**Tap-to-extend (secondary)**: Tap a word to toggle it in the selection. Useful for precision — e.g. selecting non-contiguous words in the same ayah, or extending a drag selection by one word. Tapping a selected word deselects it.

**Dismissal**: Tapping outside the selection AND all active widget containers (action bar, result card, ask input) clears everything. Taps within those overlays do not dismiss.

**Highlight rendering**: Words are individual flex items in a `justify-content: space-between` layout that produces mushaf line justification. The DOM structure must not change — no wrapper spans around selected words (this would alter the flex item count and destroy justification). Instead, apply per-word CSS classes: `.selected`, `.selected-start`, `.selected-middle`, `.selected-end`. Use overlapping backgrounds or negative margins to bridge the flex gap (`0.06em`) between adjacent selected words, creating a visually continuous highlight without restructuring the DOM.

**Cross-line selections**: Ayahs frequently span multiple lines, and `VerseLine` renders per-line. A phrase selection crossing a line boundary renders as separate segments — one per line. The first line's segment gets border-radius on the leading edge only (RTL: left side), the last line's segment gets border-radius on the trailing edge (RTL: right side), middle segments get no border-radius. The selection store tracks word positions; each `VerseLine` instance computes its own segment boundaries from the shared store.

**Level 2 — Action Bar**: Floating toolbar appears above the selection by default; flips below when selection is on the top 1-2 lines and there's insufficient room above. Compact icon + label per action in Varela Round (requires CSP config or local font bundle). Caret/arrow points toward the selection. Dismisses with the selection.

Five actions:

| Action | Type | Backend today | Stub behavior |
|--------|------|--------------|---------------|
| Ask | Interactive (input) | AI host `sendMessage` | Works — sends selected text + user question to host |
| Analyze | Immediate | `fetch_word_morphology` (single word) | Falls back to first selected word; result card labels this: "Showing analysis for: [word]" |
| Translate | Immediate | Not yet for phrase subsets | Shows placeholder: "Phrase translation coming soon" |
| Concordance | Immediate | `fetch_word_concordance` (single word) | Falls back to first selected word; result card labels this |
| Listen | Disabled | Not implemented | Button visible but disabled (dimmed `--m-text-4` color) |

Active action state: bright gold (`#e0c060`) icon with subtle glow, gold-tinted background gradient. Inactive actions use muted gold (`#8a7e6e`).

**Level 3 — Result / Input**: Immediate actions (Translate, Analyze, Concordance) produce inline overlay result cards anchored below the action bar (or above if bar is below selection). Cards use navy gradient background, subtle border, depth shadow. Cards overlay the mushaf text temporarily and contain: action label, Arabic text echo, result content.

Interactive actions (Ask): input field grows below the action bar. User types a focus query about the selected phrase, submits via arrow button. Response comes from AI host via `sendMessage` and appears in the conversation — not inline in the mushaf.

### AI Re-entry

When the user submits an Ask action, the app sends context (verse key, phrase, question) via `sendMessage` with a best-effort instruction for the AI to call `show_mushaf(surah, ayah)` after responding. The new mushaf instance highlights the full ayah in green ("you were here"). This is host/model-dependent — `localStorage` preserves state as fallback for manual return.

### Theme Palette

27 CSS custom properties (`--m-` prefix) defined in OKLCH, exported as hex/rgba in `mushaf-theme.css`.

Color semantics: gold = user interaction, green = system context. The user never causes green; green only appears when the AI brings them back.

#### Surface Ramp (hue ~240°, low chroma — deep navy)

| Token | Role | Hex |
|-------|------|-----|
| `--m-surface-1` | Deepest background, main mushaf canvas | `#091428` |
| `--m-surface-2` | Secondary panels, action bar base | `#0f1d35` |
| `--m-surface-3` | Tertiary, toolbar gradients, result card bg | `#162544` |
| `--m-surface-4` | Hover states, input fields | `#1c3050` |
| `--m-surface-5` | Active/pressed states | `#243d62` |
| `--m-surface-6` | Elevated elements, brightest surface | `#2d4a75` |

#### Text Ramp (hue ~45°, low-medium chroma — warm cream)

| Token | Role | Hex |
|-------|------|-----|
| `--m-text-1` | Primary text, Arabic ayah text | `#ede6db` |
| `--m-text-2` | Secondary text, labels, metadata | `#a8a091` |
| `--m-text-3` | Tertiary, placeholders, disabled text | `#706a5e` |
| `--m-text-4` | Faintest, ghost text, disabled icons | `#4a453d` |

#### Burnished Gold Accent (hue ~75° — user interaction)

| Token | Role | Hex |
|-------|------|-----|
| `--m-gold` | Base accent, word selection text color | `#a88030` |
| `--m-gold-bright` | Active action icon, hover emphasis, bright gold with glow | `#e0c060` |
| `--m-gold-mid` | Action bar active text, selected word text | `#ccaa4a` |
| `--m-gold-dim` | Inactive action icons, muted gold | `#8a7e6e` |
| `--m-gold-bg` | Phrase selection background wash | `rgba(168,128,48,0.24)` |
| `--m-gold-border` | Selection ring, action bar active ring | `rgba(168,128,48,0.36)` |

#### Green Accent (hue ~145° — system context)

| Token | Role | Hex |
|-------|------|-----|
| `--m-green` | Base system accent | `#6bc17a` |
| `--m-green-bright` | Emphasis state | `#8dd99a` |
| `--m-green-dim` | Subdued context | `#3a7a45` |
| `--m-green-bg` | Ayah highlight background wash | `rgba(107,193,122,0.08)` |
| `--m-green-border` | Ayah highlight ring (if needed) | `rgba(107,193,122,0.15)` |

#### Semantic Tokens

| Token | Role | Hex |
|-------|------|-----|
| `--m-disabled` | Listen button, unavailable actions | `#4a453d` (= text-4) |
| `--m-error` | Error states in result cards | `#dc2626` |
| `--m-border` | Standard dividers | `rgba(255,255,255,0.12)` |
| `--m-border-subtle` | Faint separators | `rgba(255,255,255,0.06)` |
| `--m-border-hover` | Hover-revealed borders | `rgba(255,255,255,0.20)` |
| `--m-shadow` | Card/panel depth | `rgba(0,0,0,0.4)` |

#### Color Semantics Summary

| Color | Meaning | Triggered by |
|-------|---------|-------------|
| Burnished gold | "I'm interacting with this" | User tap/selection |
| Green wash | "You were here" | AI re-entry via `show_mushaf` |
| Navy surfaces | Structural depth | Layout hierarchy |
| Warm cream | Readable text | Content rendering |

## Stakeholders
- **Primary Users**: Anyone using the mushaf MCP app in Claude Desktop (or other MCP-enabled hosts)
- **Secondary Users**: Developers building on the mushaf component
- **Technical Team**: Nour + AI agents (Conductor, Mason, Sentinel, Warden)
- **Business Owners**: Nour

## Success Criteria
- [x] Tapping words produces contiguous burnished gold phrase highlights (no gaps, no justification breakage)
- [ ] Cross-line phrase selections render correctly with per-line segments
- [x] Action bar appears on selection with 5 actions (Translate, Ask, Analyze, Similar, Listen)
- [ ] Ask routes to AI host via `sendMessage` and produces a response
- [ ] Analyze and Similar return real results for single words via `callServerTool`
- [ ] Translate shows stub for phrases, real for single words (if available)
- [x] Listen button is visible but disabled
- [ ] AI re-entry: after Ask, new mushaf opens at same ayah with green highlight (best-effort)
- [x] All hardcoded colors replaced with `--m-` palette tokens
- [ ] Stub fallbacks are labeled in the result card ("Showing analysis for: [word]")
- [x] Dismissal: tap outside selection + widget containers clears everything

## Constraints

### Technical Constraints
- VerseLine uses `flex` + `justify-content: space-between` for mushaf justification. Phrase highlight must not alter flex item count (no wrapper spans).
- VerseLine renders per-line. Cross-line selections need per-line segment rendering.
- MCP App runs in sandboxed iframe. External fonts (Varela Round) require CSP configuration in `_meta.ui.csp` or local bundling.
- `sendMessage` re-entry instruction is probabilistic — the AI may not always call `show_mushaf` after responding.
- `show_mushaf` only sets `initial_selected_verse` if the ayah exists on the resolved page.
- Existing `localStorage` keys (`quran-mushaf-page`, `quran-mushaf-tool-page`) are global, not per-instance. New state must be namespaced by `viewUUID` to avoid collision across concurrent instances.

### Business Constraints
- None. This is a feature enhancement, not a deadline-driven deliverable.

## Assumptions
- MCP Apps SDK `sendMessage`, `callServerTool`, `viewUUID`, and `IntersectionObserver` patterns work as documented
- Claude Desktop (primary host) supports MCP App tool calls from within the app iframe
- `fetch_word_morphology` and `fetch_word_concordance` MCP tools exist and accept `{ surah, ayah, word_position }` for single words
- Phrase-level backends (translation, concordance, morphology across multiple words) will be implemented later — UI stubs are acceptable now

## Solution Approaches

### Approach 1: Per-word CSS classes (selected)
**Description**: Apply `.selected-start`, `.selected-middle`, `.selected-end` classes to individual word spans. Use overlapping backgrounds to bridge the flex gap. No DOM changes.

**Pros**:
- Preserves flex justification exactly
- Works with cross-line selections (each line computes its own segments)
- No risk of breaking mushaf typography

**Cons**:
- More complex CSS (gap bridging, RTL-aware border-radius logic)
- Segment boundary computation in each VerseLine instance

**Estimated Complexity**: Medium
**Risk Level**: Low

### Approach 2: Wrapper span (rejected by review)
**Description**: Wrap consecutive selected words in a `<span class="phrase-selection">` with shared background and border-radius.

**Pros**:
- Simpler CSS
- Natural "one block" appearance

**Cons**:
- Changes flex item count → breaks justify-content: space-between justification
- Cannot span across lines (VerseLine renders per-line)
- Destroys mushaf typography — disqualifying

**Estimated Complexity**: Low
**Risk Level**: **Critical** (breaks core layout)

## Open Questions

### Critical (Blocks Progress)
- [x] Phrase highlight approach — resolved: per-word CSS classes, not wrapper spans

### Important (Affects Design)
- [x] Gold vs green semantic split — resolved: gold = user, green = system
- [x] Action bar positioning — resolved: above by default, flip below at top lines
- [ ] Varela Round: bundle locally or rely on CSP for Google Fonts CDN?

### Nice-to-Know (Optimization)
- [x] Swipe-to-select — resolved: drag-to-select via pointer events is the primary method, tap-to-extend is secondary. `touch-action: pan-y` separates horizontal drag from vertical scroll.
- [ ] Should `IntersectionObserver` pause anything specific, or is it future-proofing?

## Performance Requirements
- **Selection response**: < 16ms (single frame, no jank on tap)
- **Action bar render**: < 50ms after selection completes
- **callServerTool round-trip**: < 500ms for Analyze/Concordance
- **sendMessage**: async, no performance target (AI response time is host-dependent)

## Security Considerations
- No authentication required (mushaf is a public read-only view)
- `sendMessage` sends user's question to the AI host — no server-side persistence of queries
- CSP must be configured correctly for external font loading
- No user data stored server-side; `localStorage` is client-only per MCP App instance

## Test Scenarios

### Functional Tests
1. Tap word → gold highlight appears
2. Tap adjacent word → continuous highlight (no gap)
3. Tap word on line 7, tap word on line 8 → two-segment highlight with correct border-radius
4. Tap outside → selection + all overlays dismiss
5. Tap action bar button → does not dismiss selection
6. Ask → input appears → submit → sendMessage called with correct context
7. Analyze single word → callServerTool returns morphology → result card displays
8. Analyze phrase → fallback to first word → result card shows "Showing analysis for: [word]"
9. AI re-entry → new mushaf with green ayah highlight on correct verse
10. Listen button → disabled, no action on click

### Non-Functional Tests
1. Tap-to-highlight latency < 16ms (no frame drops)
2. 604 pages × 15 lines: selection store handles any page without degradation
3. Multiple mushaf instances in conversation: localStorage keys don't collide

## Dependencies
- **MCP Apps SDK**: `sendMessage`, `callServerTool`, `viewUUID`, `IntersectionObserver`
- **MCP Tools**: `show_mushaf` (existing), `fetch_word_morphology` (existing), `fetch_word_concordance` (existing)
- **External**: Google Fonts (Varela Round) or local font bundle
- **Svelte 5**: `$props()`, `$state()`, `$derived()`, stores

## References
- Design mockups: `.superpowers/brainstorm/` (visual companion session, 2026-03-27)
- Design narrative: `.superpowers/docs/specs/2026-03-27-mushaf-interaction-palette-design.md` (brainstorming output with implementation phases and file lists)
- MCP Apps SDK patterns: `~/ref/ext-apps/docs/patterns.md`
- MCP Apps skill: `/home/nour/.claude/plugins/marketplaces/mcp-apps/plugins/mcp-apps/skills/create-mcp-app/SKILL.md`

## Risks and Mitigation
| Risk | Probability | Impact | Mitigation Strategy |
|------|------------|--------|-------------------|
| Flex justification breakage from highlight implementation | Low (resolved) | Critical | Per-word CSS classes, no DOM restructuring. Validated by GPT-5.4 + Gemini review. |
| AI doesn't follow re-entry instruction | Medium | Medium | Best-effort pattern. localStorage fallback for manual return. |
| Google Fonts blocked by CSP in some hosts | Medium | Low | Bundle Varela Round locally as fallback. Existing QCF CDN loading proves CSP feasibility in Claude Desktop. |
| Cross-line selection rendering bugs (RTL edge cases) | Medium | Medium | Per-line segment computation with explicit start/middle/end classes. Test with known multi-line ayahs. |
| Stub fallback misleads users about phrase analysis | Low | Medium | Label all fallbacks explicitly in result card UI. |

## Expert Consultation

**Date**: 2026-03-27
**Models Consulted**: GPT-5.4, Gemini 3.1 Pro (via PAL codereview)

**Convergent findings (both models independently flagged)**:
- **Highlight rendering**: Wrapper span approach breaks flex justification. Revised to per-word CSS classes.
- **Cross-line selection**: Unaddressed in original spec. Added per-line segment rendering with RTL-aware border-radius.
- **AI re-entry**: Probabilistic, not deterministic. Reworded as best-effort with localStorage fallback.
- **CSP for fonts**: Required for Varela Round in sandboxed iframe. Noted existing QCF CDN as precedent.

**Additional findings**:
- Dismissal boundaries must exclude active widget containers (GPT-5.4 + Gemini)
- Stub fallbacks should be labeled in result card (Gemini)
- Token count: 27, not 28 (both)
- `viewUUID`-namespaced localStorage keys to avoid cross-instance collision (GPT-5.4)

All findings incorporated into this spec.

## Approval
- [ ] Technical Lead Review
- [x] Expert AI Consultation Complete (GPT-5.4 + Gemini 3.1 Pro)
- [ ] Product Owner Review

## Notes

This spec was developed through an interactive brainstorming session with browser-based visual mockups (see `.superpowers/brainstorm/`). Multiple gold accent options were prototyped and compared live before settling on burnished gold with bright gold active states (Treatment C — monochromatic warmth). The implementation plan will be created separately in `codev/plans/0072-mushaf-interaction-palette.md`.

---

## Amendments

<!-- When adding a TICK amendment, add a new entry below this line in chronological order -->

### TICK-001: UX fixes from user testing (2026-03-27)

**Summary**: 10 issues found during first interactive testing session.

**Problem Addressed**:
Phase 2 implementation had correct architecture but multiple UX/behavioral issues found during hands-on testing with the dev host browser.

**Spec Changes**:

#### Bugs

1. **Adjacent word tap-to-extend broken**: `applyTapSelection` adjacency check works in `startDrag` but not in `tapSelect` path. The `onclick` handler calls `tapSelect` which calls `applyTapSelection` — but by the time `click` fires, the previous selection was already replaced by `startDrag` from the preceding `pointerdown`. Fix: centralize all selection logic in `startDrag`/`endDrag` lifecycle, remove `onclick` handler entirely. Detect tap-vs-drag in `endDrag`: if pointer never entered a different word, it was a tap.

2. **Action panel persists after page navigation**: `handleNavigate` sets `selectedVerseKey = null` and `pageData = newData` but never calls `clearSelection()`. Fix: clear word selection on page navigation.

3. **Caret doesn't flip when bar is below**: ActionBar always renders caret pointing down. Fix: pass `position` prop ("above"|"below"), flip caret to point up when below.

4. **Line 2 clips when rendering above**: Overlay measurement uses hardcoded `overlayHeight = 120px`. Actual height with result card is larger. Also doesn't account for the translation panel / header bar consuming top space. Fix: measure actual overlay element height after render, use real available space for above/below decision.

#### UX Refinements

5. **Caret anchored to first selected word**: Overlay currently centers horizontally in `.main`. Spec requires caret tip to be directly above (or below) the center of the first word in the selection. Fix: measure first `.word-selected` element's center X, position overlay so caret aligns there.

6. **Result card on opposite side of caret**: When action bar is above the selection, result card should render ABOVE the action bar (further from the selection). When below, result card renders BELOW. The result card should never be between the action bar and the selection. Fix: change DOM order based on `position` — when above, result card comes first in DOM (renders on top), action bar below it with caret pointing at selection.

7. **Action toggle off**: Clicking an already-active action should deactivate it (close the result card / input). Fix: `handleAction` checks `activeAction === id` and clears if so.

8. **Tap-to-deselect on selected word**: Tapping the only selected word (or the last word in a phrase) should deselect it entirely, dismissing the action bar. Fix: in `endDrag` (for tap detection), if the tapped word was already selected and no drag occurred, call `toggleWord` to remove it. If the selection becomes empty, `clearSelection` runs.

9. **Action order changed**: Translate | Ask | Analyze | Similar | Listen (was: Ask | Analyze | Translate | Concordance | Listen).

10. **Rename Concordance → Similar**: Action label and ID.

#### Overlay Positioning Rules (revised)

The overlay must satisfy these rules in priority order:

1. The caret tip points at the horizontal center of the **first selected word**
2. If there is enough space above the selection for the full overlay (action bar + result card if active), render above
3. If not enough space above, render below
4. When above: DOM order is [result card] → [action bar] → [caret ▼] → selection
5. When below: DOM order is selection → [caret ▲] → [action bar] → [result card]
6. Overlay position updates on scroll (bind `onscroll` on `.scroll-inner`)
7. On page navigation, clear selection and overlay entirely

**Review**: Incorporated from `.notes/2026-03-27-mushaf-interaction-ux-feedback.md`

---
