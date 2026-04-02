#!/bin/bash
# Initialise the quran_mcp database on first postgres start.
# Runs automatically via docker-entrypoint-initdb.d/ when the volume is fresh.
# Skips gracefully if dump files are missing (server works without corpus
# data, but tools will return empty results).
#
# The dumps are data-only — they need all schema tables and columns to exist.
# We apply all migrations before loading so the schema matches the dumps.
# The app's run_migrations() will see them as already applied and skip them.

set -e

DUMP="/docker-entrypoint-initdb.d/dumps/quran_com_data.sql.gz"
MIGRATIONS_DIR="/docker-entrypoint-initdb.d/migrations"

if [ ! -f "$DUMP" ]; then
    echo "init_db: $DUMP not found — skipping corpus data load."
    echo "init_db: The server will start but tools will return empty results."
    echo "init_db: Place quran_com_data.sql.gz in .db/ and recreate the volume."
    exit 0
fi

# Apply all migrations in order so the schema matches the dump.
# Record each in schema_migration so the app doesn't re-run them.
echo "init_db: Applying all migrations ..."
for sql in $(ls "$MIGRATIONS_DIR"/*.sql | sort); do
    version=$(basename "$sql" | grep -o '^[0-9]*')
    echo "init_db:   $(basename $sql)"
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" --quiet -f "$sql"
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" --quiet -c \
        "INSERT INTO quran_mcp.schema_migration (version) VALUES ($version) ON CONFLICT DO NOTHING;"
done

echo "init_db: Loading corpus data from $DUMP ..."
gunzip -c "$DUMP" | psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" --quiet 2>&1 | grep -v "^ERROR" || true
echo "init_db: Done loading corpus data."

# Load edition content dump if available.
# Priority: full dump first, then partial, then skip.
EDITION_FULL="/docker-entrypoint-initdb.d/dumps/quran_mcp_edition_content.full.sql.gz"
EDITION_PARTIAL="/docker-entrypoint-initdb.d/dumps/quran_mcp_edition_content.partial.sql.gz"

if [ -f "$EDITION_FULL" ]; then
    echo "init_db: Loading edition content from $EDITION_FULL ..."
    gunzip -c "$EDITION_FULL" | psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" --quiet 2>&1 | grep -v "^ERROR" || true
    echo "init_db: Done loading edition content (full)."
elif [ -f "$EDITION_PARTIAL" ]; then
    echo "init_db: Loading edition content from $EDITION_PARTIAL ..."
    gunzip -c "$EDITION_PARTIAL" | psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" --quiet 2>&1 | grep -v "^ERROR" || true
    echo "init_db: Done loading edition content (partial)."
else
    echo "init_db: No edition content dump found — skipping."
    echo "init_db: Place quran_mcp_edition_content.{full,partial}.sql.gz in .db/ and recreate the volume."
fi
