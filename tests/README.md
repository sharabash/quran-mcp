# Tests

Unit tests live here. Integration and end-to-end tests that hit the real MCP stack or external services live under `tests/integration/`.

| File | Covers | Purpose |
|---|---|---|
| `README.md` | Test directory index | Documents the current unit/integration test layout and file ownership. |
| `test_config_settings.py` | Config YAML merge, env override logging, nested list env parsing | Verifies the current settings system from scratch, including nested override behavior and both comma-list and JSON-array env parsing. |
| `test_profiles.py` | Visibility tag resolution and relay enablement | Locks in profile/expose-tag precedence and relay defaults. |
| `test_middleware_stack.py` | FastMCP middleware ordering and conditional inclusion | Verifies which protocol middleware are present under different settings combinations. |
| `test_site.py` | Public site manifest validation and helper behavior | Covers missing-asset validation, landing-page negotiation, and directory route safety. |
| `test_tool_contracts.py` | MCP tool registration metadata and annotations | Validates tool count, annotations, versions, descriptions, output schemas, and parameter contracts via FastMCP Client. |
| `test_rate_limit.py` | `middleware/rate_limit.py` — LeakyBucket, daily caps, slot refund | Tests leaky bucket algorithm, per-client/global daily caps, health token bypass, global slot refund on rejection. |
| `test_tool_instructions.py` | `middleware/tool_instructions.py` — instruction appending | Tests content tool instruction injection and assistant-only audience annotation. |
| `test_mcp_call_logger.py` | `middleware/mcp_call_logger.py` — formatters and verbosity | Tests pure utility functions and verbosity modes (minimal/normal/verbose/debug, JSON/pretty). |
| `test_relay.py` | `middleware/relay.py` — pure utility functions | Tests traceparent parsing, result metadata extraction, drain_pending shutdown. |
| `test_relay_auth.py` | `mcp/tools/relay/helpers.py` — write authorization boundary | Tests preview/full bypass, GA-only token enforcement, and relay-token header validation behavior. |
| `test_http_debug.py` | `middleware/http_debug.py` — header sanitization, enable gate | Tests sensitive header masking and settings-gated middleware activation. |
| `test_wire_dump.py` | `middleware/wire_dump.py` — ASGI protocol capture | Tests HTTP capture to JSONL, non-HTTP passthrough, error recording, MCP method extraction. |
| `test_ayah_parsing.py` | `lib/ayah_parsing.py` — parse, expand, format ayah keys | Tests single key parsing, range expansion, comma/whitespace splitting, adjacent range merging. |
| `test_client_hint.py` | `lib/presentation/client_hint.py` — host/platform detection | Tests header-based host detection (ChatGPT vs Claude) and mobile/desktop platform detection. |
| `test_summary.py` | `lib/presentation/summary.py` — segment formatting, message builders | Tests format_segments, infer_summary_lang, sampling and prompt message construction. |
| `test_request_context.py` | `lib/context/request.py` — identity resolution, conversation ID | Tests 6-tier client identity hierarchy and conversation ID extraction from headers. |
| `test_turn_manager.py` | `lib/db/turn_manager.py` — pure cache/state ops | Tests LRU eviction, call index assignment, state lookup, mark_call_completed, clear_cache. |
| `test_health.py` | `lib/site/health.py` — pure helpers and cache | Tests nonce extraction, text block parsing, grounding suppression check, cache get/set/expiry. |
| `test_goodmem_filters.py` | `lib/goodmem.py` — filter expression DSL | Tests type inference, filter parsing, SQL expression building, IN clauses, range/cross-field AND, expression combining. |
| `test_goodmem_maintainer_scripts.py` | `scripts/.maintainer/goodmem/{memory_create,memory_retrieve}.py` | Tests retrieval defaults/limit validation and non-fatal subprocess failure handling for maintainer GoodMem scripts. |
| `test_llm_helpers.py` | `lib/llm/` — helpers and exception hierarchy | Tests context window error detection, token extraction, prompt validation, truncation, exception construction. |
| `test_sampling_helpers.py` | `lib/sampling/handler.py` — content conversion helpers and provider fallback handlers | Tests model preference parsing, deep merge, role normalization, image/audio format detection, OpenAI message building, and hermetic OpenAI/Anthropic/Gemini/OpenRouter handler behavior. |
| `test_fetch_orchestration.py` | `mcp/tools/_fetch_orchestration.py` — shared fetch-wrapper boundary | Tests continuation/request decoding, invalid-request contract mapping, pagination metadata shaping, ayah recomputation, and warning normalization helpers. |
| `test_runtime_state_ownership.py` | `server.py`, `lib/context/{types,lifespan}.py`, `lib/sampling/handler.py` | Guards lazy server bootstrap, AppContext leaf imports, explicit sampling ownership, and injected lifespan runtime override hooks. |
| `test_metadata_query.py` | `lib/metadata/query.py` — input validation bounds | Tests parameter range validation for all query modes (surah, juz, page, hizb, ruku, manzil). |
| `test_quran_fetch.py` | `lib/quran/fetch.py` — edition resolution | Tests static registry resolution by ID and code. |
| `test_edition_flags.py` | `lib/editions/flags.py` — context-local override reset and scoped flag overrides | Tests explicit override reset, context-manager restoration, copied-context isolation, and reset-all behavior for GoodMem-native flags. |
| `test_tafsir_fetch.py` | `lib/tafsir/` — edition resolution and dedup | Tests static registry resolution and _dedup_entries pure text collapsing logic. |
| `test_translation_fetch.py` | `lib/translation/fetch.py` — edition resolution | Tests static registry resolution by ID and language code. |
| `test_morphology.py` | `lib/morphology/` — input validation and pure functions | Tests parameter validation for morphology/paradigm/concordance and _categorize_stem, _safe_int. |
| `test_pagination.py` | `lib/presentation/pagination.py` — paginate, continuation tokens | Tests pagination math, continuation token round-trip, tamper detection, expiry, token cap enforcement. |
| `test_asset_contracts.py` | Asset file contracts | Verifies skill.md and grounding_rules.md exist and contain expected content. |
| `test_public_facades.py` | Package exports, resource registrars, manifest contracts, and shared tool error helpers | Verifies top-level package reexports, resource readback, prompt no-op registration, manifest route contracts, GoodMem facade identity, and shared error helper prefixes. |
| `test_edition_fetcher.py` | `lib/editions/fetcher/` — ayah condition building | Tests SQL condition building, range detection, edition filtering. |
| `test_edition_registry.py` | `lib/editions/registry.py` — edition resolution | Tests exact/code/language/fuzzy resolution, case insensitivity, unresolved tracking. |
| `test_grounding_gate.py` | `middleware/grounding_gate.py` — nonce lifecycle | Tests nonce issuance, validation, XML stripping, LRU eviction, authority-A, warning dedup. |
| `test_grounding_nonce_edge_cases.py` | Grounding nonce edge cases | Tests nonce reuse across tools, nonce-free fallback behavior. |
| `test_search_common.py` | `lib/search/common.py` — search utilities | Tests language detection, ayah key parsing, filter building, memory-to-data conversion. |
| `test_tafsir_html_clean.py` | Tafsir HTML cleaning | Tests tag stripping, entity decoding, footnote formatting. |
| `test_documentation_generator.py` | `lib/documentation/generator.py` — pure data utilities | Tests _type_label (12 branches), string truncation, list compaction, display transform, tag filtering, parameter rows, colorize_call, colorize_json_value. |
| `test_qmd_parser.py` | `lib/documentation/qmd_parser.py` — QMD → HTML conversion | Tests frontmatter splitting, body block conversion, verse rendering, table rendering, inline text/typography, end-to-end parse_qmd with real QMD file. |
| `test_editions_list.py` | `mcp/tools/editions/list.py` — list_editions tool logic | Tests type normalization, dedup, language filtering, sorting, response shape via FastMCP Client. |
| `test_metadata_validation.py` | `mcp/tools/metadata/fetch.py` — validation and tool contract | Tests validation rules, service-unavailable/error prefixes, and a successful structured metadata response via FastMCP Client with stub lifespan. |
| `test_mushaf_tools.py` | `mcp/tools/mushaf/{show,fetch}.py` — tool error contract and success paths | Tests invalid-request/service-unavailable envelopes plus successful structured mushaf responses for both app-facing tool wrappers. |
| `test_concordance_logic.py` | `mcp/tools/morphology/concordance.py` — pure helpers | Tests _resolve_rerank_from (8-branch decision tree) and _enforce_concordance_token_cap (binary-search truncation). |
| `test_edition_fetcher_db.py` | `lib/editions/fetcher/db.py` — DB fetch backend | Tests two-step query (existence check + ayah fetch), UndefinedTableError fallback, metadata JSONB round-trip. |
| `test_edition_fetcher_dispatch.py` | `lib/editions/fetcher/__init__.py` — dispatch logic | Tests DB-first/GoodMem-fallback/error cascade, per-edition ownership, partial hit DataGap, mixed-source editions, logging assertions. |
| `test_concordance_query.py` | `lib/morphology/concordance_query.py` — text resolution | Tests linguistic ID lookup, dict_id normalization fallback, root space-stripping, not-found errors. |
| `test_morphology_query.py` | `lib/morphology/query.py` — verse/word resolution | Tests ayah_key parsing (valid/invalid/not-found), word-by-text exact match. |
| `test_paradigm_query.py` | `lib/morphology/paradigm_query.py` — lemma/root resolution | Tests lemma exact/normalized lookup, root space-stripping, segment fetch, not-found errors. |
| `test_fetch_orchestration_warnings.py` | `mcp/tools/_fetch_orchestration.py` — warning/helper functions | Tests build_fetch_warnings (gaps, unresolved, empty), canonicalize_editions, recompute_page_ayahs. |
| `test_translation_fetch_tool.py` | `mcp/tools/translation/fetch.py` — result projection | Tests _build_translation_results with single/multiple editions and empty input. |
| `test_page_planning.py` | `lib/presentation/page_planning.py` — token estimation and page sizing | Tests Arabic/English script detection, chars-per-token ratios, auto page size selection, token estimation. |
| `test_edition_entry.py` | `lib/editions/entry.py` — BaseFetchEntry normalization | Tests ayah_key/ayah alias, setter, no-key fallback. |
| `test_relay_usage_gap.py` | `mcp/tools/relay/usage_gap.py` — usage gap reporting | Tests pool-missing error, DB insert with mock, severity clamping. |
| `test_relay_user_feedback.py` | `mcp/tools/relay/user_feedback.py` — user feedback relay | Tests pool-missing error, DB insert with mock, severity clamping. |
