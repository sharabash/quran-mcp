# Plan: Normalize Tafsir Data in PostgreSQL

## Metadata
- **ID**: plan-2026-03-26-tafsir-normalization-db
- **Status**: implemented
- **Specification**: codev/specs/0070-tafsir-normalization-db.md
- **Created**: 2026-03-26

## Phases (Machine Readable)

```json
{
  "phases": [
    {"id": "normalize-db", "title": "Phase 1: Schema migration + fetcher + import", "status": "completed"}
  ]
}
```

## Phase 1: Schema Migration + Fetcher + Import
**Dependencies**: Spec 0068 (edition_content table exists)

### Deliverables
- [x] `src/quran_mcp/lib/db/migrations/017_edition_content_normalize.sql`
- [x] `src/quran_mcp/lib/editions/fetcher/db.py` — tafsir range-overlap query + passage-key remapping
- [x] `scripts/.maintainer/import_edition_content_from_ndjson.py` — tafsir dedup + ayah_start/ayah_end
- [x] `tests/test_edition_fetcher_db.py` — updated for range-aware tafsir

### Acceptance Criteria
- [x] Tafsir 81,932 → 68,159 rows
- [x] Quran/translation unchanged
- [x] Range-overlap query works (requesting ayah 7:71 finds passage 7:70-72)
- [x] Passage-key remapping: "2:8-9" passage returned under both "2:8" and "2:9" keys
- [x] PK changed to (edition_type, edition_id, ayah_key)
- [x] 1280 tests pass
