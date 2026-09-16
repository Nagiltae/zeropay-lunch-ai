#!/usr/bin/env bash
# Harness Role: FastAPI 프로젝트 메타데이터, import 가능 여부와 Pytest를 검증한다.
# Agent Usage: ai/app, Pydantic 계약 또는 Python 의존성을 변경한 뒤 실행한다.
# Why: 서버가 import조차 되지 않거나 Python 테스트가 실패하는 상태를 완료로 판단하지 않게 한다.
# Connection: Poetry 환경과 ai/pyproject.toml을 사용하고 format/lint 검사와 check-all.sh에서 합쳐진다.
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
