# Task: 현재 코드 기준 로컬 Harness 정합성 개선

## Status

완료. 2026-09-17에 `./scripts/check-all.sh` 전체 검증이 통과했습니다.

## Goal

현재 구현된 인증, 대화, 개인화 추천 기능을 기준으로 문서, Flyway 정책, Docker 의존성 및 로컬 검증 진입점을 일치시킵니다.

## Background

기능 개발 이후 일부 소개 문서와 완료된 task의 배경이 과거 상태에 머물러 있습니다. 또한 아직 사용하지 않는 FastAPI와 Qdrant가 Docker 시작 의존성으로 연결되어 있고, 신규 untracked 파일은 공백 검사에서 제외될 수 있습니다.

## In scope

- 현재 코드와 README, 아키텍처, 테스트 및 task 상태의 정합성
- Flyway versioned migration 불변 규칙
- 현재 실제 호출 관계에 맞는 Docker Compose 시작 의존성
- 기존 검증 스크립트의 변경 파일 탐지 보강
- 최소 Java 컴파일 정적 검사와 핵심 React 사용자 흐름 테스트

## Out of scope

- GitHub Actions와 배포 자동화
- FastAPI 의도 분석 API와 Spring HTTP 클라이언트
- Kubernetes, Redis, 별도 Agent Framework
- 애플리케이션 비즈니스 규칙 변경

## Functional requirements

1. 현재 구현과 계획된 기능을 문서에서 구분합니다.
2. 적용된 `V1`, `V2`, `V3`는 수정하지 않고 이후 스키마 변경은 새 migration으로 추가하도록 규정합니다.
3. Spring Boot는 아직 호출하지 않는 FastAPI를 시작 조건으로 요구하지 않습니다.
4. FastAPI는 아직 사용하지 않는 Qdrant를 시작 조건으로 요구하지 않습니다.
5. 공백 검사는 tracked 변경뿐 아니라 untracked 파일도 확인합니다.
6. Java 컴파일 warning과 핵심 React 개인화 흐름을 최소 범위로 검증합니다.

## API contract

공개 및 내부 API 계약 변경 없음.

## Data model impact

스키마 변경 없음. 기존 Flyway migration 파일은 수정하지 않습니다.

## Architecture constraints

- React는 Spring Boot만 호출합니다.
- 현재 FastAPI는 health endpoint만 제공하며 Spring Boot HTTP 클라이언트는 없습니다.
- 현재 Qdrant Python 클라이언트와 검색 기능은 없습니다.

## Acceptance criteria

1. 문서가 현재 구현과 계획 범위를 구분합니다.
2. Agent가 Flyway 변경 규칙을 진입 문서에서 확인할 수 있습니다.
3. Compose의 `depends_on`이 실제 필수 시작 의존성만 표현합니다.
4. 기존 canonical 검사 진입점을 유지하면서 신규 파일 누락을 방지합니다.
5. 관련 검사와 `./scripts/check-all.sh` 결과를 보고합니다.

## Verification

- `./scripts/check-format.sh`
- `./scripts/check-lint.sh`
- `./scripts/check-frontend.sh`
- `./scripts/check-backend.sh`
- `./scripts/check-all.sh`

## Documentation updates

- `AGENTS.md`
- `README.md`
- `docs/architecture.md`
- `docs/database.md`
- `docs/deployment.md`
- `docs/testing.md`
- `tasks/README.md` 및 현재 task 상태
