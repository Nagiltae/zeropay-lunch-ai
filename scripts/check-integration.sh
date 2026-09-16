#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

failure_report() {
  local exit_code=$?
  trap - ERR
  echo
  echo "[FAIL] Integration verification failed. Current container state and recent logs follow."
  docker compose -f "$ROOT_DIR/docker-compose.yml" ps || true
  docker compose -f "$ROOT_DIR/docker-compose.yml" logs --tail=80 frontend backend ai mysql qdrant || true
  exit "$exit_code"
}

trap failure_report ERR

echo "== Integration verification =="

if ! command -v docker >/dev/null 2>&1; then
  echo "[FAIL] Docker is not installed. Run ./scripts/setup.sh after installing Docker."
  exit 127
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "[FAIL] Docker Compose v2 is unavailable."
  exit 127
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "[FAIL] curl is required for HTTP integration checks."
  exit 127
fi

if ! docker info >/dev/null 2>&1; then
  echo "[FAIL] Docker engine is unavailable. Start Docker Desktop or the Docker daemon."
  exit 1
fi

cd "$ROOT_DIR"
docker compose config --quiet
docker compose build --quiet
docker compose up -d --wait --wait-timeout 180

FRONTEND_ADDRESS="$(docker compose port frontend 80)"
BACKEND_ADDRESS="$(docker compose port backend 8080)"
AI_ADDRESS="$(docker compose port ai 8001)"

FRONTEND_HEALTH="$(curl --fail --silent --show-error --max-time 10 "http://$FRONTEND_ADDRESS/healthz")"
[[ "$FRONTEND_HEALTH" == "ok" ]]
echo "[PASS] Frontend health"

BACKEND_HEALTH="$(curl --fail --silent --show-error --max-time 10 "http://$BACKEND_ADDRESS/actuator/health")"
[[ "$BACKEND_HEALTH" == *'"status":"UP"'* ]]
echo "[PASS] Spring Boot health"

AI_HEALTH="$(curl --fail --silent --show-error --max-time 10 "http://$AI_ADDRESS/health")"
[[ "$AI_HEALTH" == *'"status":"ok"'* ]]
[[ "$AI_HEALTH" == *'"service":"ai"'* ]]
echo "[PASS] FastAPI health"

CONVERSATION_ID="00000000-0000-4000-8000-000000000001"
SSE_RESPONSE="$(curl --fail --silent --show-error --no-buffer --max-time 30 \
  -X POST \
  "http://$FRONTEND_ADDRESS/api/conversations/$CONVERSATION_ID/messages" \
  -H 'Accept: text/event-stream' \
  -H 'Content-Type: application/json' \
  --data '{"message":"통합 검사 메시지"}')"
[[ "$SSE_RESPONSE" == *'event:accepted'* ]]
[[ "$SSE_RESPONSE" == *'event:assistant_delta'* ]]
[[ "$SSE_RESPONSE" == *'event:completed'* ]]
echo "[PASS] Nginx to Spring Boot SSE flow"

trap - ERR
echo "[PASS] Docker service health and current cross-service flow"
