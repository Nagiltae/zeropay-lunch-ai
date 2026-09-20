# 아키텍처

## When to read
- 새로운 서비스 추가
- 컴포넌트 간 책임(책임 경계) 변경
- 인프라 연결 흐름 파악


> **Harness Role:** 서비스 책임과 변경 금지 경계를 설명합니다. Agent는 여러 서비스의 호출 방향이나 데이터 소유권을 바꾸기 전에 읽습니다. 이 문서가 없으면 React가 FastAPI를 직접 호출하거나 AI가 결정론적 필터를 소유하는 식의 구조 이탈이 생길 수 있습니다. 세부 계약은 `api-contract.md`, 데이터 소유권은 `database.md`, 검증은 `testing.md`로 연결됩니다.

## 목표 서비스 경계

```text
브라우저
  -> React 프런트엔드
  -> Spring Boot 메인 백엔드
  -> FastAPI AI 서버
```

React는 FastAPI를 직접 호출하지 않습니다. Spring Boot는 공개 애플리케이션 API이며 인증, 비즈니스 규칙, 영속성, 외부 데이터 연동, AI 요청 컨텍스트 구성을 담당합니다. FastAPI는 향후 Spring Boot에 내부 AI 기능을 제공합니다. 현재는 FastAPI health endpoint만 있으며 Spring Boot에서 FastAPI를 호출하는 HTTP 클라이언트는 없습니다.

## 서비스 지역

서비스 지역은 서울특별시 강남구 논현동(`11680108`)으로 고정합니다. 사용자는 역이나 반경을 선택하지 않으며, 저장하고 추천하는 음식점 데이터도 논현동 모집단으로 제한합니다. 좌표는 향후 정렬·확장을 위한 metadata로 유지합니다.

## 책임

### 프런트엔드

- 자연어 추천 요청 입력
- 강남구 논현동 고정 추천 범위
- 추천 결과 표시
- 취향과 식사 기록 사용자 인터페이스
- Spring Boot API만 호출
- 사용자 취향 설정과 명시적인 `먹었어요` 식사 기록

### 메인 백엔드

- 사용자, 인증, 취향, 음식점과 식사 기록
- 트랜잭션 경계와 영속 데이터
- 가격, 영업시간, 제로페이 사용 가능 여부 등의 정확한 필터
- 결정론적 점수 계산과 순위 결정
- 외부 API 연동과 실패 처리
- AI 서버 요청 구성과 응답 검증
- 최근 72시간 식사 기록과 사용자 취향을 조합한 추천 컨텍스트
- 제로페이 필수, 영업 중, 예산, 비선호와 최근 식사 제외 등 결정론적 후보 필터

### AI 서버

- 자연어 의도를 분석해 검증된 구조화 데이터로 변환
- 의미 기반 검색과 AI 워크플로 조정
- LLM 호출과 추천 설명 생성
- 기능 성숙도에 따른 AI 전용 재시도, 대체 처리, 평가, 관측성 제공

### 데이터 저장소

- MySQL: 애플리케이션 원본 데이터와 결정론적 조회의 기준 저장소 (Spring Session의 세션 저장소 포함)
- Qdrant: MySQL 데이터에서 파생된 임베딩과 검색 메타데이터 저장
- Qdrant 데이터는 원본으로 취급하지 않으며 MySQL 데이터로 재생성 가능해야 함

## 인증 및 세션

- 인증 방식: Spring Security 기반 폼 로그인이 아닌 커스텀 REST API (`/api/auth/login`) 방식을 사용합니다.
- 세션 관리: 별도의 Redis 없이 Spring Session JDBC를 사용해 MySQL에 세션을 유지합니다. 브라우저와 통신하기 위해 세션 쿠키(`SESSION`)를 사용합니다.
- 보안 설정: 외부 공격(CSRF) 방어를 위해 쿠키 기반 CSRF 토큰(`XSRF-TOKEN`)을 발행하며 프런트엔드는 상태를 변경하는 모든 요청(POST, PUT, DELETE)에서 이를 헤더로 제출합니다.
- 인증 정보 저장 금지: React는 브라우저 저장소(localStorage 등)에 세션이나 비밀번호를 일절 저장하지 않으며, 현재 인증 상태는 React Query와 서버의 `/api/auth/me` 응답으로만 판단합니다.
- 대화 소유권: 모든 대화 API는 인증을 요구하며 Spring Boot 서비스 계층에서 현재 사용자와 `conversations.user_id` 일치를 검증합니다. 프런트엔드 화면 가드는 보안 경계로 사용하지 않습니다.
- 세션 고정 방어: 로그인 성공 시 Spring Security의 세션 인증 전략으로 기존 세션 ID를 교체한 뒤 보안 컨텍스트를 저장합니다.

## 현재 구현 범위

프런트엔드 채팅 화면, 논현동 고정 범위, 취향 설정, 명시적인 식사 기록과 SSE 추천 흐름이 구현되어 있습니다. Spring Boot는 MySQL에 사용자 취향과 식사 기록을 저장하고 논현동·영업·제로페이 조건을 적용합니다. 비선호 카테고리와 최근 72시간 내 먹은 음식점은 제외하고, 메시지 예산이 없으면 사용자 기본 예산을 사용합니다.

현재 자연어 처리는 `AiIntentAnalyzer` 경계 뒤의 제한된 임시 키워드 규칙입니다. 사용자 인증, 취향과 식사 기록, 논현동 고정 추천 범위가 구현되었습니다. Spring Boot는 KOMSCO 모바일 가맹점 OpenAPI에서 논현동 단일 법정동·I0000002·KSIC 561·계속사업자 범위를 수집해 MySQL에 멱등 적재하며, 최신 행 선택·필터·저장 책임을 분리합니다. 주간 scheduler는 Asia/Seoul 일요일 03:00에 실행되고, 전체 fetch 성공 시 사라진 기존 행은 삭제하지 않고 stale inactive 처리합니다.

KOMSCO 음식점의 Place ID와 상세 보강은 `ai/`의 KOMSCO-only Playwright PCMap pipeline이 소유합니다. 후보 DOM을 수집하고 deterministic safety/order, 필요 시 Ollama Qwen ranking, `data-nlog-params` Place ID 추출, `/home` semantic validation 후 HOME/MENU/REVIEW DOM을 수집합니다. NAVER Local API와 stored Local fallback은 신규 입력으로 사용하지 않습니다. `restaurant_naver_verifications`가 verification provenance를, `restaurant_external_places`가 성공한 외부 mapping을 보존합니다.

추천 가능 상태는 KOMSCO 원본 운영 상태(`restaurants.active`), NAVER verification, `recommendation_eligibility`, `recommendation_ready`로 분리합니다. 명확한 VERIFIED 음식점·논현동 결과만 eligibility를 ELIGIBLE로 갱신하며 불일치는 INELIGIBLE, 불확실·기술 오류는 UNKNOWN입니다. 메뉴·가격·영업시간이 보강되지 않은 KOMSCO import 행은 `recommendation_ready=false`라 추천 조회에 들어가지 않습니다.

주간 Scheduler는 `Asia/Seoul` 기준 일요일 새벽 3시에 실행됩니다. 기존 가맹점의 최신 사업자 상태와 서비스 범위를 확인해 `active`를 비활성화하거나 복구하고 동기화 시각을 갱신합니다. 현재 단일 Spring Boot 인스턴스를 전제로 하며 다중 인스턴스 배포 시에는 중복 실행을 막는 분산 lock을 별도 설계해야 합니다.

KOMSCO 원본에는 메뉴, 가격과 영업시간이 없으므로 import 행은 `recommendation_ready=false`로 저장됩니다. 현재 추천 흐름은 추천 정보와 영업 일정이 갖춰진 행만 조회합니다. FastAPI 의도 분석 endpoint와 Spring HTTP 클라이언트, LLM, Qdrant 검색과 LangGraph는 아직 구현되지 않았습니다.

## 데이터 소유권

MySQL은 애플리케이션 데이터의 기준 저장소입니다. Qdrant는 파생 임베딩과 검색 메타데이터를 저장하며, 원본 데이터의 기준인 MySQL을 대체하지 않습니다.
