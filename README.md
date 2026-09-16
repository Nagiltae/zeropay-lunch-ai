# ZeroPay Lunch AI

ZeroPay Lunch AI는 자연어 요청, 사용자 취향, 예산, 최근 식사 기록, 위치, 상황 정보를 바탕으로 주변 음식점을 추천합니다.

이 서비스는 모노레포 구조를 사용하며, Spring Boot를 애플리케이션의 단일 진입점으로 둡니다.

```text
React -> Spring Boot -> FastAPI
```

## 현재 상태

현재 이 저장소는 1단계 프로젝트 뼈대 구축 상태입니다.

| 영역 | 상태 |
| --- | --- |
| 프런트엔드 | 최소 구성의 React + TypeScript + Vite 애플리케이션 생성 완료 |
| 메인 백엔드 | Java 21 + Spring Boot + Gradle 프로젝트 및 JPA/MySQL 기반 구성 완료 |
| AI 서버 | 최소 구성의 FastAPI 상태 확인 엔드포인트와 테스트 작성 완료 |
| MySQL | 로컬 Docker Compose 서비스 정의 완료 |
| API 계약 및 아키텍처 | 초기 문서 작성 완료 |

## 저장소 구조

```text
zeropay-lunch-ai/
├── frontend/    # React 애플리케이션
├── backend/     # Spring Boot 애플리케이션
├── ai/          # FastAPI AI 서버
├── docs/        # 아키텍처 및 계약 문서
└── scripts/     # 로컬 검증 명령어
```

## 로컬 환경 설정

인프라를 실행하기 전에 로컬 환경 변수 템플릿을 복사합니다.

```bash
cp .env.example .env
docker compose up -d mysql
```

프런트엔드에는 Node.js 20.19 이상이 필요합니다.

```bash
cd frontend
npm install
npm run dev
```

메인 백엔드는 Java 21을 사용합니다.

```bash
cd backend
./gradlew bootRun
```

AI 서버에는 Python 3.11 이상과 Poetry가 필요합니다.

```bash
cd ai
poetry install
poetry run uvicorn app.main:app --reload --port 8001
```

백엔드 구성과 검증 방법은 `backend/README.md`에서 확인할 수 있습니다.

사용 가능한 모든 검증은 저장소 루트에서 다음과 같이 실행합니다.

```bash
./scripts/check-all.sh
```
