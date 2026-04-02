# Generate Database Dumps

Generate the `.db/*.sql.gz` dump files needed for GitHub releases and contributor bootstrap.

Requires a running local dev DB (`quran-mcp-db` container) with populated data.

## Steps

1. **Generate `quran_com_data.sql.gz`** (quran.com schema dump):
   ```
   bash scripts/.maintainer/dump_quran_com_data.sh
   ```
   Produces `.db/quran_com_data.sql.gz` (~80-150 MB).

2. **Generate edition content dumps** (full + partial):
   ```
   python scripts/.maintainer/import_edition_content_from_ndjson.py --docker --dump
   ```
   Produces:
   - `.db/quran_mcp_edition_content.full.sql.gz` — all editions
   - `.db/quran_mcp_edition_content.partial.sql.gz` — curated subset (~30 MB)

   If data is already imported and you only need to re-dump:
   ```
   python scripts/.maintainer/import_edition_content_from_ndjson.py --docker --dump --partial-only
   ```

3. **Verify** all three files exist:
   ```
   ls -lh .db/quran_com_data.sql.gz .db/quran_mcp_edition_content.full.sql.gz .db/quran_mcp_edition_content.partial.sql.gz
   ```

## Notes

- The partial dump includes only curated editions (see `PARTIAL_EDITIONS` in the import script). This is the one attached to GitHub releases.
- The full dump is SCP'd to production during initial setup — it's not attached to releases.
- Run this command **before** `/deploy` to ensure dump files are fresh.
