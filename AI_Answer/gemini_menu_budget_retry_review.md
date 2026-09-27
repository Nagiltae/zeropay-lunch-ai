# Gemini Menu Budget Retry Review

## 판정

```text
GEMINI MENU BUDGET PILOT = INCOMPLETE_PROVIDER_AVAILABILITY
```

이번 실행은 semantic quality 평가 실패가 아니다. 고정 입력 188개 중 Gemini가 반환한 분류는 0개이며, 첫 chunk가 두 번의 HTTP 503으로 끝나 provider availability stop이 발생했다. 평가 fixture는 변경하지 않았고, 결과가 불완전하므로 quality metric은 계산하지 않았다.

## 고정 입력 및 안전 경계

- Run ID: `gemini-menu-budget-v2-retry-1`
- Model: `gemini-3.8-flash`
- Cohort: 9617, 9571, 9568, 10042, 9559 (5개 Restaurant, 188개 menu)
- Source SHA-256: `f02986eb39560164929b7314051324c3a45ec3c7d0742a966314958ae8119eed`
- Frozen fixture SHA-256: `702ed02da4aa6836553d3d6e271f1cc72eaf6966a7f0ff43769c2dd5f8232145`
- Chunk size 12, 예상 17개 chunk/request. 입력 및 fixture는 기존 pilot과 동일했다.
- Preflight: `GEMINI_API_KEY_PRESENT=true`, `GOOGLE_API_KEY_PRESENT=false`; key 값은 출력·artifact·로그에 기록하지 않았다.
- 요청은 단일 순차 runner에서 수행했다. 설정 간격은 3초, 관측된 두 request 시작 간격은 4.118초였다.
- 첫 503 뒤 exponential cooldown 후 단 한 번 retry했다. 두 번째 503 이후 추가 호출은 없었다.
- diagnostic Gemini request 0회. DB write 0, Qdrant write 0, Spring importer 미구현, runtime에서 raw Gemini 결과 미사용.

## 실행 결과

| Metric | Retry 결과 |
| --- | ---: |
| Restaurant 완료 | 0/5 |
| 메뉴 최종 상태 할당 | 0/188 |
| Gemini request attempts | 2 |
| 성공 응답 / 실패 응답 | 0 / 2 |
| Retry | 1 |
| HTTP 5xx | 2 (503 2회) |
| HTTP 429 / 403 / 400 | 0 / 0 / 0 |
| Network error / timeout | 0 / 0 |
| Fixture quality evaluation | 실행하지 않음 |

첫 chunk는 Restaurant 9617, chunk index 0 (menu 8727–8738)이었다. 안전하게 기록된 API status는 `UNAVAILABLE`, HTTP status는 503, `Retry-After` header는 관측되지 않았다. raw error body, request body, URL, credential은 보존하지 않았다.

## Reliability 구현 및 테스트

- `RequestPacer`가 real request 시작 전 최소 간격을 적용하며 interval은 `GEMINI_REQUEST_INTERVAL_SECONDS` (기본 3초)로 설정한다. retry도 같은 pacer를 통과한다.
- network/5xx에 한해 initial + 최대 1회 retry를 허용한다. 400/403/429는 retry하지 않는다. 403/429/400은 terminal checkpoint로 남기고 재실행 요청을 차단하며, 5xx 재시도 후에도 실패하면 provider-availability terminal 상태다.
- 새 run 전용 plan/checkpoint/results 경로를 사용한다. source/fixture SHA와 run ID/model을 resume 시 검증하고, frozen menu ID 목록과 결과가 정확히 일치하는 성공 chunk만 skip한다.
- Checkpoint에는 request ordinal, timestamp, restaurant/chunk, attempt, status code, safe API status/error category, Retry-After 존재 여부를 남긴다. raw provider error는 저장하지 않는다.
- Targeted 테스트: pacing, 5xx 단일 retry, 400/403/429 no-retry, exact-chunk resume 및 terminal resume 거부, 구조/ID validation을 포함해 14 passed.
- Ruff check 통과. 전체 `./scripts/check-ai.sh` 결과는 별도 기록한다.

## 품질 및 import 상태

5/5 completion과 188/188 assignment 조건을 만족하지 못했으므로 clear positive, critical negative, ambiguous fixture 평가는 모두 미수행이다. 따라서 weight-based / multi-person / alcohol / drink / course의 false-positive 수와 clear-positive accuracy는 **UNKNOWN / 평가 불가**이지 0으로 간주하지 않는다. semantic 품질에 대한 GO 또는 NO_GO 결론을 내리지 않는다.

기존 Qwen v1은 5개 중 2개 Restaurant 완료, 3 timeout, 승인 분류 0이었다. 첫 Gemini 실행은 12/188만 반환했고 429에서 종료했다. 이번 retry는 provider 503으로 첫 chunk도 완료하지 못했다. 서로 다른 원인의 operational failure이며 모델 품질 비교 근거가 아니다.

| Metric | Qwen v1 | Gemini first run | Gemini retry |
| --- | ---: | ---: | ---: |
| Restaurant 완료 | 2/5 | 0/5 | 0/5 |
| 메뉴 output | 기록 기준 미완료 | 12/188 | 0/188 |
| timeout | 3 | 0 | 0 |
| 429 | 해당 없음 | 1 | 0 |
| 5xx | 해당 없음 | 2 | 2 |
| semantic fixture 평가 가능 | 제한적/불완전 | 아니오 | 아니오 |
| Import review | NO | NO | NO |

Gemini 결과는 DB에 저장되지 않았다. Spring importer나 classification persistence migration은 생성하지 않았다. Runtime explicit-budget fail-closed 동작은 그대로이며 raw Gemini 결과를 사용하지 않는다. 26개 확대는 승인되지 않았다.

## 재현 산출물

- `gemini_menu_budget_retry_plan.json`: frozen plan 및 quality gate
- `gemini_menu_budget_retry_checkpoint.json`: 2 attempts, terminal provider availability 상태
- `gemini_menu_budget_retry_results.json`: 실제 결과와 metrics
- 기존 `gemini_menu_budget_pilot_*` artifact 및 fixture는 덮어쓰지 않았다.

## 필수 질문 답변

1. **Pacing:** sequential request pacer를 initial 및 retry 호출 직전에 적용했다.
2. **간격:** 설정 3초, 관측 평균 4.118초 (request 2회 사이 1구간).
3. **429:** 발생하지 않았다.
4. **5xx:** 2회. 첫 요청 실패 후 1회 retry했으며 회복되지 않았다.
5. **5 Restaurant 완료:** 아니오, 0/5.
6. **188개 메뉴 상태:** 아니오, 0/188.
7. **WEIGHT_BASED → ELIGIBLE:** 평가 불가 (fixture 메뉴를 응답받지 못함).
8. **MULTI_PERSON → ELIGIBLE:** 평가 불가.
9. **ALCOHOL/DRINK → ELIGIBLE:** 평가 불가.
10. **Clear positive accuracy/UNKNOWN:** 평가 불가.
11. **품질 평가 충분성:** 아니오. semantic 품질 평가 자체가 성립하지 않는다.
12. **Spring importer 조건:** 충족하지 못함.
13. **DB 저장:** 하지 않음.
14. **Runtime budget filter가 raw 결과 사용:** 아니오.
15. **26개 확대 가능:** 아니오. 고정 5곳의 operational completion부터 미완료다.

## 검증 기록

- Fixture/source SHA preflight: PASS, 이전 frozen 값과 동일.
- Gemini API: 실제 2회 호출, 양쪽 모두 503; 이후 자동 요청 없음.
- Targeted AI tests: 14 passed.
- Ruff: passed.
- Full AI harness: PASS (`264 passed, 1 skipped`; 기존 deprecation warning 1개).
- Backend harness: NOT_RUN (이번 코드 변경은 AI 측에 한정).
- Integration harness: NOT_RUN (DB import/변경 없음).
- `docker compose config --quiet`: PASS; Compose 설정에서 Gemini 환경변수는 AI service에만 전달된다.
- `git diff --check`: PASS.
- Secret scan: PASS, `Gemini API secret leak = NO` (tracked 및 untracked/non-ignored files 검사, key 미출력).
