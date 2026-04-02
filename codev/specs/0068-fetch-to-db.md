# Specification: Migrate Fetch Tools from GoodMem to PostgreSQL

## Metadata
- **ID**: spec-2026-03-25-fetch-to-db
- **Status**: implemented
- **Created**: 2026-03-25

## Clarifying Questions Asked

1. **Should GoodMem be removed entirely?** No. GoodMem remains required for search tools and available as a fallback for fetch in production. This migration scopes strictly to fetch tools.

2. **Should the NDJSON metadata be normalized into columns?** No. Store the full metadata as a JSONB column. Different edition types have different metadata shapes — quran has `qf_resource_id`, tafsir has `tafsir_row_id`/`passage_ayah_range`/`citation_url`, translation has `translation_row_id`. A single JSONB column handles this cleanly.

3. **Should we add GIN indexes on metadata paths (lang, code, qf_resource_id)?** No. The edition registry (`lib/editions/registry.py`) resolves all fuzzy/code/language-based lookups in-memory before the fetcher is called. The DB is only ever queried by exact `edition_type` + `edition_id` + surah/ayah range — all extracted columns with BTREE indexes. Language is also encoded in the `edition_id` itself (e.g. `ar-simple-clean`). GoodMem uses full GIN on metadata because it's a generic memory store; our table is purpose-built.

4. **Should Spec 0067 be brought into this repo?** No. It references private projects, targets the original codebase, and is under an off-limits constraint due to a prior regression.

## Problem Statement

quran-mcp's fetch tools depend on GoodMem — an external semantic memory service — for all content retrieval. But the fetch path uses GoodMem purely as a key-value store: build metadata filter expression (edition_type + edition_id + surah + ayah range), exact match, return content. No embeddings, no semantic search, no reranking.

This means:
- **Heavy dependency for a simple operation**: A new contributor cannot `git clone && docker compose up` and have working fetch tools — they need a running GoodMem instance with loaded data.
- **Unnecessary network overhead**: Every fetch is a GoodMem API round-trip for what should be a local database query.
- **Coupling to a private service**: GoodMem is not open-source. An open-source MCP server shouldn't require a private service for basic content retrieval.

Search tools (search_quran, search_translation, search_tafsir) legitimately use GoodMem's semantic retrieval and remain GoodMem-dependent. This spec does not address search.

## Current State

### Fetch Pipeline
```
MCP tool handler -> lib/{domain}/fetch.py -> EditionFetcher._fetch_for_edition() -> GoodMem search_memories()
```

- `EditionFetcher` (in `lib/editions/fetcher.py`) builds GoodMem filter expressions and calls `goodmem_cli.search_memories()`
- Each library-level caller (`lib/quran/fetch.py`, `lib/translation/fetch.py`, `lib/tafsir/fetch.py`) creates an `EditionFetcherConfig` with `goodmem_space` and `entry_factory`
- The fetcher iterates results, extracting `memory.content` and `memory.metadata` keyed by `ayah_key`
- `AppContext` provides both `goodmem_cli` and `db_pool` — db_pool exists but is only used for reference data (chapters, verses metadata, morphology)

### Data Corpus
NDJSON files at `../quran-mcp.original/data/goodmem/`:
- `quran.ndjson` — 43,652 records (7 editions x 6,236 ayahs)
- `translation.ndjson` — 193,316 records (31 editions x 6,236 ayahs)
- `tafsir.ndjson` — 85,855 records (14 editions x 6,236 ayahs, up to 53KB HTML per entry)

Each record: `{"content": "...", "metadata": {"edition_type", "edition_id", "surah", "ayah", "ayah_key", ...}}`

### GoodMem Production Index Strategy (inspected on Hetzner)
GoodMem's `dense_chunk_pointer` table uses:
- **PK**: `(embedder_id, space_id, pointer_id)` — double LIST-partitioned
- **GIN**: `gin(metadata)` on every partition — the workhorse for filter DSL queries
- **HNSW**: `hnsw(embedding_vector vector_ip_ops)` on leaf partitions — for semantic search only
- 318,900 memories across 3 quran spaces (openai-quran: 43,652, openai-tafsir: 81,932, openai-translation: 193,316)

GoodMem uses full GIN because it's a generic memory store. Our table is purpose-built with extracted columns — BTREE is strictly better for our access pattern.

## Desired State

### Fetch Pipeline (after)
```
MCP tool handler -> lib/{domain}/fetch.py -> EditionFetcher._fetch_for_edition() -> DB query (primary) | GoodMem (fallback)
```

- Fetch tools query PostgreSQL `edition_content` table first
- If DB has data for the requested edition -> use it (zero network overhead, sub-millisecond)
- If DB has no data and `goodmem_cli` is available -> fall back to GoodMem (current behavior)
- If neither -> raise `DataStoreError` with a clear message about running the data load script

### Fallback Semantics (per multi-agent consultation)

**Fallback granularity is per-edition, not per-ayah.** If the DB has ANY rows for an `(edition_type, edition_id)` pair, the DB owns that edition — partial results return a `DataGap`, NOT a mixed-source GoodMem supplementation. Fallback to GoodMem only triggers when the DB has ZERO rows for the requested edition.

Rationale: Mixed-source responses (some ayahs from DB, some from GoodMem) create freshness inconsistencies and hidden operational drift. A partial dump is a data loading issue, not a fetch logic issue.

**Observability**: Log which source was used (DB vs GoodMem) at INFO level for every `_fetch_for_edition` call. If the DB path is skipped due to missing table or missing edition, log at WARNING. This prevents silent fallback from masking broken migrations.

### Developer Experience (after)
```bash
git clone https://github.com/sharabash/quran-mcp
# download partial dump to .db/
docker compose up -d
# fetch_quran("1:1", "ar-simple-clean") works immediately
```

No GoodMem instance needed. No API keys. Just PostgreSQL + a data dump.

## Stakeholders
- **Primary Users**: Contributors/forkers who clone the repo and want working fetch tools
- **Secondary Users**: Production deployment (continues using GoodMem, gains DB fallback)
- **Technical Team**: AI agent team (Conductor/Mason/Sentinel/Warden)
- **Business Owner**: Nour (maintainer)

## Success Criteria
- [x] `docker compose up` on a fresh clone with partial dump loads data and serves fetch requests
- [x] `fetch_quran("1:1", "ar-simple-clean")` returns bismillah from PostgreSQL, not GoodMem
- [x] `fetch_tafsir("2:255", "en-ibn-kathir")` returns tafsir with correct `citation_url` and `passage_ayah_range`
- [x] Existing GoodMem-based tests pass unchanged (they set `db_pool=None`, hitting GoodMem path)
- [x] Fallback works: if edition not in DB but GoodMem available, GoodMem is used
- [x] Error case: if neither DB nor GoodMem available, clear `DataStoreError` raised
- [x] No changes to MCP tool handlers or fetch orchestration layer
- [x] No changes to entry factories -- they receive `(ayah_key, content, metadata)` regardless of source
- [x] Search tools remain unaffected and GoodMem-dependent
- [x] All tests pass, new tests cover DB fetcher and dispatch logic

## Constraints

### Technical Constraints
- PostgreSQL with `quran_mcp` schema (not public) -- all tables there
- Latest migration is `015_provider_continuity_token.sql` -- next is `016`
- NDJSON files are in `../quran-mcp.original/data/goodmem/`, not in this repo
- `scripts/.maintainer/` is gitignored -- maintainer scripts don't ship to forkers
- `.db/*.sql.gz` is gitignored -- dumps are downloaded, not committed
- Docker init scripts run via `docker-entrypoint-initdb.d/` on fresh volumes only
- `asyncpg` is the database driver (already in dependencies)

### Scope Constraints
- Fetch tools ONLY -- search tools remain GoodMem-dependent
- No changes to `mcp/tools/` layer or `_fetch_orchestration.py`
- No changes to `lib/quran/fetch.py`, `lib/translation/fetch.py`, `lib/tafsir/fetch.py` (interface stability)
- No changes to `EditionFetcherConfig` interface (DB fetcher ignores `goodmem_space` and `chunk_multiplier` -- these become vestigial in DB mode, which is acceptable and intentional)
- Do not touch `codev/specs/` or `codev/plans/` related to Spec 0067

## Assumptions
- The NDJSON corpus files are complete and correct (sourced from Quran Foundation)
- PostgreSQL is always available in docker compose (it already is -- `db` service exists)
- `db_pool` on `AppContext` is available when the DB is configured
- The edition registry in-memory resolution is authoritative -- the DB never needs fuzzy matching

## Solution Approaches

### Approach 1: Single `edition_content` Table with JSONB Metadata (Recommended)

**Description**: One table for all three content types (quran, translation, tafsir). Key filter fields extracted as columns for BTREE indexing. Full NDJSON metadata preserved as JSONB.

**Schema**:
- `edition_type TEXT NOT NULL CHECK (edition_type IN ('quran', 'translation', 'tafsir'))`
- `edition_id TEXT NOT NULL` -- e.g. 'ar-simple-clean'
- `surah SMALLINT NOT NULL`, `ayah SMALLINT NOT NULL`
- `ayah_key TEXT NOT NULL` -- denormalized, must equal `surah || ':' || ayah`
- `content TEXT NOT NULL`
- `metadata JSONB NOT NULL DEFAULT '{}'`
- `PRIMARY KEY (edition_type, edition_id, surah, ayah)`

**Constraints** (per multi-agent consultation):
- CHECK constraint on `edition_type` to enforce valid values
- `ayah_key` consistency: must match `surah:ayah` (validated at import time, not via CHECK — the string format `surah:ayah` doesn't map cleanly to a SQL expression)
- No GIN index on metadata JSONB — this is a deliberate design constraint, not an omission. Future callers that need metadata-level queries must add dedicated indexes or accept table scans.

**Pros**:
- Matches GoodMem's single-table-per-space pattern
- BTREE on extracted columns is faster than GIN on JSONB for our exact access pattern
- JSONB preserves all metadata without schema rigidity
- ~320K rows -- trivially small for PostgreSQL

**Cons**:
- Metadata duplication (surah/ayah in both columns and JSONB) -- acceptable for a 320K row table

**Estimated Complexity**: Medium
**Risk Level**: Low

### Approach 2: Three Separate Tables (Rejected)

**Description**: `quran_content`, `translation_content`, `tafsir_content` -- each with type-specific columns.

**Pros**: Tafsir-specific columns (passage_ayah_range, citation_url) as first-class columns

**Cons**: Triple the migration/query/maintenance surface for negligible benefit. The fetcher already parameterizes by `edition_type` -- one table with a type discriminator is simpler.

**Rejected**: Over-engineering for 320K rows with uniform access patterns.

## Open Questions

### Critical (Blocks Progress)
- [x] Should metadata be JSONB or individual columns? -> JSONB (per user direction)
- [x] Should we add GIN on metadata? -> No (BTREE on extracted columns covers all fetch queries)

### Important (Affects Design)
- [x] Fetcher refactoring: package or flat files? -> Package (`fetcher/` with `__init__.py`, `base.py`, `db.py`, `goodmem.py`)
- [x] DB query layer placement: `lib/db/` or `lib/editions/`? -> In `fetcher/db.py` -- straight asyncpg queries, no intermediate abstraction

### Nice-to-Know (Optimization)
- [x] Should we support multi-edition DB queries (`edition_id = ANY($2)`)? -> Design the `fetcher/db.py` interface to accept `edition_id` lists even if iterating internally for now. Future-proofing without premature optimization.

## Performance Requirements
- **Fetch latency**: Sub-millisecond for typical requests (1-10 ayahs, single edition) -- down from ~50-200ms GoodMem round-trip
- **Maximum query size**: 300 ayahs (existing `MAX_AYAHS_PER_QUERY` limit)
- **Data load time**: Maintainer import of full corpus (320K rows) should complete in <60 seconds
- **Docker init**: Dump load on fresh volume should complete in <30 seconds

## Security Considerations
- No new attack surface -- the DB is internal to docker compose, not exposed
- SQL queries use parameterized queries (`$1`, `$2`, etc.) via asyncpg -- no injection risk
- NDJSON import script validates JSON structure before inserting

## Test Scenarios

### Functional Tests
1. DB has data for requested edition -> returns entries from DB
2. DB has no data, GoodMem available -> falls back to GoodMem
3. DB has no data, GoodMem unavailable -> raises DataStoreError
4. Tafsir entries have correct citation_url and passage_ayah_range from metadata JSONB
5. Partial data: some ayahs in DB, some missing -> returns found + reports gaps
6. Multiple editions in single fetch -> each resolved independently

### Non-Functional Tests
1. Fetch 300 ayahs (max range) completes in <50ms from DB
2. Import script handles 389MB tafsir NDJSON without OOM (streaming)
3. Existing GoodMem-path tests pass unchanged with `db_pool=None`

## Dependencies
- **External Services**: None (that's the point -- removing GoodMem dependency for fetch)
- **Internal Systems**: PostgreSQL (`db` service in docker-compose), asyncpg pool
- **Libraries**: asyncpg (already installed), no new dependencies

## Risks and Mitigation

| Risk | Probability | Impact | Mitigation Strategy |
|------|------------|--------|-------------------|
| DB table missing at runtime | Low | Low | `fetch_edition_from_db` returns None on UndefinedTableError -> GoodMem fallback. Log at WARNING to prevent silent masking of broken migrations. |
| Data freshness divergence (DB snapshot vs live GoodMem) | Medium | Low | Dump script is easy to re-run; cascade means GoodMem picks up editions not in DB |
| Split-brain: search finds content that fetch can't retrieve | Medium | Medium | Document that NDJSON corpus, GoodMem data, and DB dumps must be updated in sync. Maintainer import script is the single source of truth. |
| Existing tests break from dispatch logic | Low | Medium | Tests with `db_pool=None` skip DB path entirely -- no behavior change |
| 389MB tafsir file causes OOM during import | Medium | Low | Stream line-by-line, batch inserts, never load full file into memory |
| Metadata fidelity loss from JSONB round-trip | Low | Low | JSONB preserves full dict; entry factories only read specific keys |

## References
- GoodMem production DB schema (inspected on Hetzner, 2026-03-25)
- Existing fetcher: `src/quran_mcp/lib/editions/fetcher.py`
- Edition registry resolution: `src/quran_mcp/lib/editions/registry.py`
- NDJSON corpus: `../quran-mcp.original/data/goodmem/{quran,translation,tafsir}.ndjson`

## Expert Consultation

**Date**: 2026-03-25
**Models Consulted**: GPT-5.4 (for), Gemini 3.1 Pro (against/devil's advocate)
**Consensus Score**: 8.5/10 (GPT-5.4: 8/10, Gemini Pro: 9/10)

**Sections Updated**:
- **Desired State**: Added "Fallback Semantics" section — per-edition fallback granularity, no mixed-source responses, observability logging requirements
- **Solution Approaches**: Added CHECK constraint on `edition_type`, ayah_key consistency validation note, explicit "no GIN" design constraint documentation
- **Open Questions**: Resolved multi-edition query interface question — future-proof db.py to accept lists
- **Risks and Mitigation**: Upgraded "DB table missing" impact from None to Low with WARNING log requirement; added split-brain risk for search/fetch data divergence
- **Scope Constraints**: Documented `goodmem_space`/`chunk_multiplier` as intentionally vestigial in DB mode

**Key consensus finding**: Both models independently identified the same critical gap — partial DB hits must NOT trigger GoodMem supplementation. Fallback is per-edition (zero rows = fallback), not per-ayah.

## Approval
- [x] Technical Lead Review
- [x] Expert AI Consultation Complete

## Amendments

### TICK-002: One-Shot Collaborator Setup (2026-03-27)

**Summary**: Bootstrap script downloads corpus dumps from GitHub Release and starts the full local stack in one command.

**Problem Addressed**: The spec promised "a stranger can clone the repo, docker compose up, and have working fetch tools" but the dumps had no distribution mechanism. Contributors had to manually find and download them.

**Spec Changes**:
- Developer Experience section fulfilled: `./scripts/setup/bootstrap.sh` is the one-shot command

**Plan Changes**:
- New deliverable: `scripts/setup/bootstrap.sh`
- Updated `docs/SETUP.md` with two-path setup guide (build on top vs collaborator)
