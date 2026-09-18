# 데이터베이스

> **Harness Role:** MySQL 데이터 소유권, 현재 테이블, Flyway 규칙과 샘플 데이터 정책의 기준입니다. Agent는 엔티티나 스키마를 바꾸기 전에 읽습니다. 이 문서가 없으면 적용된 migration을 수정하거나 prod에 샘플 데이터를 넣는 실수가 생길 수 있습니다. `AGENTS.md`의 migration guardrail, 실제 `db/migration`, 백엔드 및 Docker 통합 검사와 연결됩니다.

## 현재 결정 사항

MySQL을 애플리케이션의 기준 저장소로 사용합니다. Docker Compose에 로컬 MySQL 8.4 서비스를 정의해 두었습니다.

서비스 대상 음식점은 서울특별시 강남구 소재로 제한합니다. 음식점 데이터 적재 시 행정구역과 위치 좌표를 검증하고, 애플리케이션 조회에서도 강남구 조건을 강제해야 합니다. 구체적인 주소 필드, 좌표 형식, 경계 판정 방식은 음식점 스키마를 설계할 때 확정합니다.

벡터 데이터베이스는 Qdrant를 사용합니다. 로컬 개발과 통합 테스트에서는 Docker Compose가 Qdrant 1.19.1 컨테이너와 영속 볼륨을 생성합니다. 컬렉션 구조, 벡터 차원, 거리 함수는 임베딩 모델을 선택할 때 결정합니다.

영속성 기술은 Spring Data JPA를 사용합니다. 단순 조회는 Spring Data 저장소 기능으로 구현하고, 동적 조건이나 복합 조회가 필요해지는 시점에 QueryDSL을 추가합니다. 사용 코드가 생기기 전에는 QueryDSL 의존성과 생성 설정을 미리 추가하지 않습니다.

스키마는 Flyway가 `backend/src/main/resources/db/migration`에서 관리합니다. JPA는 실행 시 Flyway가 만든 스키마와 엔티티 매핑을 검증하며 운영 스키마를 자동 생성하지 않습니다.

## Migration 규칙

- versioned migration은 적용 후 수정하지 않습니다. 현재 `V1`, `V2`, `V3`, `V4`, `V5`, `V6`, `V7`는 불변입니다.
- 스키마 변경은 항상 다음 번호의 새 `V<n>__<description>.sql` 파일로 순방향 적용합니다.
- 이미 배포된 migration의 오류도 과거 파일을 고치지 않고 새 migration에서 보완합니다.
- `db/sample`의 repeatable migration은 local/dev 데이터용이며 스키마 변경에 사용하지 않습니다.
- DB 변경은 H2 기반 백엔드 테스트와 실제 MySQL Docker 통합 검사를 모두 확인합니다.

## 현재 테이블

| 테이블 | 역할 |
| --- | --- |
| `users` | 사용자 계정, 이메일, 활성/정지/탈퇴 상태, 권한, 생성일, 최종 로그인 일시 (UUID PK) |
| `user_credentials` | BCrypt 비밀번호 해시, 비밀번호 변경 일시, 로그인 실패 횟수, 계정 잠금 일시 (`users` 1:1 FK) |
| `SPRING_SESSION` | Spring Session JDBC가 사용하는 세션 저장 테이블 (Flyway 관리) |
| `SPRING_SESSION_ATTRIBUTES` | Spring Session 속성 저장 테이블 |
| `conversations` | UUID, 사용자(user_id) 연결, 기준 위치, 활성 여부, 생성·수정·비활성 시각 |
| `chat_messages` | 대화별 USER/ASSISTANT 메시지와 처리 상태 |
| `restaurants` | 강남구 음식점, 추천용 보강 정보, KOMSCO 원본 출처와 동기화 상태 |
| `restaurant_external_places` | 음식점별 외부 검색 제공자의 보강 필드와 매칭 판정·동기화 시각 |
| `restaurant_schedules` | 같은 요일·시간 정책을 묶는 영업 일정 |
| `restaurant_operating_days` | 일정별 영업 요일 |
| `restaurant_operating_hours` | 일정별 영업 시작·종료 시각 |
| `restaurant_closed_days` | 음식점별 정기 휴무 요일 |
| `restaurant_closed_hours` | 일정별 하루 중 휴무시간 또는 브레이크타임 |
| `message_recommendations` | assistant 메시지와 추천 음식점, 순위, 이유 연결 |
| `user_preferences` | 사용자 기본 예산과 매운맛 선호 |
| `user_preferred_categories` | 사용자 선호 음식 카테고리 |
| `user_disliked_categories` | 사용자 비선호 음식 카테고리 |
| `user_allergies` | AI 컨텍스트용 사용자 알레르기 정보 |
| `meal_history` | 사용자가 `먹었어요`로 확정한 식사와 원본 추천 메시지 |

대화 초기화와 위치 변경은 데이터를 삭제하지 않습니다. `conversations.active`를 `false`로 바꾸고 `deactivated_at`을 기록합니다. UUID를 사용하고 영속성 접근을 애플리케이션 서비스에 모아 두어 향후 채팅 기록을 MongoDB로 이전할 때 API와 추천 로직에 미치는 영향을 제한합니다. MongoDB 의존성과 이중 저장은 아직 추가하지 않았습니다.

`conversations.user_id`는 기존 데이터와 마이그레이션 호환성을 위해 DB에서는 nullable이지만, 현재 애플리케이션의 대화 생성 API는 로그인을 요구하고 항상 사용자 ID를 저장합니다. 조회, 메시지 전송과 비활성화도 같은 사용자 ID로 소유권을 검증합니다.

`meal_history`는 사용자가 명시적으로 `먹었어요`를 누른 경우에만 생성합니다. `(user_id, source_message_id, restaurant_id)` unique 제약으로 같은 추천에 대한 중복 기록을 막습니다. 추천 컨텍스트에서는 `eaten_at`이 현재 시각 기준 72시간 이내인 기록만 사용하며, 오래된 기록을 삭제하지는 않습니다.

## 영업 중 조회

시간 기준은 `Asia/Seoul`입니다. 음식점은 다음 조건을 모두 만족할 때만 조회됩니다.

1. 현재 요일이 `restaurant_operating_days`에 있음
2. 현재 시각이 `restaurant_operating_hours` 범위에 있음
3. 현재 요일이 `restaurant_closed_days`에 없음
4. 현재 시각이 `restaurant_closed_hours` 범위에 없음
5. `restaurants.zero_pay_available=true`
6. `restaurants.recommendation_ready=true`
7. `restaurants.recommendation_eligibility='ELIGIBLE'`

제로페이는 사용자 취향 옵션이 아니라 모든 후보 조회에서 강제되는 서비스 정책입니다. 현재 비선호 카테고리와 최근 72시간 내 먹은 음식점도 애플리케이션 계층에서 제외합니다.

현재 스키마는 시작 시각보다 종료 시각이 늦은 당일 영업 구간을 지원합니다. 자정을 넘기는 영업시간과 특정 공휴일 예외는 실제 데이터 계약을 정할 때 별도 일정으로 확장합니다.

## KOMSCO 음식점 원본

Flyway `V4__add_komsco_restaurant_source_fields.sql`은 기존 V1~V3를 변경하지 않고 `restaurants`에 다음 책임을 추가합니다.

- 외부 식별과 출처: `external_merchant_id`, `source_provider`, `source_reference_date`, `last_synced_at`
- 원본 주소: `detail_address`, `postal_code`, `legal_dong_code`, `legal_dong_name`
- 원본 업종·상태: `industry_code`, `industry_name`, `provider_institution_code`, `business_status_code`, `business_status_name`
- 추천 경계: `recommendation_ready`

`(source_provider, external_merchant_id)` unique 제약이 같은 KOMSCO `alt_text`의 중복 행을 막습니다. import는 전체 응답에서 `alt_text`별 가장 최신 `crtr_ymd`를 먼저 선택한 다음 `I0000002`, `ksic_cd=561`, `bzmn_stts_nm=계속사업자`, 강남구 조건을 적용합니다. 더 최신 기준일자는 갱신하고, 같은 기준일자는 실제 원본 필드가 달라졌을 때만 갱신하며, 더 오래된 기준일자는 무시합니다.

기존 `category`, `representative_menu`, `average_price`, `location_id`는 추천용 보강 데이터이며 KOMSCO가 제공하지 않으므로 nullable입니다. KOMSCO import 행은 `zero_pay_available=true`, `recommendation_ready=false`로 저장됩니다. 영업시간이 보강되기 전에는 실제 현재 영업 중 여부를 판정할 수 없고 추천 조회에도 들어가지 않습니다.

기본 import는 API 실패나 snapshot에 없는 행을 이유로 기존 데이터를 삭제하지 않는 upsert 방식입니다. 명시적으로 `KOMSCO_REPLACE_EXISTING=true`를 지정한 전체 snapshot 교체는 모든 페이지 조회·정제 성공 후 하나의 트랜잭션에서 KOMSCO 행만 삭제하고 필터 결과를 재삽입합니다. 삭제나 삽입이 실패하면 전체 교체를 롤백하며 샘플 및 다른 출처의 음식점은 삭제하지 않습니다.

매일 새벽 3시 동기화는 전체 snapshot에서 `alt_text`별 최신 행을 선택한 뒤 기존 KOMSCO 행과 비교합니다. 신규 행은 계속사업자·KSIC 561·강남구·제공기관 조건을 모두 만족할 때만 삽입합니다. 기존 행은 같은 기준일자여도 `last_synced_at`과 `updated_at`을 갱신합니다. 최신 상태가 계속사업자가 아니거나 나머지 저장 조건에서 벗어나면 삭제하지 않고 `active=false`로 전환하며, 이후 조건을 다시 만족하면 `active=true`로 복구합니다. 응답 snapshot에서 완전히 사라진 ID는 자동 비활성화하지 않습니다.

## NAVER Local 보강

Flyway `V5__create_restaurant_external_places.sql`은 KOMSCO 원본과 외부 검색 결과의 책임을 분리하기 위해 `restaurant_external_places`를 추가합니다. `(restaurant_id, provider)` unique 제약으로 음식점마다 `NAVER` 행을 하나만 유지하며 반복 실행은 insert가 아니라 update가 됩니다. 음식점 삭제 시 보강 행만 함께 정리되도록 FK에 cascade를 적용하며 반대 방향으로 NAVER 데이터가 `restaurants`를 변경하지는 않습니다.

Flyway `V6__add_naver_matching_lifecycle.sql`은 `name_score`, `address_score`, `distance_score`, `category_score`, `runner_up_score`, `score_gap`을 추가해 판정 근거를 보존합니다. `source_content_hash`는 상호·주소·상세주소·좌표·법정동처럼 매칭에 영향을 주는 KOMSCO 필드만 반영합니다. `last_attempt_status`, `last_match_attempt_at`, `next_retry_at`은 매칭 결과와 API 장애를 분리하고 상태별 재시도 및 refresh TTL을 지원합니다. 기존 정상 매칭 뒤 API가 실패하면 NAVER 후보와 `match_status`/`last_synced_at`은 유지하고 마지막 시도 정보만 갱신합니다.

보강 행은 NAVER 상호·분류·설명·링크·지번/도로명 주소·WGS84 좌표와 판정·검색어·시각만 저장합니다. API가 좌표를 `10^7` 배율 정수 문자열로 반환하는 경우 소수점 도 단위로 변환하며 이미 소수점인 값도 허용합니다. 안정적인 NAVER Place ID가 응답에 없으므로 임의 식별자를 만들지 않고 raw JSON 전체도 저장하지 않습니다. `UNMATCHED`도 상태와 검색어를 저장하고, `AMBIGUOUS`는 가장 높은 후보와 점수를 남겨 후속 검토가 가능하게 합니다. KOMSCO의 제로페이 여부, 상호, 주소, 좌표와 외부 가맹점 ID는 NAVER 값으로 덮어쓰지 않습니다.

Flyway `V7__add_restaurant_recommendation_eligibility.sql`은 추천 조회용 파생 상태를 `restaurants.recommendation_eligibility`에 추가합니다. 기본값은 `UNKNOWN`이며 기존·신규 KOMSCO, 미조회, AMBIGUOUS, UNMATCHED, API_ERROR와 category 불명은 UNKNOWN입니다. MATCHED이면서 음식점 category면 ELIGIBLE, MATCHED이면서 명확한 비음식점 category면 INELIGIBLE입니다. KOMSCO의 상호·주소·좌표 등 매칭 입력이 변경되면 과거 판정을 신뢰하지 않고 UNKNOWN으로 되돌립니다. local/dev sample은 외부 조회 없이 사용하는 승인된 fixture이므로 ELIGIBLE로 저장합니다.

## 개발용 샘플 데이터

`local`과 `dev` 프로필은 `backend/src/main/resources/db/sample`의 repeatable migration을 추가로 실행합니다. `prod`는 이 경로를 읽지 않습니다.

| 음식점 | 영업 요일·시간 | 휴무 요일 | 휴무시간 |
| --- | --- | --- | --- |
| 강남 샘플 한식당 | 월~금 11:00~21:00 | 토·일 | 15:00~17:00 |
| 역삼 샘플 국밥집 | 매일 00:00~23:59:59 | 없음 | 없음 |
| 선릉 샘플 샐러드 | 월~토 10:30~20:30 | 일 | 15:00~16:00 |

샘플 데이터는 고정 식별자와 존재 여부 조건을 사용해 중복 삽입하지 않습니다.
선릉 샘플 샐러드는 `zero_pay_available=false`이므로 데이터·조회 검증에는 남아 있지만 실제 추천 후보에서는 항상 제외됩니다.

운영 및 로컬 실행은 MySQL Connector/J를 사용합니다. 테스트에서는 H2 MySQL 모드에서 동일한 Flyway 기준 스키마와 JPA 매핑을 검증합니다. Docker 통합 검사는 실제 MySQL에 스키마와 샘플 데이터를 적용하고 대화 저장·조회까지 확인합니다.

외부 API 페이로드와 애플리케이션 소유 데이터는 구분할 수 있어야 합니다. 파생된 벡터 임베딩은 음식점의 기준 데이터로 취급하지 않습니다.

Qdrant에는 MySQL 데이터에서 다시 생성할 수 있는 임베딩과 검색용 메타데이터만 저장합니다. 사용자, 음식점, 취향, 식사 기록의 기준 데이터는 계속 MySQL이 소유합니다.
