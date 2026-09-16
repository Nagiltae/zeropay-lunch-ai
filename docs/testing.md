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
| `./scripts/check-integration.sh` | Docker health와 현재 구현된 Nginx→Spring SSE 흐름 |
| `./scripts/check-all.sh` | 위 검사의 canonical 전체 실행 |

프런트엔드에는 아직 테스트 명령이 없습니다. `check-frontend.sh`는 이를 `[SKIP]`으로 명시하며 테스트가 통과했다고 보고하지 않습니다.

## Progressive integration levels

통합 검사는 실제 기능이 존재하는 단계까지만 확장합니다.

### Level 1 — service health and current public flow

현재 구현되어 있습니다.

- Docker Compose 구성 검증
- MySQL과 Qdrant를 포함한 컨테이너 health 대기
- Nginx `/healthz`
- Spring Boot `/actuator/health`
- FastAPI `/health`
- Nginx `/api/` 프록시를 통한 Spring Boot SSE 이벤트 완료

`check-integration.sh`는 전체 이미지를 조용한 출력으로 빌드한 뒤 `docker compose up -d --wait`로 스택을 기동합니다. 검사 후 컨테이너와 볼륨을 삭제하지 않습니다. 실패 시 `docker compose ps`와 관련 서비스의 최근 로그를 출력합니다.

### Level 2 — backend dependencies

다음 기능이 구현될 때 추가합니다.

- Spring Boot가 MySQL에 실제 엔티티를 저장하고 조회
- FastAPI가 Qdrant 컬렉션을 생성하거나 검색

단순히 컨테이너 포트가 열렸다는 검사로 이 단계를 통과했다고 판단하지 않습니다.

### Level 3 — service-to-service

Spring Boot가 실제 FastAPI 내부 API를 호출하는 기능이 생길 때 다음을 검증합니다.

- Spring Boot 요청이 FastAPI 계약에 맞게 전달됨
- FastAPI 오류와 잘못된 응답을 Spring Boot가 검증하고 변환함
- 타임아웃 또는 연결 실패 처리

현재 `AI_BASE_URL` 환경변수만 있고 실제 호출 코드는 없으므로 이 단계의 검사는 만들지 않습니다.

### Level 4 — user flow

대화와 추천 기능이 구현되는 순서에 맞춰 확장합니다.

1. 대화 생성
2. 사용자 메시지 전송
3. SSE 답변 수신
4. 사용자 및 assistant 메시지 저장
5. 대화 기록 조회
6. 강남구 음식점 추천 결과 검증

브라우저 자동화나 대규모 E2E 도구는 이 흐름이 안정된 뒤 실제 필요가 있을 때만 추가합니다.

## Failure handling

- 실패한 명령의 출력과 컨테이너 로그를 먼저 확인합니다.
- 테스트를 삭제하거나 검증을 약화해 통과시키지 않습니다.
- 외부 런타임 부족으로 실행하지 못한 검사는 `[PASS]`로 보고하지 않습니다.
- 통합 실패 후 데이터 보존을 위해 자동으로 `docker compose down -v`를 실행하지 않습니다.
