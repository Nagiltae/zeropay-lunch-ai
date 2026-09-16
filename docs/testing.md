# 검증 및 통합 테스트 전략

## 목적

검증은 코드를 작성했다는 사실이 아니라 관찰 가능한 동작을 기준으로 완료 여부를 판단하기 위해 사용합니다. 가장 좁은 대상 검사를 먼저 실행하고, 여러 서비스나 실행 환경에 영향을 주는 변경은 `./scripts/check-all.sh`로 최종 확인합니다.

## 검사 진입점

| 명령 | 범위 |
| --- | --- |
| `./scripts/check-format.sh` | Git 공백 오류, AI Ruff 포맷 |
| `./scripts/check-lint.sh` | React ESLint, AI Ruff lint |
| `./scripts/check-frontend.sh` | npm 의존성 상태, TypeScript를 포함한 프로덕션 빌드, 존재하는 경우 테스트 |
| `./scripts/check-backend.sh` | Gradle compile, 테스트, 패키징 |
| `./scripts/check-ai.sh` | Poetry 메타데이터, FastAPI import, Pytest |
| `./scripts/check-integration.sh` | Docker health, 인증·세션·대화 소유권과 Nginx→Spring SSE 흐름 |
| `./scripts/check-all.sh` | 위 검사의 canonical 전체 실행 |

프런트엔드는 Vitest로 인증 API의 CSRF 헤더와 401 처리, 취향·식사 기록 요청, 대화 생성 요청, 청크 경계가 나뉜 SSE 추천 이벤트 파싱을 검증합니다. 컴포넌트 브라우저 테스트는 아직 없습니다.

## Progressive integration levels

통합 검사는 실제 기능이 존재하는 단계까지만 확장합니다.

### Level 1 — service health and current authenticated flow

현재 구현되어 있습니다.

- Docker Compose 구성 검증
- MySQL과 Qdrant를 포함한 컨테이너 health 대기
- Nginx `/healthz`
- Spring Boot `/actuator/health`
- FastAPI `/health`
- Nginx `/api/` 프록시를 통한 회원가입·로그인·현재 사용자 조회
- 인증된 대화 생성과 Spring Boot SSE 이벤트 완료

`check-integration.sh`는 전체 이미지를 조용한 출력으로 빌드한 뒤 `docker compose up -d --wait`로 스택을 기동합니다. 검사 후 컨테이너와 볼륨을 삭제하지 않습니다. 실패 시 `docker compose ps`와 관련 서비스의 최근 로그를 출력합니다.

### Level 2 — backend dependencies

MySQL 대화 흐름은 현재 구현되어 있습니다.

- Flyway가 실제 MySQL에 공통 스키마와 dev 샘플 데이터를 적용
- 사용자 취향 저장과 고정 제로페이 정책 확인
- 추천 메시지에 연결된 식사 기록의 명시적·멱등 저장과 최근 조회
- Spring Boot가 대화, 메시지와 추천 결과를 저장하고 조회
- 대화 비활성화 후 `active=false` 확인
- 영업시간과 휴무시간 native query를 H2와 실제 MySQL 흐름에서 검증

FastAPI가 Qdrant 컬렉션을 생성하거나 검색하는 검사는 아직 구현되지 않았습니다.

단순히 컨테이너 포트가 열렸다는 검사로 이 단계를 통과했다고 판단하지 않습니다.

### Level 3 — service-to-service

Spring Boot가 실제 FastAPI 내부 API를 호출하는 기능이 생길 때 다음을 검증합니다.

- Spring Boot 요청이 FastAPI 계약에 맞게 전달됨
- FastAPI 오류와 잘못된 응답을 Spring Boot가 검증하고 변환함
- 타임아웃 또는 연결 실패 처리

현재 `AI_BASE_URL` 환경변수만 있고 실제 호출 코드는 없으므로 이 단계의 검사는 만들지 않습니다.

### Level 4 — user flow

대화와 추천 기능이 구현되는 순서에 맞춰 확장합니다.

현재 Docker 통합 검사에는 다음 사용자 흐름의 서버/API 부분이 포함됩니다.

1. 회원가입과 로그인
2. 세션 쿠키 발급과 현재 사용자 조회
3. 인증된 대화 생성과 MySQL `user_id` 저장 확인
4. 다른 사용자의 대화 조회 및 메시지 전송 거부
5. 사용자 메시지 전송
6. 구조화된 추천 및 SSE 답변 수신
7. USER 및 ASSISTANT 메시지 저장
8. 추천 결과가 포함된 대화 기록 조회
9. 대화 비활성화
10. 로그아웃 후 인증 API 및 대화 접근 거부

백엔드 자동 테스트는 취향 충돌 검증, 최근 72시간 식사 범위, 다른 사용자의 추천 기록 차단, 제로페이 불가 음식점 제외, 기본 예산·비선호·최근 식사 필터와 AI 분석 fallback을 포함합니다.

브라우저 자동화와 실제 AI 추천 결과 검증은 아직 포함하지 않습니다.

브라우저 자동화나 대규모 E2E 도구는 이 흐름이 안정된 뒤 실제 필요가 있을 때만 추가합니다.

## Failure handling

- 실패한 명령의 출력과 컨테이너 로그를 먼저 확인합니다.
- 테스트를 삭제하거나 검증을 약화해 통과시키지 않습니다.
- 외부 런타임 부족으로 실행하지 못한 검사는 `[PASS]`로 보고하지 않습니다.
- 통합 실패 후 데이터 보존을 위해 자동으로 `docker compose down -v`를 실행하지 않습니다.
