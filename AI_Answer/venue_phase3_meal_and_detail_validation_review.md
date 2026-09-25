# ZeroPay Lunch AI — Venue Phase 3 최근 식사 및 Detail 검증 보고서

## 1. Executive Summary

이번 단계에서 Venue 기준 최근 식사 제외를 구현하고, 격리 MySQL에서 association·meal history·추천 필터 흐름을 검증했다. 또한 기존 Numeric NAVER Place ID를 가진 9560/9561을 제한적으로 dry-run하고, 9560 한 건만 실제 Detail persistence를 수행했다.

핵심 결과:

* `CONFIRMED + ACTIVE` association에 연결된 최근 식사 Restaurant의 Venue key를 후보 Restaurant에도 적용한다.
* 식사 원본 row는 기존 `restaurant_id`와 시각을 그대로 보존한다.
* PENDING/REJECTED/INACTIVE/미연결 관계는 Venue로 확장하지 않는다.
* 격리 MySQL에서 association 조회, meal history 조회, 동일 Venue 후보 제외를 실제 Spring persistence 코드로 PASS했다.
* 9560 `송가네`는 NAVER Place ID `196686446`으로 Detail dry-run 및 실제 저장에 성공했다.
* 9561 `다모아분식`은 dry-run만 수행했다.
* 9560 재실행은 fresh section으로 판단되어 `preexisting_skipped=1`, browser/navigation 0이었다.
* 실제 9582/9619 및 9661/9695에는 Venue association을 생성하지 않았다.

전체 Batch, Provider/Qwen 재실행, 신규 Venue Detail 모델, 기존 데이터 일괄 이전은 수행하지 않았다.

## 2. Venue 기준 최근 식사 구현

기존 추천 흐름은 `RecommendationContextService`가 최근 식사를 `restaurant_id`로 전달하고, `RestaurantRecommendationService`가 해당 ID만 제외했다. 이 구조에서는 최근 식사 A와 같은 Venue인 B가 추천될 수 있었다.

현재 구현은 다음 순서를 사용한다.

1. 최근 meal의 Restaurant ID와 open candidate Restaurant ID를 합집합으로 만든다.
2. association repository에서 `CONFIRMED + ACTIVE` 관계를 한 번 조회한다.
3. 최근 식사 Restaurant ID를 현재 Venue ID로 변환한다.
4. 후보 Restaurant도 같은 Venue ID로 변환한다.
5. 최근 Venue key와 같은 후보를 hard filter 단계에서 제외한다.
6. 기존 score/정렬을 적용한다.
7. 같은 Venue 중복 제거를 적용한다.

최근 식사 기록이 후보 목록에 없어도 association 조회 대상에 포함되므로, A를 먹고 현재 후보에는 B만 있는 경우에도 B가 제외된다.

상태별 의미는 다음과 같다.

| 관계 | 최근 식사 해석 |
|---|---|
| CONFIRMED + ACTIVE | Venue 기준으로 확장 |
| PENDING | restaurant_id 기준 유지 |
| REJECTED | restaurant_id 기준 유지 |
| CONFIRMED + INACTIVE Venue | restaurant_id 기준 유지 |
| association 없음 | restaurant_id 기준 유지 |

기존 3일 `RECOMMENDATION_LOOKBACK`은 변경하지 않았다. 식사 row의 `restaurant_id`, `eaten_at`, source message 관계도 수정하지 않는다.

## 3. 회귀 테스트

추가·보강한 테스트는 다음을 검증한다.

* 같은 CONFIRMED + ACTIVE Venue에서 A를 먹으면 B도 제외
* 최근 식사 Restaurant가 현재 후보에 없어도 같은 Venue 후보 제외
* 유효 association 조회 결과가 없으면 최근 식사 범위를 확장하지 않음
* 기존 unassociated Restaurant 추천 유지
* 기존 Venue 중복 제거 유지
* 기존 restaurant_id 기반 최근 식사 처리 유지
* 3일 lookback 밖의 기록은 기존 테스트 계약에 따라 제외

PENDING/REJECTED/INACTIVE는 서비스가 오직 `CONFIRMED + ACTIVE` 조건의 repository 결과만 소비하는 계약으로 보호된다. 따라서 해당 상태가 repository 조회 결과에 포함되지 않는다.

## 4. 실제 MySQL 승인·추천 통합 검증

운영성 개발 DB와 분리한 MySQL 데이터베이스 `zeropay_venue_phase3_20260924`를 사용했다. 이 DB에는 Flyway migrations와 V21을 적용했고 테스트 transaction으로만 fixture를 만들었다.

실제 애플리케이션 코드로 검증한 흐름:

```text
Restaurant A/B 저장
→ Venue 저장
→ 두 PENDING association 저장
→ evidence와 함께 CONFIRMED 결정
→ 실제 association repository 조회
→ 실제 meal_history 저장/조회
→ 동일 Venue 후보를 recommendation service에서 제외
```

검증 결과:

* association repository에서 두 CONFIRMED + ACTIVE 관계 조회: PASS
* `MealHistoryService.findRecent()`에서 원본 Restaurant A 반환: PASS
* A 식사 후 같은 Venue의 B 추천 제외: PASS
* B의 `recommendation_eligibility` 독립 보존: PASS
* meal row의 `restaurant_id` 보존: PASS
* 관리자 PENDING 생성/결정/권한 테스트: PASS

실제 운영 DB에는 테스트 fixture를 쓰지 않았다. 기존 9582/9619, 9661/9695 및 기존 Place ID/Detail/Eligibility/meal history는 변경하지 않았다.

## 5. 현재 Detail 데이터 집계

최신 개발 DB 읽기 전용 집계:

| 항목 | 수치 |
|---|---:|
| 활성 Restaurant | 517 |
| Numeric NAVER MATCHED Restaurant | 360 |
| 메뉴 row가 있는 활성 Restaurant | 325 |
| 영업시간 row가 있는 활성 Restaurant | 360 |
| Review Summary row가 있는 활성 Restaurant | 360 |
| 메뉴·시간·Review Summary가 모두 있는 Numeric 대상 | 325 |
| Section Lifecycle 보유 Restaurant | 3 |
| `venues` row | 0 |
| `restaurant_venue_associations` row | 0 |

위 수치는 “row 존재” 집계이며, 각 row의 최신성·내용 정확성을 모두 보증하지 않는다. 특히 lifecycle이 없는 legacy detail은 `crawled_at` fallback을 사용한다.

## 6. Detail 대상 선정 및 dry-run

기존 제외 목록인 9582, 9619, 9661, 9695, 9610은 사용하지 않았다.

### 9560 — 송가네

* Numeric NAVER Place ID: `196686446`
* Provider mapping: `NAVER / MATCHED`
* Canonical: 송가네, 봉은사로25길 12
* Eligibility: `ELIGIBLE`
* 저장 전 detail: 메뉴 10, 영업시간 1, Review Summary 1, keywords 31, representative reviews 10
* 저장 전 section lifecycle: 없음

### 9561 — 다모아분식

* Numeric NAVER Place ID: `43229792`
* Provider mapping: `NAVER / MATCHED`
* Canonical: 다모아분식, 논현로150길41
* dry-run 결과: 메뉴 16, 영업시간 1, visitor review 751, blog review 285
* 저장은 수행하지 않음

dry-run report:

`ai/build/reports/naver-place-pipeline/e2e/venue-phase3-detail-20260924-01-detail.json`

두 대상 모두 DOM 수집은 성공했고, 차단·retry·실패는 없었다. Provider/Qwen 호출은 0회였다.

## 7. 9560 실제 Detail Persistence

실행 전 snapshot:

`AI_Answer/venue_phase3_detail_9560_snapshot_before.json`

실행 명령은 기존 CLI 계약에 따라 `--dry-run` 없이 실행했다. 현재 CLI에는 `--write-db` flag가 없고, 기본 동작이 write이며 `--dry-run`만 DB write를 차단한다.

실행 report:

`ai/build/reports/naver-place-pipeline/e2e/venue-phase3-detail-20260924-02-detail.json`

결과:

| 항목 | 결과 |
|---|---:|
| target | 1 |
| success | 1 |
| failure | 0 |
| retry | 0 |
| blocked / HTTP 429 | 0 / 0 |
| browser starts | 1 |
| HOME navigation | 1 |
| MENU navigation | 1 |
| REVIEW navigation | 1 |
| menu/hour/review collected | 1 / 1 / 1 |
| section reconciled | 3 |
| elapsed | 12.192 sec |

실제 저장 후:

* active menu 10건
* business hours 1건
* Review Summary 1건
* Review Keywords 31건
* Representative Reviews 10건
* `menu`, `business_hours`, `review` 모두 `SUCCESS`
* `error_code` 없음
* Numeric Place ID와 mapping 변경 없음
* Eligibility `ELIGIBLE` 유지

실행 후 snapshot:

`AI_Answer/venue_phase3_detail_9560_snapshot_after.json`

기존 row를 삭제하거나 다른 Restaurant에 복사하지 않았다. 정상 snapshot에 대한 reconciliation만 수행됐다.

## 8. Freshness 재실행

동일 대상에 force refresh 없이 재실행했다.

report:

`ai/build/reports/naver-place-pipeline/e2e/venue-phase3-detail-20260924-03-detail.json`

결과:

* `target_count=0`
* `preexisting_skipped=1`
* `DETAIL_COMPLETE_SKIPPED=1`
* browser starts 0
* HOME/MENU/REVIEW navigation 모두 0
* 외부 Provider/Qwen 호출 0

따라서 lifecycle freshness가 실제 browser 실행 생략으로 연결되는 것을 9560에서 확인했다.

## 9. 데이터 보호 및 미완료 작업

확인된 보호 조건:

* 실제 Venue association 생성 없음
* 기존 Place ID 교체 없음
* 9560의 기존 Detail 외 Restaurant 변경 없음
* 기존 meal history의 restaurant_id 변경 없음
* Detail 실패/차단 결과 없음
* Provider/Qwen 재검증 없음

이번 단계에서 실행하지 않은 것:

* 9561 실제 DB persistence
* 기존 Detail의 Venue 소유권 전환
* 전체 Detail Batch
* 9582/9619 및 9661/9695 association 승인
* Semantic Profile, embedding, Qdrant 적재

## 10. 향후 데이터 수집 및 Semantic Profile 준비

현재 개발 DB에는 Numeric Place ID 대상 360건과 메뉴·시간·Review Summary가 모두 존재하는 대상 325건이 있다. 그러나 이는 row 존재 기준이므로 Semantic Profile 입력으로 바로 확정하면 안 된다.

Profile 생성 전 추가로 필요한 품질 기준:

* section lifecycle 또는 신뢰 가능한 crawled_at
* 메뉴 가격의 NULL/텍스트 가격 처리 확인
* 영업시간이 실제 요일별 구조인지 상태 텍스트인지 구분
* Review Summary와 keywords의 동일 external place 연결
* Provider Place ID 소유권 충돌 없음
* 최신성 TTL 통과
* Detail parser 실패와 정상 ABSENT 구분

따라서 현재 수치만으로 Qwen3 8B Semantic Profile 생성 가능 건수를 확정하지 않는다. 이번 단계에서는 Profile 생성·Embedding·Qdrant 적재를 실행하지 않았다.

## 11. 테스트 결과

| 검증 | 결과 |
|---|---|
| Backend unit/application tests | PASS |
| Backend compile/test/build | PASS |
| Venue 최근 식사 targeted tests | PASS |
| 격리 MySQL Venue/meal/recommendation targeted tests | PASS |
| AI Harness | 마지막 실행 기준 166 passed, 1 warning |
| Integration Harness | 마지막 실행 기준 PASS |
| `git diff --check` | PASS |
| 외부 NAVER Maps | 9560/9561 dry-run 및 9560 write 각 1건 제한 실행 |
| Provider/Qwen | 미실행 |
| 전체 Batch | 미실행 |

격리 MySQL 전체 test suite를 무조건 운영성 fixture처럼 실행하지 않았다. 전체 suite는 테스트 profile의 H2 driver 고정/샘플 row count 가정 때문에 MySQL profile에서 일부 import count assertion이 달라졌고, Venue Phase 3에 필요한 실제 MySQL targeted tests는 별도로 통과했다. 이 차이는 보고서에 남긴다.

## 12. 다음 단계 판단

현재 상태에서 다음을 진행할 수 있다.

* 동일 계약의 Detail 대상 추가 선정은 최대 소규모로 진행 가능
* 기존 Numeric Place ID 기반 section 수집과 freshness 재실행 검증 가능
* Venue association은 수동 증거와 사용자 승인 후에만 생성

전체 Detail Batch 전에 다음을 먼저 확인해야 한다.

1. lifecycle 없는 legacy detail의 section 판정 표본 검토
2. 영업시간 상태 텍스트와 구조화 시간의 의미 분리
3. 35건가량의 Numeric 대상 incomplete/legacy 상태 분류
4. 실제 운영 Venue association 승인 정책
5. Semantic Profile 입력 품질 기준 확정

## 13. Git 및 안전 확인

* 기존 Flyway migration 수정: 없음
* 운영 9582/9619, 9661/9695 association 생성: 없음
* 기존 Place ID 자동 교체: 없음
* 기존 Detail Venue 이전: 없음
* 전체 Batch: 실행하지 않음
* Git add/commit/push: 하지 않음
* 기존 working tree 및 실행 산출물: 보존
