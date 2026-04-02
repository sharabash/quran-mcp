# Plan: Client Hint Line Before [TOOL] Logs

## Metadata
- **ID**: plan-2026-03-29-tool-log-client-hint
- **Status**: implemented
- **Specification**: codev/specs/0073-tool-log-client-hint.md
- **Created**: 2026-03-30
- **Bead**: quran-69b

## Executive Summary

Single-phase implementation: add a `_build_client_dict` helper to `McpCallLoggerMiddleware` and call it from `_log_call` and `_log_error` to emit a client identification line before every `[TOOL]` log. No new files, no API changes, no new dependencies.

## Success Metrics
- [x] All specification success criteria met
- [x] Existing tests unbroken (1332 passed)
- [x] New unit tests cover client line emission at each verbosity level (8 new tests)
- [x] No measurable latency impact

## Phases (Machine Readable)

```json
{
  "phases": [
    {"id": "client-hint-logging", "title": "Phase 1: Client Hint Log Line"}
  ]
}
```

## Phase Breakdown

### Phase 1: Client Hint Log Line
**Dependencies**: None

#### Objectives
- Emit client identification before every `[TOOL]` log so operators can see who made each tool call
- Support both pretty (single-line JSON) and structured JSON output formats

#### Deliverables
- [x] `src/quran_mcp/middleware/mcp_call_logger.py` — modified
- [x] `tests/test_mcp_call_logger.py` — new tests added

#### Implementation Details

**New helper** in `McpCallLoggerMiddleware`:

```python
def _build_client_dict(self, context: MiddlewareContext) -> dict:
    """Build client identification dict from request context."""
    fastmcp_ctx = context.fastmcp_context
    hint = detect_client_hint(fastmcp_ctx)
    headers = get_http_headers()
    client_id = resolve_client_identity(headers=headers)
    ip = headers.get("cf-connecting-ip") if headers else None
    return {
        "host": hint.get("host", "unknown"),
        "platform": hint.get("platform", "unknown"),
        "ip": ip,
        "id": client_id,
    }
```

**New imports** at top of file:
```python
from quran_mcp.lib.presentation.client_hint import detect_client_hint
from quran_mcp.lib.context.request import get_http_headers, resolve_client_identity
```

**Modifications to `_log_call`** (pretty path, gated on `tag == "TOOL"`):
```python
if tag == "TOOL":
    client = self._build_client_dict(context)
    client_line = f"[TOOL]     client: {json.dumps(client)}"
    logger.info(client_line)
```
No extra verbosity gate needed — `_wrap_call` already prevents `_log_call` from executing at `minimal` verbosity.

**Modifications to `_log_call`** (JSON path, gated on `tag == "TOOL"`):
```python
if tag == "TOOL":
    record["client"] = self._build_client_dict(context)
```

**Modifications to `_log_error`** (pretty path, gated on `tag == "TOOL"`):
```python
if tag == "TOOL":
    client = self._build_client_dict(context)
    client_line = f"[TOOL]     client: {json.dumps(client)}"
    logger.error(client_line)  # logger.error, not .info — shares logging fate with the error line
```
No verbosity gate on error path — mirrors existing `_log_error` behavior (always emits).

**Modifications to `_log_error`** (JSON path, gated on `tag == "TOOL"`):
```python
if tag == "TOOL":
    record["client"] = self._build_client_dict(context)
```

#### Acceptance Criteria
- [x] ChatGPT client: `host: "chatgpt"`, `id: "openai-conv:<session>"`
- [x] Claude client via baggage: `host: "claude"`, `id: "claude-trace:<trace_id>"`
- [x] Generic HTTP client with `cf-connecting-ip` but no provider token: `host: "unknown"`, `id: "ip:<ip>"`
- [x] STDIO transport (no headers): `host: "unknown"`, `platform: "unknown"`, `ip: null`, `id: "unknown"`
- [x] Success at `minimal`: client line NOT emitted (inherits `_wrap_call` gate)
- [x] Error at `minimal`: client line IS emitted via `logger.error`
- [x] JSON format: tool records include `client` key; non-tool records unchanged; no separate log line
- [x] Non-tool tags (RESOURCE, PROMPT, META): no client line emitted in pretty or JSON
- [x] All existing tests pass

#### Test Plan
- **Unit Tests**: Mock `detect_client_hint`, `resolve_client_identity`, `get_http_headers` to return known values. Assert log output contains/omits client line at each verbosity level. Assert JSON records contain/omit `client` key.
- **Manual Testing**: Run server locally, make tool calls from ChatGPT and Claude, verify client line appears in logs.

#### Rollback Strategy
Revert the single commit. No schema changes, no config changes, no new files.

## Validation Checkpoints
1. **After implementation**: run full test suite, verify no regressions
2. **Manual verification**: `fastmcp dev` → make a tool call → check log output

## Expert Review
**Date**: 2026-03-30
**Models**: GPT 5.4, Gemini 3.1 Pro
**Key Feedback** (on spec, applied before plan):
- "Fetch headers once" claim was inaccurate — `detect_client_hint` does its own `get_http_headers()` call. Accepted: double ContextVar lookup is ~free.
- Error path client line must use `logger.error()` not `logger.info()` — otherwise silently dropped if log level is WARNING+.
- Pretty format must use `json.dumps()` for valid JSON (`null` not `None`, double quotes).

## Approval
- [ ] Technical Lead Review
- [ ] Expert AI Consultation Complete

## Notes
- Total estimated change: ~30 lines in `mcp_call_logger.py`, ~60 lines of tests
- No new files created
- `detect_client_hint` is in `lib/presentation/` but is pure header inspection — cross-layer import is acceptable
