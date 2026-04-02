#!/usr/bin/env bash
# Collaborator setup for quran-mcp.
#
# Sets up .env and starts the local stack. Run this once after cloning.
#
# Usage:
#     ./scripts/setup/bootstrap.sh
#
# Prerequisites:
#     - Docker and Docker Compose

set -euo pipefail

ENV_FILE=".env"
ENV_EXAMPLE=".env.example"

# ─── Colors ───────────────────────────────────────────────────────────
red()   { printf '\033[0;31m%s\033[0m\n' "$*"; }
green() { printf '\033[0;32m%s\033[0m\n' "$*"; }
dim()   { printf '\033[0;90m%s\033[0m\n' "$*"; }

# ─── Step 1: .env ────────────────────────────────────────────────────
if [ ! -f "$ENV_FILE" ]; then
    echo "Creating $ENV_FILE from $ENV_EXAMPLE ..."
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    # Set a random DB password so docker compose doesn't fail
    if command -v openssl &>/dev/null; then
        pw=$(openssl rand -hex 16)
    else
        pw="quran_mcp_local_$(date +%s)"
    fi
    sed -i "s/QURAN_MCP_DB_PASSWORD=change_me/QURAN_MCP_DB_PASSWORD=$pw/" "$ENV_FILE"
    green "✓ Created $ENV_FILE with random DB password."
    dim "  Edit $ENV_FILE to add API keys for GoodMem, sampling, etc. (optional)."
else
    dim "✓ $ENV_FILE already exists — skipping."
fi

# ─── Step 2: Data notice ────────────────────────────────────────────
echo ""
dim "Note: Database content dumps are temporarily excluded from the repository"
dim "while we finalize a distribution approach that respects content copyright."
dim "The server will start, but fetch tools that query local data will return"
dim "empty results until data is loaded separately."
echo ""

# ─── Step 3: Start the stack ─────────────────────────────────────────
echo "Starting docker compose ..."
docker compose up -d

# Wait for DB to be healthy
echo "Waiting for database to be ready ..."
for i in $(seq 1 30); do
    if docker compose exec -T db pg_isready -U "${QURAN_MCP_DB_USER:-quran_mcp_user}" -d "${QURAN_MCP_DB_DATABASE:-quran_mcp_db}" &>/dev/null; then
        break
    fi
    sleep 1
done

# ─── Step 4: Verify ──────────────────────────────────────────────────
echo ""
echo "Verifying ..."

# Check health endpoint
sleep 2
if curl -sf http://localhost:8088/.health &>/dev/null; then
    green "✓ Server is healthy at http://localhost:8088"
else
    dim "⚠ Server not responding yet — it may still be starting. Check: docker compose logs app"
fi

echo ""
green "Setup complete."
echo ""
echo "  Search tools require GoodMem API keys in .env (optional)."
echo "  Sampling (AI summaries) requires LLM API keys in .env (optional)."
echo ""
echo "  Next steps:"
echo "    • Test:  curl http://localhost:8088/.health"
echo "    • Logs:  docker compose logs -f"
echo "    • Stop:  docker compose down"
echo ""
