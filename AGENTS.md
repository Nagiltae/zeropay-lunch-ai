# ZeroPay Lunch AI Agent Guide

이 파일은 이 저장소에서 작업하는 코딩 에이전트의 정책 진입점입니다. 세부 설계는 관련 문서를 필요한 범위만 읽고 확인합니다.

## Harness study note

- **Harness Role:** 모든 Agent가 공유하는 작업 절차, 안전 경계와 완료 조건의 단일 기준입니다.
- **Agent Usage:** 어떤 작업이든 수정 전에 가장 먼저 읽고, 최종 보고 전에 Definition of Done을 다시 확인합니다.
- **Why:** 이 기준이 없으면 Agent마다 아키텍처, 검증 범위와 완료 판단이 달라질 수 있습니다.
- **Connection:** `tasks/`와 관련 `docs/`로 읽기 범위를 좁히고, `scripts/check-*.sh`로 구현 결과를 검증합니다.

## Project purpose

ZeroPay Lunch AI는 사용자의 자연어 요청, 취향, 예산, 위치, 최근 식사 기록을 바탕으로 서울특별시 강남구의 음식점을 추천하는 서비스입니다.

고정된 호출 경로는 다음과 같습니다.

```text
React -> Spring Boot -> FastAPI
```

Spring Boot는 공개 API와 비즈니스 데이터 및 결정론적 로직을 소유합니다. FastAPI는 자연어 분석, 검색 워크플로, LLM 호출과 추천 설명처럼 AI에 특화된 기능을 소유합니다.

## Agent workflow

1. 이 파일을 먼저 읽습니다.
2. 요청과 관련된 문서 및 `tasks/` 명세가 있으면 해당 파일을 읽습니다.
3. 수정 전에 현재 구현과 작업 트리 상태를 확인합니다.
4. 큰 변경은 범위, 계약, 검증 계획을 먼저 설명합니다.
5. 관련 없는 코드를 건드리지 않고 작게 구현합니다.
6. 가장 좁은 관련 검사를 먼저 실행합니다.
7. 실패 원인을 확인하고 수정한 뒤 같은 검사를 다시 실행합니다.
8. 여러 서비스나 공통 실행 환경에 영향을 주면 `./scripts/check-all.sh`를 실행합니다.
9. 작업을 완료하면 다른 에이전트가 문맥을 이어받을 수 있도록 `AI_CHANGELOG.md` 최상단에 수행한 작업과 변경 사항을 기록합니다.
10. 최종 Git diff를 검토하고 변경, 검증, 미해결 사항을 보고합니다.

코드를 작성했다는 사실만으로 작업을 완료했다고 판단하지 않습니다. 적용 가능한 검증 결과가 완료 판단의 근거입니다.

## Documentation map

- 아키텍처와 서비스 책임: `docs/architecture.md`
- 공개 및 내부 API 계약: `docs/api-contract.md`
- MySQL과 Qdrant 데이터 정책: `docs/database.md`
- AI 추천 처리 흐름: `docs/ai-flow.md`
- 코딩 및 상태 관리 규칙: `docs/conventions.md`
- 실행과 배포: `docs/deployment.md`
- 검증과 통합 테스트 단계: `docs/testing.md`
- Harness 학습 가이드: `docs/harness-study.md`
- 비자명 작업 명세: `tasks/README.md` 및 해당 task 파일

## Core rules

1. React는 Spring Boot만 호출하며 FastAPI를 직접 호출하지 않습니다.
2. Spring Boot는 메인 애플리케이션 백엔드이자 외부 서비스 진입점입니다.
3. FastAPI는 AI 워크플로와 LLM 연동을 담당합니다.
4. 거리, 가격, 영업 여부, 제로페이 여부, 정확한 필터와 최종 순위는 애플리케이션 코드와 데이터베이스에서 결정합니다.
5. LLM 출력을 프로그램 로직에 사용할 때는 검증된 구조화 스키마를 사용합니다.
6. 서비스 대상 위치와 음식점 데이터는 서울특별시 강남구로 제한합니다.
7. API, 데이터베이스, 아키텍처, 인증 또는 프레임워크를 조용히 변경하지 않습니다. 요청 범위를 넘어서는 결정은 먼저 사용자와 논의합니다.
8. 실제 필요가 없는 의존성이나 포트폴리오용 복잡성을 추가하지 않습니다.
9. 새 패턴을 추가하기 전에 기존 코드와 규칙을 확인합니다.
10. 사용자의 기존 작업과 관련 없는 파일을 수정하거나 되돌리지 않습니다.

## Database migration rules

- `backend/src/main/resources/db/migration`의 versioned migration은 한 번 적용되면 불변입니다.
- 현재 적용 기준인 `V1`, `V2`, `V3` 파일은 수정하지 않습니다.
- 스키마 변경은 항상 다음 번호의 새 `V<n>__<description>.sql` migration으로 추가합니다.
- 과거 migration의 오류를 보완할 때도 파일을 고쳐 쓰지 않고 새 migration에서 순방향으로 수정합니다.
- sample repeatable migration은 스키마 변경 용도로 사용하지 않습니다.
- DB 변경 작업은 실제 MySQL을 사용하는 통합 검사와 `docs/database.md` 갱신 여부를 확인합니다.

## Documentation updates

계약이나 설계가 실제로 바뀐 문서만 같은 변경에서 갱신합니다.

- API 요청, 응답 또는 SSE 이벤트 변경: `docs/api-contract.md`
- 테이블, 엔티티, 데이터 소유권 또는 스키마 변경: `docs/database.md`
- 서비스 책임이나 호출 경로 변경: `docs/architecture.md`
- AI 단계, 모델 출력 또는 대체 처리 변경: `docs/ai-flow.md`
- 실행, 환경변수, 컨테이너 또는 배포 변경: `docs/deployment.md`
- 개발 규칙 변경: `docs/conventions.md`

오타 수정이나 내부 구현 세부사항만으로 관련 없는 설계 문서를 갱신하지 않습니다.

## Verification

신규 환경 준비:

```bash
./scripts/setup.sh
```

대상별 검사:

```bash
./scripts/check-format.sh
./scripts/check-lint.sh
./scripts/check-frontend.sh
./scripts/check-backend.sh
./scripts/check-ai.sh
./scripts/check-integration.sh
```

최종 전체 검사:

```bash
./scripts/check-all.sh
```

- 프런트엔드만 변경했으면 프런트엔드 관련 검사부터 실행합니다.
- 백엔드만 변경했으면 Gradle wrapper 기반 검사를 실행합니다.
- AI만 변경했으면 Poetry 환경에서 Ruff와 Pytest를 실행합니다.
- 여러 서비스, API 경계, Docker 또는 공통 스크립트가 바뀌면 전체 검사를 실행합니다.
- 통합 검사는 Docker 엔진과 실행 가능한 Compose 환경을 요구합니다.
- 필요한 런타임이나 외부 환경이 없어 검사를 실행하지 못했다면 통과했다고 보고하지 않습니다.

## Safety / change boundaries

명시적인 승인 없이 다음 작업을 하지 않습니다.

- 데이터베이스, Docker 볼륨 또는 사용자 데이터를 삭제
- 파괴적 SQL 실행
- 운영 자격 증명이나 클라우드 인프라 변경
- 비밀정보를 출력하거나 저장소에 추가
- 인증 또는 입력 검증 약화
- 실패를 숨기기 위해 테스트를 삭제하거나 비활성화
- `--force`, `git reset --hard`, `git checkout --` 등 파괴적인 Git 작업 실행
- 관련 없는 대규모 코드 재작성
- Kubernetes, Redis, 별도 태스크 러너나 모노레포 도구 도입

작업을 완료하려면 이러한 변경이 꼭 필요할 경우 중단하고 이유와 영향을 설명한 뒤 명시적인 승인을 요청합니다.

## Definition of Done

코딩 작업은 적용 가능한 다음 항목을 모두 만족해야 완료입니다.

1. 요청된 동작이 구현되었습니다.
2. 작업이 명시적으로 변경하지 않는 한 기존 아키텍처와 규칙을 유지했습니다.
3. 실용적인 범위에서 관련 테스트를 추가하거나 갱신했습니다.
4. 관련 검증 스크립트를 실행했습니다.
5. 여러 서비스에 영향을 주는 변경은 `./scripts/check-all.sh`를 실행했습니다.
6. 검증 실패를 무시하지 않고 원인을 조사했습니다.
7. 관련 없는 파일을 변경하지 않았습니다.
8. 계약이나 설계 변경에 해당하는 문서를 갱신했습니다.
9. 작업 내용을 `AI_CHANGELOG.md`에 기록했습니다.
10. `git status --short`와 최종 Git diff를 함께 검토하여 untracked 파일을 포함한 모든 변경을 확인했습니다.
11. 최종 보고에 다음 내용을 포함했습니다.
    - 무엇을 변경했는지
    - 변경한 파일과 이유
    - 실행한 검증 명령
    - 각 검증의 통과 또는 실패 여부
    - 미해결 문제와 실행하지 못한 검사

## Task specifications

여러 계층을 건드리거나 계약, 데이터 모델, 마이그레이션이 포함되는 비자명 작업은 `tasks/README.md` 템플릿을 사용해 범위와 완료 기준을 먼저 기록합니다. 단순 문구 수정이나 작은 로컬 리팩터링을 위해 task 파일을 만들지 않습니다.
