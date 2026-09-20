# Frontend Agent Guide

**Scope**: React, UI, Frontend Tests.

## Common Rules
항상 최상위 `AGENTS.md`의 규칙을 준수합니다.

## Validation Scope
- Frontend 단독 변경: `./scripts/check-frontend.sh`

## Core Rules
1. Frontend(React)는 Spring Boot만 호출합니다. FastAPI(AI)를 직접 호출하지 않습니다.
2. 새로운 패턴이나 라이브러리 추가 전 기존 규칙과 UI 구조를 확인하세요.
3. 관련 없는 컴포넌트를 무단으로 리팩터링하지 않습니다.
