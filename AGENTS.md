# Project Overview

ZeroPay Lunch AI는 사용자의 자연어·취향·예산·최근 식사 기록을 바탕으로 음식점을 추천하는 모노레포다. 현재 서비스 모집단은 KOMSCO 공공데이터의 서울 강남구 논현동(`legal_dong_code=11680108`, `providerInstitutionCode=I0000002`, `industryCode=561`, `businessStatusName=계속사업자`) 음식점이다.

핵심 흐름은 `React → Spring Boot → MySQL`이며, FastAPI는 AI 내부 경계의 health/계약 기반만 구현되어 있고 Spring에서 실제 호출하지 않는다. 별도의 `ai/` Python CLI는 KOMSCO→공식 Provider/Qwen→Canonical→PCMap Place ID·상세 수집을 담당한다.

# Architecture

- React: 인증된 채팅, 취향·식사 기록 UI, Spring API/SSE 호출. FastAPI를 직접 호출하지 않는다.
- Spring Boot: 공개 API, 인증/세션, 대화·취향·식사 영속화, KOMSCO import/scheduler, 추천 business rule과 MySQL persistence.
- FastAPI: 현재 `/health` 중심의 AI 서비스. LangGraph/Qdrant/실제 Spring→FastAPI 호출은 아직 미구현이다.
- `ai/`: Provider 후보 조회, Qwen Entity Resolution, Canonical persistence, PCMap Place ID/detail CLI. 운영 추천 요청 경로와 별개다.
- MySQL/Flyway: 원본·검증·추천 데이터의 기준 저장소. Qdrant는 현재 파생 검색 저장소로만 계획되어 있다.

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

- 논현동·I0000002 KOMSCO importer와 주간 일요일 03:00(Asia/Seoul) 동기화/명시적 cleanup 경로.
- React와 Spring의 역/반경 선택 runtime 계약 제거; 좌표 metadata와 historical schema는 보존.
- 공식 Kakao/NAVER 후보 fusion과 Qwen3.5 Entity Resolution: candidate dedup, bounded prefetch, fingerprint 기반 incremental 처리와 REJECT cache.
- PCMap Maps UI/allSearch capture 기반 numeric Place ID linking과 DOM-only HOME/MENU/HOURS/REVIEW detail persistence.
- DOM-only HOME/MENU/REVIEW crawler와 idempotent detail persistence.
- `restaurant_naver_verifications` V14 provenance/status/reason 구조와 V15 source fingerprint. `restaurants.active`, `recommendation_eligibility`, 외부 Place mapping과 분리된다.
- Official Kakao/NAVER provider fusion과 Qwen3.5 Entity Resolution 경로. stable manifest 입력으로 실행하며 동일 source fingerprint의 확정 REJECT만 재사용한다.
- parser, semantic prompt, out-of-scope/non-food safety, source-change 재검증 회귀 테스트.

## In Progress

- Step 8 End-to-End preflight에서 legacy VERIFIED 10건을 Qwen3.5로 재검증해 fingerprint를 저장했고,
  동일 fingerprint REJECT 5건의 provider/Qwen 0호출을 확인했다. NAVER_LOCAL 5건은 실제
  PCMap UI allSearch capture로 numeric NAVER Place ID를 연결했고, 그중 3건의
  HOME/MENU/영업시간/REVIEW를 저장했다. 동일 대상 재실행은 Qwen/link/detail 0건이었다.
  513건 전체 배치는 미실행.

## Next

- preflight DB 정합성·harness·Git push를 마친 뒤 513건 전체 배치를 별도 실행.
- 전체 배치 중 403/429/CAPTCHA 발생 시 즉시 중단하고 DB 기반으로 재개.
- 실제 Spring → FastAPI AI 연동 구현.

## Deferred

- 514건 전체 crawl, 실제 Spring→FastAPI AI 연동, LangGraph/Qdrant 검색, 사용자 GPS/거리 추천은 아직 실행·구현하지 않았다.

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
