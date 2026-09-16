#!/usr/bin/env bash
# Harness Role: 프런트엔드 타입 검사, production build와 Vitest를 묶은 feedback loop다.
# Agent Usage: React UI, hook, API client 또는 TypeScript 타입 변경 후 실행한다.
# Why: 개발 화면만 보고 production build 실패나 회귀 테스트 실패를 놓치는 것을 방지한다.
# Connection: package.json의 build/test 명령을 실행하며 check-lint.sh, check-all.sh와 함께 사용한다.
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
