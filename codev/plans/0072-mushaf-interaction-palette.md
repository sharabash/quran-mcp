# Plan: Mushaf Word Interaction & Theme Palette

## Metadata
- **Spec**: [0072-mushaf-interaction-palette](../specs/0072-mushaf-interaction-palette.md)
- **Status**: in-progress
- **Created**: 2026-03-28
- **Branch**: `spir/mushaf-interaction-palette`

## Completed Work

### Phase 1: Theme Palette
- [x] OKLCH theme palette (27 `--m-*` tokens) in `mushaf-theme.css`
- [x] Migrate all 6 components from hardcoded hex to palette tokens
- [x] Opaque gold highlight colors to eliminate overlap seams at segment boundaries

### Phase 2: Word Selection Store
- [x] `selection.ts` — contiguous word selection within a single ayah
- [x] Drag-to-select: `startDrag` / `extendDrag` / `endDrag`
- [x] Tap-to-extend: `toggleWord` with truncation (no gaps)
- [x] Segment computation for highlight rendering (`getSegmentPosition`)
- [x] `consumeClickDismissSuppression` — prevent drag clearing on pointerup

### Phase 3: Selection UI
- [x] Gold highlight segments (start/middle/end/only) with border-radius
- [x] Highlight edge bleed (0.185em padding + negative margin + z-index:-1)
- [x] Word gap tuned to 0.085em, line-height to 1.618em with 0.854em margins
- [x] Verse-level green highlight (ayah context indicator)

### Phase 4: Action Bar & Result Card
- [x] `ActionBar.svelte` — Listen, Similar, Analyze, Ask, Translate
- [x] `ResultCard.svelte` — displays action output above/below selection
- [x] `AskInput.svelte` — free-text question input
- [x] Floating overlay positioning with above/below logic
- [x] ResultCard allowance in above/below decision (prevent top-edge clipping)
- [x] 6px gap between ActionBar and ResultCard

### Phase 5: Bug Fixes & Polish
- [x] Drag selection preserved on pointerup (Bug 3)
- [x] Middle-word deselection truncates, no gaps (Bug 2)
- [x] Green ayah highlight dismisses on empty-space click (Bug 1)
- [x] Content-driven iframe height via ResizeObserver (replaces min-height: 200vw)
- [x] ResizeObserver re-syncs on page navigation

### Phase 6: Config Toggle
- [x] `McpAppsSettings.show_mushaf.interactive` in settings.py
- [x] `config.yml` and `config.local.yml`: `interactive: false`
- [x] `show.py`: injects `interactive` into structured content
- [x] `App.svelte`: gates pointer handlers, overlay, and callbacks on `interactive`

## Remaining Work

### Phase 7: Action Backends
- [ ] Translate action — phrase-level translation via `sendMessage` to host AI
- [ ] Analyze action — word morphology via `callServerTool("fetch_word_morphology")`
- [ ] Similar action — concordance via `callServerTool("fetch_word_concordance")`
- [ ] Ask action — free-text question via `sendMessage`
- [ ] Listen action — audio playback (deferred until audio infrastructure exists)

### Phase 8: Multi-line Selection
- [ ] Selections spanning across lines within the same ayah
- [ ] Visual continuity of highlight across line breaks

### Phase 9: Re-entry
- [ ] After AI responds and mushaf scrolls out, mechanism to return to reading position
