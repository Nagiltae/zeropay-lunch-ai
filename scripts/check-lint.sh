#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "== Lint verification =="

if ! command -v npm >/dev/null 2>&1; then
  echo "[FAIL] npm is required for frontend linting."
  exit 127
fi

if ! command -v poetry >/dev/null 2>&1; then
  echo "[FAIL] Poetry is required for AI linting."
  exit 127
fi

if [[ ! -d "$ROOT_DIR/frontend/node_modules" ]]; then
  echo "[FAIL] Frontend dependencies are missing. Run ./scripts/setup.sh."
  exit 1
fi

cd "$ROOT_DIR/frontend"
npm run lint

cd "$ROOT_DIR/ai"
poetry run ruff check .

echo "[PASS] Frontend and AI lint"
