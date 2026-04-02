# Stage 1: Build all Svelte apps
FROM node:22-slim AS apps-builder
WORKDIR /build

# Install dependencies for each app (cached separately from source changes)
COPY src/quran_mcp/apps/mcp/mushaf/package.json src/quran_mcp/apps/mcp/mushaf/package-lock.json ./src/quran_mcp/apps/mcp/mushaf/
COPY src/quran_mcp/apps/public/documentation/package.json src/quran_mcp/apps/public/documentation/package-lock.json ./src/quran_mcp/apps/public/documentation/
COPY src/quran_mcp/apps/public/landing/package.json src/quran_mcp/apps/public/landing/package-lock.json ./src/quran_mcp/apps/public/landing/
RUN cd src/quran_mcp/apps/mcp/mushaf && npm ci \
    && cd /build/src/quran_mcp/apps/public/documentation && npm ci \
    && cd /build/src/quran_mcp/apps/public/landing && npm ci

# Copy source and build all three apps
COPY src/quran_mcp/apps/ ./src/quran_mcp/apps/
# Documentation and landing build to src/quran_mcp/assets/ via vite-plugin-singlefile
COPY src/quran_mcp/assets/ ./src/quran_mcp/assets/
RUN cd src/quran_mcp/apps/mcp/mushaf && npm run build \
    && cd /build/src/quran_mcp/apps/public/documentation && npm run build \
    && cd /build/src/quran_mcp/apps/public/landing && npm run build

# Stage 2: Python runtime
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Build tools for packages that need C compilation (fasttext-predict).
# Installed then removed in same layer to keep image small.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies from pyproject.toml (single source of truth).
# Parse deps from pyproject.toml so the layer is cached across src/ changes.
COPY pyproject.toml ./
RUN python -c "\
import tomllib, pathlib; \
d = tomllib.loads(pathlib.Path('pyproject.toml').read_text()); \
pathlib.Path('_deps.txt').write_text('\n'.join(d['project']['dependencies']))" \
    && pip install --no-cache-dir -r _deps.txt \
    && rm _deps.txt \
    && apt-get purge -y build-essential && apt-get autoremove -y

# Optional: install CA cert for GoodMem self-signed TLS.
# Place .deploy/goodmem-ca.crt to enable (gitignored — see setup docs).
COPY .deploy/goodmem-ca.cr[t] /usr/local/share/ca-certificates/
RUN update-ca-certificates

COPY src/ ./src/

# Copy built Svelte artifacts from Stage 1 (not tracked by git)
COPY --from=apps-builder /build/src/quran_mcp/apps/mcp/mushaf/dist/ ./src/quran_mcp/apps/mcp/mushaf/dist/
# Documentation and landing single-file HTML built into assets/
COPY --from=apps-builder /build/src/quran_mcp/assets/documentation.html ./src/quran_mcp/assets/documentation.html
COPY --from=apps-builder /build/src/quran_mcp/assets/landing.html ./src/quran_mcp/assets/landing.html

ENV PYTHONPATH=/app/src

CMD ["python", "-m", "quran_mcp.server"]
