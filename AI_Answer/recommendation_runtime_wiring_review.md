# Recommendation Runtime Wiring 검토

작성일: 2026-09-25

## 1. 요약

Spring `RestaurantRecommendationService`에 FastAPI Intent와 candidate-scoped Semantic Retrieval을 opt-in 연결했다. `AI_SEMANTIC_RUNTIME_ENABLED` 기본값은 `false`이므로 기본 서비스 동작은 기존 deterministic 경로다. Runtime을 켜도 Spring이 논현동 모집단·운영시간·ZeroPay·예산·비선호·최근 식사/최근 Venue 필터, 최종 ranking, Venue dedup 및 최대 3건을 계속 소유한다.

## 2. 500m 요구사항 조사

현재 추천 repository query는 `legal_dong_code = '11680108'`와 운영/휴무 일정, `active`, `recommendation_ready`, `recommendation_eligibility='ELIGIBLE'`, `zero_pay_available`를 적용한다. 거리 계산 또는 500m 필터는 없다. 인접 법정동 코드 `11680107` fixture가 제외되는 Repository 회귀 테스트를 추가했다.

활성 소스/문서에서 500m 요구는 발견되지 않았다. `AI_CHANGELOG.md`의 과거 radius 실험 기록, 적용된 V18 migration의 historical radius column comment, `docs/database.md`의 historical 스키마 설명은 과거 호환 정보이므로 수정하지 않았다. 새 Runtime에는 radius, workplace 위치 또는 좌표 계산을 추가하지 않았다.

## 3. 기존과 변경된 Recommendation Flow

기존 Spring 흐름은 `RecommendationContextService`가 사용자 설정·최근 식사와 intent를 모으고, repository가 논현동·운영·ZeroPay·추천 준비 상태를 조회한 뒤 Service가 예산·비선호·개별 최근 식사를 적용하고 confirmed active Venue의 최근 식사 제외/중복 제거, deterministic score, max 3을 수행했다. 현재 거리는 필터에 없었다.

변경 후 Runtime ON 흐름:

```text
Query
→ FastAPI intent (기존 AnalyzedIntent로 변환)
→ Spring repository + Service hard filters
→ 최근 식사/최근 confirmed-active-Venue 제외
→ 전체 남은 candidateRestaurantIds를 FastAPI에 전달
→ semantic cosine을 bounded tie-break signal로 부착
→ Spring deterministic score 정렬
→ confirmed-active Venue dedup
→ 최대 3건
```

Runtime OFF에서는 conditional FastAPI beans가 등록되지 않으며 기존 deterministic intent 및 추천 경로를 유지한다.

## 4. 변경 사항

- `FastApiRecommendationRuntimeConfiguration`: `app.ai.semantic-runtime-enabled=true`일 때만 client/adapter/enricher를 등록한다.
- `FastApiIntentAnalysisAdapter`: FastAPI budget과 food/context/taste term을 기존 `AnalyzedIntent`에 매핑한다. Spring default budget, preference, allergy, recent meal은 계속 Spring context 소유이며 category는 기존 deterministic 분석 결과를 보존한다.
- `RestaurantRecommendationService`: 모든 기존 hard-filter 및 최근 동일 Venue 제외 후, Venue 최종 dedup/max3 전에 남은 모든 ID로 retrieval을 호출한다. Retrieval 결과가 없는/미색인 후보도 유지한다.
- Semantic ranking은 내부 우선순위 점수 `retrievalScore`를 사용하지 않는다. `semanticSimilarity`만 유한성 검사 후 `[0,1]`로 clamp하고, 기존 deterministic score가 동률인 경우에만 보조 tie-breaker로 쓴다. 기존 budget/category/preference 점수를 대체하거나 hard filter를 되돌리지 않는다.
- Retrieval fallback은 기존 `AI_FALLBACK_ENABLED` 정책을 따른다. 활성 fallback이면 timeout/503/잘못된 응답에서 후보 목록을 유지하고, 비활성 설정이면 기존 계약대로 예외를 전파한다. HTTP 재시도는 없다.

설정은 `AI_SEMANTIC_RUNTIME_ENABLED=false`가 기본값이다. 기존 connect/response timeout(2s/8s), base URL, fallback을 재사용했다. LangGraph, LLM explanation, React, migration은 변경하지 않았다.

## 5. 후보·지역·Venue 안전성

Hard Filter 탈락 대상은 retrieval scope에 들어가지 않는다. FastAPI는 기존 Qdrant `restaurantId` 및 `claimType` payload filter로 scope 검색하고 Java client도 응답 ID가 scope 안인지 재검증한다. 검색 결과에 없는 Restaurant는 삭제되지 않는다. Semantic retrieval은 final Venue dedup/max3 이전에 호출되고 Venue Association을 생성/수정하지 않는다.

## 6. 검증 결과

| 검증 | 결과 |
|---|---|
| Recommendation/client/intent/fallback targeted tests | PASS |
| Spring Recommendation 실제 service → FastAPI live flow | PASS; 9617 한 후보, Intent 및 scoped retrieval 모두 HTTP 200 |
| Spring hard-filter scope 및 pre-dedup/pre-max3 | PASS; 4개 hard-filter 후보 ID를 전달하고 semantic tie-break 결과 포함 최대 3건 반환 |
| 미색인 후보 유지 | PASS |
| legal-dong outside 대상 | PASS; 다른 법정동 fixture 제외, 거리 필터 사용 없음 |
| Backend Harness `scripts/check-backend.sh` | PASS |
| AI Harness `scripts/check-ai.sh` | PASS; 203 passed, 1 skipped, 1 upstream deprecation warning |
| `git diff --check` | PASS |

실제 local live flow는 loopback Uvicorn(18092), 기존 Ollama embedding 모델과 Qdrant v12 collection을 사용했다. Uvicorn log에서 Intent 2회, Retrieval 3회 요청이 200으로 확인됐다(서비스 flow 1회와 기존 live contract 검증 포함). FastAPI의 MySQL 접속은 없고 Qdrant API는 query-only다. v12 collection 사후 상태는 40 points, 1024 dimension, Cosine이었다. 이 작업에서 전체 point hash 전후 비교는 수행하지 않았으나 collection 생성/upsert/delete 호출은 하지 않았다.

실제 공개 Chat/SSE 흐름 및 실제 MySQL 추천 read path는 수행하지 않았다. 공개 Chat 요청은 메시지/대화 영속화를 포함하며 작업 안전조건이 MySQL write 금지이기 때문이다. 대신 실제 `RestaurantRecommendationService`를 호출하고 repository/context를 mock하여 AI 연결만 실제화한 read-only local flow로 검증했다. `check-integration.sh`는 실행하지 않았다. 이 Harness는 개발 MySQL/Flyway 및 사용자 데이터 쓰기를 포함할 수 있다.

## 7. 데이터·Git 안전

이 작업에서 MySQL write, migration, Restaurant/Eligibility/Venue 변경, Provider/Qwen/Detail 실행, Profile/Embedding Batch, Qdrant write, collection 변경, React 변경은 없었다. 실행한 local Uvicorn process는 종료했다. Git add/commit/push 및 destructive Git 명령은 실행하지 않았다. 기존 Working Tree 변경과 산출물을 보존했다.

## 8. 미완료 및 다음 단계

- Runtime feature flag는 기본 OFF다. 이를 환경에서 ON으로 배포하기 전에 내부 네트워크 접근 제어, 응답 시간/오류 관측성, Qdrant pilot collection의 운영 적합성 및 semantic tie-break가 동률 순위에 미치는 영향을 별도 검토해야 한다.
- 공개 사용자 추천 API/SSE까지 실제 MySQL read-only로 관통하는 통합 검증은 하지 않았다.
- LLM 설명 생성, React 화면 변경, LangGraph와 전체 사용자 E2E는 범위 밖이며 미구현이다.
- 최종 책임은 계속 Spring이다. AI semantic score가 hard filter나 Spring deterministic score를 우회하지 않는다.
