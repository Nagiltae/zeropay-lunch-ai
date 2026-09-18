# Task: NAVER Local matching validation and incremental lifecycle

## Status

완료. 100개 검증 후 사용자의 별도 승인으로 활성 KOMSCO 음식점 3,272건의 최초 NAVER 전체 매칭을 완료했습니다.

## Goal

강남구 법정동을 고르게 포함하는 100개 표본으로 NAVER Local 매칭을 검증하고, 점수 근거를 보존하며, 명시적 전체 실행과 변경 기반 증분 갱신을 안전하게 지원합니다.

## In scope

- 법정동별 deterministic round-robin 표본 선택
- CSV 검증 리포트와 점수 breakdown
- 이름·주소 정규화 및 프랜차이즈 지점 충돌 방어
- `--limit`, `--incremental`, `--all` 수동 실행 모드
- source hash, refresh TTL, 상태별 retry와 API_ERROR 분리
- KOMSCO sync의 신규·변경·unchanged 및 변경 ID 구분
- Flyway V6, 자동 테스트와 관련 문서

## Out of scope

- FastAPI, LLM, Qdrant, NAVER Blog API
- NAVER 자동 Scheduler 또는 공개 HTTP API
- 기존 가중치·threshold 및 300m 제외 기준의 근거 없는 변경
- 사용자 승인 전 100개 또는 전체 실제 API 실행

## Functional requirements

1. 100개 검증 표본은 법정동 코드별로 그룹화한 뒤 각 그룹의 ID 순서로 round-robin 선택합니다.
2. 리포트는 KOMSCO 원본, 실제 query, 선택 후보, 점수 breakdown, runner-up, gap과 최종 상태를 CSV로 기록합니다.
3. 기존 40/30/20/10 가중치, MATCHED 70점, gap 8점과 300m 제외 기준을 유지합니다.
4. 양쪽에 명시된 지점명이 서로 다르면 후보에서 제외합니다.
5. 전체 실행은 명시적인 `--all`에서만 가능합니다.
6. 증분 실행은 원본 변경, enrichment 부재, 상태별 retry 도래 또는 refresh TTL 만료 행만 조회합니다.
7. API 오류는 매칭 실패와 구분하고 기존 정상 매칭 결과를 제거하지 않습니다.
8. KOMSCO sync는 실제 매칭 입력 변경 ID를 반환하지만 NAVER API를 자동 호출하지 않습니다.

## API contract

공개 API 변경 없음. 외부 NAVER Local 요청 계약은 유지합니다.

## Data model impact

- 기존 V1~V5는 수정하지 않습니다.
- V6에서 점수 breakdown, source hash, 마지막 시도 상태·시각과 다음 retry 시각을 추가합니다.
- 전체 비교 정보와 1·2차 query는 CSV 리포트에 기록하고 raw JSON은 저장하지 않습니다.

## Architecture constraints

- KOMSCO가 음식점 원본이며 NAVER 보강은 원본 필드를 덮어쓰지 않습니다.
- KOMSCO sync와 NAVER enrichment는 ID 목록 경계로만 연결하고 자동 외부 호출은 하지 않습니다.
- 인증 실패는 fail-fast, 개별 API 오류는 격리합니다.

## Acceptance criteria

1. 요청된 normalization, 지점명, 상태, gap, 증분 조건, 실패 보존과 멱등 테스트가 통과합니다.
2. `./scripts/check-backend.sh`와 `./scripts/check-all.sh`가 통과합니다.
3. 승인된 경우에만 100개 실제 검증을 실행하고 CSV 및 통계를 보고합니다.
4. 전체 3,272개 실행은 별도 사용자 승인을 받은 후에만 수행합니다.

## Verification

- `./scripts/check-backend.sh`
- `./scripts/check-all.sh`
- 사용자 승인 후 `--limit=100` 실제 실행과 DB/CSV 확인: 완료

## Validation result

- 표본: 14개 법정동별 7~8건, 총 100건
- 결과: MATCHED 63, AMBIGUOUS 9, UNMATCHED 28, API_ERROR 0
- DB: inserted 80, updated 20, skipped 0, `(restaurant_id, provider)` 중복 0
- CSV: `backend/build/reports/naver-enrichment/naver-validation-20260919-023530.csv`
- 100건 Hard Gate/eligibility 재검증: MATCHED 60, AMBIGUOUS 8, UNMATCHED 32, API_ERROR 0
- 승인된 전체 3,272건: MATCHED 1,982, AMBIGUOUS 163, UNMATCHED 1,127, API_ERROR 0
- 전체 추천 상태: ELIGIBLE 1,939, INELIGIBLE 0, UNKNOWN 1,333
- 전체 DB: inserted 3,172, updated 100, skipped 0, `(restaurant_id, provider)` 중복 0
- 전체 CSV: `backend/build/reports/naver-enrichment/naver-all-20260919-033129.csv`
- MATCHED 위험 검토 50건: `backend/build/reports/naver-enrichment/naver-full-review-20260919-033129.csv`
- KOMSCO 원본 3,272건의 실행 전·후 checksum 일치, 주 1회 Scheduler는 미구현·미활성

## Documentation updates

- `README.md`
- `docs/architecture.md`
- `docs/database.md`
- `docs/deployment.md`
- `docs/testing.md`
- `AI_CHANGELOG.md`
