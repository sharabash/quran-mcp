# Bugfix Report: Mushaf interactive config lost on fallback fetch

- **Bead**: quran-m2h.1
- **Date**: 2026-03-30
- **Severity**: P2

## Symptoms

`mcp_apps.show_mushaf.interactive: false` was loaded by the running server, but the mushaf MCP app still allowed verse and word interaction after reload.

## Reproduction

1. Set `mcp_apps.show_mushaf.interactive: false` in `config.yml` or `config.local.yml`.
2. Reload the Docker app container and reopen the mushaf app.
3. Observe: the app remains interactive on hosts that initialize or navigate through `fetch_mushaf`.

## Root Cause

`fetch_mushaf` omitted the `interactive` field from its `structured_content`.

**Root cause**: `show_mushaf` propagated the config flag, but `fetch_mushaf` did not, and the Svelte app defaults missing `interactive` to `true`.

**Details**:
- `show_mushaf` injected `structured["interactive"]` from `app_ctx.settings.mcp_apps.show_mushaf.interactive`.
- The app has a fallback path for hosts that do not deliver the initial `ontoolresult`, and it also uses `fetch_mushaf` for page navigation.
- Because `fetch_mushaf` omitted the field, fallback and navigation responses silently re-enabled interaction.

## Investigation Notes

- Checked: runtime settings inside `quran-mcp-app-1`.
- Found: `get_settings().mcp_apps.show_mushaf.interactive` was `False`, so config loading was correct.
- Verified: a direct `fetch_mushaf` call from the running server returned `interactive=False` after the patch.

## Fix

Propagate `interactive` from settings in `fetch_mushaf`, matching `show_mushaf`, and add regression coverage for both tool wrappers.

**Files modified**:
- `src/quran_mcp/mcp/tools/mushaf/fetch.py` - injects `interactive` into `structured_content`
- `tests/test_mushaf_tools.py` - asserts `interactive` is propagated in successful `show_mushaf` and `fetch_mushaf` responses

**Approach**:
This fixes the root cause at the server payload boundary, which is where the fallback path diverged. No Svelte rebuild was required because the client-side code already honors `interactive: false` when the field is present.

## Verification

- [x] Original issue resolved
- [x] Tests pass
- [x] No regressions introduced
- [x] Edge cases tested (if applicable)

## Lessons Learned

- App-only helper tools must preserve any UI-affecting flags that the primary entry tool exposes.
- For MCP apps with host-specific fallback paths, payload parity matters more than build parity.

## Related

- `codev/specs/0072-mushaf-interaction-palette.md`
- `codev/plans/0072-mushaf-interaction-palette.md`
