#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"

echo "== Backend verification =="

if ! command -v java >/dev/null 2>&1; then
  echo "[FAIL] Java is not installed. Install Java 21."
  exit 127
fi

if [[ ! -x "$BACKEND_DIR/gradlew" ]]; then
  echo "[FAIL] Gradle wrapper is missing or is not executable: backend/gradlew"
  exit 1
fi

cd "$BACKEND_DIR"
./gradlew --no-daemon build

echo "[PASS] Backend compile, tests, and build"
