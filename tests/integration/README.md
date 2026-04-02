# Integration Tests

These tests exercise the live server/bootstrap path and real MCP flows. They are marked with `@pytest.mark.integration` and are excluded from the default pytest run by project config.

| File | Covers | Purpose |
|---|---|---|
| `README.md` | Integration test index | Documents the integration suite and why it is separated from unit tests. |
| `test_server_http_surface.py` | In-process HTTP app build and public browser routes | Smoke-tests the mounted public HTTP surface without relying on the trashed historical suite. |
| `test_mcp_grounding_flow.py` | Grounding nonce flow, edition listing, translation fetch/search | Exercises the live MCP protocol path through `fastmcp.Client(mcp)` with real services. |
| `test_rate_limit_e2e.py` | `middleware/rate_limit.py` and `middleware/stack.py` — request-boundary throttling | Exercises real FastMCP streamable-HTTP calls with repeated metered tool invocations, daily-cap rejection, and health-token bypass. |
| `test_fetch_quran_e2e.py` | fetch_quran tool | E2E tests for Quran text fetch: Al-Fatiha ayahs, default edition, pagination metadata, grounding rules. |
| `test_fetch_translation_e2e.py` | fetch_translation tool | E2E tests for translation fetch: Ayat al-Kursi, default edition, non-empty English text. |
| `test_fetch_tafsir_e2e.py` | fetch_tafsir tool | E2E tests for tafsir fetch: Ibn Kathir commentary, non-empty text, dedup of grouped verses. |
| `test_continuation_e2e.py` | Continuation token round-trips | E2E tests for opaque continuation tokens across fetch and search tools: multi-page traversal, exhausted/invalid/wrong-tool error handling. |
| `test_db_lifecycle.py` | `lib/db/` — runtime_config, turn_manager, pool retention | Integration tests hitting real PostgreSQL: config CRUD, turn lifecycle (Path A/B), promote/complete, retention cleanup. |
| `test_llm_providers.py` | `lib/llm/` — Anthropic, OpenAI, Google providers | Real API calls: structured output parse (tiny prompt, cheapest models), auth error with bad key, empty prompt validation. |
| `test_relay_e2e.py` | Relay middleware + mounted relay tools + DB persistence | End-to-end mounted-boundary coverage for relay auth/consent guard and observable writes (turn/tool_call/identified_gap/user_feedback). |
| `test_fetch_db_e2e.py` | DB-backed fetch through MCP stack | Verifies fetch_quran/translation/tafsir return data after DB dispatch changes. |
