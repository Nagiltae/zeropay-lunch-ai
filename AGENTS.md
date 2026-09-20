# ZeroPay Lunch AI Agent Guide

**Project**: ZeroPay Lunch AI (자연어, 취향, 예산을 바탕으로 강남구 음식점을 추천)
**Architecture**: React -> Spring Boot (API & DB) -> FastAPI (LLM & Qdrant)

## Core Safety Rules (절대 규칙)
1. **사용자 환경 보호**: 사용자 데이터, DB, Docker 볼륨 삭제 금지. `--force`, `git reset` 등 파괴적 Git 작업 금지.
2. **Secret 금지**: 실제 API 키, 인증 정보를 출력하거나 코드에 포함하지 마.
3. **Database**: Flyway 기적용 `V<n>` 마이그레이션 파일 수정 금지. 스키마 변경은 반드시 새 파일로 작성.
4. **선택적 탐색**: 모든 문서를 기본적으로 읽지 마. 작업과 관련 없는 코드를 수정하거나 탐색하지 마.
5. **승인 우선**: API, DB, 아키텍처, 인증 무단 변경 금지. 확신이 안 서면 사용자와 먼저 논의.
6. **테스트 보호**: 실패를 피할 목적으로 테스트를 무단 삭제, 비활성화(skip)하거나 검증(assertion)을 약화하지 마. 변경 시 정당한 사유가 필수.

## Agent Exploration & Output Policy
- **선택적 읽기**: Repository 전체 탐색 금지. `tasks/<task-name>.md`의 `# Read First` 지정 문서만 읽어.
- **On-Demand Context**: `docs/` 파일들은 파일 상단의 `## When to read` 조건에 맞을 때만 읽어.
- **출력 최소화**: `cat` 전체 출력, 긴 로그, 대규모 CSV, 전체 Git diff 출력을 피해. (핵심 요약, `tail`, `grep` 우선)
- **최소 충분 검증**: Backend/Frontend/AI 중 변경된 영역에 해당하는 `./scripts/check-*.sh`만 실행. 다중 변경일 때만 `check-all.sh`.
- **반복 최소화**: 한 번 파악한 설계는 다시 묻지 말고 워킹 메모리로 유지. 동일 명령 재실행 최소화.

## Documentation Map
작업 영역에 따라 아래 AGENTS.md 및 문서를 추가로 읽어:
- **[Backend]**: `backend/AGENTS.md` (Spring Boot, DB, Scheduler)
- **[Frontend]**: `frontend/AGENTS.md` (React, UI)
- **[AI]**: `ai/AGENTS.md` (FastAPI, LLM, Vector DB)
- **[Architecture]**: `docs/architecture.md`
- **[Database]**: `docs/database.md`
- **[Changelog]**: `AI_CHANGELOG.md` (과거 이력이 명시적으로 필요할 때만 참조)

## Definition of Done & Report
작업 완료 시 `AI_CHANGELOG.md` 최상단에 변경 사항을 요약하고, 다음 짧은 포맷으로 보고해:

```markdown
## Changed
(핵심 변경 3~7개)
## Validation
(실행한 검증과 패스 여부)
## Risk
(문제나 수동 확인이 필요할 때만)
## Remaining
(남은 일이 있을 때만)
```
*(장황한 서론, 코드 설명, 테스트 전체 로그는 생략할 것)*
