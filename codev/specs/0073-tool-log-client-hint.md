# TICK Specification: Client Hint Line Before [TOOL] Logs

## Metadata
- **ID**: spec-2026-03-29-tool-log-client-hint
- **Protocol**: TICK
- **Created**: 2026-03-29
- **Status**: implemented

## Task Description

Add a `[TOOL]     client: { ... }` log line immediately before every `[TOOL]` call log line emitted by `McpCallLoggerMiddleware`. The line surfaces client detection results so operators can see **who** made each tool call at a glance in production logs.

Example (log_level `normal`):

```
INFO     [TOOL]     client: { "host": "chatgpt", "platform": "desktop", "ip": "203.0.113.42", "id": "openai-conv:sess-abc123" }
INFO     [TOOL]     fetch_tafsir(ayahs="112:1-4", editions=["en-ibn-kathir"]) → OK (>64KB, 180ms)
```

## Scope

### In Scope
- Emit one `logger.info()` line with `[TOOL]` prefix and `client:` label before each tool call log
- Include four fields: `host` (from `detect_client_hint`), `platform` (from `detect_client_hint`), `ip` (from `cf-connecting-ip` header), `id` (from `resolve_client_identity`)
- Pretty-print as valid JSON via `json.dumps()` with field order `host, platform, ip, id` — renders `null` for missing IP (not Python `None`), double quotes (not single quotes)
- **Success path**: emit at `normal`, `verbose`, `debug`; suppress at `minimal`
- **Error path**: emit at all verbosity levels (including `minimal`) — mirrors existing `_log_error` behavior which always shows the error line
- Support `json` output format: add a `"client"` key to the existing JSON record (no separate log line)

### Out of Scope
- Adding client hint lines before `[RESOURCE]`, `[PROMPT]`, or `[META]` log lines (can be added later)
- Changing the existing `[TOOL]` log line format
- Persisting client hints to database or adding new middleware

## Success Criteria
- [x] `[TOOL]     client: { ... }` line appears immediately before every `[TOOL]` call log at `normal`+ verbosity
- [x] `host` field is `"chatgpt"`, `"claude"`, or `"unknown"`
- [x] `platform` field is `"mobile"`, `"desktop"`, or `"unknown"`
- [x] `ip` field is the `cf-connecting-ip` value, or `null` when absent (e.g., STDIO transport)
- [x] `id` field matches `resolve_client_identity()` output (e.g., `"openai-conv:sess-abc"`, `"claude-cc:1.2.3.4"`)
- [x] Suppressed at `minimal` verbosity on success path; emitted at all levels on error path (matches `_log_error` behavior)
- [x] JSON format adds `"client": { "host": "...", "platform": "...", "ip": "...", "id": "..." }` key to existing tool record (both success and error)
- [x] Existing tests unbroken; new unit tests cover the client line
- [x] No breaking changes

## Constraints
- Must not add measurable latency — `detect_client_hint` and `resolve_client_identity` are synchronous header lookups, no I/O
- `[TOOL]     client: ` prefix must align with existing `[TOOL]     ` spacing (5-space pad after tag)

## Assumptions
- `detect_client_hint` from `lib/presentation/client_hint.py` is importable from middleware. Although named "presentation," the function is pure header inspection with no UI dependencies — acceptable cross-layer import.
- `resolve_client_identity` from `lib/context/request.py` is already used in the middleware stack
- `cf-connecting-ip` is available in `get_http_headers()` on Cloudflare-fronted deployments; `null` otherwise
- **Context bridging**: middleware receives `MiddlewareContext`, not `fastmcp.Context`. Access the underlying Context via `context.fastmcp_context` (may be `None`).

## Implementation Approach

Add the client line emission inside `McpCallLoggerMiddleware._log_call` (and `_log_error`), right before the existing `logger.info(line)` / `logger.error(line)` call.

### Context & Header Access

Header access via `get_http_headers()` is a `ContextVar` lookup — no I/O, negligible cost. `detect_client_hint()` calls `get_http_headers()` internally, so the middleware helper will result in two lookups per log event. This is acceptable and not worth refactoring the `detect_client_hint` signature for.

```python
fastmcp_ctx = context.fastmcp_context          # may be None
hint = detect_client_hint(fastmcp_ctx)          # calls get_http_headers() internally
headers = get_http_headers()                    # second lookup, ~free ContextVar read
client_id = resolve_client_identity(headers=headers)
ip = headers.get("cf-connecting-ip") if headers else None
```

**IP field semantics**: `client.ip` is the `cf-connecting-ip` header (Cloudflare edge-observed end-user IP). This may differ from the transport-level IP logged at `debug` verbosity via the existing `_extract_client_ip()` helper, which reads the ASGI socket address. Both are intentionally preserved — `cf-connecting-ip` is the operator-useful value; transport IP is the debug-level fallback.

### Key Changes
- `src/quran_mcp/middleware/mcp_call_logger.py`:
  - Import `detect_client_hint` from `lib/presentation/client_hint`, `resolve_client_identity` and `get_http_headers` from `lib/context/request`
  - Add a `_build_client_dict` helper that takes `context: MiddlewareContext` and returns `{"host": ..., "platform": ..., "ip": ..., "id": ...}`
  - In `_log_call` (pretty path): format client dict as spaced JSON, emit `logger.info(f"[TOOL]     client: {formatted}")` before the main line; gate on `tag == "TOOL"`
  - In `_log_error` (pretty path): same client line before the error line, emitted via `logger.error()` (not `logger.info()`) so it shares the same logging fate as the error it describes (no verbosity gate — always emit)
  - In `_log_call` / `_log_error` (JSON path): add `"client"` key to existing record dict; no separate line
  - Gate on `tag == "TOOL"` — only emit for tool calls, not resources/prompts/meta
- `tests/test_mcp_call_logger.py` (or equivalent): add tests for client line presence/absence at each verbosity level

### JSON Format Example

Success:
```json
{
  "type": "tool",
  "name": "fetch_tafsir",
  "status": "ok",
  "size_bytes": 68000,
  "duration_ms": 180,
  "request_id": "req-abc",
  "client": {
    "host": "chatgpt",
    "platform": "desktop",
    "ip": "203.0.113.42",
    "id": "openai-conv:sess-abc123"
  }
}
```

Error:
```json
{
  "type": "tool",
  "name": "fetch_quran",
  "status": "error",
  "error": "ValueError: invalid ayah range",
  "duration_ms": 2,
  "request_id": "req-def",
  "client": {
    "host": "unknown",
    "platform": "unknown",
    "ip": null,
    "id": "unknown"
  }
}
```

## Risks
| Risk | Mitigation |
|------|------------|
| `detect_client_hint` expects `fastmcp.Context`, not `MiddlewareContext` | Bridge via `context.fastmcp_context`; pass `None` if unavailable — `_detect_host` works with headers alone |
| `get_http_headers()` returns `None` on STDIO | All fields become `null`/`"unknown"` — the line still emits, just with unknowns |
| Two IP sources could confuse operators (`cf-connecting-ip` vs transport IP) | Spec explicitly documents: `client.ip` = edge IP, debug suffix = transport IP |

## Testing Approach
### Test Scenarios
1. **ChatGPT client**: mock headers with `x-openai-session` → verify `host: "chatgpt"`, `id: "openai-conv:..."`
2. **Claude client**: mock headers with `baggage: sentry-trace_id=...` → verify `host: "claude"`, `id: "claude-trace:..."`
3. **Unknown client**: no identifying headers → verify `host: "unknown"`, `id: "unknown"`
4. **Minimal verbosity (success)**: verify client line is NOT emitted
7. **Minimal verbosity (error)**: verify client line IS emitted (matches error line behavior)
5. **JSON format**: verify `client` key in JSON record, no separate log line
6. **STDIO transport**: no headers at all → all fields are `null`/`"unknown"`

## Notes
- The `[TOOL]` prefix is reused (not a new tag) so the client line visually groups with the call line in log output
- `ip` is the raw `cf-connecting-ip`, not the resolved identity — operators want to see the actual IP alongside the logical identity
