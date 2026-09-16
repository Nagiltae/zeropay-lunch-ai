#!/usr/bin/env bash
# Harness Role: tracked 변경과 신규 파일의 기본 공백 품질 및 Python 포맷을 확인한다.
# Agent Usage: 파일을 수정한 뒤 가장 먼저 실행해 작은 형식 오류를 빠르게 찾는다.
# Why: untracked 파일이 최종 diff와 검증에서 조용히 빠지는 문제를 줄인다.
# Connection: check-all.sh의 첫 단계이며 Git 상태와 Ruff 설정을 사용한다.
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

git -C "$ROOT_DIR" diff HEAD --check

UNTRACKED_COUNT=0
UNTRACKED_WHITESPACE_FAILURE=0
while IFS= read -r -d '' file; do
  UNTRACKED_COUNT=$((UNTRACKED_COUNT + 1))
  absolute_path="$ROOT_DIR/$file"

  if [[ -f "$absolute_path" ]] && grep -Iq . "$absolute_path"; then
    if grep -nE '[[:blank:]]+$' "$absolute_path"; then
      echo "[FAIL] Trailing whitespace in untracked file: $file"
      UNTRACKED_WHITESPACE_FAILURE=1
    fi
  fi
done < <(git -C "$ROOT_DIR" ls-files --others --exclude-standard -z)

if (( UNTRACKED_WHITESPACE_FAILURE != 0 )); then
  exit 1
fi

echo "[PASS] Git whitespace (${UNTRACKED_COUNT} untracked files inspected)"

cd "$ROOT_DIR/ai"
poetry run ruff format --check .

echo "[PASS] AI formatting"
