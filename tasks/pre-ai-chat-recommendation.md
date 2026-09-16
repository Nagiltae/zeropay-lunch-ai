# Task: FastAPI 이전 채팅 추천 기반 구축

## Status

완료. 이 문서는 구현 당시 범위를 보존한 실행 명세이며 현재 상태는 `README.md`와 관련 `docs/`를 기준으로 확인합니다.

## Goal

FastAPI 없이도 React와 Spring Boot가 강남구 위치, MySQL 대화 기록, 영업 중인 샘플 음식점 데이터를 이용해 결정론적인 추천 흐름을 제공하도록 합니다.

## Background

작성 당시에는 React와 Spring Boot 사이의 POST SSE 연결만 구현되어 있었고 대화, 메시지, 음식점은 영속화하지 않았습니다. 현재는 이 task의 범위가 구현되었으며 실제 음식점 데이터를 적재하기 전까지 승인된 가상 음식점 3개를 local과 dev 환경에서만 사용합니다.

## In scope

- Spring Boot 설정을 properties에서 YAML과 local/dev/prod 프로필로 전환
- Flyway 기반 MySQL 스키마
- 대화 활성 상태와 메시지 영속화
- 강남구 기준 위치 검증
- 음식점, 영업 요일·시간, 휴무 요일·시간 저장과 현재 영업 중 조회
- 승인된 샘플 음식점 3개를 local/dev 프로필에 삽입
- 임시 결정론적 키워드 분석과 음식점 추천
- 구조화된 SSE 추천 이벤트
- React 대화 생성·초기화·기록 조회와 추천 카드
- 관련 자동 테스트와 통합 검증

## Out of scope

- FastAPI 호출과 AI 자연어 분석
- LLM, 임베딩, Qdrant 검색
- 실제 음식점 데이터 수집 또는 적재
- 인증과 사용자 계정
- MongoDB 도입
- 공휴일과 특정 날짜의 임시 영업 일정

## Functional requirements

1. 대화는 생성 시 `active=true`이며 초기화 또는 위치 변경 시 `active=false`가 됩니다.
2. 위치가 바뀌면 기존 대화를 비활성화하고 새 대화를 사용합니다.
3. 대화와 메시지 식별자는 향후 저장소 교체를 고려해 UUID를 사용합니다.
4. 메시지는 USER와 ASSISTANT 역할 및 처리 상태와 함께 저장합니다.
5. 지원 위치는 서울특별시 강남구 프리셋으로 제한합니다.
6. 음식점의 영업 요일, 영업시간, 휴무 요일, 휴무시간은 분리해 저장합니다.
7. `Asia/Seoul` 현재 시각이 영업시간에 포함되고 휴무시간에는 포함되지 않는 음식점만 조회합니다.
8. local/dev에서만 승인된 샘플 음식점 3개를 중복 없이 삽입합니다.
9. Spring Boot가 키워드를 제한적으로 해석하고 필터와 최종 순위를 결정합니다.
10. 추천 결과와 assistant 메시지는 대화 기록에서 복구할 수 있어야 합니다.

## API contract

- 대화 생성, 비활성화, 메시지 기록 조회 API를 추가합니다.
- 메시지 SSE에 구조화된 `recommendations` 이벤트를 추가합니다.
- 상세 계약은 구현과 함께 `docs/api-contract.md`에 기록합니다.

## Data model impact

- `conversations`
- `chat_messages`
- `restaurants`
- `restaurant_schedules`
- `restaurant_operating_days`
- `restaurant_operating_hours`
- `restaurant_closed_days`
- `restaurant_closed_hours`
- `message_recommendations`

MySQL이 기준 저장소입니다. MongoDB는 이번에 추가하지 않으며 애플리케이션 서비스와 저장소 접근을 분리해 이후 전환 범위를 제한합니다.

## Architecture constraints

- React는 Spring Boot만 호출합니다.
- 결정론적 필터와 순위는 Spring Boot와 MySQL이 담당합니다.
- FastAPI를 호출하거나 모방하지 않습니다.
- 샘플 데이터는 prod 프로필에 삽입하지 않습니다.
- 프로필 YAML에 비밀번호와 운영 자격 증명을 기록하지 않습니다.

## Acceptance criteria

1. local, dev, prod 프로필이 각각 의도한 호스트와 환경변수 정책을 가집니다.
2. 승인된 샘플 데이터가 local/dev에서만 생성됩니다.
3. 영업시간 및 휴무시간을 고려한 조회가 테스트됩니다.
4. 대화 초기화와 위치 변경이 기존 대화를 비활성화합니다.
5. React가 서버 대화 기록과 추천 결과를 표시합니다.
6. 관련 서비스 검사와 전체 검사가 통과합니다.

## Verification

- `./scripts/check-backend.sh`
- `./scripts/check-frontend.sh`
- `./scripts/check-lint.sh`
- `./scripts/check-integration.sh`
- `./scripts/check-all.sh`

## Documentation updates

- `docs/api-contract.md`
- `docs/database.md`
- `docs/architecture.md`
- `docs/testing.md`
- `docs/deployment.md`
- `README.md`
