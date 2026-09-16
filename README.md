# ZeroPay Lunch AI

ZeroPay Lunch AI는 자연어 요청, 사용자 취향, 예산, 최근 식사 기록, 위치, 상황 정보를 바탕으로 주변 음식점을 추천합니다.

이 서비스는 모노레포 구조를 사용하며, Spring Boot를 애플리케이션의 단일 진입점으로 둡니다.

```text
React -> Spring Boot -> FastAPI
```

## 현재 상태

현재 이 저장소는 FastAPI의 실제 AI 기능을 연결하기 전에 필요한 인증, 대화 영속화와 개인화 추천 기반까지 구현한 상태입니다.

| 영역 | 상태 |
| --- | --- |
| 프런트엔드 | 세션 인증, React Query 대화·취향·최근 식사 상태, POST SSE, 추천 카드와 `먹었어요` 흐름 구현 완료 |
| 메인 백엔드 | 인증·Spring Session JDBC, 대화·취향·식사 기록 영속화, 제로페이·영업시간·개인화 필터와 샘플 추천 SSE 구현 완료 |
| AI 서버 | 최소 구성의 FastAPI 상태 확인 엔드포인트와 테스트 작성 완료 |
| MySQL | Flyway V1~V3 스키마와 local/dev 샘플 음식점 3개 적용 |
| Qdrant | 로컬 Docker Compose 서비스만 정의, AI 검색 연동 대기 중 |
| Spring→FastAPI | 내부 의도 분석 계약과 fallback 경계만 준비, 실제 HTTP 클라이언트는 미구현 |
| API 계약 및 아키텍처 | 현재 구현과 계획 범위를 `docs/`에 구분해 기록 |

## 저장소 구조

```text
zeropay-lunch-ai/
├── frontend/    # React 애플리케이션
├── backend/     # Spring Boot 애플리케이션
├── ai/          # FastAPI AI 서버
├── docs/        # 아키텍처 및 계약 문서
├── tasks/       # 비자명 작업의 실행 명세와 템플릿
└── scripts/     # 로컬 검증 명령어
```

Agent가 이 저장소에서 규칙을 읽고 구현을 검증하는 전체 구조를 공부하려면 `docs/harness-study.md`를 먼저 참고하세요.

## 필수 도구

- Docker와 Docker Compose v2
- Java 21 이상
- Node.js 20.19 이상과 npm
- Python 3.11~3.13
- Poetry 2.x

`setup.sh`는 도구가 없을 때 운영체제 패키지를 자동 설치하지 않으며 필요한 조치를 출력하고 실패합니다.

## Quick start

저장소 루트에서 다음 순서로 실행합니다.

```bash
test -f .env || cp .env.example .env
./scripts/setup.sh
docker compose up --build -d --wait
docker compose ps
```

`setup.sh`는 잠금 파일을 사용해 프로젝트 의존성을 준비하고 현재 필수 저장소인 MySQL이 정상 상태가 될 때까지 기다립니다. `docker compose up`은 React, Spring Boot, FastAPI, MySQL과 향후 검색용 Qdrant를 실행하지만 아직 연결되지 않은 FastAPI와 Qdrant는 Spring Boot의 시작 조건이 아닙니다.

| 서비스 | 로컬 주소 |
| --- | --- |
| React | `http://localhost:3000` |
| Spring Boot 상태 확인 | `http://localhost:8080/actuator/health` |
| FastAPI 상태 확인 | `http://localhost:8001/health` |
| Qdrant 대시보드 | `http://localhost:6333/dashboard` |
| MySQL | `localhost:3306` |

전체 검증은 Docker 엔진이 실행 중인 상태에서 수행합니다.

```bash
./scripts/check-all.sh
```

검증은 변경 파일 공백, 린트, 서비스별 빌드와 테스트, Docker health 및 인증→취향→Nginx→Spring Boot SSE→식사 기록 흐름을 확인합니다. 자세한 단계는 `docs/testing.md`를 참고하세요.

컨테이너를 중지할 때는 다음 명령을 사용합니다.

```bash
docker compose down
```

이 명령은 `mysql-data`와 `qdrant-data` 볼륨을 삭제하지 않습니다. `docker compose down -v`는 로컬 데이터를 삭제하므로 주의합니다.

## 런타임을 직접 실행하는 개발 방식

애플리케이션 코드를 각 런타임에서 직접 실행하고 데이터 저장소만 Docker로 유지할 수 있습니다. 먼저 `./scripts/setup.sh`를 한 번 실행한 뒤 사용합니다.

터미널 1:

```bash
docker compose up -d --wait mysql qdrant
```

터미널 2에서는 루트 `.env`의 로컬 값을 환경변수로 전달합니다. `.env` 자체는 Spring Boot가 자동으로 읽지 않습니다.

```bash
cd backend
SPRING_PROFILES_ACTIVE=local \
MYSQL_USER=zeropay \
MYSQL_PASSWORD=zeropay_local \
./gradlew bootRun
```

터미널 3:

```bash
cd ai
poetry run uvicorn app.main:app --reload --port 8001
```

터미널 4:

```bash
cd frontend
npm run dev
```

Vite는 `/api` 요청을 `http://localhost:8080`의 Spring Boot로 전달합니다.

Docker Compose의 Spring Boot는 `dev` 프로필을 사용합니다. `local`과 `dev`에는 승인된 가상 음식점 3개가 중복 없이 삽입되고, `prod`에는 샘플 데이터가 삽입되지 않습니다. 프로필별 상세 설정은 `docs/deployment.md`, 테이블과 샘플 데이터는 `docs/database.md`를 참고하세요.

## 검사 명령

각 스크립트는 호출 위치와 무관하게 저장소 루트를 계산합니다.

```bash
./scripts/check-format.sh
./scripts/check-lint.sh
./scripts/check-frontend.sh
./scripts/check-backend.sh
./scripts/check-ai.sh
./scripts/check-integration.sh
./scripts/check-all.sh
```

백엔드 세부사항은 `backend/README.md`, Docker 및 향후 EC2 방향은 `docs/deployment.md`, 검증 정책은 `docs/testing.md`를 참고하세요.
