# ZeroPay Lunch AI 영업시간 검증 및 5건 Pilot 보고서

## 1. Executive Summary

- 영업시간 파서는 실제 9617 DOM에 있던 `매일 07:00 - 20:30`을 기존에 시간 필드로 분해하지 못하는 결함이 확인됐다.
- `DomCollectedDetail.to_place_detail()`에 최소 파싱을 추가해 요일·시작·종료 시각을 보존하고, 시간 없는 상태 문구는 추론하지 않도록 수정했다.
- 관련 테스트 33개와 최종 AI Harness 161개가 통과했다.
- 완료 데이터 9617의 Orchestrator 재사용 검증은 Qwen 0회, Place ID 외부 요청 0회, Detail 외부 요청 0회로 성공했다.
- 신규/미완료 5건 Pilot은 `9576, 9599, 9604, 9610, 9627`로 제한했다. Provider/Qwen은 이미 VERIFIED인 상태를 재사용했으며 재실행하지 않았다.
- 4건은 NAVER numeric Place ID `UNRESOLVED`, 1건은 기존 `AMBIGUOUS`로 남아 Detail은 0건 실행됐다. 잘못된 장소를 저장하지 않은 것이 이번 Pilot의 안전한 결과다.
- Pilot 중 UNRESOLVED 결과 기록 SQL의 컬럼 수 결함도 발견·수정했고, 수정 후 9576/9599는 오류 없이 UNRESOLVED를 기록했다.

## 2. 영업시간 DOM 및 Parser 비교

### 실제 DOM

9617(`1987855627`) 한 건을 `--force-refresh --dry-run`으로 제한 재방문했다.

보존된 runtime report:

`ai/build/reports/naver-place-pipeline/e2e/hours-dryrun-9617-20260924-detail.json`

실제 raw hours evidence:

```text
영업 전07:00에 영업 시작 매일 07:00 - 20:30 접기 영업시간 수정 제안하기
```

### 기존 결함

기존 변환은 원문 전체를 `BusinessHour.day`와 `description`에만 넣었고 `open_time`, `close_time`을 채우지 않았다. 그래서 DB에는 영업시간 1행이 있었지만 두 시간 필드가 NULL이었다.

### 적용한 최소 수정

수정 파일:

- `ai/app/naver/place_dom_detail_crawler.py`
- `ai/tests/naver/test_place_dom_detail_crawler.py`

요일 토큰(`매일`, `평일`, `주말`, 월~일) 뒤의 `HH:MM - HH:MM` 또는 `HH:MM ~ HH:MM`만 구조화한다.

- 실제 시간 범위가 있으면 `day/open_time/close_time` 저장
- 시간 범위가 없는 상태 문구는 `description`만 보존
- 상태 문구로 주간 반복시간을 추론하지 않음
- 기존 section SUCCESS/ABSENT_CONFIRMED/FAILED 계약은 변경하지 않음

추가 회귀 테스트:

- `매일 07:00 - 20:30` → `매일`, `07:00`, `20:30`
- 시간 없는 `영업 종료...` → open/close NULL 유지

기존 9617 DB row는 강제 갱신하지 않았다. 기존 데이터 보호 원칙에 따라 수정된 파서는 다음 정상 Detail 저장부터 적용된다.

## 3. Orchestrator 통합 검증

완료 상태인 9617에 다음 정상 Orchestrator를 실행했다.

```text
poetry run python -u -m app.batch.e2e_pipeline_orchestrator \
  --limit 1 --restaurant-ids 9617
```

Run ID: `20260924-020358-422418`

결과:

- Entity Resolution: VERIFIED skip 1, Qwen 0회
- Canonical: 재실행 없음
- Place ID: numeric mapping 이미 완료되어 후보 0, browser 0
- Detail: fresh 완료로 skip 1, browser/navigation 0
- 전체 실행시간: 약 1.09초
- E2E summary 및 child stage report 생성

보존된 report:

```text
ai/build/reports/naver-place-pipeline/e2e/20260924-020358-422418-entity_resolution.json
ai/build/reports/naver-place-pipeline/e2e/20260924-020358-422418-place_id.json
ai/build/reports/naver-place-pipeline/e2e/20260924-020358-422418-detail.json
ai/build/reports/naver-place-pipeline/e2e/20260924-020358-422418-summary.json
```

완료 데이터 재사용과 불필요한 외부 요청 생략은 확인했다. 신규 데이터의 전체 Orchestrator 연결은 다음 Pilot에서 별도로 평가했다.

## 4. Pilot 대상 선정

Snapshot:

- `AI_Answer/final_5_pilot_snapshot_before.json`
- `AI_Answer/final_5_pilot_snapshot_after.json`

선정 기준은 KOMSCO 활성·ELIGIBLE·VERIFIED이지만 numeric NAVER mapping과 Detail이 미완료인 대상이다. 이미 정상 Detail이 완료된 9617, 9559, 9561 등은 제외했다.

| ID | 이름 | 사전 상태 | 선정 이유 |
|---:|---|---|---|
| 9576 | 호별관 | VERIFIED, numeric 없음 | Place ID/Detail 미완료 |
| 9599 | (주)육덕패밀리 | VERIFIED, numeric 없음 | Place ID/Detail 미완료 |
| 9604 | 지유가오카핫쵸메7호점 | VERIFIED, numeric 없음 | Place ID/Detail 미완료 |
| 9610 | 삼미 | VERIFIED, NAVER numeric AMBIGUOUS | 보류 상태 확인 |
| 9627 | 파니나로 | VERIFIED, numeric 없음 | Place ID/Detail 미완료 |

기존 Verification이 이미 VERIFIED이므로 이 Pilot은 Provider/Qwen 신규 판단 Pilot이 아니라, 완료된 Verification을 재사용하는 Place ID→Detail downstream Pilot이다.

## 5. 음식점별 실제 Pilot 결과

| ID | Orchestrator run | Place ID | Detail | 결과 |
|---:|---|---|---|---|
| 9576 | `20260924-020935-885216` | UNRESOLVED | 미진입 | 후보 numeric ID 없음 |
| 9599 | `20260924-020857-820477` | UNRESOLVED | 미진입 | 후보 numeric ID 없음 |
| 9604 | `20260924-020915-804540` | UNRESOLVED | 미진입 | 후보 numeric ID 없음 |
| 9610 | `20260924-020658-332074` | 기존 AMBIGUOUS 보존 | 미진입 | 기본 정책상 재시도 안 함 |
| 9627 | `20260924-020924-828281` | UNRESOLVED | 미진입 | 후보 numeric ID 없음 |

모든 실행에서:

- Verification은 `VERIFIED/MATCHED` 유지
- Recommendation eligibility는 `ELIGIBLE` 유지
- Qwen/Provider Entity Resolution은 재실행하지 않음
- Numeric ID가 확정되지 않아 Detail을 실행하지 않음
- 403/429/CAPTCHA/BLOCKED 없음

## 6. Pilot 중 발견·수정한 오류

9576 첫 실행(`20260924-020513-379694`)과 9599 첫 실행(`20260924-020720-329217`)에서 UNRESOLVED 결과를 기록할 때 다음 오류가 발생했다.

```text
ERROR 1136 (21S01): Column count doesn't match value count at row 1
```

원인은 unresolved INSERT가 8개 컬럼에 9개 값을 생성한 것이었다. 매칭 성공 경로에는 없고, numeric ID가 없는 결과를 저장하는 경로에만 있었다.

최소 수정:

- `ai/app/naver/place_id_linker_cli.py`
- `ai/tests/naver/test_place_id_linker.py`

`external_place_id=NULL`을 명시하고 INSERT 컬럼·값 개수를 일치시켰다. 수정 후 9599와 9576은 동일한 검색 결과를 `UNRESOLVED`로 정상 기록하고 Detail을 생략했다.

## 7. Provider/Qwen 및 처리시간

이번 5건 Pilot은 기존 VERIFIED 결과를 재사용했으므로 Provider/Qwen 측정값은 다음과 같다.

| 항목 | 실제 결과 |
|---|---:|
| Provider 재호출 | 0 |
| Qwen 재호출 | 0 |
| Canonical 재실행 | 0 |
| Place ID 검색 대상 | 4건 |
| Place ID 기존 AMBIGUOUS skip | 1건 |
| Place ID MATCHED | 0건 |
| Detail 대상 | 0건 |
| Detail 저장 | 0건 |

개별 Place ID 실행은 각 대상 약 5~6초였으며, 이는 실제 NAVER UI 검색 실행값이다. Qwen/Provider 처리시간을 이번 실행시간에 합산하지 않았다.

## 8. Place ID 및 Detail 정확도

- `9610`의 기존 AMBIGUOUS 상태는 기본 Linker 정책이 재시도하지 않고 보존했다.
- 나머지 4건은 numeric 후보가 없어 `UNRESOLVED`로 남았다.
- AMBIGUOUS/UNRESOLVED를 MATCHED로 강제하지 않았다.
- Numeric ID가 없으므로 다른 지점의 Detail을 저장할 가능성을 차단했다.
- 이번 Pilot에서는 Detail DOM·MySQL 저장까지 도달한 신규 대상이 없으므로 신규 대상의 메뉴·영업시간·리뷰 정확성은 검증되지 않았다.

## 9. DB 전후 정합성

사후 조회 결과:

| ID | Verification | Eligibility | Numeric status | 메뉴 | Lifecycle |
|---:|---|---|---|---:|---:|
| 9576 | VERIFIED/MATCHED | ELIGIBLE | UNRESOLVED | 0 | 0 |
| 9599 | VERIFIED/MATCHED | ELIGIBLE | UNRESOLVED | 0 | 0 |
| 9604 | VERIFIED/MATCHED | ELIGIBLE | UNRESOLVED | 0 | 0 |
| 9610 | VERIFIED/MATCHED | ELIGIBLE | AMBIGUOUS | 0 | 0 |
| 9627 | VERIFIED/MATCHED | ELIGIBLE | UNRESOLVED | 0 | 0 |

대상 외 음식점의 DB 갱신은 수행하지 않았다. Provider/Qwen 상태, Canonical, Recommendation eligibility를 변경하지 않았다. Pilot 대상의 기존 unresolved/ambiguous 상태 기록 갱신 외에 Detail 데이터는 생성되지 않았다.

## 10. 테스트

| 검증 | 결과 |
|---|---|
| 영업시간/Detail/Place ID targeted tests | 33 passed |
| AI Harness | 161 passed, warning 1 |
| Backend | source/schema 변경 없음; 실행하지 않음 |
| Integration | source/schema 변경 없음; 실행하지 않음 |
| External NAVER UI | 9617 제한 dry-run, Pilot 4건 검색 |
| External Provider/Qwen | 이번 작업에서 실행하지 않음 |
| 전체 Batch | 실행하지 않음 |

## 11. 아직 검증되지 않은 사항

- 신규 대상 Provider→Qwen→Canonical 전체 신규 흐름은 이번 대상들이 이미 VERIFIED여서 검증하지 않았다.
- 신규 대상 중 MATCHED numeric ID가 없어 Detail 실환경 저장은 검증하지 못했다.
- 9617의 기존 영업시간 DB row는 보존했으므로 수정된 파서가 실제 DB에 재저장된 결과는 아직 없다.
- 9610 AMBIGUOUS를 재검증하려면 명시적 force-retry 정책 검토가 필요하지만 이번 작업에서는 수행하지 않았다.
- 전체 Batch와 대량 처리 성능은 검증하지 않았다.

## 12. 전체 Batch 전 해결할 문제

1. 영업시간 파서 수정 후 실제 저장이 필요한 기존 Detail 대상의 재수집 범위를 별도 승인해야 한다.
2. Provider/Qwen 신규 판단이 필요한 대상은 현재 다수가 `NO_CANDIDATE`/ERROR이므로, 검색어 정책을 바꾸기 전에 별도 Recall 검토가 필요하다.
3. Place ID `AMBIGUOUS` 대상은 자동 강제 연결하지 않고 수동/명시적 재검증 정책을 정해야 한다.

현재 상태에서 전체 Batch를 실행하지 않았다.

## 13. Git 및 안전 확인

- 이번 작업 source 수정: `ai/app/naver/place_dom_detail_crawler.py`, `ai/app/naver/place_id_linker_cli.py`
- 이번 작업 test 수정: `ai/tests/naver/test_place_dom_detail_crawler.py`, `ai/tests/naver/test_place_id_linker.py`
- Migration 수정: 없음
- 기존 Working Tree 변경: 보존
- 실행 결과/Manifest/Stage report/Snapshot: 보존
- `git diff --check`: PASS
- commit: 안 함
- push: 안 함
- staged: 없음
