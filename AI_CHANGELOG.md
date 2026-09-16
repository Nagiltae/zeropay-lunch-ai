# AI Agent Work History

이 파일은 AI 에이전트들이 작업한 내역과 시스템 변경 사항을 기록하여, 이후에 투입되는 다른 에이전트가 프로젝트 문맥을 빠르게 파악할 수 있도록 돕는 파일입니다.

새로운 작업을 완료할 때마다 이 파일의 최상단에 작업 내역을 추가합니다.

## [2026-09-17] Harness 학습 설명과 저장소 기반 학습 가이드 추가
- 핵심 정책·계약·환경 문서에 Harness Role, Agent Usage, Why와 Connection 관점의 짧은 설명 추가
- setup과 모든 check script에 실행 시점, 실패 방지 목적과 연결 관계를 설명하는 주석 추가
- 현재 실제 파일, 추천 읽기 순서, Agent 실행 흐름, feedback loop, guardrail과 애플리케이션 코드의 구분을 `docs/harness-study.md`에 정리
- 실행 명령, 설정값과 비즈니스 로직은 변경하지 않음

## [2026-09-17] 현재 코드 기준 로컬 Harness 정합성 개선
- **문서·명세**: 인증, 개인화, 식사 기록과 현재 FastAPI/Qdrant 미연동 상태를 README, 아키텍처, 배포, 테스트 및 task 상태에 반영
- **Flyway 안전성**: 적용된 V1~V3 불변과 이후 스키마 변경 시 신규 migration 추가 규칙을 Agent 정책과 DB 문서에 명시
- **Docker**: Spring Boot의 미사용 FastAPI 시작 의존성과 FastAPI의 미사용 Qdrant 시작 의존성을 제거하고 환경변수 설명을 실제 Compose 동작과 일치시킴
- **검증**: tracked 변경 전체와 untracked 텍스트 파일의 공백 검사를 추가하고 Java compiler lint를 warning-as-error로 적용
- **프런트엔드 테스트**: 선호·비선호 상호 배제·저장과 명시적 `먹었어요` 흐름의 jsdom 컴포넌트 테스트 추가
- **검증 결과**: `./scripts/check-all.sh`의 Format, Lint, Frontend, Backend, AI, Integration 전체 통과
- **제외 범위**: 사용자 지시에 따라 GitHub Actions 및 CI/CD는 후속 작업으로 유지

## [2026-09-17] FastAPI 이전 개인화 추천 기반 완성
- **정책 결정**: 제로페이는 선택 설정이 아닌 모든 추천의 필수 조건이며, 식사 기록은 사용자가 `먹었어요`를 누를 때만 생성하고 최근 72시간만 추천에 사용
- **백엔드**:
  - 사용자 기본 예산, 매운맛, 선호·비선호 카테고리와 알레르기 저장 API 구현
  - 추천 메시지 소유권을 검증하는 멱등 식사 기록 API와 Flyway V3 스키마 구현
  - `RecommendationContextService`가 취향과 최근 식사를 조립하고 예산·비선호·최근 식사·제로페이 조건을 결정론적 추천에 반영
  - `AiIntentAnalyzer`, 내부 요청·응답 계약, 임시 분석기와 장애 fallback 경계 구현
  - FastAPI 연결·응답 timeout, 최대 시도와 fallback 환경설정 계약 추가
- **프런트엔드**:
  - React Query 기반 취향 설정 화면과 저장 기능 구현
  - 추천 카드에 최근 3일 반영 안내와 `먹었어요` 버튼 및 기록 상태 표시
- **검증**:
  - 취향, 72시간 식사 범위, 추천 소유권, 제로페이 강제, 개인화 필터와 fallback 자동 테스트 추가
  - Docker 통합 검사에 취향 저장과 명시적·멱등 식사 기록 흐름 추가
- **제외 범위**: FastAPI 의도 분석 엔드포인트, 실제 HTTP 클라이언트, LLM과 Qdrant 검색은 다음 단계

## [2026-09-17] 인증·세션 보안 경계 및 검증 보완
- **목표**: 최초 인증 구현 검토에서 확인된 대화 소유권 누락, 세션 고정 방어 누락과 불완전한 통합 검사를 보완
- **백엔드**:
  - 모든 대화 API를 로그인 필수로 제한하고 서비스 계층에서 `conversations.user_id` 소유권 검증
  - 로그인 성공 시 `ChangeSessionIdAuthenticationStrategy`로 세션 ID 교체 후 보안 컨텍스트 저장
  - 중복 이메일을 `409 EMAIL_ALREADY_IN_USE`로 변환하고 인증 입력 길이 및 BCrypt 72바이트 제한 검증
  - 인증·세션 교체·대화 소유권 통합 테스트 추가
- **프런트엔드**:
  - 인증 확인 전 저장된 대화 이력 요청을 차단하고 로그아웃 시 메모리와 localStorage의 대화 상태 제거
  - 인증 API의 CSRF 헤더, 401 처리와 로그아웃 요청 테스트 추가
  - 임시 렌더링 로그 제거
- **검증 하네스**:
  - 임시 Puppeteer 프로젝트와 고정 `/tmp/cookies.txt` 제거
  - 통합 검사를 실제 회원가입→로그인→세션→대화 소유자 DB 저장→타 사용자 접근 거부→로그아웃 흐름으로 확장
- **문서화**: API 인증 조건, 대화 소유권, 세션 고정 방어와 통합 테스트 범위를 관련 문서에 반영

## [2026-09-17] 프런트엔드 인증 가드 무한 루프 버그 수정
- **목표**: 프런트엔드 초기 진입 시 "로딩 중..." 화면에서 무한 루프에 빠지는 이슈 해결
- **문제 원인**: React Query v5 환경에서, 인증되지 않은 상태(401 에러)일 때 렌더링된 `AuthScreen` 컴포넌트가 전역 훅인 `useAuth`를 다시 호출하면서 만료된(stale) 쿼리의 재요청을 유발. 이로 인해 로딩 상태(`isPending`)가 계속 `true`로 바뀌어 `App` 컴포넌트가 `AuthScreen`을 언마운트하고 다시 "로딩 중..."을 렌더링하는 현상이 초당 수천 번 발생(Nginx 502/401 무한 요청).
- **해결 방안**:
  - `frontend/src/hooks/useAuth.ts` 파일을 분리.
  - 전역 인증 상태를 조회하는 역할은 `useCurrentUser`로 분리하여 `App.tsx`에서만 호출하도록 변경.
  - 로그인/회원가입 등의 사이드 이펙트(Mutation) 기능은 `useAuthMutations`로 분리하여 `AuthScreen.tsx`에서만 호출하도록 변경.
- **결과**: 브라우저 렌더링 무한 루프 해결 및 정상적인 로그인/회원가입 모달 노출 확인. 프런트엔드 컨테이너 리빌드 완료.

## [2026-09-17] 사용자 인증 및 세션 시스템 구현
- **목표**: 사용자를 식별하여 개인화된 AI 추천을 제공하기 위한 기반 마련
- **백엔드 (Spring Boot)**
  - `User`, `UserCredentials` JPA 엔티티 및 DB 마이그레이션(V2) 작성
  - Spring Session JDBC 연동 및 MySQL 기반 세션 스토리지 적용
  - Spring Security를 활용하여 폼/베이직 인증 비활성화, `/api/auth/signup, login, logout, me, csrf` 엔드포인트 구현
  - `CookieCsrfTokenRepository` 설정 및 React 등 SPA 호환성을 위한 `CsrfTokenRequestAttributeHandler` 패치
  - `Conversation` 엔티티에 인증된 `userId`를 매핑하도록 구조 변경
- **프런트엔드 (React)**
  - `@tanstack/react-query`를 통한 전역 인증 상태(`useAuth`) 구현
  - `fetchWithAuth` API 래퍼를 통해 모든 요청 시 자동으로 `X-XSRF-TOKEN` 헤더와 인증 쿠키를 주입하도록 구성
  - `AuthScreen` 컴포넌트(로그인/회원가입 모달) 제작 및 `App.tsx` 인증 가드(미인증 시 채팅 제한) 적용
- **DevOps / Testing**
  - 통합 테스트 스크립트(`check-integration.sh`)에서 CSRF 토큰을 미리 발급받아 POST 요청 시 헤더에 첨부하도록 보강하여 통과 확인.
- **문서화**: `docs/api-contract.md`, `docs/database.md`, `docs/architecture.md`에 변경 사항 갱신 완료.
