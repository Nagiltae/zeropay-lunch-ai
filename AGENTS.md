# Project Overview

ZeroPay Lunch AI는 사용자의 자연어·취향·예산·최근 식사 기록을 바탕으로 음식점을 추천하는 모노레포다. 현재 서비스 모집단은 KOMSCO 공공데이터의 서울 강남구 논현동(`legal_dong_code=11680108`, `providerInstitutionCode=I0000002`, `industryCode=561`, `businessStatusName=계속사업자`) 음식점이다.

핵심 흐름은 `React → Spring Boot → MySQL`이다. 추천 Runtime은 feature flag가 켜진 경우 `Spring → FastAPI Intent → Spring Hard Filter → candidate-scoped Retrieval → Spring Ranking/Venue dedup/max3`를 사용한다. 기본값은 OFF이며, 별도의 `ai/` Python CLI는 KOMSCO→공식 Provider/Qwen→Canonical→PCMap Place ID·상세 수집을 담당한다.

# Architecture

- React: 인증된 채팅, 취향·식사 기록 UI, Spring API/SSE 호출. FastAPI를 직접 호출하지 않는다.
- Spring Boot: 공개 API, 인증/세션, 대화·취향·식사 영속화, KOMSCO import/scheduler, 추천 business rule과 MySQL persistence.
- FastAPI: `/health`, 내부 intent/scoped retrieval API. Spring 추천 경로는 opt-in이며 FastAPI는 후보 검색·근거 trace만 소유한다.
- `ai/`: Provider 후보 조회, Qwen Entity Resolution, Canonical persistence, PCMap Place ID/detail CLI. 운영 추천 요청 경로와 별개다.
- MySQL/Flyway: 원본·검증·추천 데이터의 기준 저장소. Qdrant는 파생 검색 Shadow Pilot 저장소이며 최종 추천 권한은 Spring에 있다.

자세한 책임 경계는 [docs/architecture.md](docs/architecture.md), API는 `docs/api-contract.md`, 스키마는 `docs/database.md`를 canonical 문서로 본다.

# Module Ownership

| 영역 | 소유 로직 |
|---|---|
| `frontend/` | 화면, 인증 상태, 채팅/SSE, 취향·식사 기록 요청 |
| `backend/.../restaurant/importer` | KOMSCO API pagination/dedup/filter/upsert, Sunday scheduler, cleanup |
| `backend/.../restaurant` | Restaurant source state, recommendation eligibility, deterministic candidate query |
| `backend/.../recommendation` | 추천 context, fallback intent 분석, 결정론적 후보 필터/순위 |
| `ai/app/providers/` | Kakao/NAVER 공식 후보 조회와 입력 manifest |
| `ai/app/entity_resolution/` | Qwen ranking, structured validation, quality gate/cache |
| `ai/app/canonical/` | ACCEPT Canonical·provider mapping 생성과 MySQL persistence |
| `ai/app/naver/` | Maps UI/allSearch Place ID와 HOME/MENU/HOURS/REVIEW 수집 |
| `ai/app/batch/` | E2E orchestration, 진행률·runtime report, pacing |

# Current State

## Completed

- Spring Recommendation에 FastAPI intent 및 semantic retrieval을 opt-in 연결했다. Intent 오류는 기존 deterministic analyzer로, retrieval 오류는 설정된 fallback 정책으로 처리한다. hard-filter 후보 전체를 Venue dedup/max3 전에 검색하고 bounded cosine은 deterministic score 동률에서만 tie-breaker로 사용한다.

- 논현동·I0000002 KOMSCO importer와 주간 일요일 03:00(Asia/Seoul) 동기화/명시적 cleanup 경로.
- React와 Spring의 역/반경 선택 runtime 계약 제거; 좌표 metadata와 historical schema는 보존.
- 공식 Kakao/NAVER 후보 fusion과 Qwen3.5 Entity Resolution: candidate dedup, bounded prefetch, fingerprint 기반 incremental 처리와 REJECT cache.
- PCMap Maps UI/allSearch capture 기반 numeric Place ID linking과 DOM-only HOME/MENU/HOURS/REVIEW detail persistence.
- DOM-only HOME/MENU/REVIEW crawler와 idempotent detail persistence.
- `restaurant_naver_verifications` V14 provenance/status/reason 구조와 V15 source fingerprint. `restaurants.active`, `recommendation_eligibility`, 외부 Place mapping과 분리된다.
- Official Kakao/NAVER provider fusion과 Qwen3.5 Entity Resolution 경로. stable manifest 입력으로 실행하며 동일 source fingerprint의 확정 REJECT만 재사용한다.
- parser, semantic prompt, out-of-scope/non-food safety, source-change 재검증 회귀 테스트.
- V21 Venue 1차 모델(`venues`, `restaurant_venue_associations`)과 `CONFIRMED` association 기반 Spring 추천 중복 제거를 추가했다. 기존 Restaurant/Place ID/Detail 소유권과 API 계약은 유지하며 전체 데이터 이전은 하지 않았다.
- Venue 연결 검토/승인 API를 추가했다. 후보는 읽기 전용으로 찾고, 관리자가 `PENDING`을 명시적으로 `CONFIRMED` 또는 `REJECTED`로 결정한다. 실제 운영 association은 아직 0건이다.
- `CONFIRMED + ACTIVE` Venue를 최근 식사 해석에도 적용하되 원본 meal의 `restaurant_id`는 보존한다. 격리 MySQL 검증과 기존 Numeric Place ID 기반 9560 Detail 저장/freshness 재실행을 완료했다.
- `AI_SEMANTIC_RUNTIME_ENABLED` 기본 OFF의 Spring Recommendation wiring을 완료했다. opt-in 시 FastAPI intent → 기존 hard filters → full candidate-scoped retrieval → bounded semantic tie-break → Venue dedup/max3 순서이며 local live service flow와 AI/Backend Harness를 통과했다. 상세 결과는 `AI_Answer/recommendation_runtime_wiring_review.md`에 기록했다.
- 최종 Spring 후보의 `reason`에만 붙는 Grounded Recommendation Explanation API/Client를 연결했다. 설명 단계에서 최종 Restaurant ID scope 안의 intent 보조 Evidence를 읽고 Safe Fact로 제한한다. 실제 3-query Qwen 재검증에서 grounded 3/3은 미달했으므로 Runtime 기본 OFF를 유지한다. `AI_Answer/recommendation_explanation_revalidation_review.md` 참조.
- `AI_SEMANTIC_RUNTIME_ENABLED`와 `AI_LLM_EXPLANATION_ENABLED`를 분리했다. 둘 다 기본 OFF이며, Semantic ON/LLM OFF에서는 최종 추천 후보의 Safe Fact 기반 deterministic reason을 반환하고 Ollama client도 생성하지 않는다. React 채팅 카드와 기존 SSE `recommendations.items[].reason` 연결을 테스트로 확인했다. 관련 결과는 `AI_Answer/mvp_recommendation_ui_e2e_review.md` 참조.
- disposable MySQL을 사용하는 별도 Spring `e2e` profile 및 Playwright full-stack harness를 추가했다. React Browser → Spring Chat/SSE → FastAPI → query-only Qdrant v12/embedding-only Ollama → deterministic reason 흐름을 세 Query로 검증했다. LLM generation 0회, Qdrant point count 불변, E2E 전용 DB/volume cleanup을 확인했다. 상세 결과는 `AI_Answer/mvp_full_stack_e2e_review.md` 참조.

## In Progress

- Step 8 End-to-End preflight에서 legacy VERIFIED 10건을 Qwen3.5로 재검증해 fingerprint를 저장했고,
  동일 fingerprint REJECT 5건의 provider/Qwen 0호출을 확인했다. NAVER_LOCAL 5건은 실제
  PCMap UI allSearch capture로 numeric NAVER Place ID를 연결했고, 그중 3건의
  HOME/MENU/영업시간/REVIEW를 저장했다. 동일 대상 재실행은 Qwen/link/detail 0건이었다.
  513건 전체 배치는 미실행.

## Next

- 513건 전체 배치는 별도 작업으로 남아 있으며 이번 Runtime wiring에서 실행하지 않았다.
- 전체 Batch가 별도 승인되어 실행될 경우 403/429/CAPTCHA에서 즉시 중단하고 DB 기반으로 재개한다.
- Semantic Runtime은 기본 OFF로 유지한다. 이를 켜는 배포 전 설정·관측성·장애 대응 검토를 별도 수행한다.
- 실제 LLM Explanation은 3/3 GROUNDED가 확인될 때까지 기본 OFF로 유지한다. Safe Fact deterministic reason은 semantic runtime opt-in에서 기본 경로다.
- 2026-09-25 Detail Quality Backfill에서 source-grounded `ProfileReadinessPolicy`를 적용했다. 360곳에서 검증 기준선 4곳, 최종 strict-ready 26곳, 신규 READY 22곳이다. 이전 audit의 5번째 9590은 원문과 요일이 불일치해 제외했다. Group A 7곳(hours-only)과 Group B 20곳만 처리했고, 발견한 요일-시간 parser 결함은 snapshot 원문으로 보정했다. Profile/Qwen/Embedding/Qdrant 작업은 하지 않았다. 상세 결과는 `AI_Answer/detail_quality_backfill_review.md`와 snapshot을 참조한다.
- 반복 가능한 Browser full-stack E2E는 `./scripts/check-mvp-e2e.sh`로 실행한다. 고유 Compose project와 disposable `zeropay_lunch_mvp_e2e` DB를 사용하고, dev DB 및 기존 Qdrant collection은 변경하지 않는다.
- Venue association 운영 데이터 생성, Restaurant/Detail의 Venue 소유권 전환, 전체 Batch는 별도 검증 후 진행한다.
- 승인된 Venue association을 실제 데이터에 적용하기 전 사업자 관계·동일 장소 근거와 사용자 승인을 확인한다. Venue 단위 Detail/최근 식사 이전은 별도 계약으로 남긴다.
- 신규 READY 14곳의 Semantic Profile 생성은 다음 별도 단계에서 readiness/evidence를 다시 확인한 뒤 제한적으로 진행한다. 이번 Backfill 결과만으로 Profile을 자동 생성하거나 승인하지 않는다.
- 전체 Detail 수집과 Embedding/Qdrant 적재는 품질 기준과 표본 검토 후 별도 진행한다.

## Deferred

- 514건 전체 crawl, LangGraph, 사용자 GPS/거리 추천은 미실행이다. Semantic Runtime 및 Deterministic Explanation UI는 opt-in 경로이며, LLM Explanation은 품질 gate 미통과로 기본 OFF다. Semantic Runtime은 기존 Qdrant pilot collection을 읽기 전용으로 사용한다.

# Important Design Decisions

- KOMSCO 공공데이터가 모집단 Source of Truth다. NAVER Local API, historical Local row, legacy checkpoint는 신규 resolver 입력이 아니다.
- deterministic 코드는 candidate 수집/명백한 non-food·지역 contradiction·기술 안전장치만 담당하고, 비정형 entity 의미 판단은 Qwen이 담당한다. Qwen은 Place ID를 생성하거나 단독 확정하지 않는다.
- Place ID는 candidate DOM의 `data-nlog-params` JSON에서만 추출한다. marker/internal NAVER API는 금지한다.
- `restaurants.active`(원천 운영 상태), `recommendation_eligibility`(추천 가능성), `restaurant_naver_verifications`(NAVER 검증 provenance), `restaurant_external_places`(성공한 외부 mapping)는 서로 다른 의미다.
- report-only는 DB/checkpoint를 쓰지 않는다. `--write-db`에서만 detail와 verification persistence를 수행한다.
- 적용된 Flyway migration은 수정하지 않고 다음 V 번호로만 변경한다.

# Data Pipeline

`KOMSCO name/address/optional coordinates → Kakao/NAVER 후보 조회·dedup → Qwen Entity Resolution → ACCEPT/REJECT/UNKNOWN verification → Canonical/provider mapping → PCMap Maps UI/allSearch numeric Place ID → HOME/MENU/HOURS/REVIEW DOM → MySQL upsert`.

검증 성공 후에도 detail section 상태는 Place ID 상태와 독립이다. KOMSCO source matching field가 바뀌면 기존 NAVER verification은 `UNRESOLVED/SOURCE_CHANGED`로 재검증 대상이 된다.

# Development / Harness

저장소 루트에서 변경 범위에 맞게 실행한다.

```bash
./scripts/check-ai.sh
./scripts/check-backend.sh
./scripts/check-frontend.sh
./scripts/check-integration.sh   # Docker/MySQL/Flyway 포함 변경일 때
git diff --check
```

AI resolver CLI와 manifest/status/ledger 명령은 `ai/README.md`를 읽는다. 실제 NAVER/KOMSCO 요청, DB write, cleanup은 사용자의 명시적 승인과 opt-in이 없으면 실행하지 않는다.

# Autonomous Execution

이 프로젝트는 현재 개발 단계이므로 에이전트가 구현·수정·검증 작업을 최대한 자율적으로 수행한다.

일반적인 개발 작업에 대해서는 사용자에게 중간 승인을 요청하지 않는다.

에이전트는 다음 작업을 스스로 판단해 자유롭게 수행할 수 있다.

- 소스 코드 생성/수정/삭제
- 테스트 코드 생성/수정
- 문서 수정
- 파일 이동/패키지 구조 정리
- lint / format / build / test 실행
- Docker 관련 일반 개발 명령
- Docker service 시작/중지/재시작
- Docker build
- read-only DB 조회
- 개발용 DB migration 적용
- 외부 API smoke test
- 로컬 개발 명령 실행
- Git diff/status 확인
- 일반적인 환경변수/개발 설정 조정
- 현재 architecture에 맞는 리팩터링
- dead/legacy 코드 제거

선택지가 여러 개인 일반적인 개발 문제는
사용자에게 묻지 말고 현재 architecture,
최소 변경 원칙, Harness Engineering 규칙을 기준으로
가장 적절한 방법을 스스로 선택한다.

작업 도중 일반적인 상태 보고나 중간 승인을 요청하지 않는다.
가능한 범위에서 작업을 끝까지 수행한 뒤 결과를 보고한다.

## 권한 문제 예외 규칙

다만 작업이 다음과 같은 **권한 문제 때문에 실패한 경우에는**
다른 방법으로 우회하지 말고 즉시 사용자에게 알린다.

예:

- `Permission denied`
- `Operation not permitted`
- sandbox restriction
- workspace 밖 경로 접근 차단
- `~/.gradle` 쓰기 실패
- `~/.docker` 쓰기 실패
- 사용자 홈 디렉터리 쓰기 실패
- 시스템 경로 접근 실패
- 파일/디렉터리 owner 또는 mode 문제
- Docker socket 접근 권한 문제
- 실행 파일 permission 문제

권한 문제 발생 시 반드시 다음 순서로 처리한다.

1. read-only 명령으로 원인을 확인한다.
2. 실제 파일 권한 문제인지 sandbox 제한인지 구분한다.
3. 권한이 필요한 작업을 정확히 사용자에게 설명한다.
4. 필요한 명령 또는 권한 범위를 제시한다.
5. 사용자 승인을 기다린다.

권한 문제를 피하기 위해
다음과 같은 우회 방법을 사용자 승인 없이 사용하지 않는다.

- `GRADLE_USER_HOME`을 `/tmp` 또는 다른 경로로 변경
- `DOCKER_CONFIG`를 임시 경로로 변경
- `HOME`을 다른 경로로 변경
- 사용자 설정/cache를 임시 위치에 복사
- 실제 Harness와 다른 실행 환경을 만들어 테스트
- 권한 실패를 피하기 위해 원래 명령을 다른 명령으로 대체
- sandbox 제한을 우회하기 위한 임시 실행 구조 생성

즉:

"권한 때문에 실패"
→ 다른 방법을 찾아서 조용히 우회

하지 말고,

"권한 때문에 실패"
→ 원인 확인
→ 사용자에게 필요한 권한 요청

으로 처리한다.

사용자가 권한을 허용하지 않은 경우에만
가능한 대안을 설명할 수 있으며,
그 대안도 사용자 동의 없이 자동 적용하지 않는다.

## Safety

개발 단계라도 다음 작업은 임의 실행하지 않는다.

- 사용자 데이터 삭제
- `TRUNCATE`
- 운영/중요 데이터 `DROP`
- Docker volume 삭제
- 적용된 Flyway migration 수정
- destructive Git operation
- force push
- secret 노출

권한 문제 이외의 일반적인 개발 이슈는
가급적 사용자에게 질문하지 말고 자율적으로 해결한다.

# Safety / Do Not Break

- 사용자·대화·취향·history·Docker volume을 삭제하지 않는다. `TRUNCATE`, DB 재생성, destructive Git, force push 금지.
- secrets/API key를 출력하거나 커밋하지 않는다.
- 429/403/BLOCKED는 retry/proxy 우회 없이 현재 batch를 즉시 종료한다. checkpoint/ledger/report는 보존한다.
- 적용된 V migration, legacy checkpoint/report, runtime manifest/ledger/checkpoint/log는 임의 수정·커밋하지 않는다.
- Resolver/Qwen/threshold/veto를 평가 중 임의 완화하지 않는다. 50건 baseline과 실패 원인은 report로 남긴다.
- 코드가 아닌 문서/아키텍처 milestone이 바뀌면 작업 완료 시 이 파일의 `Current State`/`Next`를 갱신한다. 사소한 수정마다 갱신하지 않는다.

# Key Files

- `README.md`, `docs/architecture.md`, `docs/database.md`, `docs/testing.md`
- `backend/src/main/java/.../restaurant/importer/` 및 `.../restaurant/domain/Restaurant.java`
- `backend/src/main/resources/db/migration/V14__create_naver_verifications.sql`, `V15__add_verification_source_fingerprint.sql`
- `ai/app/batch/e2e_pipeline_orchestrator.py`, `batch_progress.py`, `place_request_limiter.py`
- `ai/app/providers/place_provider.py`, `provider_input.py`, `provider_candidate_retrieval_cli.py`
- `ai/app/entity_resolution/provider_entity_resolution_cli.py`, `qwen_candidate_matcher.py`, `verification_quality_gate.py`
- `ai/app/canonical/canonical_builder.py`, `canonical_persistence_cli.py`
- `ai/app/naver/place_resolver_cli.py`, `place_id_linker_cli.py`, `place_detail_enrichment_cli.py`, `place_detail_persistence.py`
- `ai/tests/`, `backend/src/test/`, `scripts/check-*.sh`
