# Plan: Migrate Fetch Tools from GoodMem to PostgreSQL

## Metadata
- **ID**: plan-2026-03-25-fetch-to-db
- **Status**: implemented
- **Specification**: codev/specs/0068-fetch-to-db.md
- **Created**: 2026-03-25

## Executive Summary

Migrate fetch tools from GoodMem to PostgreSQL using the spec's recommended Approach 1: single `edition_content` table with JSONB metadata. Four sequential phases, each independently committable. The fetcher is refactored into a package before the DB backend is added, keeping the pure-refactor phase separate from the behavior-change phase.

## Success Metrics
- [x] All specification success criteria met (10 checkboxes in spec)
- [x] Existing tests pass unchanged throughout all phases
- [x] New tests cover DB fetcher, dispatch logic, and fallback behavior
- [x] `docker compose up` with partial dump serves fetch requests from PostgreSQL

## Phases (Machine Readable)

```json
{
  "phases": [
    {"id": "schema-infra", "title": "Phase 1: Database Schema & Bootstrap Infrastructure", "status": "completed"},
    {"id": "data-pipeline", "title": "Phase 2: Data Import Pipeline", "status": "completed"},
    {"id": "fetcher-refactor", "title": "Phase 3: Fetcher Package Refactoring", "status": "completed"},
    {"id": "db-backend", "title": "Phase 4: DB Backend & Dispatch Logic", "status": "completed"}
  ]
}
```

## Phase Breakdown

### Phase 1: Database Schema & Bootstrap Infrastructure
**Dependencies**: None

#### Objectives
- Create the `edition_content` table via migration
- Modernize the Docker init pipeline to support edition content dumps
- Remove redundant setup script

#### Deliverables
- [x] `src/quran_mcp/lib/db/migrations/016_edition_content.sql`
- [x] `.db/init_db.sh` (renamed from `load_corpus.sh`, extended for edition content dumps)
- [x] `docker-compose.yml` updated (volume mount references new filename + dump files)
- [x] `scripts/setup/load_quran_com_data.py` deleted
- [x] `scripts/setup/README.md` updated (entry removed)

#### Implementation Details

**Migration `016_edition_content.sql`**:
```sql
CREATE TABLE quran_mcp.edition_content (
    edition_type TEXT NOT NULL CHECK (edition_type IN ('quran', 'translation', 'tafsir')),
    edition_id   TEXT NOT NULL,
    surah        SMALLINT NOT NULL,
    ayah         SMALLINT NOT NULL,
    ayah_key     TEXT NOT NULL,
    content      TEXT NOT NULL,
    metadata     JSONB NOT NULL DEFAULT '{}',
    PRIMARY KEY (edition_type, edition_id, surah, ayah)
);

-- NOTE: No idx_edition_content_lookup needed — PK already provides this exact BTREE.

CREATE INDEX idx_edition_content_ayah_key
    ON quran_mcp.edition_content (edition_type, edition_id, ayah_key);
```

**Rename `.db/load_corpus.sh` -> `.db/init_db.sh`**:
- Keep existing quran_com_data load logic
- Add edition content dump loading after quran_com_data
- Priority: `quran_mcp_edition_content.full.sql.gz` > `quran_mcp_edition_content.partial.sql.gz`
- Skip gracefully if neither exists (same pattern as current quran_com_data handling)

**Docker-compose volume mounts**:
- `.db/init_db.sh` -> `02-init-db.sh` (was `02-load-corpus.sh`)
- Add conditional mounts for edition content dump files

**Prune `scripts/setup/load_quran_com_data.py`**: Delete (redundant with init_db.sh).

#### Acceptance Criteria
- [x] Migration applies cleanly on fresh docker volume
- [x] `\d quran_mcp.edition_content` shows correct schema with CHECK constraint
- [x] `init_db.sh` loads quran_com_data.sql.gz (existing behavior preserved)
- [x] `init_db.sh` skips edition content load gracefully when dumps absent
- [x] Dump precedence: when both full and partial exist, full is loaded (partial ignored)
- [x] init_db.sh has executable permissions and runs correctly under docker-entrypoint-initdb.d ordering
- [x] Existing tests pass (no behavior change)

#### Test Plan
- **Manual Testing**: `docker compose down -v && docker compose up -d`, verify migration in logs, verify table exists via psql

#### Rollback Strategy
Drop migration 016, revert init_db.sh rename, restore load_quran_com_data.py.

---

### Phase 2: Data Import Pipeline
**Dependencies**: Phase 1 (table must exist)

#### Objectives
- Create maintainer script to import NDJSON corpus into `edition_content` table
- Generate full and partial SQL dumps for distribution

#### Deliverables
- [x] `scripts/.maintainer/import_edition_content_from_ndjson.py`
- [x] `scripts/.maintainer/README.md` updated
- [x] `.db/quran_mcp_edition_content.full.sql.gz` generated (gitignored)
- [x] `.db/quran_mcp_edition_content.partial.sql.gz` generated (gitignored)

#### Implementation Details

**Import script** (`scripts/.maintainer/import_edition_content_from_ndjson.py`):
- Accepts `--data-dir` path (default: `../quran-mcp.original/data/goodmem/`)
- Streams NDJSON line-by-line (handles 389MB tafsir without OOM)
- Batched inserts (1000 rows per batch) via `COPY` or `executemany`
- Idempotent: `DELETE FROM edition_content WHERE edition_type=$1 AND edition_id=$2` per edition before reimport (handles orphan removal cleanly), then batch INSERT. Preferred over ON CONFLICT DO UPDATE because upsert is append-only and leaves orphaned rows if NDJSON shrinks.
- Validates `ayah_key` consistency: must equal `{surah}:{ayah}`
- Auto-detects docker exec vs direct psql (reuse pattern from existing dump script)
- Progress reporting: record count per file
- `--dump` flag: after import, produce SQL dumps
- `--partial-only` flag: only dump the curated subset

**Partial dump editions** (from spec):
- ar-simple-clean, ar-uthmani-minimal
- en-abdel-haleem, en-sahih-international
- en-ibn-kathir, ar-qurtubi, ar-kashaf, ar-tahrir-wa-tanwir, ar-nathm-aldurar

#### Acceptance Criteria
- [x] Import completes for all three NDJSON files without error
- [x] Row counts match: quran ~43,652, translation ~193,316, tafsir ~85,855
- [x] Full dump file exists at `.db/quran_mcp_edition_content.full.sql.gz`
- [x] Partial dump loads on fresh volume via init_db.sh
- [x] Reimport (idempotency) succeeds without errors

#### Test Plan
- **Manual Testing**: Run import against `../quran-mcp.original/data/goodmem/`, verify counts, generate dumps, test dump load on fresh docker volume

#### Rollback Strategy
`TRUNCATE quran_mcp.edition_content;` — data-only, no schema changes in this phase.

---

### Phase 3: Fetcher Package Refactoring
**Dependencies**: None (pure refactor, no dependency on Phase 1/2)

#### Objectives
- Convert `lib/editions/fetcher.py` into a `lib/editions/fetcher/` package
- Extract GoodMem logic into its own module
- Zero behavior change — pure structural refactor

#### Deliverables
- [x] `src/quran_mcp/lib/editions/fetcher/` package created:
  - `__init__.py` — re-exports `EditionFetcher`, `EditionFetcherConfig`, `FetchResult`, `MAX_AYAHS_PER_QUERY`
  - `base.py` — `EditionFetcherConfig`, `FetchResult`, `MAX_AYAHS_PER_QUERY`, `_validate_range_count`, shared `_build_ayah_conditions` logic
  - `goodmem.py` — GoodMem-specific fetch logic (extracted from current `_fetch_for_edition`)
- [x] `src/quran_mcp/lib/editions/fetcher.py` deleted (replaced by package)
- [x] `src/quran_mcp/lib/editions/__init__.py` updated if needed (imports from fetcher package)
- [x] All existing tests pass unchanged

#### Implementation Details

**`base.py`**: Shared types and utilities.
- Move `EditionFetcherConfig`, `FetchResult` dataclasses here
- Move `MAX_AYAHS_PER_QUERY` constant and `_validate_range_count` method
- Move `_build_ayah_conditions` here (will be reused by db.py in Phase 4 for SQL WHERE clause generation)

**`goodmem.py`**: GoodMem backend.
- Move `_fetch_for_edition` GoodMem logic (filter building, search_memories call, result parsing)
- Move `_build_edition_filter` (GoodMem DSL-specific)
- Keep all GoodMem imports (`build_filter_expression`, `parse_filter_string`)
- Single async function: `fetch_from_goodmem(goodmem_cli, config, ayah_list, edition_id) -> tuple[list[Any], DataGap | None]`

**`__init__.py`**: Public API — `EditionFetcher` class.
- The `EditionFetcher` class lives here
- `fetch()` method unchanged (iterates editions, calls `_fetch_for_edition`)
- `_fetch_for_edition` delegates to `goodmem.fetch_from_goodmem` (for now — Phase 4 adds DB dispatch)
- Re-exports: `EditionFetcher`, `EditionFetcherConfig`, `FetchResult`, `MAX_AYAHS_PER_QUERY`

**Import compatibility**: Any code that does `from quran_mcp.lib.editions.fetcher import X` must still work via the package `__init__.py` re-exports.

#### Acceptance Criteria
- [x] All existing tests pass with zero changes
- [x] `from quran_mcp.lib.editions.fetcher import EditionFetcher, EditionFetcherConfig, FetchResult` still works
- [x] `lib/quran/fetch.py`, `lib/translation/fetch.py`, `lib/tafsir/fetch.py` unchanged
- [x] `lib/editions/types.py` lazy import of `EditionFetcher` still resolves

#### Test Plan
- **Unit Tests**: Run full existing test suite — any failure means the refactor broke something
- **Manual Testing**: `python -c "from quran_mcp.lib.editions.fetcher import EditionFetcher, EditionFetcherConfig, FetchResult; print('OK')"`

#### Rollback Strategy
Restore `fetcher.py` from git, delete `fetcher/` directory.

---

### Phase 4: DB Backend & Dispatch Logic
**Dependencies**: Phase 1 (table), Phase 2 (data), Phase 3 (package structure)

#### Objectives
- Implement PostgreSQL fetch backend
- Add dispatch logic: DB first -> GoodMem fallback -> error
- Add fallback observability logging
- Write comprehensive tests

#### Deliverables
- [x] `src/quran_mcp/lib/editions/fetcher/db.py` — DB fetch backend
- [x] `src/quran_mcp/lib/editions/fetcher/__init__.py` — updated with dispatch logic
- [x] `src/quran_mcp/lib/editions/errors.py` — updated error message ("Data store" not "GoodMem")
- [x] `tests/test_edition_fetcher_db.py` — unit tests for DB backend
- [x] `tests/test_edition_fetcher_dispatch.py` — dispatch/fallback tests
- [x] `tests/integration/test_fetch_db_e2e.py` — E2E through MCP stack
- [x] Test directory READMEs updated

#### Implementation Details

**`fetcher/db.py`**: DB backend.
```python
async def fetch_from_db(
    db_pool: asyncpg.Pool,
    edition_type: str,
    edition_id: str,
    ayah_list: list[str],
) -> dict[str, tuple[str, dict]] | None:
    """Fetch edition content from PostgreSQL.

    Returns:
        dict mapping ayah_key -> (content, metadata_dict), or
        None if edition_content table doesn't exist or has zero rows for this edition.
    """
```

**Two-step query** (per multi-agent consultation — critical for correct fallback):

Step 1 — Edition existence check:
```sql
SELECT EXISTS (
    SELECT 1 FROM quran_mcp.edition_content
    WHERE edition_type = $1 AND edition_id = $2
    LIMIT 1
)
```
If False -> return `None` (edition not loaded, signals fallback to GoodMem).

Step 2 — Ayah fetch (only if edition exists):
```sql
SELECT ayah_key, content, metadata
FROM quran_mcp.edition_content
WHERE edition_type = $1 AND edition_id = $2 AND ayah_key = ANY($3::text[])
```

**Why two steps**: A single query returning zero rows cannot distinguish "edition not loaded" from "requested ayahs don't exist in a loaded edition." Without the existence check, requesting out-of-bounds ayahs for a loaded edition would falsely trigger GoodMem fallback, violating the spec's per-edition ownership rule.

- Returns `None` on `asyncpg.UndefinedTableError` (table doesn't exist yet) -> signals fallback
- Returns `None` if edition not in DB (existence check False) -> signals fallback
- Returns `dict` (possibly with fewer entries than requested) if edition exists -> DB owns it, partial results return DataGap, NO GoodMem supplementation
- Other asyncpg errors propagate as `DataStoreError`
- Interface accepts `edition_id` as single string (iterate externally) but internal SQL supports `ANY` for future batch use

**Dispatch logic in `fetcher/__init__.py`**: Update `_fetch_for_edition`:
```python
async def _fetch_for_edition(self, ctx, ayah_list, edition_id):
    # 1. Try DB if pool available
    if ctx.db_pool is not None:
        from .db import fetch_from_db
        db_result = await fetch_from_db(ctx.db_pool, self.config.edition_type, edition_id, ayah_list)
        if db_result is not None:
            logger.info(f"DB fetch: {self.config.edition_type}/{edition_id}, {len(db_result)} entries")
            return self._build_entries_from_found(db_result, ayah_list, edition_id)
        else:
            logger.warning(f"DB fetch skipped (no data): {self.config.edition_type}/{edition_id}, falling back")

    # 2. GoodMem fallback
    if ctx.goodmem_cli is not None:
        return await self._fetch_from_goodmem(ctx, ayah_list, edition_id)

    # 3. Neither
    raise DataStoreError(operation="fetch", cause=RuntimeError("No data backend available"))
```

**Fallback semantics** (per spec): Per-edition, not per-ayah. If DB returns any data for this edition, DB owns it — partial results generate `DataGap`, no GoodMem supplementation.

**`errors.py`**: Change `DataStoreError.__init__` message from `"GoodMem {operation} failed"` to `"Data store {operation} failed"`.

#### Acceptance Criteria
- [x] `fetch_quran("1:1", "ar-simple-clean")` returns bismillah from DB (not GoodMem)
- [x] `fetch_tafsir("2:255", "en-ibn-kathir")` returns tafsir with correct metadata from DB
- [x] With `db_pool=None`, existing GoodMem path works unchanged
- [x] With DB data + no GoodMem, fetch works from DB alone
- [x] With neither, `DataStoreError` raised with clear message
- [x] Fallback logged at WARNING when DB skipped
- [x] Source logged at INFO when DB or GoodMem used
- [x] Partial DB hit: DB has some ayahs for edition, missing ayahs -> DataGap returned, GoodMem NOT called
- [x] Multi-edition mixed-source: edition A in DB, edition B not in DB -> A from DB, B from GoodMem
- [x] Edition exists in DB but requested ayahs don't -> empty result with DataGap, NOT GoodMem fallback
- [x] All existing tests pass (they use `db_pool=None`)

#### Test Plan

**Unit Tests** (`tests/test_edition_fetcher_db.py`):
- DB returns rows -> verify entries built correctly with metadata from JSONB
- DB table missing (`UndefinedTableError`) -> returns None
- DB returns empty for this edition -> returns None
- DB connection error -> raises DataStoreError
- Tafsir metadata: citation_url and passage_ayah_range preserved through JSONB round-trip

**Dispatch Tests** (`tests/test_edition_fetcher_dispatch.py`):
- Both backends available, DB has data -> DB used, GoodMem NOT called
- DB returns None, GoodMem available -> GoodMem used (fallback)
- DB only (goodmem_cli=None), DB has data -> works
- GoodMem only (db_pool=None) -> existing behavior preserved
- Neither available -> DataStoreError
- **Partial DB hit**: DB has edition but not all requested ayahs -> DataGap, NO GoodMem supplementation
- **Mixed-source editions**: fetch 2 editions, one in DB one not -> A from DB, B from GoodMem
- **Edition exists, ayahs don't**: loaded edition, request non-existent ayahs -> empty + DataGap, NOT fallback
- **Logging assertions**: verify INFO log on DB fetch, WARNING log on fallback (use caplog)

**Integration Tests** (`tests/integration/test_fetch_db_e2e.py`):
- Full MCP stack test with real PostgreSQL + loaded edition_content
- fetch_quran, fetch_translation, fetch_tafsir return expected data from DB

#### Rollback Strategy
Revert fetcher/__init__.py dispatch to GoodMem-only. Delete db.py. Revert errors.py message. Delete test files.

---

## Dependency Map
```
Phase 1 (Schema) ──→ Phase 2 (Data Pipeline) ──→ Phase 4 (DB Backend)
                                                      ↑
                     Phase 3 (Fetcher Refactor) ──────┘
```

Phase 3 has no dependency on Phase 1/2 and can run in parallel. Phase 4 depends on all three.

## Resource Requirements
### Development Resources
- **Mason**: Implements each phase sequentially
- **Sentinel**: Reviews each phase's code quality
- **Warden**: Validates structural fit (especially Phase 3 package refactor and Phase 4 new module)

### Infrastructure
- PostgreSQL (existing `db` service in docker-compose)
- NDJSON corpus files at `../quran-mcp.original/data/goodmem/`
- No new services or dependencies

## Validation Checkpoints
1. **After Phase 1**: Migration applies, table exists, init_db.sh works
2. **After Phase 2**: Data imported, dumps generated, counts match NDJSON
3. **After Phase 3**: All existing tests pass, imports compatible
4. **After Phase 4**: DB fetch works, fallback works, full test suite green

## Monitoring and Observability
### Logging Requirements
- INFO: `"DB fetch: {edition_type}/{edition_id}, {count} entries"` on successful DB fetch
- INFO: `"GoodMem fetch complete: {edition_type}/{edition_id}, {count} entries"` (existing)
- WARNING: `"DB fetch skipped (no data): {edition_type}/{edition_id}, falling back"` when edition not in DB
- WARNING: `"DB fetch skipped (table missing), falling back"` when table doesn't exist

## Expert Review

**Date**: 2026-03-25
**Models Consulted**: GPT-5.4 (for, 8/10), Gemini 3.1 Pro (against, 9/10)
**Consensus Score**: 8.5/10

**Key Feedback**:
1. **CRITICAL BUG FIXED**: Edition existence check must be separate from ayah query — single query returning zero rows cannot distinguish "edition not loaded" from "requested ayahs don't exist." Added two-step query to Phase 4.
2. **Redundant index removed**: `idx_edition_content_lookup` duplicates PK BTREE — removed from Phase 1 migration.
3. **Import orphan handling**: Changed from ON CONFLICT DO UPDATE (append-only, leaves orphans) to DELETE+INSERT per edition.
4. **Acceptance criteria strengthened**: Added dump precedence, partial-hit, mixed-source, and logging assertion tests.
5. **Phase decomposition validated**: Both models endorsed the 4-phase structure, especially Phase 3 as a separate pure refactor.

**Plan Adjustments**:
- Phase 1: Removed redundant index, added dump precedence acceptance criteria
- Phase 2: Changed import strategy from upsert to delete+insert per edition
- Phase 4: Added two-step existence check, 4 new acceptance criteria, 4 new test cases

## Approval
- [x] Technical Lead Review
- [x] Expert AI Consultation Complete
