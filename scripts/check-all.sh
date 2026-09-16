#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Checking frontend"
"$repo_root/scripts/check-frontend.sh"

echo "Checking backend"
"$repo_root/scripts/check-backend.sh"

echo "Checking AI server"
"$repo_root/scripts/check-ai.sh"
