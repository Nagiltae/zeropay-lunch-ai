# ZeroPay Lunch AI Place ID 매칭 실패 원인 분석 보고서

## 1. 결론 요약

- 9576과 9599의 현재 UNRESOLVED는 numeric ID 파서나 주소 검증에서 탈락한 것이 아니라, NAVER Maps UI가 해당 검색어에 장소 결과를 반환하지 않은 결과다.
- 두 검색 모두 HTTP 200, `rcode=09350720`, `place=None`, `bus=None`, parsed candidate 0건이었다.
- 주소를 보강한 대체 검색어도 각각 HTTP 200·후보 0건이었다.
- 따라서 이번 증거만으로 검색어 생성 결함, DOM 변경, numeric ID 추출 결함, 주소 검증 결함이라고 확정하지 않았다.
- 9617은 정상 비교 사례로 `1987855627 / MATCHED`를 유지했고, 수정된 영업시간 파서를 실제 DB에 반영했다.
- 현재 작업에서 matching 알고리즘은 수정하지 않았다. 기존 working tree에 이미 반영된 unresolved SQL 수정과 영업시간 파서 수정은 회귀 테스트와 함께 재검증했다.

## 2. 정상 사례와 실패 사례 비교

| 단계 | 9617 성공 | 9576 실패 | 9599 실패 |
|---|---|---|---|
| KOMSCO 이름 | `(주)에스지푸드 논현역 마성떡볶이` | `호별관` | `(주)육덕패밀리` |
| Canonical 이름 | `마성떡볶이 논현역점` | `호별관` | `육덕패밀리` |
| Canonical 주소 | 논현역 지하 1층 주소 | 논현로114길 22 | 학동로4길 49 |
| NAVER Local evidence | 이름·주소 MATCHED | 없음 | 없음 |
| Linker query | `논현동 마성떡볶이 논현역점` | `논현동 호별관` | `논현동 육덕패밀리` |
| allSearch place | 존재 | 없음 | 없음 |
| parsed candidates | numeric 후보 1개 | 0개 | 0개 |
| 최종 상태 | MATCHED | UNRESOLVED | UNRESOLVED |

9617은 Qwen/Canonical 단계에서 생성된 NAVER_LOCAL 이름·주소 evidence가 있고, UI 검색 결과의 단일 numeric 후보가 이름·주소 검증을 통과했다. 9576/9599는 KOMSCO/Canonical은 있지만 NAVER_LOCAL evidence가 없어 Linker가 Canonical 이름으로 직접 검색했다.

9599는 KOMSCO 주소가 `학동로4길 45`이고 Canonical road address가 `학동로4길 49`로 서로 다르다. 이것은 데이터 품질 위험으로 기록하지만, 이번 UI 응답이 빈 결과였으므로 실제 실패 원인이라고 단정하지 않는다.

## 3. 단계별 진단 결과

### 9576

DB 입력:

- KOMSCO/Canonical 이름: `호별관`
- KOMSCO/Canonical 주소: `서울특별시 강남구 논현로114길 22 (논현동)`
- NAVER_LOCAL mapping: 없음
- 기존 NAVER row: `UNRESOLVED`, query `논현동 호별관`

기본 검색:

- Query: `논현동 호별관`
- HTTP status: 200
- `rcode`: `09350720`
- allSearch `place`: `None`
- allSearch `bus`: `None`
- Python parsed candidates: 0
- numeric ID 추출 단계 진입: 불가
- 주소 검증 단계 진입: 불가

주소 보강 검색:

- Query: `논현동 호별관 논현로114길 22`
- HTTP status: 200
- parsed candidates: 0

### 9599

DB 입력:

- KOMSCO 이름: `(주)육덕패밀리`
- Canonical 이름: `육덕패밀리`
- KOMSCO 주소: `서울특별시 강남구 학동로4길 45(논현동)`
- Canonical road address: `서울 강남구 학동로4길 49`
- NAVER_LOCAL mapping: 없음
- 기존 NAVER row: `UNRESOLVED`, query `논현동 육덕패밀리`

기본 검색:

- Query: `논현동 육덕패밀리`
- HTTP status: 200
- `rcode`: `09350720`
- allSearch `place`: `None`
- allSearch `bus`: `None`
- Python parsed candidates: 0
- numeric ID 추출 단계 진입: 불가
- 주소 검증 단계 진입: 불가

주소 보강 검색:

- Query: `논현동 육덕패밀리 학동로4길 45`
- HTTP status: 200
- parsed candidates: 0

## 4. 원인 분류

| 가능성 | 판정 | 근거 |
|---|---|---|
| A. 검색어로 결과가 없음 | 확인됨 | 기본·주소 보강 query 모두 `place=None`, 후보 0 |
| B. 결과는 있으나 numeric ID 추출 실패 | 확인되지 않음 | 파서에 전달할 place 후보 자체가 없음 |
| C. numeric ID가 주소 검증에서 탈락 | 확인되지 않음 | numeric 후보가 생성되지 않음 |
| D. Canonical/NAVER Local mapping 불일치 | 위험 요인 | 9576/9599는 Local evidence 없음; 9599 주소 차이 존재 |
| E. NAVER UI/DOM 변경 | 근거 부족 | HTTP 200과 정상 구조의 빈 결과 응답을 받음; 9617·기존 parser 테스트는 정상 |

이번 결과는 “현재 검색어·현재 NAVER 검색 데이터로 장소가 확인되지 않음”까지 확정한다. 실제 상호가 존재하지 않는다는 뜻이나 KOMSCO 원본이 부적격이라는 뜻으로 확대하지 않는다.

## 5. 기존 구현 및 테스트 점검

### 확인된 기존 결함

이전 Pilot에서 Place ID `UNRESOLVED` 저장 SQL에 컬럼 8개 대비 값 9개가 생성되는 결함이 발견됐다. 현재 working tree에는 다음 수정이 이미 반영되어 있다.

- `external_place_id=NULL` 명시
- INSERT 컬럼·값 개수 일치
- `ai/tests/naver/test_place_id_linker.py` 회귀 테스트

수정 후 9576/9599의 UNRESOLVED 결과 기록은 정상 완료됐다.

### 영업시간 파서

기존에는 DOM 원문을 day/description에만 넣어 `open_time/close_time`이 NULL이었다. 현재 working tree의 파서 수정은 다음을 보장한다.

- `매일 07:00 - 20:30` → `매일`, `07:00`, `20:30`
- 시간 없는 영업 상태 문구 → 시간 필드 NULL, 임의 추론 없음

이번 작업에서 matching 알고리즘, 주소 기준 완화, numeric ID 추측 로직은 추가하지 않았다.

## 6. 9617 영업시간 제한 재수집

실행:

```text
BATCH_RUN_ID=hours-write-9617-20260924
python -m app.naver.place_detail_enrichment_cli \
  --limit 1 --restaurant-ids 9617 --force-refresh
```

Report:

`ai/build/reports/naver-place-pipeline/e2e/hours-write-9617-20260924-detail.json`

결과:

- 대상 1, 성공 1
- HOME/MENU/REVIEW navigation 각 1회
- 메뉴 24건, 키워드 35건, 대표 리뷰 10건, 요약 1건 유지
- 영업시간 active row: `매일 / 07:00 / 20:30`
- 기존 잘못된 row는 `active=0`으로 남아 삭제하지 않음
- 403/429/CAPTCHA/BLOCKED 없음

## 7. 제한적 실환경 요청 및 산출물

9576/9599 관련 NAVER UI 요청은 총 6회 이하였다.

- 기본 진단 2회
- raw payload 관측 2회
- 주소 보강 query 2회

보존 report:

```text
ai/build/reports/naver-place-pipeline/e2e/20260923-172734-482623-place_id.json
ai/build/reports/naver-place-pipeline/e2e/20260923-172745-603833-place_id.json
ai/build/reports/naver-place-pipeline/e2e/20260923-172807-333425-place_id.json
ai/build/reports/naver-place-pipeline/e2e/20260923-172822-562964-place_id.json
```

9617 비교·영업시간 report:

```text
ai/build/reports/naver-place-pipeline/e2e/placeid-9617-20260923-place_id.json
ai/build/reports/naver-place-pipeline/e2e/hours-write-9617-20260924-detail.json
```

## 8. 테스트

- AI Harness: `161 passed`, warning 1
- Place ID/Detail targeted tests: PASS
- `git diff --check`: PASS
- 외부 Provider/Qwen: 실행하지 않음
- 전체 Batch: 실행하지 않음
- 9610: 이번 진단 실환경 대상에서 제외

## 9. DB 변경 범위

- 9576/9599: 기존 NAVER UNRESOLVED 상태 기록 범위만 갱신; Verification/Canonical/Eligibility/Detail 변경 없음
- 9617: 영업시간 parser 보정에 따른 Detail 재저장만 수행
- 9617의 메뉴·리뷰 row 수와 active 상태 보존
- 대상 외 음식점 변경 없음
- Flyway migration 수정 없음

## 10. 다음 Pilot 확대 가능 여부

Numeric Place ID 실패는 코드상 numeric 추출·주소 검증 결함으로 확인되지 않았고, 현재 대상의 NAVER 검색 데이터/evidence 부족이 원인이다. 따라서 매칭 기준을 완화하거나 임의의 Fallback을 추가하지 않은 현재 상태가 안전하다.

다음 Pilot은 다음 조건에서만 확대한다.

1. NAVER_LOCAL 또는 신뢰할 수 있는 검색 결과 evidence가 있는 대상 선정
2. AMBIGUOUS는 명시적 재검증 승인 없이 유지
3. NO_CANDIDATE 대상은 원본 부적격으로 변환하지 않음
4. MATCHED 확인 후에만 Detail 실행

## 11. Git 및 안전 확인

- 이번 분석 중 matching source 추가 수정: 없음
- 현재 working tree에 반영된 기존 수정: 영업시간 parser 및 unresolved INSERT 수정
- 이번 분석 관련 신규 테스트 추가: 없음
- DB 위험 작업: DROP/TRUNCATE 없음
- commit: 안 함
- push: 안 함
- staged: 없음
