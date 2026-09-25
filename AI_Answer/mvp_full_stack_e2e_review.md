# Isolated Full-stack MVP E2E 검토

## 판정

**MVP FULL-STACK E2E = PASS**

격리된 Spring `e2e` profile과 disposable MySQL에서 실제 Browser → React → Spring Chat/SSE → FastAPI → Ollama embedding → Qdrant v12 → Spring → SSE → React 흐름을 세 가지 사용자 Query로 확인했다. LLM Explanation은 비활성화되어 있었고, 모든 표시 reason은 deterministic Safe Fact 경로로 생성됐다.

수치와 Query별 결과는 [mvp_full_stack_e2e_results.json](mvp_full_stack_e2e_results.json)에 보존했다.

## 기존 E2E 공백과 격리 방식

기존 `scripts/check-integration.sh`는 기본 `docker-compose.yml`의 영속 MySQL volume을 사용하고, 샘플 Restaurant·사용자·대화 데이터를 저장한다. 따라서 이번 E2E에 재사용하지 않았다.

대신 [docker-compose.mvp-e2e.yml](../docker-compose.mvp-e2e.yml)로 고유한 Compose project를 만들었다. MySQL은 호스트 port를 publish하지 않고, `zeropay_lunch_mvp_e2e` database와 project 전용 named volume만 사용했다. Spring은 [application-e2e.yml](../backend/src/main/resources/application-e2e.yml)의 고정 datasource와 `SPRING_PROFILES_ACTIVE=e2e`를 사용했다. Harness는 활성 profile과 접속한 DB 이름을 실행 전에 확인했다. Flyway는 기존 V1–V21 migration을 처음부터 적용했으며 migration 파일은 수정하지 않았다.

기존 개발 Compose의 MySQL·서비스는 실행 전후 그대로 유지됐다. 격리 Backend network는 별도이며 기존 Backend/MySQL service에 연결하지 않는다. 개발 MySQL write는 0건이다.

## Fixture 및 서비스

E2E DB에는 Qdrant v12에서 실제 claim evidence가 존재하는 Restaurant `9617`을 재현하고, 논현동이 아닌 `9620`을 지역 hard-filter 제외 fixture로 넣었다. 양쪽 모두 운영 중·ZeroPay eligible·운영시간 조건을 만족하도록 구성해 지역 필터를 분리해서 확인했다. 인증은 일반 signup/login API로 E2E 전용 사용자를 만들었다.

별도 FastAPI image는 MySQL에 연결하지 않는다. Spring/React/FastAPI는 disposable Compose project에서 실행했고, Ollama와 Qdrant는 host의 기존 read-only 데이터 서비스에 연결했다.

## 안전 장치

- Semantic runtime: `true`; LLM Explanation: `false`.
- Qdrant guard proxy는 `zeropay_semantic_claim_pilot_v12` collection info 조회와 `/points/query`만 허용하고 다른 경로/쓰기 method를 차단했다. point count는 40에서 시작해 40으로 끝났다.
- Ollama guard proxy는 `qwen3-embedding:0.6b`의 `/api/embed`만 허용했다. `/api/chat`, `/api/generate` 등 generation 호출은 0회였다.
- proxy가 Qdrant query payload의 Restaurant scope와 응답 payload를 비교했다. 후보 `[9617]`, 결과 `[9617]`, scope 위반 0.
- 실행 종료/오류 시 harness trap은 고유 Compose project만 중지하고 해당 project volume을 제거한다. 최종 실행 후 E2E container 및 volume이 제거됐고, 기존 개발 Compose 서비스는 계속 실행 중이었다.

## Browser 결과

Playwright는 기존 저장소에 없어서 `@playwright/test`를 최소 dev dependency로 추가했다. Browser는 실제 React/nginx와 Spring HTTP/SSE를 사용했고 API mock은 사용하지 않았다. 세 번의 요청 모두 기존 `recommendations` SSE event의 Restaurant ID와 `reason`이 React 카드에 표시된 값과 일치했다. 결과는 각각 1개이며 max 3 제한을 만족했다.

| Query | 추천 ID | React reason |
|---|---:|---|
| 떡볶이 먹고 싶어 | 9617 | 떡볶이 메뉴가 확인되어 추천했어요. |
| 혼밥하면서 떡볶이 먹고 싶어 | 9617 | 떡볶이 메뉴가 확인되고 혼밥하기 좋다는 고객 평가가 확인돼 추천했어요. |
| 가성비 좋은 곳 | 9617 | 가성비가 좋다는 고객 평가가 확인돼 추천했어요. |

두 번째 Query는 음식 및 식사 맥락의 Evidence를 모두 반영했다. 지역 외 fixture `9620`과 후보 scope 밖 Restaurant는 반환되지 않았다. 카드와 reason이 Browser에서 표시됐으며, 실제 데이터베이스의 대화 persistence는 격리 DB에만 발생했다.

## 실제 호출 및 쓰기 결과

- Intent Analysis: 3회
- Semantic Retrieval: 3회
- Qdrant query: 6회 (각 추천 retrieval 및 설명용 evidence lookup 포함)
- Ollama embedding: 6회
- Qwen Explanation generation: 0회
- Qdrant writes: 0회; point count 40 → 40
- E2E DB: fixture Restaurant 2건, 사용자 1건, conversation 1건, chat message 6건, recommendation row 3건
- 개발 MySQL writes: 0건

테스트 후 E2E DB volume은 제거했다. 정확한 숫자는 결과 JSON에 기록했다.

## 검증 명령

- Browser Playwright: 1 test passed (3 Query)
- Frontend Harness: build 성공, 5 test suites / 11 tests 통과
- Backend Harness: Gradle build/test 성공
- AI Harness: 228 passed, 1 skipped (live contract test)
- `git diff --check`: 통과
- 기존 `scripts/check-integration.sh`는 dev DB를 쓰기 때문에 실행하지 않았다. 이번 격리 Browser E2E가 실제 통합 경로를 대신 검증했다.

구현 가능한 반복 실행 스크립트는 [check-mvp-e2e.sh](../scripts/check-mvp-e2e.sh)이며, Qdrant/Ollama read-only guard는 [read_only_dependency_proxy.py](../scripts/e2e/read_only_dependency_proxy.py)에 있다.

## 한계 및 다음 단계

이번 E2E는 하나의 승인 Restaurant fixture와 세 Query로 MVP 사용자 경로를 검증한 통합 smoke test이며 추천 품질의 재평가나 다수 사용자 동시성 시험은 아니다. LLM 설명은 검증 기준 미달에 따라 계속 OFF다. 이번 작업은 React UI 연결을 포함했으나 AWS 배포, CI, 관측성 구축은 수행하지 않았다.

기존 사용자 변경사항은 보존했다. Git add/commit/push는 하지 않았다.
