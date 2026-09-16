#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MISSING=0

ok() {
  echo "[OK] $1"
}

fail() {
  echo "[FAIL] $1"
  MISSING=1
}

echo "================================"
echo "ZeroPay Lunch AI Setup"
echo "================================"

if command -v docker >/dev/null 2>&1; then
  ok "Docker found: $(docker --version)"
  if docker compose version >/dev/null 2>&1; then
    ok "Docker Compose found: $(docker compose version --short)"
  else
    fail "Docker Compose v2 is unavailable. Install or enable the Docker Compose plugin."
  fi
  if docker info >/dev/null 2>&1; then
    ok "Docker engine is running"
  else
    fail "Docker is installed but the engine is unavailable. Start Docker Desktop or the Docker daemon."
  fi
else
  fail "Docker is not installed. Install Docker Desktop or Docker Engine with Compose v2."
fi

if command -v java >/dev/null 2>&1; then
  JAVA_VERSION="$(java -version 2>&1 | awk -F '"' '/version/ {print $2; exit}')"
  JAVA_MAJOR="${JAVA_VERSION%%.*}"
  if [[ "$JAVA_MAJOR" =~ ^[0-9]+$ ]] && (( JAVA_MAJOR >= 21 )); then
    ok "Java found: $JAVA_VERSION"
  else
    fail "Java 21 or newer is required; found ${JAVA_VERSION:-unknown}."
  fi
else
  fail "Java is not installed. Install Java 21."
fi

if [[ -x "$ROOT_DIR/backend/gradlew" ]]; then
  ok "Gradle wrapper found"
else
  fail "Gradle wrapper is missing or not executable: backend/gradlew"
fi

if command -v node >/dev/null 2>&1; then
  NODE_VERSION="$(node --version)"
  if node -e 'const [major, minor] = process.versions.node.split(".").map(Number); process.exit(major > 20 || (major === 20 && minor >= 19) ? 0 : 1)'; then
    ok "Node.js found: $NODE_VERSION"
  else
    fail "Node.js 20.19 or newer is required; found $NODE_VERSION."
  fi
else
  fail "Node.js is not installed. Install Node.js 20.19 or newer."
fi

if command -v npm >/dev/null 2>&1; then
  ok "npm found: $(npm --version)"
else
  fail "npm is not installed. Install npm with Node.js."
fi

if command -v python3 >/dev/null 2>&1; then
  PYTHON_VERSION="$(python3 --version 2>&1 | awk '{print $2}')"
  if python3 -c 'import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 14) else 1)'; then
    ok "Python found: $PYTHON_VERSION"
  else
    fail "Python 3.11 through 3.13 is required; found $PYTHON_VERSION."
  fi
else
  fail "Python 3 is not installed. Install Python 3.11 through 3.13."
fi

if command -v poetry >/dev/null 2>&1; then
  ok "Poetry found: $(poetry --version)"
else
  fail "Poetry is not installed. Install Poetry 2.x."
fi

if (( MISSING != 0 )); then
  echo
  echo "Setup stopped because required tools are missing or unavailable."
  exit 1
fi

if [[ ! -f "$ROOT_DIR/.env" ]]; then
  cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
  ok "Created local .env from .env.example"
else
  ok "Existing local .env preserved"
fi

echo
echo "== Installing locked project dependencies =="

cd "$ROOT_DIR/frontend"
npm ci
ok "Frontend dependencies ready"

cd "$ROOT_DIR/backend"
if ! GRADLE_OUTPUT="$(./gradlew --no-daemon dependencies 2>&1)"; then
  echo "$GRADLE_OUTPUT"
  echo "[FAIL] Backend dependency preparation failed."
  exit 1
fi
ok "Backend dependencies ready"

cd "$ROOT_DIR/ai"
poetry sync --with dev
ok "AI dependencies ready"

cd "$ROOT_DIR"
docker compose config --quiet
ok "Docker Compose configuration valid"

echo
echo "== Starting local data services =="
docker compose up -d --wait --wait-timeout 120 mysql qdrant
ok "MySQL and Qdrant are healthy"

echo
echo "Setup completed successfully."
echo "Start application services with: docker compose up --build -d"
echo "Run verification with: ./scripts/check-all.sh"
