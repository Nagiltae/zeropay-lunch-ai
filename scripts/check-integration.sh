#!/usr/bin/env bash
# Harness Role: 실제 Docker 서비스 사이의 인증·DB·SSE 사용자 흐름을 검증한다.
# Agent Usage: API 경계, DB, Docker, 인증 또는 여러 서비스를 함께 바꾼 뒤 실행한다.
# Why: 각 서비스 테스트는 통과하지만 proxy, cookie, migration이나 서비스 연결이 깨지는 문제를 찾는다.
# Connection: docker-compose.yml을 기동하고 실패 시 상태와 로그를 보여 주며 check-all.sh의 마지막 단계가 된다.
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

OWNER_COOKIE_JAR="$(mktemp "${TMPDIR:-/tmp}/zeropay-owner-cookies.XXXXXX")"
OTHER_COOKIE_JAR="$(mktemp "${TMPDIR:-/tmp}/zeropay-other-cookies.XXXXXX")"

cleanup() {
  rm -f "$OWNER_COOKIE_JAR" "$OTHER_COOKIE_JAR"
}

trap cleanup EXIT

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

curl --fail --silent --show-error --max-time 10 \
  -c "$OWNER_COOKIE_JAR" \
  "http://$FRONTEND_ADDRESS/api/auth/csrf" \
  -o /dev/null
OWNER_CSRF_TOKEN="$(awk '$6 == "XSRF-TOKEN" {print $7}' "$OWNER_COOKIE_JAR")"
[[ -n "$OWNER_CSRF_TOKEN" ]]

RUN_ID="$(date +%s)-$$"
OWNER_EMAIL="integration-owner-$RUN_ID@example.com"
OTHER_EMAIL="integration-other-$RUN_ID@example.com"
PASSWORD="integration-password-123"

curl --fail --silent --show-error --max-time 10 \
  -b "$OWNER_COOKIE_JAR" -c "$OWNER_COOKIE_JAR" \
  -X POST \
  "http://$FRONTEND_ADDRESS/api/auth/signup" \
  -H 'Content-Type: application/json' \
  -H "X-XSRF-TOKEN: $OWNER_CSRF_TOKEN" \
  --data "{\"email\":\"$OWNER_EMAIL\",\"password\":\"$PASSWORD\",\"displayName\":\"통합 검사 소유자\"}" \
  -o /dev/null

LOGIN_RESPONSE="$(curl --fail --silent --show-error --max-time 10 \
  -b "$OWNER_COOKIE_JAR" -c "$OWNER_COOKIE_JAR" \
  -X POST \
  "http://$FRONTEND_ADDRESS/api/auth/login" \
  -H 'Content-Type: application/json' \
  -H "X-XSRF-TOKEN: $OWNER_CSRF_TOKEN" \
  --data "{\"email\":\"$OWNER_EMAIL\",\"password\":\"$PASSWORD\"}")"
OWNER_USER_ID="$(printf '%s' "$LOGIN_RESPONSE" \
  | sed -n 's/.*"userId":"\([^"]*\)".*/\1/p')"
SESSION_COOKIE="$(awk '$6 == "SESSION" {print $7}' "$OWNER_COOKIE_JAR")"
[[ -n "$OWNER_USER_ID" ]]
[[ -n "$SESSION_COOKIE" ]]

ME_RESPONSE="$(curl --fail --silent --show-error --max-time 10 \
  -b "$OWNER_COOKIE_JAR" \
  "http://$FRONTEND_ADDRESS/api/auth/me")"
[[ "$ME_RESPONSE" == *"\"email\":\"$OWNER_EMAIL\""* ]]
echo "[PASS] Signup, login, session cookie, and current-user lookup"

PREFERENCE_RESPONSE="$(curl --fail --silent --show-error --max-time 10 \
  -b "$OWNER_COOKIE_JAR" -c "$OWNER_COOKIE_JAR" \
  -X PUT \
  "http://$FRONTEND_ADDRESS/api/preferences/me" \
  -H 'Content-Type: application/json' \
  -H "X-XSRF-TOKEN: $OWNER_CSRF_TOKEN" \
  --data '{"defaultBudget":12000,"spiceLevel":"MEDIUM","preferredCategories":["KOREAN_SOUP"],"dislikedCategories":["SALAD"],"allergies":["땅콩"]}')"
[[ "$PREFERENCE_RESPONSE" == *'"defaultBudget":12000'* ]]
[[ "$PREFERENCE_RESPONSE" == *'"zeroPayRequired":true'* ]]
echo "[PASS] User preference persistence and fixed ZeroPay policy"

CONVERSATION_RESPONSE="$(curl --fail --silent --show-error --max-time 10 \
  -b "$OWNER_COOKIE_JAR" -c "$OWNER_COOKIE_JAR" \
  -X POST \
  "http://$FRONTEND_ADDRESS/api/conversations" \
  -H 'Content-Type: application/json' \
  -H "X-XSRF-TOKEN: $OWNER_CSRF_TOKEN" \
  --data '{"locationId":"gangnam"}')"
CONVERSATION_ID="$(printf '%s' "$CONVERSATION_RESPONSE" \
  | sed -n 's/.*"conversationId":"\([^"]*\)".*/\1/p')"
[[ -n "$CONVERSATION_ID" ]]
[[ "$CONVERSATION_RESPONSE" == *'"active":true'* ]]
CONVERSATION_USER_ID="$(printf "SELECT user_id FROM conversations WHERE id = '%s';\n" "$CONVERSATION_ID" \
  | docker compose exec -T mysql sh -c \
    'mysql --batch --skip-column-names -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"')"
[[ "$CONVERSATION_USER_ID" == "$OWNER_USER_ID" ]]
echo "[PASS] Authenticated conversation ownership persisted in MySQL"

curl --fail --silent --show-error --max-time 10 \
  -c "$OTHER_COOKIE_JAR" \
  "http://$FRONTEND_ADDRESS/api/auth/csrf" \
  -o /dev/null
OTHER_CSRF_TOKEN="$(awk '$6 == "XSRF-TOKEN" {print $7}' "$OTHER_COOKIE_JAR")"
curl --fail --silent --show-error --max-time 10 \
  -b "$OTHER_COOKIE_JAR" -c "$OTHER_COOKIE_JAR" \
  -X POST \
  "http://$FRONTEND_ADDRESS/api/auth/signup" \
  -H 'Content-Type: application/json' \
  -H "X-XSRF-TOKEN: $OTHER_CSRF_TOKEN" \
  --data "{\"email\":\"$OTHER_EMAIL\",\"password\":\"$PASSWORD\",\"displayName\":\"통합 검사 타 사용자\"}" \
  -o /dev/null
curl --fail --silent --show-error --max-time 10 \
  -b "$OTHER_COOKIE_JAR" -c "$OTHER_COOKIE_JAR" \
  -X POST \
  "http://$FRONTEND_ADDRESS/api/auth/login" \
  -H 'Content-Type: application/json' \
  -H "X-XSRF-TOKEN: $OTHER_CSRF_TOKEN" \
  --data "{\"email\":\"$OTHER_EMAIL\",\"password\":\"$PASSWORD\"}" \
  -o /dev/null
OTHER_HISTORY_STATUS="$(curl --silent --show-error --max-time 10 \
  -b "$OTHER_COOKIE_JAR" \
  -o /dev/null -w '%{http_code}' \
  "http://$FRONTEND_ADDRESS/api/conversations/$CONVERSATION_ID")"
OTHER_MESSAGE_STATUS="$(curl --silent --show-error --max-time 10 \
  -b "$OTHER_COOKIE_JAR" \
  -X POST \
  -H 'Accept: text/event-stream' \
  -H 'Content-Type: application/json' \
  -H "X-XSRF-TOKEN: $OTHER_CSRF_TOKEN" \
  --data '{"message":"소유권 검사"}' \
  -o /dev/null -w '%{http_code}' \
  "http://$FRONTEND_ADDRESS/api/conversations/$CONVERSATION_ID/messages")"
[[ "$OTHER_HISTORY_STATUS" == "404" ]]
[[ "$OTHER_MESSAGE_STATUS" == "404" ]]
echo "[PASS] Conversation ownership isolation"

SSE_RESPONSE="$(curl --fail --silent --show-error --no-buffer --max-time 30 \
  -b "$OWNER_COOKIE_JAR" -c "$OWNER_COOKIE_JAR" \
  -X POST \
  "http://$FRONTEND_ADDRESS/api/conversations/$CONVERSATION_ID/messages" \
  -H 'Accept: text/event-stream' \
  -H 'Content-Type: application/json' \
  -H "X-XSRF-TOKEN: $OWNER_CSRF_TOKEN" \
  --data '{"message":"통합 검사 메시지"}')"
[[ "$SSE_RESPONSE" == *'event:accepted'* ]]
[[ "$SSE_RESPONSE" == *'event:recommendations'* ]]
[[ "$SSE_RESPONSE" == *'event:assistant_delta'* ]]
[[ "$SSE_RESPONSE" == *'event:completed'* ]]
[[ "$SSE_RESPONSE" != *'"zeroPayAvailable":false'* ]]
echo "[PASS] Nginx to Spring Boot SSE flow"

ASSISTANT_MESSAGE_ID="$(printf '%s' "$SSE_RESPONSE" \
  | sed -n 's/.*"assistantMessageId":"\([^"]*\)".*/\1/p' \
  | head -n 1)"
RESTAURANT_ID="$(printf '%s' "$SSE_RESPONSE" \
  | sed -n 's/.*"restaurantId":\([0-9]*\).*/\1/p' \
  | head -n 1)"
[[ -n "$ASSISTANT_MESSAGE_ID" ]]
[[ -n "$RESTAURANT_ID" ]]

MEAL_RESPONSE="$(curl --fail --silent --show-error --max-time 10 \
  -b "$OWNER_COOKIE_JAR" -c "$OWNER_COOKIE_JAR" \
  -X POST \
  "http://$FRONTEND_ADDRESS/api/meals" \
  -H 'Content-Type: application/json' \
  -H "X-XSRF-TOKEN: $OWNER_CSRF_TOKEN" \
  --data "{\"restaurantId\":$RESTAURANT_ID,\"sourceMessageId\":\"$ASSISTANT_MESSAGE_ID\"}")"
MEAL_ID="$(printf '%s' "$MEAL_RESPONSE" \
  | sed -n 's/.*"mealId":"\([^"]*\)".*/\1/p')"
[[ -n "$MEAL_ID" ]]
REPEATED_MEAL_RESPONSE="$(curl --fail --silent --show-error --max-time 10 \
  -b "$OWNER_COOKIE_JAR" -c "$OWNER_COOKIE_JAR" \
  -X POST \
  "http://$FRONTEND_ADDRESS/api/meals" \
  -H 'Content-Type: application/json' \
  -H "X-XSRF-TOKEN: $OWNER_CSRF_TOKEN" \
  --data "{\"restaurantId\":$RESTAURANT_ID,\"sourceMessageId\":\"$ASSISTANT_MESSAGE_ID\"}")"
[[ "$REPEATED_MEAL_RESPONSE" == *"\"mealId\":\"$MEAL_ID\""* ]]
RECENT_MEALS_RESPONSE="$(curl --fail --silent --show-error --max-time 10 \
  -b "$OWNER_COOKIE_JAR" \
  "http://$FRONTEND_ADDRESS/api/meals/recent")"
[[ "$RECENT_MEALS_RESPONSE" == *"\"mealId\":\"$MEAL_ID\""* ]]
echo "[PASS] Explicit and idempotent recent meal recording"

HISTORY_RESPONSE="$(curl --fail --silent --show-error --max-time 10 \
  -b "$OWNER_COOKIE_JAR" \
  "http://$FRONTEND_ADDRESS/api/conversations/$CONVERSATION_ID")"
[[ "$HISTORY_RESPONSE" == *'"role":"USER"'* ]]
[[ "$HISTORY_RESPONSE" == *'"role":"ASSISTANT"'* ]]
[[ "$HISTORY_RESPONSE" == *'"sampleData":true'* ]]
echo "[PASS] Persisted conversation history and sample recommendation"

curl --fail --silent --show-error --max-time 10 \
  -b "$OWNER_COOKIE_JAR" -c "$OWNER_COOKIE_JAR" \
  -X POST \
  "http://$FRONTEND_ADDRESS/api/conversations/$CONVERSATION_ID/deactivate" \
  -H "X-XSRF-TOKEN: $OWNER_CSRF_TOKEN" \
  -o /dev/null
DEACTIVATED_RESPONSE="$(curl --fail --silent --show-error --max-time 10 \
  -b "$OWNER_COOKIE_JAR" \
  "http://$FRONTEND_ADDRESS/api/conversations/$CONVERSATION_ID")"
[[ "$DEACTIVATED_RESPONSE" == *'"active":false'* ]]
echo "[PASS] Conversation deactivation"

curl --fail --silent --show-error --max-time 10 \
  -b "$OWNER_COOKIE_JAR" -c "$OWNER_COOKIE_JAR" \
  -X POST \
  "http://$FRONTEND_ADDRESS/api/auth/logout" \
  -H "X-XSRF-TOKEN: $OWNER_CSRF_TOKEN" \
  -o /dev/null
ME_AFTER_LOGOUT_STATUS="$(curl --silent --show-error --max-time 10 \
  -b "$OWNER_COOKIE_JAR" \
  -o /dev/null -w '%{http_code}' \
  "http://$FRONTEND_ADDRESS/api/auth/me")"
CONVERSATION_AFTER_LOGOUT_STATUS="$(curl --silent --show-error --max-time 10 \
  -b "$OWNER_COOKIE_JAR" \
  -o /dev/null -w '%{http_code}' \
  "http://$FRONTEND_ADDRESS/api/conversations/$CONVERSATION_ID")"
[[ "$ME_AFTER_LOGOUT_STATUS" == "401" ]]
[[ "$CONVERSATION_AFTER_LOGOUT_STATUS" == "401" ]]
echo "[PASS] Logout invalidates authenticated access"

trap - ERR
echo "[PASS] Docker service health and current cross-service flow"
