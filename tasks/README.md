# Task specifications

`tasks/`는 에이전트가 긴 대화 없이도 범위와 완료 조건을 이해해야 하는 비자명 작업의 실행 명세를 보관합니다.

## File naming
- 소문자 kebab-case를 사용합니다.
- 기능과 결과가 드러나는 이름을 사용합니다.
- 예: `chat-message-persistence.md`, `gangnam-restaurant-import.md`

## Template
아래 템플릿을 복사하고 해당 없는 절은 생략합니다.

```markdown
# Goal
작업의 최종 목적

# Scope
이번 작업에서 변경/개발할 범위

# Read First
- 작업에 필요한 문서만 나열하여 Agent가 무조건 전체를 탐색하지 않게 방지합니다.
- 예: `backend/AGENTS.md`, `docs/database.md`

# Constraints
- 아키텍처 제약, API 계약 등 반드시 지켜야 할 사항

# Definition of Done
- 사용자가 확인할 수 있는 완료 조건

# Validation
- 실행할 대상별 검사 (`./scripts/check-*.sh`)

# Report
- 작업 완료 시 보고할 항목
```
