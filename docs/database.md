# 데이터베이스

> **Harness Role:** MySQL 데이터 소유권, 현재 테이블, Flyway 규칙과 샘플 데이터 정책의 기준입니다. Agent는 엔티티나 스키마를 바꾸기 전에 읽습니다. 이 문서가 없으면 적용된 migration을 수정하거나 prod에 샘플 데이터를 넣는 실수가 생길 수 있습니다. `AGENTS.md`의 migration guardrail, 실제 `db/migration`, 백엔드 및 Docker 통합 검사와 연결됩니다.

## 현재 결정 사항

MySQL을 애플리케이션의 기준 저장소로 사용합니다. Docker Compose에 로컬 MySQL 8.4 서비스를 정의해 두었습니다.

서비스 대상 음식점은 서울특별시 강남구 소재로 제한합니다. 음식점 데이터 적재 시 행정구역과 위치 좌표를 검증하고, 애플리케이션 조회에서도 강남구 조건을 강제해야 합니다. 구체적인 주소 필드, 좌표 형식, 경계 판정 방식은 음식점 스키마를 설계할 때 확정합니다.

벡터 데이터베이스는 Qdrant를 사용합니다. 로컬 개발과 통합 테스트에서는 Docker Compose가 Qdrant 1.19.1 컨테이너와 영속 볼륨을 생성합니다. 컬렉션 구조, 벡터 차원, 거리 함수는 임베딩 모델을 선택할 때 결정합니다.

영속성 기술은 Spring Data JPA를 사용합니다. 단순 조회는 Spring Data 저장소 기능으로 구현하고, 동적 조건이나 복합 조회가 필요해지는 시점에 QueryDSL을 추가합니다. 사용 코드가 생기기 전에는 QueryDSL 의존성과 생성 설정을 미리 추가하지 않습니다.

스키마는 Flyway가 `backend/src/main/resources/db/migration`에서 관리합니다. JPA는 실행 시 Flyway가 만든 스키마와 엔티티 매핑을 검증하며 운영 스키마를 자동 생성하지 않습니다.

## Migration 규칙

- versioned migration은 적용 후 수정하지 않습니다. 현재 `V1`, `V2`, `V3`는 불변입니다.
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
| `restaurants` | 강남구 음식점 기준 정보와 샘플 여부 |
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

제로페이는 사용자 취향 옵션이 아니라 모든 후보 조회에서 강제되는 서비스 정책입니다. 현재 비선호 카테고리와 최근 72시간 내 먹은 음식점도 애플리케이션 계층에서 제외합니다.

현재 스키마는 시작 시각보다 종료 시각이 늦은 당일 영업 구간을 지원합니다. 자정을 넘기는 영업시간과 특정 공휴일 예외는 실제 데이터 계약을 정할 때 별도 일정으로 확장합니다.

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
