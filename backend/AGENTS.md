# Backend Agent Guide

**Scope**: Spring Boot, DB (MySQL, Flyway), Scheduler, API Contracts.

## Common Rules
항상 최상위 `AGENTS.md`의 규칙을 준수합니다.

## Validation Scope
- Backend 단독 변경: `./scripts/check-backend.sh`
- DB 마이그레이션 포함: `./scripts/check-integration.sh`

## Database Migration Rules (Flyway)
1. `backend/src/main/resources/db/migration`의 versioned migration은 한 번 적용되면 불변입니다.
2. 기적용된 `V<n>` 파일은 절대 수정하지 않습니다. 오류 보완도 새 migration 파일로 순방향 수정합니다.
3. 스키마 변경 작업은 통합 테스트와 `docs/database.md` 갱신 여부를 확인합니다.
4. 파괴적 작업(DROP, DELETE 남발)은 금지합니다.

## Dependencies & External Calls
1. 외부 공공데이터/유료 API 자동 호출을 금지합니다. 호출이 필요하면 URL/query를 마스킹하여 사용자에게 보여주고 승인을 받으세요.
2. 불필요한 라이브러리(포트폴리오용 복잡성)를 추가하지 마세요.
3. React는 Spring Boot만 호출합니다. Spring Boot는 메인 API 엔드포인트입니다.
