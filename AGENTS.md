# Project Overview

ZeroPay Lunch AI는 사용자의 자연어·취향·예산·최근 식사 기록을 바탕으로 음식점을 추천하는 모노레포다. 현재 서비스 모집단은 KOMSCO 공공데이터의 서울 강남구 논현동(`legal_dong_code=11680108`, `providerInstitutionCode=I0000002`, `industryCode=561`, `businessStatusName=계속사업자`) 음식점이다.

핵심 흐름은 `React → Spring Boot → MySQL`이며, FastAPI는 AI 내부 경계의 health/계약 기반만 구현되어 있고 Spring에서 실제 호출하지 않는다. 별도의 `ai/` Python CLI는 KOMSCO→PCMap Place ID 검증·상세 수집을 담당한다.

# Architecture

- React: 인증된 채팅, 취향·식사 기록 UI, Spring API/SSE 호출. FastAPI를 직접 호출하지 않는다.
- Spring Boot: 공개 API, 인증/세션, 대화·취향·식사 영속화, KOMSCO import/scheduler, 추천 business rule과 MySQL persistence.
- FastAPI: 현재 `/health` 중심의 AI 서비스. LangGraph/Qdrant/실제 Spring→FastAPI 호출은 아직 미구현이다.
- `ai/`: Playwright PCMap resolver/detail crawler와 Ollama/Qwen 평가·report CLI. 운영 추천 요청 경로와 별개다.
- MySQL/Flyway: 원본·검증·추천 데이터의 기준 저장소. Qdrant는 현재 파생 검색 저장소로만 계획되어 있다.

자세한 책임 경계는 [docs/architecture.md](docs/architecture.md), API는 `docs/api-contract.md`, 스키마는 `docs/database.md`를 canonical 문서로 본다.

# Module Ownership

| 영역 | 소유 로직 |
|---|---|
| `frontend/` | 화면, 인증 상태, 채팅/SSE, 취향·식사 기록 요청 |
| `backend/.../restaurant/importer` | KOMSCO API pagination/dedup/filter/upsert, Sunday scheduler, cleanup |
| `backend/.../restaurant` | Restaurant source state, recommendation eligibility, deterministic candidate query |
| `backend/.../recommendation` | 추천 context, fallback intent 분석, 결정론적 후보 필터/순위 |
| `ai/app/place_resolver_cli.py` | PCMap DOM candidate 수집, Place ID(`data-nlog-params`) 추출, `/home` 검증 |
| `ai/app/qwen_candidate_matcher.py` | `QWEN_MODEL` 기반 Qwen candidate ranking/semantic structured validation |
| `ai/app/provider_entity_resolution_cli.py` | Kakao/NAVER official candidate fusion, Qwen Entity Resolution, report-only quality gate/cache |
| `ai/app/place_dom_detail_crawler.py` | 검증된 HOME 재사용, HOME/MENU/REVIEW DOM 수집 |

# Current State

## Completed

- 논현동·I0000002 KOMSCO importer와 주간 일요일 03:00(Asia/Seoul) 동기화/명시적 cleanup 경로.
- React와 Spring의 역/반경 선택 runtime 계약 제거; 좌표 metadata와 historical schema는 보존.
- KOMSCO-only PCMap resolver: 최대 20 candidate 수집, 최대 12개 Qwen pool, Top-5 detail validation, 429/403 즉시 중단, rate limit 기본 2.5초 navigation/5초 restaurant.
- NAVER Local API와 stored Local fallback은 신규 resolver에서 사용하지 않는다.
- DOM-only HOME/MENU/REVIEW crawler와 idempotent detail persistence.
- `restaurant_naver_verifications` V14 provenance/status/reason 구조와 V15 source fingerprint. `restaurants.active`, `recommendation_eligibility`, 외부 Place mapping과 분리된다.
- Official Kakao/NAVER provider fusion과 Qwen3.5 report-only Entity Resolution 경로. stable manifest 입력으로 DB/Playwright 없이 실행하며 동일 source fingerprint REJECT만 재사용한다.
- parser, semantic prompt, out-of-scope/non-food safety, source-change 재검증 회귀 테스트.

## In Progress

- Step 8 End-to-End 파이프라인 Pilot 완료(5건 검증). 514건 전체 배치는 미실행.

## Next

- 514건 전체 배치: `e2e_pipeline_orchestrator.py --limit 514` 실행 전 rate-limit/checkpoint/ledger 운영 절차 확인.
- Step 8 Pilot 결과를 바탕으로 REJECT/UNRESOLVED 케이스에 대한 quality review.
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

`KOMSCO name/address/optional coordinates → PCMap search → deterministic ordering/safety → Qwen ranking → candidate Place ID → reused /home strict/semantic validation → VERIFIED/REJECTED/UNRESOLVED/ERROR/BLOCKED reason → HOME/MENU/REVIEW DOM → MySQL upsert`.

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

이 프로젝트에서는 에이전트가 작업 수행 중 일반적인 구현 선택이나 파일 수정, 테스트 실행, 빌드, 로컬 개발 명령에 대해 사용자 승인을 요청하지 않는다.
`AGENTS.md`, 기존 아키텍처, 코드, 테스트를 기준으로 합리적으로 판단하여 작업 완료까지 자율적으로 진행한다.

다음 경우에도 별도 확인 없이 진행한다.
- 소스 코드 생성/수정
- 테스트 코드 생성/수정
- 문서 수정
- lint / format / build / test 실행
- Docker service 상태 확인
- read-only DB 조회
- 외부 API smoke test
- Git diff/status 확인
- 정상적인 git add / commit / push

단, 아래 작업이 필요해지는 경우에는 임의 실행하지 않는다.
- 데이터 삭제
- TRUNCATE / DROP
- Docker volume 삭제
- 적용된 Flyway migration 수정
- destructive Git operation
- force push
- secret 노출
- `AGENTS.md`의 Safety / Do Not Break 규칙 위반

위 금지 작업이 없이는 목표를 달성할 수 없다면 안전한 범위까지 작업한 뒤 해당 blocker만 최종 보고한다.

선택지가 여러 개 있는 경우 사용자에게 질문하지 말고 현재 architecture와 최소 변경 원칙에 가장 잘 맞는 방법을 선택한다.
작업 도중 상태 보고나 중간 승인을 요청하지 말고, 완료 또는 실제 blocker 발생 시에만 결과를 보고한다.

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
- `ai/app/place_pipeline_cli.py`, `place_resolver_cli.py`, `place_resolver.py`
- `ai/app/provider_input.py`, `provider_candidate_retrieval_cli.py`, `provider_entity_resolution_cli.py`
- `ai/app/qwen_candidate_matcher.py`, `place_dom_detail_crawler.py`, `place_detail_persistence.py`
- `ai/tests/`, `backend/src/test/`, `scripts/check-*.sh`
