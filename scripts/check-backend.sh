#!/usr/bin/env bash
# Harness Role: Java compiler lint, Spring 테스트와 패키징을 Gradle build 하나로 검증한다.
# Agent Usage: backend 코드, 설정, migration 또는 Java 계약 변경 후 실행한다.
# Why: 코드 작성만 끝내고 컴파일·JPA 매핑·Flyway·테스트 실패를 놓치는 것을 방지한다.
# Connection: Gradle wrapper와 backend/build.gradle을 사용하고 check-all.sh에 결과를 제공한다.
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
