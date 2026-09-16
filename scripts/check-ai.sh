#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
AI_DIR="$ROOT_DIR/ai"

echo "== AI service verification =="

if ! command -v poetry >/dev/null 2>&1; then
  echo "[FAIL] Poetry is not installed. Install Poetry 2.x and run ./scripts/setup.sh."
  exit 127
fi

cd "$AI_DIR"
poetry check
poetry run python -c "import app.main"
poetry run pytest

echo "[PASS] AI project metadata, import sanity, and tests"
