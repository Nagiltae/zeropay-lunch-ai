#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="zplunch_mvp_e2e_${$}"
COMPOSE=(docker compose -p "$PROJECT" -f "$ROOT_DIR/docker-compose.mvp-e2e.yml")
ARTIFACT_DIR="$ROOT_DIR/AI_Answer"
RUN_DIR="$(mktemp -d "${TMPDIR:-/tmp}/zplunch-mvp-e2e.XXXXXX")"
QDRANT_GUARD_PID=""
OLLAMA_GUARD_PID=""
RESULT="$ARTIFACT_DIR/mvp_full_stack_e2e_results.json"
ASSESSMENT="BLOCKED"

cleanup() {
  local code=$?
  if [[ "$code" -ne 0 ]]; then
    RESULT="$RESULT" PROJECT="$PROJECT" node -e 'const fs=require("fs");fs.writeFileSync(process.env.RESULT,JSON.stringify({environment:{database:"isolated-e2e",semanticRuntime:true,llmExplanation:false},queries:[],browserE2E:"NOT-PASS",semanticRequests:0,qdrantQueries:0,embeddingCalls:0,llmExplanationCalls:0,devMysqlWrites:0,e2eMysqlWrites:0,qdrantWrites:0,cleanup:"scoped E2E resources removed by EXIT cleanup",assessment:"BLOCKED",failureNote:"Harness failed before verified browser completion; see command output."},null,2)+"\n")'
  fi
  [[ -z "$QDRANT_GUARD_PID" ]] || kill "$QDRANT_GUARD_PID" 2>/dev/null || true
  [[ -z "$OLLAMA_GUARD_PID" ]] || kill "$OLLAMA_GUARD_PID" 2>/dev/null || true
  if [[ -n "$PROJECT" ]]; then
    "${COMPOSE[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
  fi
  rm -rf "$RUN_DIR"
  exit "$code"
}
trap cleanup EXIT INT TERM

cd "$ROOT_DIR"
command -v docker >/dev/null
command -v curl >/dev/null
command -v npm >/dev/null
docker info >/dev/null
docker compose version >/dev/null
for port in 3017 6335 11435; do
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "[FAIL] Required isolated E2E port $port is already in use."
    exit 1
  fi
done

# Never use the repository's default Compose project; its MySQL volume is persistent dev data.
[[ "$PROJECT" == zplunch_mvp_e2e_* ]]
"${COMPOSE[@]}" config --quiet
[[ "$(curl -fsS http://127.0.0.1:6333/collections/zeropay_semantic_claim_pilot_v12 | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{const x=JSON.parse(s);process.stdout.write(String(x.result.points_count))})')" -gt 0 ]]
QDRANT_BEFORE="$(curl -fsS http://127.0.0.1:6333/collections/zeropay_semantic_claim_pilot_v12 | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>process.stdout.write(String(JSON.parse(s).result.points_count)))')"
curl -fsS http://127.0.0.1:11434/api/tags | rg -q 'qwen3-embedding:0.6b'

python3 "$ROOT_DIR/scripts/e2e/read_only_dependency_proxy.py" --mode qdrant --port 6335 >"$RUN_DIR/qdrant-guard.log" 2>&1 &
QDRANT_GUARD_PID=$!
python3 "$ROOT_DIR/scripts/e2e/read_only_dependency_proxy.py" --mode ollama --port 11435 >"$RUN_DIR/ollama-guard.log" 2>&1 &
OLLAMA_GUARD_PID=$!
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:6335/collections/zeropay_semantic_claim_pilot_v12 >/dev/null \
    && kill -0 "$QDRANT_GUARD_PID" 2>/dev/null && kill -0 "$OLLAMA_GUARD_PID" 2>/dev/null; then break; fi
  sleep 1
done

"${COMPOSE[@]}" up -d --build --wait --wait-timeout 240
DB_NAME="$("${COMPOSE[@]}" exec -T mysql mysql -N -u mvp_e2e_user -pmvp_e2e_only_password -e 'SELECT DATABASE()' zeropay_lunch_mvp_e2e 2>/dev/null | tail -n 1)"
[[ "$DB_NAME" == zeropay_lunch_mvp_e2e ]]
"${COMPOSE[@]}" exec -T backend sh -c 'test "$SPRING_PROFILES_ACTIVE" = e2e'
"${COMPOSE[@]}" exec -T mysql mysql --default-character-set=utf8mb4 -u mvp_e2e_user -pmvp_e2e_only_password zeropay_lunch_mvp_e2e < "$ROOT_DIR/scripts/fixtures/mvp_e2e_restaurants.sql"

cd "$ROOT_DIR/frontend"
npx playwright test --config playwright.config.ts --reporter=list | tee "$RUN_DIR/playwright.log"
cd "$ROOT_DIR"

# Assert actual DB target and writes, then preserve counts before disposable volume cleanup.
DB_COUNTS="$("${COMPOSE[@]}" exec -T mysql mysql -N -u mvp_e2e_user -pmvp_e2e_only_password zeropay_lunch_mvp_e2e -e \
  "SELECT (SELECT COUNT(*) FROM users),(SELECT COUNT(*) FROM conversations),(SELECT COUNT(*) FROM chat_messages),(SELECT COUNT(*) FROM message_recommendations)")"
QDRANT_AFTER="$(curl -fsS http://127.0.0.1:6333/collections/zeropay_semantic_claim_pilot_v12 | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>process.stdout.write(String(JSON.parse(s).result.points_count)))')"
[[ "$QDRANT_AFTER" -gt 0 ]]
[[ "$QDRANT_AFTER" == "$QDRANT_BEFORE" ]]
QDRANT_QUERIES="$(rg -c '"event": "allowed", "mode": "qdrant", "path": "/collections/zeropay_semantic_claim_pilot_v12/points/query"' "$RUN_DIR/qdrant-guard.log" || echo 0)"
EMBEDDING_CALLS="$(rg -c '"event": "allowed", "mode": "ollama", "path": "/api/embed"' "$RUN_DIR/ollama-guard.log" || echo 0)"
GENERATION_CALLS="$(rg -c '"path": "/api/(chat|generate)"' "$RUN_DIR/ollama-guard.log" || echo 0)"
SEMANTIC_REQUESTS="$("${COMPOSE[@]}" logs --no-color ai | rg -c 'POST /internal/v1/semantic-retrieval' || echo 0)"
SCOPE_VIOLATIONS="$(python3 - "$RUN_DIR/qdrant-guard.log" <<'PY'
import json, sys
violations = 0
for line in open(sys.argv[1], encoding="utf-8"):
    try:
        item = json.loads(line)
    except json.JSONDecodeError:
        continue
    if item.get("mode") == "qdrant" and item.get("path", "").endswith("/points/query"):
        if not set(item.get("returnedRestaurantIds", [])).issubset(set(item.get("candidateRestaurantIds", []))):
            violations += 1
print(violations)
PY
)"
[[ "$QDRANT_QUERIES" -gt 0 && "$EMBEDDING_CALLS" -gt 0 && "$SEMANTIC_REQUESTS" -ge 3 ]]
[[ "$GENERATION_CALLS" == 0 && "$SCOPE_VIOLATIONS" == 0 ]]

INTENT_REQUESTS="$("${COMPOSE[@]}" logs --no-color ai | rg -c 'POST /internal/v1/intent-analysis' || echo 0)"
RESULT="$RESULT" QDRANT_BEFORE="$QDRANT_BEFORE" QDRANT_AFTER="$QDRANT_AFTER" \
DB_COUNTS="$DB_COUNTS" QDRANT_QUERIES="$QDRANT_QUERIES" EMBEDDING_CALLS="$EMBEDDING_CALLS" \
SCOPE_VIOLATIONS="$SCOPE_VIOLATIONS" INTENT_REQUESTS="$INTENT_REQUESTS" \
GENERATION_CALLS="$GENERATION_CALLS" SEMANTIC_REQUESTS="$SEMANTIC_REQUESTS" \
PLAYWRIGHT_LOG="$RUN_DIR/playwright.log" \
  node "$ROOT_DIR/scripts/e2e/write_results.mjs"

echo "[PASS] isolated browser E2E; results: $RESULT"
