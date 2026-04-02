# Bugfix Report: Mushaf noninteractive mode allows normal selection again

- **Bead**: quran-m2h.2
- **Date**: 2026-03-30
- **Severity**: P2

## Symptoms

With `mcp_apps.show_mushaf.interactive: false`, the mushaf app still showed `cursor: pointer`, blocked native mouse selection, and intercepted pointer events on words.

## Reproduction

1. Set `mcp_apps.show_mushaf.interactive: false`.
2. Open the mushaf app and try to drag-select text with the mouse.
3. Observe: the cursor suggests clickable interaction and native selection is blocked.

## Root Cause

The app disabled callbacks at the top level, but the word spans still rendered as interactive elements.

**Root cause**: `VerseLine.svelte` always attached pointer handlers and forced `cursor: pointer` plus `user-select: none`, even when the app-level `interactive` flag was false.

**Details**:
- `App.svelte` gated the callback props, but `VerseLine.svelte` still rendered `onpointerdown`, `onpointerenter`, and `onclick`.
- `handlePointerDown()` always called `preventDefault()`.
- The word styling continued to advertise interaction visually even in noninteractive mode.

## Investigation Notes

- Checked: `App.svelte`, `MushafPage.svelte`, and `VerseLine.svelte`.
- Found: the noninteractive state was only enforced at the callback wiring layer, not at the rendered DOM and CSS layer.
- Verified: the app rebuilt successfully after the change and the mushaf tool regression tests still passed.

## Fix

Propagate `interactive` as an explicit prop into the mushaf components and use it to control both behavior and presentation.

**Files modified**:
- `src/quran_mcp/apps/mcp/mushaf/src/App.svelte` - passes `interactive` into `MushafPage`
- `src/quran_mcp/apps/mcp/mushaf/src/lib/MushafPage.svelte` - forwards `interactive` into `VerseLine`
- `src/quran_mcp/apps/mcp/mushaf/src/lib/VerseLine.svelte` - only attaches pointer/click handlers when interactive, restores `cursor: text` and native text selection otherwise

**Approach**:
This keeps interactive mode unchanged while making noninteractive mode render as plain selectable text. It removes the false affordance instead of layering another special case on top.

## Verification

- [x] Original issue resolved
- [x] Tests pass
- [x] No regressions introduced
- [x] Edge cases tested (if applicable)

## Lessons Learned

- A feature flag that disables behavior should also disable the matching affordance.
- For UI flags, callback gating alone is insufficient; the DOM contract and CSS contract need to match.

## Related

- `codev/specs/0072-mushaf-interaction-palette.md`
- `codev/plans/0072-mushaf-interaction-palette.md`
