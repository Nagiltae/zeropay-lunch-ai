#!/usr/bin/env bash
# Harness Role: React/TypeScript와 Python 코드의 정적 규칙 위반을 실행 전에 찾는다.
# Agent Usage: frontend 또는 AI 코드를 변경한 뒤 서비스 빌드와 함께 실행한다.
# Why: 컴파일이나 테스트가 잡지 못하는 잘못된 Hook 사용과 Python 품질 문제를 방지한다.
# Connection: frontend/eslint.config.js와 ai/pyproject.toml의 규칙을 check-all.sh에 연결한다.
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
