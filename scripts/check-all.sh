#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

declare -a CHECK_NAMES=()
declare -a CHECK_RESULTS=()
FAILED=0

run_check() {
  local name="$1"
  local script="$2"

  echo
  echo "--------------------------------"
  echo "$name"
  echo "--------------------------------"

  CHECK_NAMES+=("$name")
  if "$script"; then
    CHECK_RESULTS+=("PASS")
  else
    CHECK_RESULTS+=("FAIL")
    FAILED=1
  fi
}

echo "================================"
echo "ZeroPay Lunch AI Verification"
echo "================================"

run_check "Format" "$SCRIPT_DIR/check-format.sh"
run_check "Lint" "$SCRIPT_DIR/check-lint.sh"
run_check "Frontend" "$SCRIPT_DIR/check-frontend.sh"
run_check "Backend" "$SCRIPT_DIR/check-backend.sh"
run_check "AI" "$SCRIPT_DIR/check-ai.sh"
run_check "Integration" "$SCRIPT_DIR/check-integration.sh"

echo
echo "================================"
echo "Verification Summary"
echo "================================"

for index in "${!CHECK_NAMES[@]}"; do
  printf '[%s] %s\n' "${CHECK_RESULTS[$index]}" "${CHECK_NAMES[$index]}"
done

echo
if (( FAILED != 0 )); then
  echo "Verification failed. See the failing section output above."
  exit 1
fi

echo "All checks passed."
