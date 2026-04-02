# Specification: Normalize Tafsir Data in PostgreSQL

## Metadata
- **ID**: spec-2026-03-26-tafsir-normalization-db
- **Status**: implemented
- **Created**: 2026-03-26

## Problem Statement

Tafsir entries in `edition_content` are duplicated per-ayah when a passage covers multiple ayahs. Ibn Kathir's commentary on 2:99-103 is stored as 4 identical rows, with `passage_ayah_range` metadata indicating the real scope. Across all tafsir editions: 81,932 rows, 68,159 unique passages, 13,773 duplicates.

The duplication was a workaround for GoodMem's HNSW post-filtering. Now that fetch uses PostgreSQL (Spec 0068), the workaround is unnecessary and complicates range queries.

## Desired State

- One row per unique tafsir passage (not per ayah)
- `ayah_start` and `ayah_end` columns for range-based filtering
- Range-overlap query: `WHERE ayah_start <= X AND ayah_end >= Y`
- Quran/translation entries unchanged (single-ayah, `ayah_start = ayah_end`)
- Fetcher remaps passage-range keys back to individual requested ayah keys (preserving interface contract)

## Solution

- Migration 017: add `ayah_start`/`ayah_end`, populate, dedup tafsir, change PK to `(edition_type, edition_id, ayah_key)`, drop `ayah` column
- `fetcher/db.py`: branch query by edition_type — range-overlap for tafsir, exact match for quran/translation
- Import script: dedup tafsir during import, add `ayah_start`/`ayah_end` to COPY columns

## Success Criteria
- [x] Migration applies cleanly on existing data
- [x] Tafsir rows deduplicated: 81,932 → 68,159
- [x] Quran/translation rows unchanged
- [x] `fetcher/db.py` handles both single-ayah and range queries
- [x] `fetch_tafsir("2:8-9", "en-ibn-kathir")` returns passage correctly
- [x] `fetch_quran("1:1", "ar-simple-clean")` still works (no regression)
- [x] Import script produces normalized data on reimport
- [x] All existing tests pass + new tests for range queries
- [x] Passage-range keys remapped to individual requested ayah keys (Warden catch)
- [x] 1280 tests pass

## Key Design Decision: Passage-Key Remapping

Warden identified during review that after normalization, tafsir `ayah_key` values are passage ranges (e.g., `"2:8-9"`) but `__init__.py._build_entries_from_found()` looks up individual ayah keys (e.g., `"2:8"`). The fix: `db.py` remaps passage-range keys back to individual requested ayah keys after the query, preserving the `fetch_from_db` return contract. `__init__.py` unchanged.
