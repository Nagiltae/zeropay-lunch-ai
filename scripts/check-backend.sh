#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ! -x "$repo_root/backend/gradlew" ]]; then
  echo "Backend check skipped: the Spring Boot project has not been generated yet."
  exit 0
fi

cd "$repo_root/backend"
./gradlew test
./gradlew build

