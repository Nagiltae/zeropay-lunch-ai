# AI Agent Guide

**Scope**: FastAPI, LLM, Vector DB (Qdrant), LangGraph, Data processing logic.

## Common Rules
항상 최상위 `AGENTS.md`의 규칙을 준수합니다.

## Validation Scope
- AI 단독 변경: `./scripts/check-ai.sh` (Poetry 환경, Ruff, Pytest)

## Core Rules
1. FastAPI는 AI 워크플로와 LLM 연동만 담당합니다. 비즈니스 원천 데이터(영업 여부, 가격, 제로페이 가맹 여부 등)의 결정론적 로직은 Backend로 넘기거나 위임하세요.
2. LLM 출력을 프로그램 로직에 사용할 경우 반드시 검증된 구조화 스키마를 사용하세요.
3. 서울특별시 강남구 지역으로 대상을 한정합니다.
4. AI 처리 단계 변경 시 `docs/ai-flow.md`를 업데이트하세요.
