# Task: Manage restaurant recommendation eligibility

## Status

완료. 자동 검증과 사용자가 승인한 NAVER 100건 재실행을 완료했습니다.

## Goal

KOMSCO 원본을 유지하면서 NAVER 매칭과 category 근거로 실제 점심 추천 가능 여부를 별도 상태로 관리합니다.

## In scope

- `ELIGIBLE`, `INELIGIBLE`, `UNKNOWN` 상태와 Flyway V7
- 재사용 가능한 NAVER 음식점 category 정책
- NAVER 저장과 eligibility의 트랜잭션 갱신
- 추천 후보 조회에서 ELIGIBLE 강제
- 기존 샘플/test fixture 호환
- 승인된 100건 재실행과 MATCHED 검토 CSV

## Out of scope

- 전체 3,272개 NAVER 실행
- KOMSCO 원본 수정·삭제
- FastAPI, LLM, Qdrant, Blog API

## Functional requirements

1. MATCHED+음식점 category는 ELIGIBLE입니다.
2. MATCHED+명확한 비음식점 category는 INELIGIBLE입니다.
3. AMBIGUOUS, UNMATCHED, API_ERROR, 미조회와 category 불명은 UNKNOWN입니다.
4. 추천 조회는 기존 조건과 함께 ELIGIBLE만 반환합니다.
5. KOMSCO 매칭 입력 변경은 기존 eligibility를 UNKNOWN으로 되돌립니다.
6. category 분류는 matching과 eligibility가 같은 정책을 사용합니다.
7. 실제 100건 재실행 전 redacted NAVER 요청과 범위를 제시하고 승인받습니다.

## Data model impact

- 기존 V1~V6는 수정하지 않습니다.
- V7에서 `restaurants.recommendation_eligibility`를 추가하고 기존/신규 KOMSCO는 UNKNOWN, sample 데이터는 ELIGIBLE로 유지합니다.

## Verification

- NAVER category/eligibility 회귀 테스트
- 추천 repository 테스트
- `./scripts/check-backend.sh`
- `./scripts/check-all.sh`
- 승인 후 `--limit=100` 실제 실행

## Result

- 실제 100건: MATCHED 60, AMBIGUOUS 8, UNMATCHED 32, API_ERROR 0
- 추천 상태: ELIGIBLE 60, INELIGIBLE 0, UNKNOWN 40
- DB: NAVER 100행, 서로 다른 restaurant 100건, 이번 실행에서 100건 update
- 전체 3,272건 실행은 수행하지 않음
- 전체 검증 CSV: `backend/build/reports/naver-enrichment/naver-validation-20260919-030231.csv`
- MATCHED 20건 검토 CSV: `backend/build/reports/naver-enrichment/naver-matched-review-20260919-030231.csv`
