# Gemini 3.8 Flash Minimal Capability & Stability Probe

## 판정

```text
GEMINI CAPABILITY PROBE = RATE_LIMITED
```

Stage 1 plain-text gate는 3개 독립 요청 중 정확한 `OK` 응답 2개로 통과했다. Stage 2에서는 요청이 HTTP 503으로 반복 실패했고, 마지막 허용 retry에서 HTTP 429가 발생했다. 429 직후 추가 호출 없이 종료했으며 Stage 3–5는 실행하지 않았다. 따라서 menu classifier와 payload 크기의 안정성은 이번 결과로 판단할 수 없다. 5 Restaurant Pilot 재개도 아직 권고하지 않는다.

## Preflight 및 고정 입력

- Run ID: `gemini-capability-probe-1`
- 모델: `gemini-3.8-flash` only
- Stage 0: PASS — `google-genai 2.25.0` import, 45초 timeout, SDK config serialization, minimal structured schema 및 기존 classifier schema serialization 통과.
- Secret presence: `GEMINI_API_KEY_PRESENT=true`, `GOOGLE_API_KEY_PRESENT=false`. 실제 값은 출력/로그/artifact에 기록하지 않았다.
- Source SHA-256: `f02986eb39560164929b7314051324c3a45ec3c7d0742a966314958ae8119eed`; fixture SHA-256: `702ed02da4aa6836553d3d6e271f1cc72eaf6966a7f0ff43769c2dd5f8232145`. 이전 두 pilot과 동일.
- Frozen cohort 5개, source menu 188개. Stage 3/4/5 메뉴 ID는 snapshot과 frozen fixture에서 확인했다. Stage 5는 기존 Restaurant 9617의 chunk 0, IDs 8727–8738이다.
- 요청 간격 5초, 동시 요청 없음. 실제 시작 간격 최소 5.000초, 평균 5.592초. 하나의 요청이 약 9.1초 걸려 다음 시작 간격도 더 길었다.
- API attempts 8, retries 3. DB write 0, Qdrant write 0, Spring importer 없음, runtime 사용 없음.

## Stage 결과

`inputBytes`는 UTF-8 기준으로 Gemini `contents`에 넣은 문자열의 크기이며 SDK envelope/HTTP framing은 포함하지 않는다. Menu classifier 단계의 byte 수는 기존 classifier가 보내는 prompt를 그대로 직렬화해 계산했다.

| Stage | Request Type | Menu Count | Attempts | 유효 응답 | HTTP status | 평균 latency | Result |
| --- | --- | ---: | ---: | ---: | --- | ---: | --- |
| 1 | Plain text | 0 | 4 | 2/3 독립 요청 | 503 ×2 | 3.995s | PASS (최소 2개 기준) |
| 2 | Structured minimal | 0 | 4 | 0/2 독립 요청 | 503 ×3, 429 ×1 | 1.757s | FAIL / RATE_LIMITED |
| 3 | Menu classifier | 1 | 0 | 미실행 | — | — | NOT_RUN |
| 4 | Menu classifier | 3 | 0 | 미실행 | — | — | NOT_RUN |
| 5 | Menu classifier | 12 | 0 | 미실행 | — | — | NOT_RUN |

| Stage | Contents bytes |
| --- | ---: |
| 1 plain prompt | 22 |
| 2 structured prompt | 48 |
| 3 one-menu classifier prompt | 831 |
| 4 three-menu classifier prompt | 1,018 |
| 5 twelve-menu classifier prompt | 1,852 |

Stage 1 request sequence: 성공 → 503 → 해당 요청의 1회 retry 503 → 성공. 독립 요청 3개 가운데 2개가 정확히 `OK`를 반환했다.

Stage 2 sequence: 첫 독립 요청 503 → 1회 retry 503 → 두 번째 독립 요청 503 → 1회 retry 429. 마지막 429에서 즉시 종료했다. 503 event 5회 전체에 `Retry-After`는 관측되지 않았고 429 event에도 header는 없었다. API status는 503에서 `UNAVAILABLE`, 429에서 `RESOURCE_EXHAUSTED`였다. raw response body/error message는 저장하지 않았다.

## 해석

- 일반 Gemini 요청은 현재 환경에서 간헐적으로 성공한다(3개 중 2개). 최소 요청 capability는 확인됐지만 매 요청 안정성은 확인되지 않았다.
- Structured request는 provider에 전송됐으나 성공한 API response가 한 번도 없었다. 따라서 structured JSON의 schema 호환성/안정성은 **검증 불가**다. `STRUCTURED_OUTPUT_UNSTABLE`로 단정하지 않는다.
- 429가 Structured stage에서 발생해 hard stop했다. 이번 probe의 가장 가까운 원인은 provider availability/rate-limit이며, 메뉴 prompt/schema나 payload 문제의 증거는 없다.
- 1/3/12 메뉴 classifier 단계는 전부 미실행이다. Payload 증가와 오류의 관계를 비교할 수 없다.
- 메뉴 분류 의미 품질, clear-positive, negative/ambiguous fixture 결과는 이번 probe에서 평가하지 않았다.

## 필수 질문 답변

1. **아주 작은 일반 요청은 안정적이었나?** 매번은 아니다. 3개 독립 요청 중 2개가 정확히 성공해 stage 통과 기준은 만족했지만, 나머지 하나는 503과 retry 503이었다.
2. **Structured Output 자체는 안정적인가?** 판단 불가. 성공 response가 0개라 schema를 검증할 수 없었다.
3. **메뉴 1개 classification?** 미실행.
4. **메뉴 3개 classification?** 미실행.
5. **메뉴 12개 classification?** 미실행.
6. **503 발생 stage?** Stage 1에서 2회, Stage 2에서 3회.
7. **429 발생?** 예, Stage 2의 두 번째 독립 요청에 대한 retry에서 1회. 즉시 종료했다.
8. **Payload 크기와 실패 관계?** 추론할 수 없다. classifier 단계가 전부 호출되지 않았다.
9. **문제 원인에 가장 가까운 것?** provider availability/rate-limit. Structured Output 결함은 확인되지 않았다.
10. **5 Restaurant Pilot 재실행 준비?** 아니다. rate limit에서 중단됐고 Stage 2가 통과하지 못했다. 별도 quota/provider 안정성 확인 후 최소 진단을 재개해야 한다.

## Safety 및 산출물

- API 호출은 순차. retry는 5xx/network에 한 번만 허용했고, 400/403/429 retry는 0회.
- 429 이후 request 0회. Stage 3–5 request 0회.
- 기존 `gemini_menu_budget_pilot_*`, `gemini_menu_budget_retry_*`, fixture는 유지했다.
- Gemini API secret leak: NO (tracked 및 untracked/non-ignored 파일 scan).
- `docker compose config --quiet`: PASS. Gemini secret 전달 설정은 AI service에만 존재하며 Spring/React에는 설정되지 않았다.
- DB/Qdrant write: 0/0.
- Targeted probe/classifier tests: 23 passed. Full `./scripts/check-ai.sh`: 272 passed, 1 skipped, 1 existing deprecation warning. Ruff 및 `git diff --check`: PASS.
- Backend/Frontend harness: 범위 밖이며 미실행. Integration harness: DB/import 변경이 없어 미실행.
