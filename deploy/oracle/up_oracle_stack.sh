#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

if [ ! -f ".env" ]; then
  echo ".env not found in ${ROOT_DIR}" >&2
  echo "Copy deploy/oracle/.env.oracle.example to .env and fill secrets first." >&2
  exit 1
fi

echo "Building and starting continuum-api + continuum-c3 + c3-gateway..."
docker compose -f docker-compose.c3.yml up -d --build
echo
echo "Running services:"
docker compose -f docker-compose.c3.yml ps
echo
echo "Health check (API):"
curl -fsS "http://127.0.0.1:7860/health" || true
