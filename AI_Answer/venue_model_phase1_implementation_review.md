# ZeroPay Lunch AI — Venue 모델 1차 구현 및 기존 Batch 호환성 검토

## 1. Executive Summary

이번 단계에서 Venue 관계를 기존 Restaurant/Place ID/Detail 소유권과 분리된 additive 모델로 구현했다.

완료한 내용:

* `venues`와 `restaurant_venue_associations` 신규 Flyway V21 추가
* Restaurant 1건당 association 최대 1건 제약
* association 상태 `PENDING`, `CONFIRMED`, `REJECTED` 모델링
* 기존 KOMSCO restaurant, Numeric NAVER mapping, Detail 테이블은 변경하지 않음
* `CONFIRMED` association이 있고 Venue도 `ACTIVE`인 추천 후보만 Venue ID 기준으로 dedup
* PENDING/REJECTED/미연결 Restaurant는 기존 추천 경로 유지
* 기존 Recommendation API의 `restaurantId`, 식사 기록, message recommendation 저장 계약 유지
* 격리 MySQL에서 Migration/FK/UNIQUE 검증
* Spring Backend, Integration, AI Harness 통과

최초 Integration 실행에서는 association repository derived query가 연관 필드 구조와 맞지 않는 결함이 발견됐다. `restaurantId`를 `restaurant.id` 경로인 `findAllByRestaurant_IdInAndStatusAndVenue_Status`로 수정한 뒤 재실행이 PASS했다.

전체 데이터 Venue 이전이나 전체 Batch는 실행하지 않았다. 9582/9619 및 9661/9695도 자동 연결하지 않았다.

## 2. 기존 구조와 영향 범위

기존 데이터 흐름은 다음과 같다.

```text
restaurants (KOMSCO 원본 가맹점)
  → verification / canonical_restaurants
  → restaurant_external_places (Provider mapping 및 Numeric Place ID)
  → restaurant_menus / business_hours / review tables
  → recommendation 및 message_recommendations
```

현재 Numeric NAVER Place ID와 Detail은 `restaurant_id`에 종속되어 있다. Python Batch도 이 계약을 사용하고 있으므로, 이번 단계에서 Place ID나 Detail의 소유자를 Venue로 교체하지 않았다.

Spring 추천은 `RestaurantJpaRepository.findOpenRestaurants()`로 Restaurant를 조회한 뒤 예산·카테고리·최근 식사·ZeroPay 조건을 적용한다. 채팅 persistence와 meal history 및 기존 API 응답은 모두 `restaurant_id`를 사용한다.

따라서 1차 Venue 도입에서 변경한 범위는 추천 후보의 표시 중복 제거뿐이며, 저장·상세·결제 자격·식사 기록의 식별자는 기존대로 유지했다.

## 3. Venue 모델과 Schema

### `venues`

물리적 장소의 보조 식별자다.

* `id` PK
* `name`, `address`
* optional `latitude`, `longitude`
* `venue_status`: `ACTIVE`/`INACTIVE`
* `created_at`, `updated_at`

### `restaurant_venue_associations`

KOMSCO Restaurant와 Venue의 검증 관계를 저장한다.

* `restaurant_id` FK → `restaurants.id`
* `venue_id` FK → `venues.id`
* `association_status`: `PENDING`, `CONFIRMED`, `REJECTED`
* `evidence`, `verified_at`, timestamps
* `UNIQUE(restaurant_id)`: 한 가맹점은 1차 구현에서 하나의 Venue만 연결
* `(restaurant_id, venue_id)` UNIQUE
* `(venue_id, association_status)` 조회 index

하나의 Venue에 여러 Restaurant가 연결되는 것은 허용한다. 그러나 이번 단계에는 실제 association row를 운영 데이터에 삽입하지 않았다. 상호·주소·좌표가 같다는 이유만으로 CONFIRMED를 만들지 않았다.

Migration은 적용된 기존 파일을 수정하지 않고 `V21__create_venue_associations.sql`로 추가했다.

## 4. Venue 도입 결정의 근거

이전 감사에서 다음 두 쌍은 동일 장소 가능성이 높았다.

| 그룹 | 공통 근거 | 현재 처리 |
|---|---|---|
| 9582 / 9619 | 우정양곱창, 도산대로30길 23, 동일 좌표, Place ID 1921750340은 9582 소유 | 자동 연결하지 않음 |
| 9661 / 9695 | 현대순대국, 강남대로124길 20, 동일 좌표, Place ID 19882368은 9661 소유 | 자동 연결하지 않음 |

현재 근거는 물리 장소 가능성을 보여주지만, KOMSCO 사업자/제로페이 자격이 같은지까지 보장하지 않는다. 그러므로 Venue association은 업무 검증 후 명시적으로 생성해야 한다.

## 5. 기존 데이터 호환 방식

이번 단계에서는 다음을 보장한다.

* 기존 Restaurant는 association이 없어도 기존 추천에 계속 포함될 수 있음
* 기존 Numeric Place ID 소유자는 변경하지 않음
* 기존 Detail row와 section lifecycle은 이동·복제하지 않음
* 기존 `restaurant_id` 기반 API 응답 유지
* 기존 message recommendation 및 meal history는 변경하지 않음
* CONFIRMED 연결이 있더라도 Restaurant의 Eligibility를 다른 Restaurant에 상속하지 않음

Venue Provider mapping과 Venue Detail 소유권 전환은 구현하지 않았다. 현재는 기존 `restaurant_external_places`와 Detail을 단일 source of truth로 유지한다.

## 6. Spring 추천 중복 제거 구현

`RestaurantRecommendationService`에 `RestaurantVenueAssociationJpaRepository`를 연결했다.

동작 순서:

1. 기존 open Restaurant 조회
2. 기존 예산·카테고리·ZeroPay·최근 식사 필터 적용
3. 기존 score 및 deterministic ordering 적용
4. `CONFIRMED` association과 `ACTIVE` Venue만 조회
5. 같은 `venue_id`는 첫 번째 Restaurant만 유지
6. association이 없거나 PENDING/REJECTED이면 `restaurant_id`를 자체 key로 사용
7. 최대 3건 반환

대표 Restaurant는 기존 score → average price → restaurant ID 순서의 첫 결과로 결정된다. 이는 API의 `restaurantId`를 유지하면서 추천 중복을 줄이기 위한 1차 정책이다.

최근 식사 기록은 기존처럼 `restaurant_id` 기반으로 처리한다. 따라서 Venue 단위 최근 식사 의미 변경은 이번 단계에서 하지 않았으며, 후속 정책 결정이 필요하다.

## 7. Python Batch 영향

다음 정책은 변경하지 않았다.

* Adaptive Search 및 Provider Prefetch
* Qwen Semantic Validation
* VERIFIED/REJECTED Cache 및 Search Policy Version
* reason별 TTL 및 BLOCKED cooldown
* Numeric Place ID 원자적 INSERT
* `PLACE_ID_EXTERNAL_ID_CONFLICT` 차단
* Detail Section Lifecycle 및 Freshness
* Persistent MySQL session

Python Batch는 계속 Restaurant 기반으로 Place ID와 Detail을 저장한다. CONFIRMED Venue가 있다는 이유로 동일 Place ID를 다른 Restaurant에 복사하지 않는다. Venue 단위 수집 dedup은 소유권 계약을 먼저 확정한 후 후속 단계에서 다룬다.

## 8. 격리 MySQL 검증

테스트 DB `zeropay_place_it_1790188426887`에 현재 `restaurants` 구조와 V21을 적용했다. 운영 `zeropay_lunch`의 가맹점·mapping·Detail row는 테스트에 사용하지 않았다.

검증 결과:

* Venue 생성 및 association 저장: PASS
* 같은 Venue에 두 Restaurant의 CONFIRMED 연결: PASS
* 한 Restaurant의 PENDING 연결: PASS
* 같은 Restaurant의 중복 association: MySQL 1062로 차단
* 존재하지 않는 Venue FK: MySQL 1452로 차단
* 기존 Restaurant FK 제약 유지: PASS

격리 DB의 테스트 row는 보존했으며 운영 데이터와 분리되어 있다.

## 9. 테스트 결과

| 검증 | 결과 |
|---|---|
| Backend compile/test/build | PASS |
| AI Harness | 166 passed, 1 warning |
| Integration Harness | PASS |
| Spring 추천 Venue dedup unit test | PASS |
| 격리 MySQL V21/FK/UNIQUE | PASS |
| `git diff --check` | PASS |
| 외부 Provider/Qwen/NAVER | 실행하지 않음 |
| 전체 Batch | 실행하지 않음 |

최초 Integration 실행은 association repository 경로 오류로 실패했지만, 원인 수정 후 전체 Integration Harness가 PASS했다. 이 오류는 회귀 테스트에서 Spring 추천 서비스의 repository 호출 검증으로 보강했고, 최종 조회 조건에는 `VenueStatus.ACTIVE`도 포함했다.

## 10. 기존 데이터 적용 계획

이번 단계에서는 운영성 가맹점 association을 생성하지 않았다. 다음 단계에서 association을 추가하려면 최소한 다음 증거가 필요하다.

1. KOMSCO external merchant ID 또는 사업자 관계 확인
2. 동일 장소의 Provider Place ID와 주소/좌표 evidence
3. 두 원본이 같은 Venue를 공유해도 되는 업무 정책 확인
4. 각 Restaurant의 ZeroPay eligibility를 독립적으로 유지할 수 있는지 검증

단계적 전환 계획:

* 1단계: 수동 승인된 association만 생성하고 기존 Restaurant/Place ID/Detail은 그대로 유지
* 2단계: 추천 조회에서 ACTIVE Venue에 대한 CONFIRMED association만 dedup
* 3단계: Venue provider mapping을 추가할 필요가 있는지 검토
* 4단계: 신규 Place ID와 Detail부터 Venue 소유로 저장하는 별도 계약 검증
* 5단계: 기존 Detail 이전은 checksum/row 비교 후 별도 migration으로 수행
* 각 단계 실패 시 기존 Restaurant 경로를 유지

이중 쓰기를 시작하기 전에는 동일 Place ID의 소유권을 Restaurant와 Venue 양쪽에서 동시에 관리하지 않도록 단일 저장 계약을 확정해야 한다.

## 11. 미완료 및 위험

* 9582/9619, 9661/9695의 운영 association 확정: 미완료
* 기존 Numeric Place ID/Detail의 Venue 이전: 미구현
* Venue 단위 메뉴·영업시간·리뷰 persistence: 미구현
* Venue 단위 최근 식사 이력 해석: 미결정
* 추천 응답에 `venueId`를 추가하는 API 변경: 하지 않음
* Venue 소유 Provider mapping: 하지 않음

현재 구현은 “추천 결과에서 CONFIRMED 관계의 중복을 제거하는 1차 호환 계층”이다. 전체 Venue 전환이나 기존 데이터 자동 병합을 의미하지 않는다.

## 12. Git 및 안전 확인

* 기존 Migration 수정: 없음
* 신규 Migration: `V21__create_venue_associations.sql`
* 운영 Restaurant/Place ID/Detail 자동 변경: 없음
* 기존 KOMSCO 가맹점 자동 병합: 없음
* 전체 Batch: 실행하지 않음
* 외부 Provider/Qwen/NAVER: 실행하지 않음
* Git add/commit/push: 하지 않음
* 기존 working tree 및 산출물: 보존
