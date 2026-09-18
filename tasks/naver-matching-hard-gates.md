# Task: Reduce NAVER matching false positives with hard gates

## Status

완료. 외부 API 재호출 없이 기존 100건 CSV/DB 결과를 재평가했습니다.

## Goal

실제 100건 검증 결과를 근거로 기존 점수 가중치와 threshold는 유지하면서 명백한 비음식점 후보와 근거가 약한 MATCHED 판정을 보수적으로 차단합니다.

## In scope

- 후보 category/name hard gate
- MATCHED strong-evidence gate
- 기존 100건 DB/CSV 결과의 무호출 재평가
- matcher 테스트와 관련 문서

## Out of scope

- NAVER API 재호출
- 전체 음식점 실행
- 기존 40/30/20/10 가중치, 70점, gap 8점, 300m 기준 변경
- FastAPI, LLM, Qdrant, Blog API

## Functional requirements

1. 명시된 NAVER category가 음식점 계열이 아니면 후보에서 제외합니다.
2. 최소 이름 점수를 통과하지 못한 후보는 제외합니다.
3. MATCHED는 기존 total/gap 조건과 함께 강한 주소 증거 또는 강한 이름+50m 이내 증거가 필요합니다.
4. total은 높지만 strong evidence가 부족한 후보는 AMBIGUOUS로 분류합니다.
5. 기존 100건은 저장 결과로 재평가하고 전후 통계와 변경 사례를 보고합니다.

## Verification

- `./scripts/check-backend.sh`
- `./scripts/check-all.sh`
- 기존 CSV/DB 100건 offline replay

## Decision and result

- weak address인 기존 MATCHED 20건의 거리 분포는 30m 이내 15건, 30~50m 3건, 50m 초과 2건이었습니다.
- 50m는 기존 최고 거리점수 구간과 같고, 31.9m·36.5m·46.3m의 강한 이름 후보를 유지하면서 63.4m와 167.7m 후보를 보수적으로 내립니다.
- 재평가: MATCHED 63→59, AMBIGUOUS 9→8, UNMATCHED 28→33.
- 수미초밥은 MATCHED→AMBIGUOUS, 구야네 프리미엄 반찬은 MATCHED→UNMATCHED입니다.
- 전체 NAVER 호출과 DB 상태 일괄 갱신은 수행하지 않았습니다.
