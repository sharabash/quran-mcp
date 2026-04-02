# Plan: Normalize Tafsir Data in GoodMem

## Metadata
- **ID**: plan-2026-03-26-tafsir-normalization-goodmem
- **Status**: implemented
- **Specification**: codev/specs/0071-tafsir-normalization-goodmem.md
- **Created**: 2026-03-26

## Executive Summary

Deduplicate tafsir memories in GoodMem by creating a new normalized space via SQL-level copy operations. No re-embedding. No API calls. Embedding vectors carried over from the original space. Validated end-to-end on production.

## Phases (Machine Readable)

```json
{
  "phases": [
    {"id": "normalize", "title": "Phase 1: Create normalized tafsir space", "status": "completed"}
  ]
}
```

## Phase 1: Create Normalized Tafsir Space
**Dependencies**: None (operates on existing GoodMem production DB)

### Deliverables
- [x] New `tafsir` space with deduplicated memories
- [x] All chunks and pointers copied with correct metadata
- [x] Original `openai-tafsir` space preserved as backup
- [x] Exhaustive validation (25+ tests)

### Implementation Steps

1. **Create space**: INSERT into `goodmem.space` duplicating `openai-tafsir` config
2. **Link embedder**: INSERT into `goodmem.space_embedder` (triggers partition creation)
3. **Copy deduplicated memories**: CTE groups by (edition_id, content_sha256), picks first ayah_key per group, inserts with updated metadata (integer types, ayah_start/ayah_end)
4. **Copy memory_chunks**: Map old memory_id → new memory_id via (edition_id, content_sha256), bulk INSERT
5. **Copy dense_chunk_pointers**: Map old chunk_id → new chunk_id via (memory mapping + chunk_sequence_number), bulk INSERT with embedding vectors and updated metadata
6. **Validate**: 25 tests covering counts, integrity, metadata shape, semantic search, filtered search, production safety

### Acceptance Criteria
- [x] 67,818 memories (from 81,932)
- [x] 132,149 chunks and pointers each
- [x] All 14 editions match unique passage counts
- [x] Zero orphans, zero bad ranges, zero duplicates
- [x] Semantic search ranks target chunks correctly
- [x] Range-overlap filter works
- [x] Production untouched

## Remaining Work

- [x] Update server config to use new `tafsir` space for search (config.local.yml swapped)
- [x] Update search result parsing for range-format ayah_keys (search.py fixed)
- [x] Clean redundant metadata from normalized space (67,818 memories + 132,149 pointers)
- [ ] A/B test search quality: same queries against old vs new space
- [ ] After validation period, consider decommissioning `openai-tafsir` space

## Amendment History

### TICK-001: Complete Remaining Work (2026-03-26)

**Changes**:
- Phase 2 added: metadata cleanup + search parsing + config swap
  1. Clean redundant metadata from `tafsir` space (remove `passage_ayah_key`, `passage_ayah_range`, `ayah` fields — superseded by `ayah_start`/`ayah_end`)
  2. Fix `search_tafsir` result parsing: `parse_ayah_key("2:8-9")` fails on range-format keys. Update to handle `"surah:start-end"` format or use `ayah_start`/`ayah_end` metadata directly.
  3. Update `_OVERFETCH_MULTIPLIER` or comment — dedup overfetch is no longer needed with normalized space.
  4. Swap `config.local.yml` `goodmem.space.tafsir` from `openai-tafsir` to `tafsir` (local dev). Production Hetzner config.local.yml updated separately.
  5. A/B test: run same search queries against both spaces, compare result quality.
