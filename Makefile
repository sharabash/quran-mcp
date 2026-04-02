.PHONY: build-frontend dev up

# Build all Svelte frontend apps.
# Documentation and landing produce single-file HTML into src/quran_mcp/assets/.
# Mushaf produces a dist/ directory used by the MCP mushaf resource.
build-frontend:
	cd src/quran_mcp/apps/public/documentation && npm install && npm run build
	cd src/quran_mcp/apps/public/landing && npm install && npm run build
	cd src/quran_mcp/apps/mcp/mushaf && npm install && npm run build

# Start the server with frontend assets built first.
dev: build-frontend
	fastmcp dev src/quran_mcp/server.py

# Start services via docker compose.
up:
	docker compose up -d --build
