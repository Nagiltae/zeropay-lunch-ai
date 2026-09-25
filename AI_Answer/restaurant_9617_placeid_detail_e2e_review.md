# 9617 Place ID 및 Detail E2E 검증 보고서

## 1. Executive Summary

- 대상은 `restaurant_id=9617` 한 건으로 제한했다. Provider/Qwen/Canonical은 재실행하지 않았다.
- 기존 `VERIFIED / MATCHED`, `ELIGIBLE`, Canonical 및 Kakao/NAVER Local mapping을 재사용했다.
- NAVER Maps UI/allSearch 기반 Place ID linking은 `1987855627 / MATCHED`로 완료됐다.
- Detail dry-run은 HOME/MENU/REVIEW를 모두 정상 수집했고, 이후 실제 MySQL 저장도 성공했다.
- 동일 대상 무강제 재실행은 `preexisting_skipped=1`, browser/navigation 0으로 종료되어 Freshness skip을 확인했다.
- 403/429/CAPTCHA/BLOCKED는 발생하지 않았다. 전체 Batch와 다른 음식점 처리는 실행하지 않았다.

## 2. 실행 전 DB 상태

Snapshot: `AI_Answer/restaurant_9617_snapshot_before.json`

| 항목 | 실행 전 상태 |
|---|---|
| KOMSCO | `(주)에스지푸드 논현역 마성떡볶이`, 학동로 지하 102 (논현동) |
| Verification | `VERIFIED / MATCHED` |
| Search policy | `provider-search-v2` |
| Eligibility | `ELIGIBLE` |
| Canonical | `마성떡볶이 논현역점`, 논현역 지하 1층 주소 |
| Kakao mapping | `993636779 / MATCHED` |
| NAVER Local mapping | 이름·주소 저장, numeric ID 없음 |
| Detail lifecycle | 0행 |
| 메뉴/영업시간/리뷰 | 모두 0행 |

실행 명령은 모두 `--limit 1 --restaurant-ids 9617`을 사용했다.

## 3. Numeric NAVER Place ID 확보

실행:

```text
BATCH_RUN_ID=placeid-9617-20260923
python -m app.naver.place_id_linker_cli --limit 1 --restaurant-ids 9617
```

Report: `ai/build/reports/naver-place-pipeline/e2e/placeid-9617-20260923-place_id.json`

결과:

| 항목 | 결과 |
|---|---:|
| 대상/처리 | 1 / 1 |
| MATCHED | 1 |
| UNRESOLVED | 0 |
| AMBIGUOUS | 0 |
| browser starts | 1 |
| Place ID | `1987855627` |
| 검색어 | `논현동 마성떡볶이 논현역점` |
| 소요시간 | 약 5.6초 |

기존 NAVER Local mapping의 이름 `마성떡볶이 논현역점`과 논현역 지하 1층 주소를 기준으로 UI 검색 결과를 대조했다. Linker는 이름 정규화 후 주소 쌍이 `EXACT` 또는 `STRONG_MATCH`인 numeric 후보만 인정하며, 이번 실행에서는 단일 후보가 남아 `MATCHED`로 저장됐다. 비공식 내부 API replay나 ID 추측은 사용하지 않았다.

DB에는 `restaurant_external_places(provider='NAVER', external_place_id='1987855627', match_status='MATCHED')`가 생성됐고 기존 KAKAO/NAVER_LOCAL mapping은 보존됐다.

## 4. Detail dry-run

Report: `ai/build/reports/naver-place-pipeline/e2e/detail-dryrun-9617-20260923-detail.json`

```text
BATCH_RUN_ID=detail-dryrun-9617-20260923
python -m app.naver.place_detail_enrichment_cli --limit 1 --restaurant-ids 9617 --dry-run
```

| 항목 | 결과 |
|---|---:|
| 대상/처리/성공 | 1 / 1 / 1 |
| HOME/MENU/REVIEW navigation | 1 / 1 / 1 |
| 메뉴 | 24건 |
| 영업시간 | 1행 |
| 리뷰 집계 | visitor 50, blog 12 |
| section failure | 0 |
| DB write | 없음 |

dry-run 직후 관련 Detail 테이블 row count는 계속 0이어서 DB 쓰기 차단을 확인했다.

## 5. Detail 실제 DB 저장

Report: `ai/build/reports/naver-place-pipeline/e2e/detail-write-9617-20260923-detail.json`

```text
BATCH_RUN_ID=detail-write-9617-20260923
python -m app.naver.place_detail_enrichment_cli --limit 1 --restaurant-ids 9617
```

저장 결과:

| 영역 | 결과 |
|---|---:|
| 메뉴 | 24건, active 24건, price NULL 0건 |
| 영업시간 | 1건, active 1건 |
| Review Summary | 1건 |
| Review Keywords | 35건, active 35건 |
| Representative Reviews | 10건, active 10건 |
| Section lifecycle | menu/business_hours/review 모두 SUCCESS |
| reconciliation | 3 sections |
| 실패/차단 | 0 / 0 |
| 처리시간 | 약 12.1초 |

대표적으로 메뉴 `마성김밥(4,500원)`, `치즈김밥(5,500원)`, `카야토스트(4,500원)` 등이 저장됐다. 영업시간은 1행이 저장됐으나 현재 결과의 `business_status` 텍스트가 `영업 종료...` 형태로 보존되고 `open_time/close_time`은 NULL이다. 이는 이번 실행의 저장 실패는 아니지만, 영업시간 파싱 품질은 별도 확인이 필요한 관찰 사항이다.

## 6. 실행 전후 비교

After snapshot: `AI_Answer/restaurant_9617_snapshot_after.json`

- Verification은 `VERIFIED / MATCHED`로 유지됐다.
- Recommendation eligibility는 `ELIGIBLE`로 유지됐다.
- Numeric NAVER mapping만 새로 생성됐다.
- Detail row와 세 section lifecycle이 새로 생성됐다.
- 메뉴·영업시간·리뷰 저장 중 중복 row는 확인되지 않았다.
- 기존 9559·9561 데이터는 이번 명령의 대상 범위에 포함되지 않았다.

## 7. Section Lifecycle 및 Freshness 재실행

저장 직후 상태:

| section | state | error_code |
|---|---|---|
| menu | SUCCESS | NULL |
| business_hours | SUCCESS | NULL |
| review | SUCCESS | NULL |

재실행 report: `ai/build/reports/naver-place-pipeline/e2e/detail-repeat-9617-20260923-detail.json`

```text
BATCH_RUN_ID=detail-repeat-9617-20260923
python -m app.naver.place_detail_enrichment_cli --limit 1 --restaurant-ids 9617
```

결과는 `target_count=0`, `preexisting_skipped=1`, `browser_starts=0`, HOME/MENU/REVIEW navigation 모두 0이었다. `--force-refresh` 없이 최신 SUCCESS lifecycle이 실제 대상 제외로 연결됐다.

## 8. Runtime Report 및 범위

- Place ID: 1건 처리, 1 MATCHED, browser start 1, Provider/Qwen 0.
- Detail dry-run: 1건 처리, 세 navigation 1회씩, section failure 0, DB 변경 없음.
- Detail write: 1건 처리, 세 navigation 1회씩, 세 section reconciliation, 성공 1.
- Detail repeat: 0건 처리, 기존 완료 skip 1, browser/navigation 0.
- Provider/Qwen/Canonical 단계는 이번 작업에서 재실행하지 않았다. 이전 Canonical/Verification 결과를 사용했다.

## 9. 발견한 문제와 수정 여부

- 코드 결함 수정: 없음.
- 테스트 수정: 없음.
- Migration 수정: 없음.
- 영업시간 1행의 `open_time/close_time`이 NULL이고 상태 텍스트가 비정형으로 보이는 점은 데이터 품질 확인 대상이다. 이번 작업 범위를 벗어나므로 임의 수정하지 않았다.
- Place ID 저장 row에는 linker 설계상 numeric ID와 status/query가 핵심으로 저장되고 이름·주소 metadata는 NULL이다. 동일성 판정은 저장 전 UI 후보와 기존 NAVER_LOCAL evidence로 수행됐다.

## 10. 테스트

| 검증 | 결과 |
|---|---|
| NAVER/Detail targeted tests | 31 passed |
| AI Harness | 158 passed, warning 1 |
| Backend | 이번 작업에서 source/schema 변경 없음; 재실행하지 않음 |
| Integration | 이번 작업에서 source/schema 변경 없음; 재실행하지 않음 |
| 외부 Place ID | 9617 한 건만 실행 |
| 외부 Detail | 9617 한 건만 dry-run/write/repeat 실행 |
| 외부 Provider/Qwen | 실행하지 않음 |
| 전체 Batch | 실행하지 않음 |

## 11. 아직 검증하지 못한 사항

- 9617의 전체 E2E를 Orchestrator 한 번으로 실행한 것은 아니다. Provider/Qwen/Canonical은 이전 실행 결과를 재사용하고 Place ID/Detail을 개별 실행했다.
- 영업시간 파서의 비정형 텍스트가 실제 영업시간 의미를 완전히 보존하는지는 추가 확인이 필요하다.
- 다른 음식점의 Place ID/Detail 정확도와 대량 처리 성능은 검증하지 않았다.

## 12. 다음 Pilot 확대 가능 여부

9617 단건의 Place ID 연결, Detail dry-run, 실제 persistence, freshness skip은 완료됐다. 다만 영업시간 파싱 관찰 사항을 확인한 뒤 2건 이상으로 확대하는 것이 안전하다. 전체 Batch는 아직 실행하지 않는다.

## 13. Git 및 안전 확인

- 이번 작업에서 source/test/migration 수정: 없음
- 기존 DB: 9617의 정상 Place ID/Detail 저장 외 변경 없음
- 기존 산출물: 보존
- 새 Snapshot: `restaurant_9617_snapshot_before.json`, `restaurant_9617_snapshot_after.json`
- `git diff --check`: PASS
- commit: 안 함
- push: 안 함
- staged: 없음
