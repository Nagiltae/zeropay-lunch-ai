# 백엔드

ZeroPay Lunch AI의 메인 애플리케이션 백엔드입니다. 외부 요청의 단일 진입점으로서 인증, 비즈니스 규칙, 영속성, 외부 데이터 연동, AI 서버 호출을 담당합니다.

| 항목 | 값 |
| --- | --- |
| 프로젝트 | Gradle - Groovy |
| 언어 | Java |
| Spring Boot | 4.1.1 |
| 그룹 | `com.zeropaylunch` |
| 아티팩트 / 이름 | `backend` |
| 패키지 이름 | `com.zeropaylunch.backend` |
| 패키징 | Jar |
| Java | 21 |

## 의존성

- Spring Web MVC: HTTP API 제공
- Validation: API 요청과 응답 경계의 데이터 검증
- Spring Boot Actuator: 운영 상태 확인
- Spring Data JPA: 도메인 데이터 영속성
- MySQL Connector/J: 운영 및 로컬 MySQL 연결
- H2: 외부 데이터베이스 없이 테스트 컨텍스트 실행

기본 영속성 기술은 Spring Data JPA입니다. QueryDSL은 동적 조건이나 복합 조회를 처음 구현할 때 추가합니다.

## 채팅 API

React는 다음 API에 사용자 메시지를 보내고 POST 응답을 SSE 스트림으로 읽습니다.

```http
POST /api/conversations/{conversationId}/messages
Accept: text/event-stream
Content-Type: application/json
```

현재는 SSE 연결 검증을 위한 안내형 응답을 전송합니다. 대화 영속화, FastAPI 호출, 음식점 추천은 이후 단계에서 구현합니다. 이벤트별 계약은 `docs/api-contract.md`를 참고하세요.

## 실행

직접 실행할 때는 저장소 루트에서 MySQL과 Qdrant를 먼저 시작합니다.

```bash
cd ..
docker compose up -d mysql qdrant
cd backend
./gradlew bootRun
```

기본 서버 주소는 `http://localhost:8080`이며, 운영 상태는 `GET /actuator/health`에서 확인할 수 있습니다. 기본 데이터베이스 접속값은 루트 `.env.example` 및 `docker-compose.yml`과 일치합니다. 필요하면 `SPRING_DATASOURCE_URL`, `SPRING_DATASOURCE_USERNAME`, `SPRING_DATASOURCE_PASSWORD` 환경 변수로 재정의할 수 있습니다.

전체 통합 환경에서는 루트의 `docker compose up --build -d` 명령으로 실행합니다. 이때 백엔드는 Compose 내부의 `mysql:3306`과 `ai:8001`을 사용합니다.

## 검증

```bash
./gradlew test
./gradlew build
```
