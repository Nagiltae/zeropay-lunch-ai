# Task: FastAPI 이전 개인화 추천 기반 구축

## Status

완료. 2026-09-17에 현재 로컬 Harness의 `./scripts/check-all.sh` 전체 검증이 통과했습니다. FastAPI HTTP 연동, LLM과 Qdrant 검색은 계획 범위로 남아 있습니다.

## Goal

FastAPI와 실제 AI 모델을 연결하기 전에 사용자 취향, 최근 식사 기록, 결정론적 음식점 후보 필터, 내부 AI 계약과 장애 대체 정책을 React와 Spring Boot에 완성합니다.

## Background

작성 당시 추천은 사용자 메시지와 위치만 사용했습니다. 현재는 MySQL이 소유하는 취향과 식사 기록, Spring Boot가 강제하는 필수 조건과 FastAPI 연동에 사용할 Java 구조화 계약까지 구현되었습니다.

## In scope

- 사용자 취향 조회·저장 API와 React 설정 화면
- 사용자가 추천 카드에서 `먹었어요`를 눌렀을 때만 생성되는 식사 기록
- 추천 컨텍스트에서 최근 72시간 식사 기록만 사용
- 모든 음식점 후보에 제로페이 가능 조건 강제
- 사용자 취향과 최근 식사를 반영한 결정론적 후보 필터 및 순위
- Spring Boot 내부 AI 의도 분석 계약, 임시 분석기와 fallback 경계
- FastAPI 클라이언트 타임아웃·재시도·fallback 설정 계약
- 관련 테스트, 통합 검사와 문서

## Out of scope

- FastAPI 추천 또는 자연어 분석 엔드포인트 구현
- LLM, 임베딩, Qdrant 검색
- 실제 음식점 데이터 적재
- 음식 재료 데이터가 필요한 알레르기 자동 필터
- MongoDB 도입

## Functional requirements

1. 제로페이 가능 음식점만 후보가 될 수 있으며 사용자 설정으로 해제할 수 없습니다.
2. 사용자는 선호·비선호 카테고리, 알레르기, 기본 예산과 매운맛 선호를 저장할 수 있습니다.
3. 선호와 비선호 카테고리는 동시에 선택할 수 없습니다.
4. 식사 기록은 추천 카드의 `먹었어요` 버튼을 누른 경우에만 저장합니다.
5. 추천하지 않은 음식점이나 다른 사용자의 추천 메시지는 식사 기록으로 저장할 수 없습니다.
6. 같은 추천 메시지와 음식점의 식사 기록 요청은 중복 생성하지 않습니다.
7. 추천 컨텍스트와 최근 식사 API는 현재 시각 기준 최근 72시간만 사용합니다.
8. 최근에 먹은 음식점과 비선호 카테고리는 추천 후보에서 제외합니다.
9. 메시지에 예산이 없으면 사용자 기본 예산을 사용하고 선호 카테고리는 결정론적 점수에 반영합니다.
10. 실제 FastAPI 클라이언트가 없거나 실패하면 설정된 정책에 따라 임시 결정론적 분석기를 사용합니다.

## API contract

- `GET /api/preferences/me`
- `PUT /api/preferences/me`
- `GET /api/meals/recent`
- `POST /api/meals`
- Spring Boot 내부 `IntentAnalysisRequest` / `AnalyzedIntent` 계약

## Data model impact

- `user_preferences`
- `user_preferred_categories`
- `user_disliked_categories`
- `user_allergies`
- `meal_history`

Flyway V3 마이그레이션으로 추가합니다.

## Architecture constraints

- React는 Spring Boot만 호출합니다.
- MySQL과 Spring Boot가 취향, 식사 기록, 제로페이·영업 여부·가격과 최종 순위를 소유합니다.
- FastAPI는 MySQL에 직접 접근하지 않습니다.
- LLM이 제로페이 필수 조건이나 강남구 범위를 완화할 수 없습니다.

## Acceptance criteria

1. 취향 설정을 저장하고 새로고침 후 복구할 수 있습니다.
2. 추천 카드에 식사 기록 안내와 `먹었어요` 버튼이 표시됩니다.
3. 저장된 최근 식사가 API와 이후 추천에서 반영됩니다.
4. 제로페이 불가 샘플 음식점은 어떤 요청에도 추천되지 않습니다.
5. 내부 AI 계약과 fallback 동작이 자동 테스트됩니다.
6. `./scripts/check-all.sh`가 통과합니다.

## Verification

- `./scripts/check-backend.sh`
- `./scripts/check-frontend.sh`
- `./scripts/check-integration.sh`
- `./scripts/check-all.sh`

## Documentation updates

- `docs/api-contract.md`
- `docs/database.md`
- `docs/architecture.md`
- `docs/ai-flow.md`
- `docs/testing.md`
- `docs/deployment.md`
