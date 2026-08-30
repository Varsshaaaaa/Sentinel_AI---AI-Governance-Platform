#!/usr/bin/env bash
# Local development setup (Docker Compose)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

cd "$PROJECT_ROOT"
log() { echo "[sentinelai] $*"; }

log "Starting local stack (DynamoDB Local + API)..."
docker compose up -d --build

log "Local stack running:"
log "  API:      http://localhost:8080/docs"
log "  DynamoDB: http://localhost:8000"
log ""
log "Stop with: docker compose down"
