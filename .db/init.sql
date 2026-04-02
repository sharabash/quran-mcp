-- Bootstrap quran_mcp schema
CREATE SCHEMA IF NOT EXISTS quran_mcp;

-- Set default search_path for the user
ALTER ROLE quran_mcp_user SET search_path TO quran_mcp, public;

-- Grant permissions
GRANT ALL ON SCHEMA quran_mcp TO quran_mcp_user;

-- Migration tracking table (used by both the app's run_migrations()
-- and the docker init script that pre-applies migration 006 for corpus data).
CREATE TABLE IF NOT EXISTS quran_mcp.schema_migration (
    version     INT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
