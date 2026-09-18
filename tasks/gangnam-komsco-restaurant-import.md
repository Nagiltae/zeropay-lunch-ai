# Task: 강남구 KOMSCO 음식점 적재

## Status

완료

## Goal

한국조폐공사 모바일 가맹점기본정보 OpenAPI에서 강남구 14개 법정동의 전체 페이지를 수집하고, `alt_text`별 최신 상태를 기준으로 계속사업자인 음식점만 MySQL에 멱등 적재합니다.

## Background

현재 추천은 local/dev 샘플 음식점 3개만 사용합니다. 실제 AI 연동 전에 MySQL이 소유할 강남구 제로페이 음식점 원본 데이터를 안전하게 동기화할 기반이 필요합니다. KOMSCO 응답에는 추천용 메뉴, 가격과 영업시간이 없으므로 원본 적재와 추천 준비 상태를 분리합니다.

## In scope

- KOMSCO 환경설정과 timeout
- 14개 강남구 법정동 pagination
- 외부 DTO와 JPA Entity 분리
- `alt_text`별 최신 `crtr_ymd` 선택
- 제공기관, 계속사업자, KSIC 561, 강남구 필터
- Flyway V4와 멱등 upsert
- opt-in 일회성 local import runner
- 명시적으로 승인된 경우 성공한 전체 snapshot으로 KOMSCO 행만 트랜잭션 교체
- 단위·영속성·실패 안전성 테스트
- DB, 아키텍처, 배포와 테스트 문서

## Out of scope

- 공개 import API
- Scheduler
- Naver API
- FastAPI, Qdrant와 LLM
- 메뉴·가격·영업시간 자동 보강
- 기존 데이터 삭제 또는 snapshot 부재 행 비활성화

## Functional requirements

1. 각 법정동의 모든 페이지를 성공적으로 수집한 뒤에만 DB 쓰기를 시작합니다.
2. 필수 필드가 없는 행은 전체 수집을 중단하지 않고 제외합니다.
3. `alt_text`별 가장 최신 `crtr_ymd` 하나를 고른 뒤 필터링합니다.
4. 최신 상태가 계속사업자이고 `ksic_cd=561`이며 강남구인 데이터만 적재합니다.
5. 동일 import 재실행은 중복 행을 만들지 않습니다.
6. 새 기준일자가 더 최신이면 갱신하고 더 오래되면 기존 데이터를 유지합니다.
7. 외부 호출 실패 시 기존 DB를 변경하지 않고 service key를 로그에 남기지 않습니다.
8. KOMSCO 행은 추천 필수 정보가 보강되기 전까지 추천 후보에서 제외합니다.

## API contract

공개 API 변경 없음. 외부 KOMSCO API 계약만 DTO로 매핑합니다.

## Data model impact

- 기존 V1~V3는 수정하지 않습니다.
- 신규 V4에서 `restaurants`에 외부 출처·사업자 상태·주소·법정동·업종·동기화 컬럼과 unique constraint를 추가합니다.
- KOMSCO에 없는 AI 보강 컬럼은 nullable로 전환하고 `recommendation_ready`로 추천 가능 여부를 명시합니다.

## Architecture constraints

- 외부 API 연동과 원본 데이터 소유권은 Spring Boot와 MySQL에 둡니다.
- KOMSCO key를 코드, 문서, 테스트 출력이나 로그에 기록하지 않습니다.
- 수집, 최신화, 필터와 DB 저장 책임을 분리합니다.
- 추천 조회는 `recommendation_ready=true`를 강제합니다.

## Acceptance criteria

1. 요구된 14가지 테스트 시나리오가 자동 검증됩니다.
2. 수동 import가 fetched, deduplicated, active, inserted, updated, skipped 집계를 출력합니다.
3. 신규·동일·최신·과거 record 정책이 DB에서 멱등하게 동작합니다.
4. `./scripts/check-backend.sh`가 통과합니다.
5. 공통 실행 환경 변경을 포함하므로 `./scripts/check-all.sh`가 통과합니다.

## Verification

- `./scripts/check-backend.sh`
- `./scripts/check-integration.sh`
- `./scripts/check-all.sh`
- 실제 key가 사용 가능한 경우 opt-in one-shot import와 DB 집계

## Documentation updates

- `docs/architecture.md`
- `docs/database.md`
- `docs/deployment.md`
- `docs/testing.md`
- `.env.example`
- `README.md`
