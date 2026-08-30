#!/usr/bin/env bash
# Package Lambda deployment artifact (Linux x86_64 wheels for AWS Lambda)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/common.sh"

BUILD_DIR="${PROJECT_ROOT}/infrastructure/build"
PACKAGE_DIR="${BUILD_DIR}/lambda-package"
ZIP_FILE="${BUILD_DIR}/sentinelai-lambda.zip"

rm -rf "$PACKAGE_DIR" "$ZIP_FILE"
mkdir -p "$PACKAGE_DIR"

install_deps() {
  if command -v docker >/dev/null 2>&1; then
    log "Installing dependencies via Docker (linux/amd64, python3.11)..."
    docker run --rm --platform linux/amd64 \
      -v "${PROJECT_ROOT}:/src:ro" \
      -v "${PACKAGE_DIR}:/out" \
      python:3.11-slim bash -lc '
        pip install --quiet --upgrade pip &&
        pip install --quiet --target /out \
          "fastapi>=0.115.0" "mangum>=0.19.0" "pydantic>=2.9.0" "pydantic-settings>=2.6.0" \
          "boto3>=1.35.0" "pyyaml>=6.0.2" "httpx>=0.27.0" "python-jose[cryptography]>=3.3.0" \
          "passlib[bcrypt]>=1.7.4" "python-multipart>=0.0.12" "structlog>=24.4.0" \
          "tenacity>=9.0.0" "email-validator>=2.2.0" "litellm>=1.52.0"
      '
  else
    log "Docker not found — installing manylinux x86_64 wheels via pip..."
    python3 -m pip install --quiet --upgrade pip
    python3 -m pip install --quiet --target "$PACKAGE_DIR" \
      --platform manylinux2014_x86_64 \
      --python-version 3.11 \
      --implementation cp \
      --only-binary=:all: \
      "${PROJECT_ROOT}"
  fi
}

install_deps

log "Copying application code..."
cp -r "${PROJECT_ROOT}/shared" "$PACKAGE_DIR/"
cp -r "${PROJECT_ROOT}/governance" "$PACKAGE_DIR/"
cp -r "${PROJECT_ROOT}/backend" "$PACKAGE_DIR/"
cp -r "${PROJECT_ROOT}/lambda" "$PACKAGE_DIR/"

log "Zipping package..."
cd "$PACKAGE_DIR"
zip -r "$ZIP_FILE" . \
  -x "*.pyc" "*__pycache__/*" "bin/*" "*/bin/*" >/dev/null

UNZIPPED=$(du -sm "$PACKAGE_DIR" | cut -f1)
log "Lambda package created: $ZIP_FILE ($(du -h "$ZIP_FILE" | cut -f1), ${UNZIPPED}M unzipped)"
if [[ "$UNZIPPED" -gt 240 ]]; then
  warn "Unzipped size ${UNZIPPED}M exceeds Lambda 250M limit — deploy may fail."
fi
