"""asyncpg connection pool management with schema migrations and retention cleanup.

Usage:
    from quran_mcp.lib.db.pool import create_pool, close_pool

    pool = await create_pool(db_settings, relay_settings)
    # ... use pool ...
    await close_pool(pool)
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import asyncpg

if TYPE_CHECKING:
    from quran_mcp.lib.config.settings import DatabaseSettings, RelaySettings

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_SCHEMA_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _quote_schema_identifier(schema_name: str) -> str:
    """Return a validated SQL identifier for the configured schema name."""
    if not _SCHEMA_IDENTIFIER_RE.fullmatch(schema_name):
        raise ValueError(f"Invalid PostgreSQL schema name: {schema_name!r}")
    return f'"{schema_name}"'


async def create_pool(
    db_settings: "DatabaseSettings",
    relay_settings: "RelaySettings | None" = None,
) -> asyncpg.Pool | None:
    """Create an asyncpg pool, run migrations, and run retention cleanup.

    Returns None if connection fails (graceful degradation).

    Args:
        db_settings: DatabaseSettings instance with host, port, user, credentials, etc.
        relay_settings: RelaySettings instance (optional). If provided,
                        retention cleanup runs using relay_settings.retention_days.
    """
    if not db_settings.password:
        logger.info("Database credentials not configured — skipping DB pool creation")
        return None

    schema = db_settings.schema_name
    _quote_schema_identifier(schema)

    async def _init_conn(conn: asyncpg.Connection) -> None:
        await conn.execute(
            "SELECT set_config('search_path', $1, false)",
            f"{schema}, public",
        )

    try:
        pool = await asyncpg.create_pool(
            host=db_settings.host,
            port=db_settings.port,
            user=db_settings.user,
            password=db_settings.password,
            database=db_settings.database,
            min_size=db_settings.min_pool_size,
            max_size=db_settings.max_pool_size,
            command_timeout=45,
            init=_init_conn,
        )
        logger.info(
            "Database pool created (pool %s-%s)",
            db_settings.min_pool_size,
            db_settings.max_pool_size,
        )
    except Exception as e:
        # Intentional: DB is optional — server works without it (fetch uses GoodMem fallback)
        logger.warning(f"Database pool creation failed: {e}. Relay disabled.")
        return None

    try:
        await run_migrations(pool, db_settings.schema_name)
    except Exception as e:
        # Intentional: migration failure degrades relay but doesn't block server startup
        logger.warning(f"Database migration failed: {e}. Relay may be degraded.")

    if relay_settings and relay_settings.retention_days > 0:
        try:
            await run_retention_cleanup(pool, db_settings.schema_name, relay_settings.retention_days)
        except Exception as e:
            # Intentional: retention cleanup is best-effort housekeeping
            logger.warning(f"Retention cleanup failed: {e}")

    return pool


async def close_pool(pool: asyncpg.Pool | None) -> None:
    """Close the pool if it exists."""
    if pool is not None:
        await pool.close()
        logger.info("Database pool closed")


async def run_migrations(pool: asyncpg.Pool, schema_name: str) -> None:
    """Run pending SQL migrations under an advisory lock.

    Migrations are numbered .sql files in the migrations/ directory.
    The schema_migration table tracks which versions have been applied.
    An advisory lock prevents concurrent migration runs.
    """
    schema_identifier = _quote_schema_identifier(schema_name)
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Ensure schema exists
            await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_identifier}")

            # Advisory lock (hash of 'quran_mcp_migrations')
            await conn.execute("SELECT pg_advisory_xact_lock(7173829401)")

            # Ensure schema_migration table exists
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {schema_identifier}.schema_migration (
                    version     INT PRIMARY KEY,
                    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

            # Get already-applied versions
            rows = await conn.fetch(
                f"SELECT version FROM {schema_identifier}.schema_migration ORDER BY version"
            )
            applied = {row["version"] for row in rows}

            # Find and run pending migrations
            migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
            for mf in migration_files:
                version = int(mf.name.split("_")[0])
                if version in applied:
                    continue

                logger.info(f"Applying migration {mf.name} (version {version})")
                sql = mf.read_text()
                await conn.execute(sql)
                await conn.execute(
                    f"INSERT INTO {schema_identifier}.schema_migration (version) VALUES ($1)",
                    version,
                )
                logger.info(f"Migration {mf.name} applied successfully")


async def run_retention_cleanup(
    pool: asyncpg.Pool,
    schema_name: str,
    retention_days: int,
) -> None:
    """Delete turns older than retention_days. Cascades to tool_call via FK."""
    schema_identifier = _quote_schema_identifier(schema_name)
    result = await pool.execute(
        f"DELETE FROM {schema_identifier}.turn WHERE started_at < NOW() - $1::interval",
        timedelta(days=retention_days),
    )
    # result is like "DELETE 5"
    count = result.split()[-1] if result else "0"
    if count != "0":
        logger.info(f"Retention cleanup: deleted {count} turns older than {retention_days} days")
