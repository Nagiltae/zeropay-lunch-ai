# ZeroPay Lunch AI — Venue Phase 2 연결 승인 및 추천 정합성 검토

## 1. Executive Summary

이번 단계에서는 기존 V21 Venue 모델을 확장하지 않고, 명시적 검토·승인 절차와 추천 중복 제거 계약을 검증했다.

결과는 다음과 같다.

* 유사 주소 또는 좌표를 가진 후보를 읽기 전용으로 조회할 수 있다.
* 관리자는 후보를 바로 확정하지 않고 `PENDING` association을 만든 뒤 `CONFIRMED` 또는 `REJECTED`로 결정한다.
* `CONFIRMED`이면서 `ACTIVE` Venue인 관계만 추천 중복 제거에 사용된다.
* PENDING, REJECTED, INACTIVE, 미연결 Restaurant는 기존 restaurant 단위 추천 경로를 유지한다.
* 9582/9619 및 9661/9695는 동일 물리 장소 가능성이 높지만, 운영 association은 생성하지 않았다.
* 기존 Place ID·Detail·Eligibility·식사 기록의 소유권과 API 계약은 변경하지 않았다.

이번 개발 DB 확인 결과 `venues = 0`, `restaurant_venue_associations = 0`이다. 실제 가맹점의 자동 병합이나 CONFIRMED 승인은 수행하지 않았다.

## 2. Venue 연결 검증 및 승인 구현

### 후보 조회

`RestaurantJpaRepository.findPotentialVenueAssociations()`가 활성 Restaurant 쌍을 읽기 전용으로 조회한다. 후보 조건은 다음 중 하나다.

* 주소가 정확히 동일함
* 두 좌표가 모두 존재하고 위도·경도가 정확히 동일함

이 조회 결과는 “검토 후보”일 뿐 동일 장소를 확정하지 않는다. 이름 유사도나 동일 주소만으로 CONFIRMED를 생성하지 않는다.

### 승인 lifecycle

`VenueAssociationAdminService`와 `RestaurantVenueAssociation`의 계약은 다음과 같다.

```text
후보 조회
  → 관리자 PENDING 생성
  → 명시적 evidence 기록
  → CONFIRMED 또는 REJECTED 결정
```

* 한 Restaurant에는 현재 association 하나만 허용된다.
* PENDING만 CONFIRMED/REJECTED로 전환할 수 있다.
* 동일한 최종 결정의 반복 요청은 idempotent하다.
* CONFIRMED는 ACTIVE Venue에 대해서만 허용된다.
* 결정 시 `verified_at`, evidence, `updated_at`을 기록한다.
* 이미 결정된 association을 반대 상태로 변경하는 요청은 충돌로 거부한다.
* 기존 Restaurant의 Eligibility와 Verification은 변경하지 않는다.

## 3. 관리자 API 및 권한 정책

기존 ADMIN 역할을 재사용했다. 별도 권한이나 인증 스키마는 추가하지 않았다.

| Method | Endpoint | 동작 |
|---|---|---|
| GET | `/api/admin/venue-associations/candidates` | 주소/좌표 기반 검토 후보 조회 |
| POST | `/api/admin/venue-associations` | PENDING Venue association 생성 |
| PATCH | `/api/admin/venue-associations/{associationId}` | CONFIRMED/REJECTED 결정 |

`/api/admin/**`은 `ROLE_ADMIN`만 접근할 수 있다. 회귀 테스트에서 미인증 요청은 401, 일반 사용자 요청은 403, ADMIN 요청은 200을 확인했다.

관리자 API를 통한 실제 운영 association 생성은 이번 단계에서 실행하지 않았다.

## 4. 중복 의심 가맹점 검토

### 9582 / 9619

두 원본은 `우정 양곱창` 계열의 상호, 도산대로30길 23 주소 계열, 동일 좌표를 가진다. Numeric Place ID `1921750340`은 현재 9582에 연결되어 있다.

이는 동일 물리 장소 가능성을 강하게 시사하지만, 두 KOMSCO 기록의 사업자 또는 제로페이 자격이 동일하다는 근거는 아니다. 따라서 9619에 Place ID, Eligibility, Detail을 복사하거나 association을 자동 생성하지 않았다.

### 9661 / 9695

두 원본은 `현대순대국`, 강남대로124길 20, 동일 좌표 계열이다. Numeric Place ID `19882368`은 현재 9661에 연결되어 있다.

이 그룹도 물리 장소 가능성과 가맹점 자격은 별도 문제이므로 추가 증거와 사용자/업무 승인이 필요하다. 이번 단계에서 자동 연결하지 않았다.

### 승인에 필요한 추가 근거

두 그룹 모두 다음이 확인되기 전에는 CONFIRMED로 승인하면 안 된다.

* KOMSCO 원본 가맹점의 사업자 관계 또는 동일 장소 공유 정책
* 외부 Provider 장소가 실제 같은 지점이라는 독립 근거
* 각 가맹점의 ZeroPay Eligibility를 독립적으로 유지할 수 있는지
* 같은 Venue를 추천에서 하나로 표시해도 되는 업무 승인

## 5. 추천 서비스 정합성

`RestaurantRecommendationService`의 순서는 다음과 같다.

1. 기존 open Restaurant 조회
2. ZeroPay, 예산, 카테고리, 비선호, 최근 식사 등 Restaurant 단위 hard filter
3. 기존 score와 `score desc → average_price asc → restaurant_id asc` 정렬
4. `CONFIRMED + ACTIVE` association 조회
5. 동일 Venue key의 첫 Restaurant만 유지
6. 최대 3건 제한

따라서 대표 Restaurant는 기존 필터와 정렬을 통과한 Restaurant 중 첫 항목이다. 탈락한 Restaurant의 Eligibility, 가격, 영업시간, 거리 정보는 다른 Restaurant에 상속되지 않는다.

상태별 동작:

| 상태 | 추천 중복 제거 |
|---|---|
| CONFIRMED + ACTIVE | Venue 기준으로 1건만 표시 |
| PENDING | 적용하지 않음 |
| REJECTED | 적용하지 않음 |
| CONFIRMED + INACTIVE | 적용하지 않음 |
| association 없음 | 기존 restaurant_id 기준 유지 |

중복 제거는 필터와 정렬 뒤에 수행되므로, 유효한 다른 Venue 후보가 있으면 계속 결과에 포함될 수 있다. 현재 구현은 Venue 중복 제거만 담당하며 기존 score·hard filter 정책은 변경하지 않는다.

## 6. 최근 식사 및 대표 Restaurant

최근 식사 제외는 여전히 `restaurant_id` 기준이다. 따라서 같은 Venue에 연결된 A에서 식사해도, 별도 Restaurant B는 현재 코드상 최근 식사 제외 대상이 아니다.

이는 이번 단계에서 업무 정책을 임의로 바꾸지 않은 결과다. Venue 단위 최근 식사 제외를 도입하려면 다음을 별도 승인해야 한다.

* 원본 meal row의 restaurant_id 보존
* CONFIRMED + ACTIVE 관계에만 Venue 단위 해석 적용
* PENDING/미연결 Restaurant는 기존 의미 유지
* 개별 Eligibility는 변경하지 않음

따라서 이번 단계에서는 추천 동작을 변경하지 않고 설계 이슈로 남겼다.

## 7. Place ID 및 Detail 호환성

Venue association은 기존 `restaurant_external_places`, Numeric NAVER Place ID, Detail, Section Lifecycle의 소유권을 변경하지 않는다.

검증한 안전 조건:

* CONFIRMED association을 이유로 Place ID를 다른 Restaurant에 복사하지 않음
* 기존 mapping을 Venue mapping으로 덮어쓰지 않음
* Detail row와 lifecycle row를 복제하거나 이전하지 않음
* `PLACE_ID_EXTERNAL_ID_CONFLICT` 정책 유지
* 기존 `restaurant_id` 기반 API와 meal history 유지

장기적으로 Venue 단위 Detail을 공유하려면 Provider mapping과 Detail의 단일 소유권 계약, 중복 수집 방지, API 표현을 별도 설계해야 한다. 이번 단계에서는 구현하지 않았다.

## 8. 실제 데이터와 MySQL 검증 범위

현재 개발 DB를 읽기 전용으로 확인한 결과:

```text
venues: 0
restaurant_venue_associations: 0
```

따라서 실제 9582/9619 또는 9661/9695에는 어떤 association도 생성되지 않았다.

V21의 FK/UNIQUE 및 Venue association 저장 구조는 기존 격리 MySQL 검증에서 다음을 확인했다.

* Venue와 association 생성
* 동일 Venue에 여러 Restaurant 연결
* 한 Restaurant의 중복 association 차단
* 존재하지 않는 Venue FK 차단
* 기존 Restaurant FK 보존

이번 Phase 2의 서비스 테스트는 Spring/H2에서 PENDING 생성, 명시적 결정, idempotent 반복 결정, 반대 결정 거부를 검증했다. 현재 Integration Harness는 Docker/MySQL로 서비스 health, 인증, API 및 기존 추천 흐름을 통과했다. 다만 실제 운영 DB에 association을 생성하는 테스트는 수행하지 않았다.

## 9. 테스트 결과

| 검증 | 결과 |
|---|---|
| Venue association service tests | PASS |
| Admin endpoint 권한 테스트 | PASS |
| Recommendation Venue dedup test | PASS |
| Backend `./gradlew test` | PASS |
| Backend compile/test/build | PASS |
| AI Harness | 166 passed, 1 warning |
| Integration Harness | PASS |
| `git diff --check` | PASS |
| 외부 Provider/Qwen/NAVER | 실행하지 않음 |
| 전체 Batch | 실행하지 않음 |

추가된 핵심 회귀 테스트는 다음을 다룬다.

* PENDING 생성 후 CONFIRMED 결정
* 동일 결정 재요청 idempotency
* 중복 PENDING 생성 거부
* REJECTED 이후 CONFIRMED 반전 거부
* 미인증/일반 사용자/ADMIN 권한 분리
* CONFIRMED ACTIVE Venue 중복 제거와 미연결 Restaurant 보존

## 10. 실제 데이터 적용 준비 결론

| 그룹 | 결론 | 사용자/업무 승인 |
|---|---|---|
| 9582 / 9619 | 동일 물리 장소 가능성 높음, 업무적 동일 Venue 미확정 | 필요 |
| 9661 / 9695 | 동일 물리 장소 가능성 높음, 업무적 동일 Venue 미확정 | 필요 |

이번 단계에서 두 그룹을 자동 CONFIRMED로 만들면 KOMSCO 자격과 외부 장소 소유권을 혼동할 수 있다. 사용자가 승인하기 전에는 PENDING 검토 자료로만 관리해야 한다.

## 11. 다음 단계와 미완료 사항

1. 승인 대상에 대해 사업자/가맹점 관계와 동일 장소 근거를 별도 확인한다.
2. 승인된 association만 운영 데이터에 명시적으로 생성한다.
3. 기존 Restaurant 기반 Place ID·Detail을 자동 이전하지 않는다.
4. Venue 단위 Detail 공유 또는 신규 저장 계약은 별도 migration/호환성 검증 후 진행한다.
5. Venue 단위 최근 식사 제외 여부를 업무 정책으로 결정한다.
6. association이 운영 데이터에 생성된 뒤 MySQL 추천 Repository와 관리자 API를 실제 association fixture로 재검증한다.

전체 Batch, Provider/Qwen 재실행, Place ID 재연결은 이번 단계의 완료 조건이 아니며 수행하지 않았다.

## 12. Git 및 데이터 보호

* 기존 Flyway migration 수정: 없음
* 운영 Restaurant/Eligibility/Verification/Place ID/Detail 변경: 없음
* 실제 Venue association 생성: 없음
* 기존 가맹점 자동 병합: 없음
* 전체 Batch: 실행하지 않음
* 외부 Provider/Qwen/NAVER: 실행하지 않음
* Git add/commit/push: 하지 않음
* 기존 working tree와 산출물: 보존

이번 단계에서 추가한 소스/테스트 변경은 기존 미커밋 변경과 함께 유지했으며, 다른 변경을 정리하거나 되돌리지 않았다.
