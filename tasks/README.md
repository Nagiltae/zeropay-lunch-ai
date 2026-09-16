# Task specifications

`tasks/`는 에이전트가 긴 대화 없이도 범위와 완료 조건을 이해해야 하는 비자명 작업의 실행 명세를 보관합니다.

## Harness study note

- **Harness Role:** 비자명한 작업의 범위, 제외 대상과 관찰 가능한 완료 조건을 구현 전에 고정합니다.
- **Agent Usage:** 여러 계층, API, DB migration 또는 AI workflow를 바꾸기 전에 읽거나 새 명세를 작성합니다.
- **Why:** 명세가 없으면 Agent가 요청 범위를 넓히거나 일부 요구사항을 완료했다고 잘못 판단할 수 있습니다.
- **Connection:** `AGENTS.md`의 정책을 구체적인 작업 단위로 좁히고 관련 `docs/`와 검증 명령을 연결합니다.

## When to create a task spec

다음 중 하나 이상에 해당하면 구현 전에 task 파일을 작성합니다.

- 프런트엔드, Spring Boot, FastAPI 중 둘 이상을 변경
- 공개 또는 내부 API 계약 변경
- 데이터베이스 스키마나 마이그레이션 추가
- 인증, 외부 데이터, AI 워크플로 추가
- 여러 단계로 나눠 구현하거나 명확한 제외 범위가 필요한 작업

단순 문구 수정, 작은 스타일 변경, 명확한 단일 파일 버그 수정에는 task 파일을 만들지 않습니다. 완료된 명세를 구현 기록이나 일반 문서 대신 사용하지 않습니다.

에이전트에게는 다음처럼 요청할 수 있습니다.

```text
Implement tasks/<task-name>.md.
```

에이전트는 `AGENTS.md`, 해당 task 명세, task가 가리키는 관련 문서를 읽고 작업합니다.

## File naming

- 소문자 kebab-case를 사용합니다.
- 기능과 결과가 드러나는 이름을 사용합니다.
- 예: `chat-message-persistence.md`, `gangnam-restaurant-import.md`

## Template

아래 템플릿을 복사하고 해당 없는 절은 `해당 없음`으로 명시합니다.

```markdown
# Task: <name>

## Status

계획 / 진행 중 / 완료 / 일부 완료 중 하나를 기록하고, 일부 완료이면 남은 범위를 적습니다.

## Goal

달성해야 하는 결과를 설명합니다.

## Background

이 작업이 필요한 이유와 현재 동작을 설명합니다.

## In scope

- 변경할 수 있는 기능, 서비스, 파일 영역

## Out of scope

- 이번 작업에서 변경하지 않을 기능과 시스템

## Functional requirements

1. 관찰 가능한 요구사항
2. 실패 및 경계 조건

## API contract

요청, 응답, 이벤트와 오류를 정의합니다. 해당 없으면 명시합니다.

## Data model impact

테이블, 필드, 인덱스, 마이그레이션 영향을 정의합니다. 해당 없으면 명시합니다.

## Architecture constraints

- 유지해야 하는 기존 서비스 경계와 결정

## Acceptance criteria

1. 사용자가 확인할 수 있는 완료 조건
2. 자동 검증 가능한 완료 조건

## Verification

- 실행할 대상별 검사
- 여러 서비스에 영향이 있으면 `./scripts/check-all.sh`

## Documentation updates

- 계약이나 설계가 실제로 바뀌는 문서만 나열
```

## Completion

구현 완료 시 task 파일의 요구사항과 검증 결과를 확인한 뒤 상태를 갱신합니다. 요구사항 일부가 남았다면 `완료`로 표시하지 않고 남은 범위를 적습니다. 최종 보고는 `AGENTS.md`의 Definition of Done을 따릅니다.
