#!/usr/bin/env bash
# Package a minimal Agent Chat Lambda artifact (separate from the main API bundle).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/common.sh"

BUILD_DIR="${PROJECT_ROOT}/infrastructure/build"
PACKAGE_DIR="${BUILD_DIR}/chat-lambda-package"
ZIP_FILE="${BUILD_DIR}/sentinelai-chat-lambda.zip"

rm -rf "$PACKAGE_DIR" "$ZIP_FILE"
mkdir -p "$PACKAGE_DIR"

log "Installing chat Lambda dependencies via Docker (linux/amd64, python3.11)..."
if ! command -v docker >/dev/null 2>&1; then
  die "Docker is required to build the chat Lambda package with Linux wheels"
fi

docker run --rm --platform linux/amd64 \
  -v "${PACKAGE_DIR}:/out" \
  python:3.11-slim bash -lc '
    pip install --quiet --upgrade pip &&
    pip install --quiet --target /out \
      "fastapi>=0.115.0" "mangum>=0.19.0" "pydantic>=2.9.0" "pydantic-settings>=2.6.0" \
      "httpx>=0.27.0" "structlog>=24.4.0"
  '

log "Copying chat application code..."
mkdir -p "${PACKAGE_DIR}/backend/api/routes" "${PACKAGE_DIR}/backend/services"

cp -r "${PROJECT_ROOT}/shared" "$PACKAGE_DIR/"
cp "${PROJECT_ROOT}/backend/__init__.py" "${PACKAGE_DIR}/backend/"
cp "${PROJECT_ROOT}/backend/api/__init__.py" "${PACKAGE_DIR}/backend/api/"
cp "${PROJECT_ROOT}/backend/api/chat_app.py" "${PACKAGE_DIR}/backend/api/"
cp "${PROJECT_ROOT}/backend/api/routes/__init__.py" "${PACKAGE_DIR}/backend/api/routes/"
cp "${PROJECT_ROOT}/backend/api/routes/chat.py" "${PACKAGE_DIR}/backend/api/routes/"
cp "${PROJECT_ROOT}/backend/api/routes/health.py" "${PACKAGE_DIR}/backend/api/routes/"
cp "${PROJECT_ROOT}/backend/services/__init__.py" "${PACKAGE_DIR}/backend/services/"
cp "${PROJECT_ROOT}/backend/services/agent_chat_service.py" "${PACKAGE_DIR}/backend/services/"
cp "${PROJECT_ROOT}/backend/chat_lambda_handler.py" "${PACKAGE_DIR}/chat_handler.py"

log "Zipping chat package..."
cd "$PACKAGE_DIR"
zip -r "$ZIP_FILE" . \
  -x "*.pyc" "*__pycache__/*" "bin/*" "*/bin/*" >/dev/null

UNZIPPED=$(du -sm "$PACKAGE_DIR" | cut -f1)
log "Chat Lambda package created: $ZIP_FILE ($(du -h "$ZIP_FILE" | cut -f1), ${UNZIPPED}M unzipped)"
if [[ "$UNZIPPED" -gt 240 ]]; then
  warn "Unzipped size ${UNZIPPED}M exceeds Lambda 250M limit — deploy may fail."
fi
