# 실행 및 배포

## When to read
- Docker / Docker Compose 설정 변경
- 환경변수 추가/수정
- 배포 인프라(AWS 등) 작업


> **Harness Role:** local/dev/prod 환경과 Docker 실행 방식을 재현 가능한 절차로 설명합니다. Agent는 환경변수, profile, container 또는 실행 명령을 바꾸기 전에 읽습니다. 이 문서가 없으면 개인 PC 상태에 의존하거나 잘못된 서비스 주소를 사용할 수 있습니다. `.env.example`, profile YAML, `docker-compose.yml`, `setup.sh`와 연결됩니다.

## 로컬 개발

처음 환경을 준비할 때는 저장소 루트의 `./scripts/setup.sh`를 실행합니다. 스크립트는 필수 도구를 검사하고 잠금 파일 기반 의존성을 준비한 뒤 현재 애플리케이션의 필수 저장소인 MySQL을 기동하여 health 상태를 확인합니다. Qdrant는 검색 기능을 개발할 때 Compose에서 별도로 기동할 수 있습니다.

애플리케이션 코드를 각 런타임에서 직접 실행하고 데이터 저장소만 Docker Compose로 실행할 수도 있습니다.

```bash
docker compose up -d mysql qdrant
```

- React: Vite 개발 서버
- Spring Boot: Gradle `bootRun`
- FastAPI: Poetry와 Uvicorn
- MySQL과 Qdrant: Docker Compose

Spring Boot 설정은 다음 프로필로 분리합니다.

| 프로필 | 용도 | 연결 방식 |
| --- | --- | --- |
| `local` | 애플리케이션을 개발 PC에서 직접 실행 | `localhost`의 MySQL과 FastAPI |
| `dev` | 개발 PC의 Docker Compose 전체 스택 | Compose 호스트명 `mysql`, `ai` |
| `prod` | AWS 운영 환경 | 모든 연결 정보와 자격 증명을 환경변수로 주입 |

YAML에는 DB 비밀번호나 운영 자격 증명을 저장하지 않습니다. `local` 실행도 `.env`를 Spring Boot가 자동으로 읽지 않으므로 필요한 값을 환경변수로 전달해야 합니다.

```bash
cd backend
SPRING_PROFILES_ACTIVE=local \
MYSQL_USER=zeropay \
MYSQL_PASSWORD=zeropay_local \
./gradlew bootRun
```

위 값은 로컬 예시이며 운영 값으로 사용하지 않습니다. `local`과 `dev`는 샘플 음식점 migration을 실행하고 `prod`는 공통 스키마 migration만 실행합니다.

FastAPI 연동 정책은 환경변수로 조정합니다.

| 환경변수 | 기본값 | 용도 |
| --- | --- | --- |
| `AI_BASE_URL` | local `http://localhost:8001`, dev `http://ai:8001` | 내부 FastAPI 주소 |
| `AI_CONNECT_TIMEOUT` | `2s` | 연결 제한 시간 |
| `AI_RESPONSE_TIMEOUT` | `8s` | 응답 제한 시간 |
| `AI_MAX_ATTEMPTS` | `1` | 최대 호출 횟수, 기본은 자동 재시도 없음 |
| `AI_FALLBACK_ENABLED` | `true` | AI 호출 실패 시 임시 분석기 사용 여부 |

현재 실제 FastAPI HTTP 클라이언트는 없으므로 timeout과 최대 시도 설정은 클라이언트 구현 시 적용됩니다. fallback 선택과 임시 분석기는 현재 추천 흐름에서 동작합니다.

KOMSCO 일회성 import 설정은 다음과 같습니다.

| 환경변수 | 기본값 | 용도 |
| --- | --- | --- |
| `KOMSCO_SERVICE_KEY` | 없음 | 데이터 포털 인증키. 저장소·로그에 기록하지 않음 |
| `KOMSCO_PAGE_SIZE` | `1000` | 법정동별 한 페이지 요청 건수 |
| `KOMSCO_CONNECT_TIMEOUT` | `3s` | 외부 API 연결 제한 시간 |
| `KOMSCO_READ_TIMEOUT` | `20s` | 외부 API 응답 제한 시간 |
| `KOMSCO_IMPORT_ENABLED` | `false` | opt-in `ApplicationRunner` 활성화 |
| `KOMSCO_REPLACE_EXISTING` | `false` | 성공한 전체 snapshot으로 기존 KOMSCO 행을 트랜잭션 교체 |
| `KOMSCO_SCHEDULER_ENABLED` | direct 실행 `false`, Compose `true` | 일일 동기화 활성화 |
| `KOMSCO_SCHEDULER_CRON` | `0 0 3 * * SUN` | Spring cron, 기본 매주 일요일 03:00 |
| `KOMSCO_SCHEDULER_ZONE` | `Asia/Seoul` | cron 해석 timezone |

루트 `.env`는 Docker Compose가 변수 치환에 사용하지만 Spring Boot를 IntelliJ나 Gradle로 직접 실행할 때는 자동 로드되지 않습니다. 직접 실행할 때는 `.env` 값을 환경변수로 내보내고 `KOMSCO_IMPORT_ENABLED=true`와 `--spring.main.web-application-type=none`을 지정합니다. 일회성 import의 일반 기본값은 `false`입니다. 전체 교체는 사용자가 범위와 API 쿼리를 승인한 경우에만 `KOMSCO_REPLACE_EXISTING=true`로 실행합니다. 공개 HTTP import API는 없으며 수동 runner와 Scheduler가 같은 `RestaurantImportService`를 사용합니다.

Docker Compose는 사용자가 승인한 KOMSCO 쿼리를 매주 일요일 03:00에 실행하도록 Scheduler를 기본 활성화합니다. IntelliJ나 Gradle의 `local` 직접 실행은 기본 비활성이므로 필요하면 `KOMSCO_SCHEDULER_ENABLED=true`를 명시합니다. Scheduler는 단일 백엔드 인스턴스를 전제로 하며, AWS에서 여러 인스턴스를 동시에 운영하기 전에는 DB 기반 분산 lock 또는 별도 단일 실행 주체를 결정해야 합니다.

과거 NAVER API HUB 보강 환경변수는 신규 pipeline에서 사용하지 않습니다. 기존 historical 설정이 남아 있는 배포 환경에서는 삭제 전 영향 확인이 필요합니다.

| 환경변수 | 기본값 | 용도 |
| --- | --- | --- |
| `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | 사용 안 함 | 신규 pipeline은 NAVER Local API를 호출하지 않음 |
| `NAVER_CONNECT_TIMEOUT` | `3s` | 연결 제한 시간 |
| `NAVER_READ_TIMEOUT` | `5s` | 응답 제한 시간 |
| `NAVER_REQUEST_INTERVAL` | `200ms` | 순차 호출 사이 최소 간격 |
| `NAVER_RETRY_BACKOFF` | `500ms` | 429·5xx·일시적 연결 장애 재시도 대기 |
| `NAVER_MAX_ATTEMPTS` | `2` | 한 검색의 최대 시도 횟수 |
| `NAVER_ENRICHMENT_ENABLED` | `false` | opt-in 수동 `ApplicationRunner` 활성화 |
| `NAVER_ENRICHMENT_LIMIT` | `100` | 검증·증분 실행에서 `--limit` 생략 시 처리 상한 |
| `NAVER_MATCHED_REFRESH_TTL` | `720h` | 변경 없는 MATCHED 결과 재확인 주기 |
| `NAVER_AMBIGUOUS_RETRY_DELAY` | `168h` | AMBIGUOUS 재시도 대기 |
| `NAVER_UNMATCHED_RETRY_DELAY` | `168h` | UNMATCHED 재시도 대기 |
| `NAVER_API_ERROR_RETRY_DELAY` | `1h` | 개별 API 장애 재시도 대기 |
| `NAVER_REPORT_DIRECTORY` | `build/reports/naver-enrichment` | 실행별 CSV 리포트 경로 |

`.env`는 Compose에서만 자동 변수 치환됩니다. IntelliJ/Gradle의 `local` 실행에서는 위 자격 증명과 실행 플래그를 프로세스 환경변수로 전달해야 합니다. Compose에도 변수가 연결되어 있지만 기본 실행은 `NAVER_ENRICHMENT_ENABLED=false`이며 Scheduler는 없습니다. 기본 실행은 최대 100개 법정동별 표본 검증이고, `--incremental --limit=<n>`과 별도 승인 후 `--all`을 명시할 수 있습니다. 인증 실패(401/403)는 즉시 중단하고, 429와 일시적인 5xx만 제한적으로 재시도합니다.

MySQL과 Qdrant 포트는 로컬 호스트에만 바인딩됩니다. 컨테이너가 없어도 Compose가 이미지를 내려받고 컨테이너와 영속 볼륨을 생성합니다.

## 로컬 통합 테스트

전체 서비스를 컨테이너로 실행합니다.

```bash
docker compose up --build -d
docker compose ps
```

React 정적 파일은 Nginx가 제공합니다. Nginx는 `/api/` 요청을 Spring Boot로 전달하며 FastAPI를 직접 노출하지 않습니다. Spring Boot는 Compose 내부 호스트명 `mysql`을 사용합니다. `AI_BASE_URL`과 `QDRANT_URL`은 향후 연동을 위해 준비되어 있지만 현재 Spring Boot는 FastAPI를 호출하지 않고 FastAPI도 Qdrant를 호출하지 않으므로 서로의 시작 조건이 아닙니다.

Compose는 Spring Boot에 `SPRING_PROFILES_ACTIVE=dev`를 설정합니다.

채팅 API의 SSE 이벤트가 브라우저에 즉시 전달되도록 Nginx의 `/api/` 프록시는 응답 버퍼링과 캐시를 사용하지 않으며 읽기 제한 시간을 300초로 설정합니다.

```text
브라우저
  -> Nginx + React
      -> Spring Boot
          -> MySQL

현재 독립 실행(연동 예정):
  FastAPI
  Qdrant
```

컨테이너는 `docker compose down`으로 중지합니다. 이 명령은 `mysql-data`와 `qdrant-data` 볼륨을 삭제하지 않습니다.

## AWS EC2 배포 방향

운영 배포에서는 로컬에서 사용한 Dockerfile로 이미지를 빌드해 Amazon ECR에 저장하고, EC2가 이미지를 내려받아 Docker Compose로 실행합니다.

- 외부에는 Nginx의 HTTP/HTTPS 포트만 공개
- Spring Boot와 FastAPI는 Compose 내부 네트워크에서 실행
- 운영 MySQL은 Amazon RDS 사용 권장
- Qdrant는 초기에는 EC2의 영속 볼륨에서 실행 가능
- 비밀 정보는 저장소의 `.env`가 아니라 AWS Systems Manager Parameter Store 또는 Secrets Manager로 관리
- 이미지 태그는 `latest` 대신 Git 커밋 SHA 사용

EC2용 Compose 파일과 CI/CD 워크플로는 AWS 계정, ECR 저장소, 도메인, RDS 연결 정보가 정해진 뒤 추가합니다.
