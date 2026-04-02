# Specification: Normalize Tafsir Data in GoodMem

## Metadata
- **ID**: spec-2026-03-26-tafsir-normalization-goodmem
- **Status**: implemented
- **Created**: 2026-03-26

## Problem Statement

Tafsir entries in GoodMem are duplicated per-ayah when a passage covers multiple ayahs. A mufassir's commentary on 2:99-103 is stored as 4 identical memories (one per ayah), each with its own chunks and embedding vectors. Across all 14 editions: 81,932 total memories, 67,818 unique passages, 14,114 duplicates (17.2%).

This wastes embedding storage, and more importantly degrades semantic search quality: duplicate memories consume top-K slots with redundant results, pushing out genuinely different relevant passages.

The duplication was originally a workaround for HNSW post-filtering limitations — more copies per passage meant more chances to survive the top-K cutoff when filtering by ayah number. But this trades search diversity for filter recall, and the trade-off is wrong: if a passage is semantically irrelevant to the query, having 5 copies doesn't make it relevant.

## Current State

- **openai-tafsir** space: 81,932 memories, 177,712 chunks, 177,712 dense_chunk_pointers
- Each duplicate memory has identical `original_content`, `original_content_sha256`, and `content_type`
- Metadata has `passage_ayah_range` (e.g., "2:8-9") indicating the real scope, but `ayah` is set to the individual ayah number
- `surah` and `ayah` metadata are stored as floats (e.g., `2.0`, `8.0`) — a data quality issue from the original ingestion

## Desired State

- **tafsir** space (new): ~67,818 deduplicated memories
- One memory per unique passage per edition
- Metadata includes `ayah_start` and `ayah_end` (integers) for range-based filtering
- `surah` and `ayah` metadata corrected to integers
- Embedding vectors copied from the original space (no re-embedding, $0 cost)
- Filter DSL uses range-overlap predicates: `ayah_start <= X AND ayah_end >= Y`
- Original `openai-tafsir` space preserved as backup

## Solution

SQL-level copy and deduplication. No GoodMem API calls. No re-embedding.

### Process

1. Create new `tafsir` space (same config as `openai-tafsir`)
2. Link to same embedder (triggers automatic partition creation)
3. For each (edition_id, content_sha256), select one representative memory (lowest ayah_key = passage start)
4. INSERT representative memories into new space with updated metadata:
   - `surah`: float → integer
   - `ayah`: set to passage start (integer)
   - `ayah_start`: parsed from `passage_ayah_range` (integer)
   - `ayah_end`: parsed from `passage_ayah_range` (integer)
5. Copy `memory_chunk` rows (map old memory_id → new memory_id via edition_id + content_sha256)
6. Copy `dense_chunk_pointer` rows with embedding vectors (map old chunk_id → new chunk_id via memory mapping + chunk_sequence_number, update space_id and metadata)
7. Validate: referential integrity, counts, metadata shape, semantic search quality, filtered search

### Key Findings

- **No re-embedding required**: Embedding vectors are copied as-is from `dense_chunk_pointer`. Semantic ranking quality preserved — validated by targeted chunk retrieval tests.
- **No triggers on memory INSERT**: GoodMem's embedding pipeline is application-driven (`bg_job`), not DB-triggered. Copying memories with `processing_status = 'COMPLETED'` does not trigger re-processing.
- **Partition creation is automatic**: Inserting into `space_embedder` triggers partition creation for the new space.
- **CASCADE works correctly**: Deleting a memory removes its chunks and pointers cleanly.
- **Filter DSL supports range-overlap**: `CAST(val('$.ayah_start') AS INT) <= X AND CAST(val('$.ayah_end') AS INT) >= Y` works for scoped retrieval.

## Success Criteria

- [x] New `tafsir` space has exactly 67,818 memories (matches unique passage count)
- [x] All 14 edition counts match unique passage counts from original space
- [x] Zero orphaned chunks or pointers
- [x] All memories have `ayah_start`, `ayah_end` as integers
- [x] `ayah_start <= ayah_end` for all memories
- [x] Zero duplicates in new space (one memory per edition + content_hash)
- [x] Semantic search returns relevant results with correct ranking
- [x] Filtered range-overlap search works correctly
- [x] Pointer metadata has correct shape (integer types, ayah_start/ayah_end present)
- [x] Original `openai-tafsir` space untouched (81,932 memories)
- [x] Production fetch_tafsir and search_tafsir still work

## Data Volume

| Metric | openai-tafsir (old) | tafsir (new) | Reduction |
|--------|-------------------|-------------|-----------|
| Memories | 81,932 | 67,818 | 17.2% |
| Chunks | 177,712 | 132,149 | 25.6% |
| Pointers | 177,712 | 132,149 | 25.6% |
| Embedding cost | — | $0 | — |

## Amendments

### TICK-001: Complete Remaining Work (2026-03-26)

**Summary**: Clean redundant metadata, update search result parsing for range-format ayah_keys, swap config.

**Problem Addressed**: The normalized `tafsir` space exists and is validated, but production still uses `openai-tafsir`. Search result parsing assumes single-ayah `ayah_key` format. Redundant metadata fields waste space.

**Spec Changes**:
- Added TICK-001 amendment section

**Plan Changes**:
- Phase 2 added: metadata cleanup, search parsing, config swap

## Risks and Mitigation

| Risk | Mitigation |
|------|-----------|
| Production disruption | Original space completely untouched. New space is independent. |
| Data loss | All operations are additive (INSERT into new space). Nothing deleted from old space. |
| Embedding quality degradation | Vectors copied bit-for-bit. Validated via targeted semantic search. |
| Filter DSL incompatibility | Range-overlap predicates tested and confirmed working. |
