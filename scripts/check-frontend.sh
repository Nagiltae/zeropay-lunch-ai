#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"

echo "== Frontend verification =="

if ! command -v node >/dev/null 2>&1; then
  echo "[FAIL] Node.js is not installed. Install Node.js 20.19 or newer."
  exit 127
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "[FAIL] npm is not installed. Install npm with Node.js."
  exit 127
fi

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "[FAIL] Frontend dependencies are missing. Run ./scripts/setup.sh."
  exit 1
fi

cd "$FRONTEND_DIR"
npm ls --depth=0 >/dev/null
npm run build

if npm pkg get scripts.test | grep -qv '^{}$'; then
  npm test
else
  echo "[SKIP] Frontend tests: no test script is defined."
fi

echo "[PASS] Frontend dependency validation and production build"
