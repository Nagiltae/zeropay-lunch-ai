#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v npm >/dev/null 2>&1; then
  echo "Frontend check failed: npm is not installed."
  exit 127
fi

cd "$repo_root/frontend"
npm run lint
npm run build

