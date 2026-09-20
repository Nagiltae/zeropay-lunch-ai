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
- Flyway: 프로필별 스키마 migration과 local/dev 샘플 데이터 관리

기본 영속성 기술은 Spring Data JPA입니다. QueryDSL은 동적 조건이나 복합 조회를 처음 구현할 때 추가합니다.

## 채팅 API

React는 다음 API에 사용자 메시지를 보내고 POST 응답을 SSE 스트림으로 읽습니다.

```http
POST /api/conversations/{conversationId}/messages
Accept: text/event-stream
Content-Type: application/json
```

Spring Boot는 세션 인증과 대화 소유권을 처리하고 대화, 메시지, 사용자 취향과 명시적인 식사 기록을 MySQL에 저장합니다. 추천에서는 현재 영업 중이고 제로페이가 가능한 개발용 샘플 음식점에 예산, 비선호 카테고리와 최근 72시간 식사 기록을 결정론적으로 적용합니다. KOMSCO 실제 가맹점 원본을 수동 적재하고 NAVER Local 검색 결과를 별도 테이블에 보강할 수 있지만 메뉴·가격·영업시간 보강 전에는 추천 후보에서 제외됩니다. FastAPI 호출은 아직 연결하지 않았습니다. 이벤트별 계약은 `docs/api-contract.md`를 참고하세요.

## 실행

직접 실행할 때는 저장소 루트에서 MySQL과 Qdrant를 먼저 시작합니다.

```bash
cd ..
docker compose up -d mysql qdrant
cd backend
SPRING_PROFILES_ACTIVE=local \
MYSQL_USER=zeropay \
MYSQL_PASSWORD=zeropay_local \
./gradlew bootRun
```

기본 서버 주소는 `http://localhost:8080`이며, 운영 상태는 `GET /actuator/health`에서 확인할 수 있습니다. Spring Boot 프로필은 `local`, `dev`, `prod`로 분리되어 있고 민감 정보는 환경변수로만 전달합니다.

전체 통합 환경에서는 루트의 `docker compose up --build -d` 명령으로 실행합니다. 이때 백엔드는 Compose 내부의 `mysql:3306`을 사용합니다. `ai:8001` 주소는 향후 HTTP 클라이언트용으로 설정되어 있지만 현재 시작 의존성이나 호출 경로는 아닙니다.

KOMSCO 적재는 루트 `.env`를 셸 환경으로 내보낸 뒤 `KOMSCO_IMPORT_ENABLED=true`와 `--spring.main.web-application-type=none`을 함께 지정해 한 번 실행합니다. 자세한 명령과 환경변수는 루트 `README.md`와 `docs/deployment.md`를 참고하세요.

Place ID 보강은 별도 Local API runner 없이 AI의 KOMSCO→PCMap DOM pipeline에서 수행합니다. 기존 `restaurant_external_places` 데이터는 historical mapping으로 보존됩니다.

## 검증

```bash
./gradlew test
./gradlew build
```
