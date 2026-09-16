#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v poetry >/dev/null 2>&1; then
  echo "AI check failed: Poetry is not installed."
  exit 127
fi

cd "$repo_root/ai"
poetry check
poetry run ruff check .
poetry run pytest

