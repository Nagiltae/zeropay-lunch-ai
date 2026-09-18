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
| MySQL | Flyway V1~V6 스키마, local/dev 샘플 음식점 3개, KOMSCO 원본과 NAVER Local 보강 결과 저장 |
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

## KOMSCO 음식점 일회성 import

KOMSCO 모바일 가맹점 데이터는 공개 API나 Scheduler가 아니라 opt-in `ApplicationRunner`로 적재합니다. 루트 `.env`의 `KOMSCO_SERVICE_KEY`는 Spring Boot가 자동으로 읽지 않으므로 셸 환경으로 내보낸 뒤 실행합니다. 실제 키를 명령행이나 로그에 직접 적지 않습니다.

```bash
set -a
source .env
set +a
cd backend
SPRING_PROFILES_ACTIVE=local KOMSCO_IMPORT_ENABLED=true \
  ./gradlew bootRun --args='--spring.main.web-application-type=none'
```

실행 전 MySQL이 떠 있어야 합니다. 14개 강남구 법정동의 모든 페이지 수집이 성공한 뒤에만 DB upsert를 시작하며 결과 집계를 로그로 출력합니다. KOMSCO에는 메뉴·가격·영업시간이 없으므로 적재 직후 행은 `recommendation_ready=false`이고 기존 추천 후보에는 포함되지 않습니다.

기존 KOMSCO snapshot을 새 필터 결과로 완전히 교체할 때만 `KOMSCO_REPLACE_EXISTING=true`를 함께 지정합니다. 전체 API 조회와 정제가 성공한 뒤 하나의 DB 트랜잭션에서 `source_provider=KOMSCO` 행만 삭제·재삽입하며, 실패하면 삭제까지 롤백합니다.

Docker Compose의 백엔드는 `Asia/Seoul` 기준 매일 새벽 3시에 동일한 전체 조회를 실행합니다. 최신 상태가 계속사업자가 아니거나 KSIC 561·강남구·제공기관 조건에서 벗어난 기존 가맹점은 삭제하지 않고 `active=false`로 전환합니다. 조건을 다시 만족하면 `active=true`로 복구하며, 확인된 기존 행은 `last_synced_at`과 `updated_at`을 갱신합니다. 직접 실행 환경에서는 `KOMSCO_SCHEDULER_ENABLED=true`로 활성화할 수 있습니다.

## NAVER Local 음식점 보강

활성 KOMSCO 음식점을 NAVER API HUB 지역 검색 결과와 비교하는 기능은 공개 API나 Scheduler가 아닌 opt-in `ApplicationRunner`입니다. KOMSCO 상호·주소·좌표를 원본으로 유지하며 NAVER 결과와 `MATCHED`/`AMBIGUOUS`/`UNMATCHED`, 점수 근거와 마지막 API 시도 상태는 별도 `restaurant_external_places` 테이블에 저장합니다. 추천 가능 여부는 `restaurants.recommendation_eligibility`의 `ELIGIBLE`/`INELIGIBLE`/`UNKNOWN`으로 별도 관리하며 기본 검증 범위는 100개입니다.

Spring Boot는 `.env`를 자동으로 읽지 않으므로 직접 실행할 때 환경변수로 내보냅니다. 실제 API 실행은 호출 범위와 redacted 요청을 확인하고 승인한 뒤에만 수행합니다.

```bash
set -a
source .env
set +a
cd backend
SPRING_PROFILES_ACTIVE=local NAVER_ENRICHMENT_ENABLED=true \
  ./gradlew bootRun --args='--spring.main.web-application-type=none --limit=100'
```

검증 모드는 법정동 코드와 음식점 ID를 기준으로 deterministic round-robin 표본을 선택하고 CSV를 `build/reports/naver-enrichment`에 남깁니다. 증분 실행은 `--incremental --limit=100`, 전체 실행은 별도 사용자 확인 후에만 `--all`을 지정합니다. 증분 대상은 보강 행 부재, KOMSCO 매칭 입력 변경, 상태별 재시도 시각 도래 또는 refresh TTL 만료 행입니다.

검색은 `상호명 법정동명`을 먼저 사용하고 신뢰할 수 있는 후보가 없을 때 `상호명 강남구`를 한 번만 추가합니다. 각 검색은 최대 5개 후보만 받고, 상호명·주소·300m 이내 거리·음식점 카테고리 점수를 적용합니다. 명시된 category가 음식점 계열이 아니거나 이름 증거가 최소 기준보다 낮으면 점수 계산 후보에서 제외합니다. MATCHED는 기존 70점·gap 8점 외에도 주소 25점 이상 또는 이름 32점 이상이면서 50m 이내라는 strong evidence가 필요하고, total만 높은 경우 AMBIGUOUS로 남깁니다. 401/403은 실행을 중단하며 개별 일시 장애는 `API_ERROR` 시도로 기록하되 기존 정상 매칭을 제거하지 않습니다.

`MATCHED+음식점 category`만 ELIGIBLE입니다. `MATCHED+명확한 비음식점 category`는 INELIGIBLE이고 AMBIGUOUS, UNMATCHED, API_ERROR, 미조회 또는 category 불명은 UNKNOWN입니다. 추천 조회는 기존 영업·제로페이·보강 완료 조건과 함께 ELIGIBLE을 강제합니다.

NAVER의 WGS84 좌표는 응답에 따라 소수점 도(degree) 또는 `10^7` 배율 정수 문자열로 올 수 있으므로 저장·거리 계산 전에 소수점 좌표로 정규화합니다.

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
