#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "== Format verification =="

if ! command -v git >/dev/null 2>&1; then
  echo "[FAIL] Git is required for whitespace verification."
  exit 127
fi

if ! command -v poetry >/dev/null 2>&1; then
  echo "[FAIL] Poetry is required for the AI format check."
  exit 127
fi

git -C "$ROOT_DIR" diff --check

cd "$ROOT_DIR/ai"
poetry run ruff format --check .

echo "[PASS] Git whitespace and AI formatting"
