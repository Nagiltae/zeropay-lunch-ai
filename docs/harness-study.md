# Harness Engineering in This Project

ZeroPay Lunch AI에서 Harness Engineering은 Agent를 위한 별도 프레임워크가 아닙니다. Agent가 같은 규칙을 읽고, 현재 아키텍처와 계약 안에서 제한된 변경을 만들고, 반복 가능한 명령으로 결과를 검증한 뒤 근거와 함께 완료를 보고하도록 저장소 자체를 구성한 방식입니다.

이 저장소의 Harness는 네 부분이 연결되어 동작합니다.

1. `AGENTS.md`가 행동 규칙과 완료 조건을 정합니다.
2. `tasks/`와 `docs/`가 작업 범위와 현재 계약을 제공합니다.
3. build 설정, 테스트와 Docker Compose가 실행 가능한 검증 환경을 제공합니다.
4. `scripts/check-*.sh`가 구현 결과를 빠른 검사부터 실제 통합 흐름까지 되돌려 줍니다.

Controller, Service, React Component와 FastAPI endpoint는 Harness 자체가 아닙니다. 그것들은 Harness가 문서, 테스트와 스크립트를 통해 변경 범위를 제한하고 검증하는 애플리케이션입니다.

## Harness File Map

현재 저장소에서 학습에 중요한 Harness 파일은 다음과 같습니다.

```text
AGENTS.md                         # Agent 정책, guardrail, Definition of Done
GEMINI.md                         # 다른 Agent를 canonical 정책으로 안내
README.md                         # 사람과 Agent를 위한 프로젝트 진입점
AI_CHANGELOG.md                   # 최근 Agent 작업의 인수인계 기록
.env.example                     # 환경변수 이름과 안전한 로컬 예시
.gitignore                       # 비밀·생성 파일의 Git 유입 방지
docker-compose.yml               # 재현 가능한 로컬 서비스 토폴로지

docs/
├── harness-study.md             # 이 학습 가이드
├── architecture.md              # 서비스 책임과 호출 경계
├── api-contract.md              # 공개 API, SSE, 계획된 내부 AI 계약
├── database.md                  # 데이터 소유권, Flyway와 샘플 정책
├── ai-flow.md                   # 현재·목표 AI 흐름과 결정론적 경계
├── conventions.md               # 서비스별 구현 규칙
├── deployment.md                # profile, 환경변수와 실행 방법
└── testing.md                   # 검증 범위와 단계별 통합 전략

tasks/
├── README.md                    # task 작성 기준과 템플릿
├── pre-ai-chat-recommendation.md
├── user-session-authentication.md
├── pre-fastapi-personalization-foundation.md
└── local-harness-alignment.md

scripts/
├── setup.sh                     # 최초 환경 준비
├── check-format.sh              # 변경 파일 공백과 Python format
├── check-lint.sh                # React/Python lint
├── check-frontend.sh            # TypeScript build와 Vitest
├── check-backend.sh             # Java compiler lint, 테스트와 build
├── check-ai.sh                  # Python metadata, import와 Pytest
├── check-integration.sh         # Docker 기반 실제 사용자 흐름
└── check-all.sh                 # 전체 검사의 canonical 진입점

frontend/
├── package.json                 # frontend build/test 명령과 의존성
├── package-lock.json            # frontend 의존성 재현
├── eslint.config.js             # TypeScript/React 정적 규칙
└── tsconfig.app.json            # strict TypeScript 경계

backend/
├── build.gradle                 # Java/Spring build, compiler lint와 테스트 설정
├── gradlew                      # 고정 Gradle 실행 진입점
├── gradle/wrapper/              # Gradle 버전 재현
└── src/main/resources/
    ├── application.yml          # 공통 Spring/Flyway 정책
    ├── application-local.yml
    ├── application-dev.yml
    ├── application-prod.yml     # 실행 환경별 연결 설정
    └── db/
        ├── migration/           # 불변 versioned schema history
        └── sample/              # local/dev repeatable 샘플 데이터

ai/
├── pyproject.toml               # Python 의존성, Ruff와 Pytest 규칙
├── poetry.lock                  # Python 의존성 재현
└── tests/                       # AI 서비스 자동 검증
```

현재 GitHub Actions 같은 CI 파일은 없습니다. 따라서 로컬에서는 `scripts/check-all.sh`가 최종 검증 진입점이며, 실행 여부는 `AGENTS.md`의 정책과 Agent의 최종 보고로 확인합니다.

## File Roles

### 정책과 작업 범위

| 경로 | 역할 | Agent가 사용하는 시점 | 필요한 이유 | 연결 |
| --- | --- | --- | --- | --- |
| `AGENTS.md` | canonical Agent 정책과 Definition of Done | 모든 작업의 시작과 종료 | Agent마다 다른 방식으로 구현·완료 판단하는 것을 방지 | `tasks/`, `docs/`, `scripts/` 전체 |
| `GEMINI.md` | Gemini를 `AGENTS.md`로 안내 | Gemini가 저장소에 진입할 때 | 별도 정책 복제로 생기는 충돌 방지 | `AGENTS.md` |
| `tasks/README.md` | 비자명 작업 명세 템플릿 | 여러 계층·계약·DB 변경 전 | 범위 확대와 요구사항 누락 방지 | 개별 task, 관련 docs, verification 명령 |
| `tasks/*.md` | 특정 작업의 목표·제외 범위·완료 기준 | 사용자가 task 구현을 요청하거나 관련 작업을 이어갈 때 | 과거 결정과 남은 범위를 추측하지 않게 함 | `AGENTS.md`, `docs/`, `check-*.sh` |
| `AI_CHANGELOG.md` | 최근 변경의 인수인계 요약 | 현재 구현의 배경을 빠르게 볼 때와 작업 완료 후 | 다른 Agent가 이미 한 일을 반복하는 문제 감소 | Git diff와 권위 있는 docs를 보조 |

`AI_CHANGELOG.md`는 계약의 기준이 아닙니다. 내용이 충돌하면 실제 코드와 `docs/`의 현재 계약을 다시 확인해야 합니다.

### 아키텍처와 계약

| 경로 | 역할 | Agent가 사용하는 시점 | 필요한 이유 | 연결 |
| --- | --- | --- | --- | --- |
| `docs/architecture.md` | React, Spring Boot, FastAPI와 저장소 책임 정의 | 서비스 경계 변경 전 | 잘못된 직접 호출과 데이터 소유권 이동 방지 | API, DB, AI 문서 |
| `docs/api-contract.md` | HTTP, SSE와 내부 AI payload 정의 | Controller, DTO, API client 수정 전 | 호출자와 제공자의 계약 drift 방지 | frontend API 테스트, backend 테스트, integration |
| `docs/database.md` | 테이블, 영업 정책, Flyway 규칙 정의 | Entity, Repository, SQL 수정 전 | 과거 migration 수정과 데이터 정책 위반 방지 | migration SQL, JPA validate, integration |
| `docs/ai-flow.md` | 결정론적 로직과 AI 역할 분리 | 추천 분석·fallback·FastAPI 변경 전 | LLM에 필수 필터와 순위를 넘기는 실수 방지 | architecture, API contract, AI tests |
| `docs/conventions.md` | 구현 패턴과 의존성 선택 기준 | 새 패턴·도구 도입 전 | 서비스마다 다른 상태 관리와 불필요한 복잡성 방지 | lint/build 설정 |
| `docs/deployment.md` | local/dev/prod 실행 계약 | profile, Docker, 환경변수 수정 전 | 개인 환경에만 동작하는 설정 방지 | `.env.example`, Compose, setup |
| `docs/testing.md` | 검사별 보장 범위와 아직 없는 검증 명시 | 구현 계획과 완료 판단 시 | 실행하지 않은 범위를 검증됐다고 오판하지 않게 함 | 모든 check script |

### 실행 환경과 비밀정보

| 경로 | 역할 | Agent가 사용하는 시점 | 필요한 이유 | 연결 |
| --- | --- | --- | --- | --- |
| `.env.example` | 필요한 변수의 공개 계약 | 환경변수 추가·변경 시 | 실제 secret 커밋과 숨은 로컬 설정 의존 방지 | `.gitignore`, Compose, Spring profiles |
| `.gitignore` | secret과 생성 결과 제외 | 작업 전후 `git status` 확인 시 | `.env`, build, 가상환경 유입 방지 | Definition of Done의 Git 검토 |
| `docker-compose.yml` | 서비스와 health의 재현 가능한 토폴로지 | 전체 실행과 integration 검사 시 | 수동으로 구성한 환경 차이 방지 | Dockerfiles, setup, integration |
| `scripts/setup.sh` | 도구·잠금 의존성·필수 MySQL 준비 | 새 환경의 첫 실행 | 준비되지 않은 환경의 실패를 코드 오류로 오해하지 않게 함 | lock files, `.env.example`, Compose |
| `application-*.yml` | Spring profile별 연결 정책 | backend 실행 환경 변경 시 | local/dev/prod 주소와 secret 정책 혼합 방지 | deployment 문서와 Compose |

### Build, Test와 Validation

| 경로 | 역할 | Agent가 사용하는 시점 | 필요한 이유 | 연결 |
| --- | --- | --- | --- | --- |
| `frontend/package.json` | build, lint, Vitest 명령 정의 | frontend 검사 실행 시 | 사람이 기억한 임의 명령 대신 저장소 명령 사용 | frontend check, package lock |
| `backend/build.gradle` | Java compiler lint, Spring build/test 정의 | backend 검사 실행 시 | 컴파일 warning과 테스트 실패를 자동 차단 | Gradle wrapper, backend check |
| `ai/pyproject.toml` | Poetry, Ruff, Pytest 규칙 정의 | AI 검사 실행 시 | Python 환경·스타일·테스트 기준 차이 방지 | poetry lock, AI checks |
| `scripts/check-format.sh` | 변경 파일과 Python format 검사 | 구현 직후 | 신규 파일과 작은 형식 오류를 조기 발견 | Git, Ruff, check-all |
| `scripts/check-lint.sh` | frontend/AI 정적 검사 | 코드 변경 후 | 실행 전 정적 문제 발견 | ESLint, Ruff, check-all |
| `scripts/check-frontend.sh` | build와 frontend tests | frontend 변경 후 | 타입·production build·UI/API 회귀 확인 | package scripts, check-all |
| `scripts/check-backend.sh` | Gradle build 전체 | backend·migration 변경 후 | compiler, Spring context, JPA/Flyway와 테스트 확인 | Gradle, check-all |
| `scripts/check-ai.sh` | AI metadata, import와 tests | AI 변경 후 | 실행 불가능한 FastAPI 코드 완료 보고 방지 | Poetry, Pytest, check-all |
| `scripts/check-integration.sh` | 실제 Docker 사용자 흐름 | 서비스 경계·DB·인증 변경 후 | 단독 테스트가 못 찾는 cookie, proxy, DB 연결 문제 발견 | Compose, MySQL, Nginx, APIs |
| `scripts/check-all.sh` | 모든 검사를 실행하고 결과 요약 | 다중 서비스 변경의 최종 단계 | 일부 성공을 전체 성공으로 착각하지 않게 함 | 모든 check script와 DoD |

테스트 파일도 feedback loop의 일부입니다. 하지만 테스트 대상인 Controller나 Component 자체가 Harness가 아닌 것처럼, 각 테스트 코드는 이 문서에서 전부 나열하기보다 해당 서비스 검사에서 실행되는 검증 자산으로 이해하면 됩니다.

## Reading Order

### 핵심 순서

1. `AGENTS.md` — Agent가 따라야 할 절차, 금지 행동과 완료 조건을 먼저 확인합니다.
2. `docs/architecture.md` — 무엇을 어느 서비스가 소유하는지 이해합니다.
3. `tasks/README.md`와 최신 관련 task — 추상 정책이 실제 작업 범위로 어떻게 좁혀지는지 봅니다.
4. `docs/api-contract.md`와 `docs/database.md` — 코드 양쪽과 DB가 공유하는 구체적인 계약을 확인합니다.
5. `docs/testing.md` — 어떤 검사가 무엇을 보장하고 무엇은 아직 보장하지 않는지 봅니다.
6. `scripts/check-all.sh` — 전체 feedback loop가 어떤 순서로 조립되는지 읽습니다.
7. 각 `scripts/check-*.sh` — 서비스별 명령과 실패 조건을 확인합니다.
8. `docker-compose.yml`과 `scripts/check-integration.sh` — 실제 서비스 토폴로지와 사용자 흐름 검증을 연결해 봅니다.

### 참고 순서

9. `docs/conventions.md`, `docs/ai-flow.md` — 구현 방식과 AI 책임을 더 자세히 확인합니다.
10. `docs/deployment.md`, `.env.example`, profile YAML — 동일 코드를 환경별로 실행하는 방식을 공부합니다.
11. `frontend/package.json`, `backend/build.gradle`, `ai/pyproject.toml` — 검사 스크립트가 실제로 호출하는 도구 설정을 확인합니다.
12. `AI_CHANGELOG.md` — 최근 변경 배경을 확인하되 현재 계약과 실제 코드로 다시 검증합니다.

## What To Look For

### `AGENTS.md`

- Agent가 수정 전에 반드시 확인해야 하는 것은 무엇인가?
- 승인 없이 하면 안 되는 작업은 무엇인가?
- Flyway migration은 어떤 방식으로만 변경할 수 있는가?
- 코드 작성과 “완료” 사이에 어떤 검증이 필요한가?

### `tasks/README.md`와 개별 task

- 어떤 규모부터 task 명세가 필요한가?
- In scope와 Out of scope가 구현 범위를 어떻게 제한하는가?
- acceptance criteria가 자동 검증과 연결되는가?
- task 상태와 남은 범위가 분리되어 있는가?

### `docs/architecture.md`

- 브라우저가 호출할 수 있는 서버는 어디인가?
- 결정론적 필터와 AI 기능은 어떻게 분리되는가?
- 현재 구현과 목표 구조가 구분되어 있는가?

### `docs/api-contract.md`

- 구현된 API와 계획 중인 API는 어떻게 표시되는가?
- SSE event 이름, 순서와 payload는 무엇인가?
- React 타입과 Spring DTO가 이 계약에 맞는가?

### `docs/database.md`

- MySQL과 Qdrant 중 원본 데이터의 소유자는 누구인가?
- 왜 기존 `V1`, `V2`, `V3`를 수정하면 안 되는가?
- local/dev 샘플 데이터와 prod 데이터가 어떻게 분리되는가?

### `docs/testing.md`

- unit/service/integration 검사의 경계는 어디인가?
- 현재 통합 검사가 실제로 수행하는 사용자 흐름은 무엇인가?
- 아직 검증하지 않는 기능은 무엇인가?

### `scripts/check-all.sh`

- 검사 실패 후에도 나머지 검사를 실행하는 이유는 무엇인가?
- 최종 exit code와 PASS/FAIL 요약은 어떻게 결정되는가?
- 어떤 변경에서 이 전체 검사가 필요한가?

### `scripts/check-integration.sh`

- 어떤 container health를 기다리는가?
- CSRF token, session cookie와 대화 소유권을 어떻게 검증하는가?
- 실패 시 Agent가 분석할 로그를 어떻게 제공하는가?
- 검사 후 보존되는 데이터와 container는 무엇인가?

### `docker-compose.yml`

- 현재 실제 필수 시작 의존성은 무엇인가?
- FastAPI와 Qdrant가 아직 독립 실행인 이유는 무엇인가?
- 어떤 포트가 localhost에만 노출되는가?

### `.env.example`과 `.gitignore`

- 저장소에 공개해도 되는 값과 안 되는 값은 무엇인가?
- 새 환경변수를 추가하면 Compose, profile과 문서를 어디까지 함께 바꿔야 하는가?

## Agent Execution Flow

Codex에게 “Restaurant 기능을 구현해줘”라고 요청했다고 가정하면 현재 저장소의 흐름은 다음과 같습니다.

```text
사용자 요청
  -> AGENTS.md에서 규칙·안전 경계·Definition of Done 확인
  -> git status --short로 기존 작업과 untracked 파일 확인
  -> tasks/README.md 기준으로 task 필요 여부 판단
  -> 관련 task가 있으면 읽고, 비자명 신규 작업이면 명세 작성
  -> docs/architecture.md에서 Spring Boot 책임 확인
  -> docs/api-contract.md와 docs/database.md에서 API·DB 계약 확인
  -> Restaurant 관련 실제 코드와 기존 테스트 분석
  -> 범위 안에서 구현하고 필요한 테스트 추가
  -> ./scripts/check-backend.sh로 빠른 대상 검증
  -> API·DB·Docker에 영향이 있으면 ./scripts/check-integration.sh 실행
  -> 여러 영역 변경이면 ./scripts/check-all.sh 실행
  -> 실패 출력과 로그 분석 후 수정하고 같은 검사 재실행
  -> git status --short와 git diff로 전체 변경 확인
  -> AGENTS.md Definition of Done과 task acceptance criteria 확인
  -> AI_CHANGELOG.md에 의미 있는 작업 내용 기록
  -> 변경 파일, 실행 명령, 결과와 미해결 문제 보고
```

Restaurant 스키마를 바꿔야 한다면 `V1`을 편집하지 않습니다. `docs/database.md`의 규칙에 따라 다음 번호의 migration을 추가하고 백엔드 검사와 실제 MySQL 통합 검사를 실행합니다.

## Feedback Loop

현재 feedback loop는 다음처럼 구현되어 있습니다.

```text
구현
  -> 가장 좁은 check script 실행
  -> 실패 exit code와 출력 확인
  -> 단위·서비스 테스트 실패 분석
  -> Docker 실패면 check-integration.sh가 출력한 ps와 최근 로그 분석
  -> 원인에 해당하는 코드·설정·테스트만 수정
  -> 같은 check script 재실행
  -> 여러 영역이면 check-all.sh로 전체 회귀 확인
  -> 모든 적용 가능한 검사가 성공해야 완료 보고
```

중요한 점은 “코드를 작성했다”와 “작업이 완료됐다”가 다르다는 것입니다. `AGENTS.md`의 Definition of Done과 실제 검사 결과가 두 상태 사이의 문을 담당합니다.

## Guardrails

| 막으려는 행동 | 막는 파일과 규칙 |
| --- | --- |
| Architecture 임의 변경 | `AGENTS.md` Core rules, `docs/architecture.md`, task Out of scope, 문서 갱신 의무 |
| 기존 Flyway migration 수정 | `AGENTS.md` Database migration rules, `docs/database.md` Migration 규칙 |
| 비밀정보 노출 | `AGENTS.md` Safety, `.gitignore`, `.env.example`, profile YAML의 환경변수 참조 |
| 파괴적인 Git 명령 | `AGENTS.md` Safety의 `--force`, `reset --hard`, `checkout --` 금지 |
| 테스트 삭제·비활성화 | `AGENTS.md` Safety와 DoD, `docs/testing.md` Failure handling |
| 관계없는 대규모 수정 | `AGENTS.md` Core rules, task In/Out of scope, 최종 Git diff 검토 |
| 검증 없는 완료 처리 | `AGENTS.md` Definition of Done, 대상별 check scripts, `check-all.sh` |
| 미구현 AI 기능을 구현됐다고 가정 | `docs/architecture.md`, `docs/ai-flow.md`, `docs/deployment.md`의 현재 상태 구분 |
| local 샘플을 prod에 적재 | profile별 Flyway location, `docs/database.md`, `docs/deployment.md` |

이 guardrail들은 대부분 “금지 문장”과 “실행 가능한 검사”가 함께 있을 때 강해집니다. 예를 들어 migration 불변성은 정책으로 제한하고, 새 migration이 동작하는지는 Gradle/H2와 Docker/MySQL 검사로 확인합니다.

## What Is Not Harness

다음은 일반 애플리케이션 코드입니다.

- `backend/src/main/java/**/Controller.java`: HTTP 요청 처리
- `backend/src/main/java/**/Service.java`: 인증, 대화, 추천과 식사 기록 비즈니스 로직
- `backend/src/main/java/**/domain/*.java`: Entity와 domain model
- `frontend/src/components/*.tsx`: 사용자가 보는 화면
- `frontend/src/hooks/*.ts`: React 상태와 서버 연동
- `ai/app/main.py`: FastAPI 애플리케이션

이 코드들은 Harness가 관리하고 검증하는 대상입니다. 예를 들어 `RestaurantRecommendationService`는 Harness가 아니라 비즈니스 코드이고, 이 코드의 책임 범위를 설명하는 `architecture.md`, 기대 동작을 검증하는 테스트와 `check-backend.sh`가 Harness입니다.

반대로 다음은 Harness에 직접 참여합니다.

- Agent의 행동을 제한하는 정책
- 현재 시스템의 계약과 경계를 설명하는 문서
- 작업 범위를 고정하는 task 명세
- 동일한 환경을 재현하는 lock file, profile과 Docker 설정
- 구현 실패를 되돌려 주는 테스트와 검증 스크립트
- 무엇을 했고 무엇을 검증했는지 남기는 최종 diff와 작업 기록

구분 기준은 간단합니다. 사용자에게 음식점을 추천하는 동작을 직접 수행하면 애플리케이션이고, Agent가 그 동작을 안전하고 반복 가능하게 변경하도록 안내·제한·검증하면 Harness입니다.
