# Telugu Transliteration and Translation Dataset Proposal

This contribution proposes a Telugu transliteration and translation dataset proposal in the import-friendly NDJSON shape used by quran-mcp's edition content pipeline.

## Files

- `translation.te-telugu.nonempty.ndjson`
  - NDJSON records with:
    - `content` (translation text)
    - `metadata.edition_type = "translation"`
    - `metadata.edition_id = "te-telugu"`
    - `metadata.surah`, `metadata.ayah`, `metadata.ayah_key`
    - `metadata.transliteration_telugu` and `metadata.arabic` preserved from the source JSON
- `edition.te-telugu.json`
  - Proposed edition metadata entry for `src/quran_mcp/data/editions.json`
- `empty-ayahs-reference.txt`
  - Empty in this update because all ayahs in the source now have translation text

## Data quality notes

- Source file covered all 114 surahs.
- Total source ayahs: 6236
- Non-empty ayahs included: 6236
- Empty ayahs excluded: 0

## Intended review flow

1. Confirm whether maintainers accept external corpus submissions in this repository.
2. If accepted, map this dataset into maintainers' preferred ingestion path.
3. Review licensing/provenance requirements before merge.
