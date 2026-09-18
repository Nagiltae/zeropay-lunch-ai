# AI Agent Work History

이 파일은 AI 에이전트들이 작업한 내역과 시스템 변경 사항을 기록하여, 이후에 투입되는 다른 에이전트가 프로젝트 문맥을 빠르게 파악할 수 있도록 돕는 파일입니다.

새로운 작업을 완료할 때마다 이 파일의 최상단에 작업 내역을 추가합니다.

## [2026-09-19] NAVER Local 최초 전체 3,272건 매칭
- **실행 승인**: MATCHED 20건 인간 검토 후 사용자의 명시적 승인으로 `--all` 1회 실행; 주 1회 Scheduler는 미구현·미활성
- **실행 결과**: processed 3,272, MATCHED 1,982, AMBIGUOUS 163, UNMATCHED 1,127, API_ERROR 0; inserted 3,172, updated 100, skipped 0
- **추천 상태**: ELIGIBLE 1,939, INELIGIBLE 0, UNKNOWN 1,333; MATCHED+UNKNOWN 43건은 현재 category 정책에서 음식점임을 확정할 수 없어 추천에서 제외
- **무결성**: NAVER 3,272행/서로 다른 restaurant 3,272건, duplicate 0, 명시적 비음식점 category+ELIGIBLE 0, 모든 마지막 API 시도 SUCCESS
- **KOMSCO 보존**: 원본 필드 checksum이 실행 전·후 `XOR=1973841089`, `SUM=6969399285795`로 일치
- **리포트**: 전체 `backend/build/reports/naver-enrichment/naver-all-20260919-033129.csv`, 복합 위험 상위 50건 `naver-full-review-20260919-033129.csv`

## [2026-09-19] Restaurant 추천 가능 상태 분리
- **상태 설계**: KOMSCO 원본을 유지하면서 `restaurants.recommendation_eligibility`에 ELIGIBLE/INELIGIBLE/UNKNOWN을 저장하는 Flyway V7 추가
- **공유 정책**: NAVER category를 FOOD/NON_FOOD/UNKNOWN으로 분류하는 정책을 Candidate Hard Gate와 추천 가능 판정에서 공유
- **추천 안전성**: 추천 repository는 기존 `recommendation_ready` 조건과 함께 ELIGIBLE만 반환하고, KOMSCO 매칭 입력 변경·API_ERROR는 UNKNOWN으로 되돌림
- **실제 100건 재실행**: 사용자 승인 후 MATCHED 60, AMBIGUOUS 8, UNMATCHED 32, API_ERROR 0; ELIGIBLE 60, INELIGIBLE 0, UNKNOWN 40
- **DB 검증**: NAVER enrichment 100행/서로 다른 restaurant 100건으로 중복 없음; 전체 3,272건은 실행하지 않음
- **검토 리포트**: `backend/build/reports/naver-enrichment/naver-validation-20260919-030231.csv`, MATCHED 20건 `naver-matched-review-20260919-030231.csv`
- **검증**: eligibility/category/repository/writer/report 회귀 테스트, `./scripts/check-backend.sh`, `./scripts/check-all.sh` 통과

## [2026-09-19] NAVER Matching false-positive Hard Gate 보정
- **근거 분석**: 기존 MATCHED 중 주소 점수 25 미만 20건은 거리 30m 이내 15건, 30~50m 3건, 50m 초과 2건으로 확인
- **거리 결정**: 기존 최고 거리점수 경계와 실제 분포를 근거로 strong evidence 거리 기준을 50m로 선택; 기존 300m 후보 제외는 유지
- **Candidate Hard Gate**: 명시된 NAVER category가 음식점 계열이 아니거나 이름 점수가 22점 미만인 후보를 점수 경쟁에서 제외
- **MATCHED Gate**: 기존 70점·runner-up gap 8점에 더해 주소 25점 이상 또는 이름 32점 이상+50m 이내를 요구하고, 근거가 부족하면 AMBIGUOUS 처리
- **정책 유지**: 기존 이름/주소/거리/category 40/30/20/10 가중치와 viable 45점은 변경하지 않음
- **오프라인 재평가**: API 재호출 없이 기존 100건 CSV/DB로 MATCHED 63→59, AMBIGUOUS 9→8, UNMATCHED 28→33 확인
- **핵심 사례**: 수미초밥 MATCHED→AMBIGUOUS, 구야네·열린약국 MATCHED→UNMATCHED; 수미초밥과 구야네를 실제 값 기반 회귀 테스트로 고정
- **실행 범위**: 전체 3,272건 NAVER 호출 및 기존 DB status 일괄 갱신은 수행하지 않음

## [2026-09-19] NAVER Local 100건 검증·증분 갱신 기반
- **검증 표본**: 활성 KOMSCO 음식점을 법정동 코드별 ID 순서로 round-robin 선택해 14개 동이 7~8건씩 포함되는 deterministic 100건 모드 구현
- **판정 근거**: 기존 40/30/20/10점, MATCHED 70점, gap 8점, 300m 기준은 유지하고 점수 breakdown, runner-up, gap, 실제 query를 DB와 CSV에 기록
- **정규화 보강**: HTML·공백·특수문자·괄호·띄어쓰기 차이를 정리하고 양쪽의 명시적 프랜차이즈 지점명이 다르면 후보에서 제외
- **실행 안전성**: 검증 `--limit=100`, 제한 증분 `--incremental --limit=<n>`, 명시적 전체 `--all`을 분리하고 순차 호출·timeout·제한 retry 유지
- **증분 정책**: enrichment 부재, 상호·주소·좌표 등 source hash 변경, 상태별 retry 도래, MATCHED refresh TTL 만료만 재조회; KOMSCO sync는 변경 ID를 반환하되 NAVER를 자동 호출하지 않음
- **장애 보존**: `API_ERROR` 시도 상태와 다음 retry를 분리하고 기존 정상 MATCHED 후보·점수·동기화 시각은 유지
- **DB**: V1~V5를 유지하고 V6에 점수 상세, source hash, 마지막 시도 상태·시각, 다음 retry 시각 및 조회 index 추가
- **실제 검증**: 사용자 승인 100건에서 MATCHED 63, AMBIGUOUS 9, UNMATCHED 28, API_ERROR 0; 80건 insert, 기존 20건 update, restaurant/provider 중복 0
- **리포트**: `backend/build/reports/naver-enrichment/naver-validation-20260919-023530.csv`에 header 포함 101행 생성
- **검증**: `./scripts/check-backend.sh`, `./scripts/check-all.sh` 전체 통과, 실제 MySQL Flyway V6 적용 및 기존 NAVER 20행 보존 확인

## [2026-09-18] NAVER Local 음식점 매칭 및 보강
- **외부 연동**: NAVER API HUB 지역 검색을 opt-in 수동 runner로 연결하고 활성 KOMSCO 음식점을 기본 20개까지만 순차 처리
- **검색 정책**: `상호명+법정동`과 제한된 `상호명+강남구` fallback, 검색당 최대 5개 후보, 429·5xx 제한 재시도와 401/403 fast-fail 적용
- **결정론적 매칭**: HTML/공백 상호 정규화, 주소 토큰, Haversine 거리와 음식점 category를 100점 정책으로 합산해 MATCHED/AMBIGUOUS/UNMATCHED 분류
- **좌표 호환**: 실제 API 진단에서 확인한 WGS84 `10^7` 배율 정수와 소수점 좌표를 모두 decimal degree로 변환
- **DB**: 기존 V1~V4를 유지하고 V5 `restaurant_external_places`를 추가해 KOMSCO 원본과 NAVER 보강을 분리; `(restaurant_id, provider)` unique upsert 적용
- **환경**: 기존 `.env`의 `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`을 local 프로세스 또는 Compose가 주입하며 기본 실행은 비활성
- **실제 검증**: 사용자 승인 범위 20건에서 MATCHED 14, AMBIGUOUS 2, UNMATCHED 4, API 실패 0; 수정 전 생성된 같은 20행을 전부 update해 총 20행/음식점 20개 유지
- **자동 검증**: NAVER 파싱, nullable, 정규화, 좌표, 거리, 후보 선택, 상태 판정, fallback, 장애 격리, 인증 실패와 idempotent upsert 테스트 추가; `check-backend.sh`와 최종 `check-all.sh` 통과

## [2026-09-18] KOMSCO 음식점 일일 동기화 Scheduler 추가
- **실행 시간**: Spring Scheduler가 `Asia/Seoul` 기준 매일 새벽 3시에 승인된 KOMSCO 강남구 전체 조회를 실행
- **상태 동기화**: 기존 행은 매 실행마다 `last_synced_at`, `updated_at`과 원본 필드를 갱신하고, 계속사업자·KSIC 561·강남구·제공기관 조건에서 벗어나면 `active=false`, 다시 만족하면 `active=true`로 복구
- **신규 데이터**: 모든 저장 조건을 만족하는 신규 `alt_text`만 삽입하고, 응답에서 완전히 사라진 ID는 임의 비활성화하지 않음
- **장애 안전성**: 전체 pagination·최신화 성공 후에만 DB 동기화를 시작하며 API 실패 시 기존 DB를 유지
- **설정**: `KOMSCO_SCHEDULER_ENABLED`, `KOMSCO_SCHEDULER_CRON`, `KOMSCO_SCHEDULER_ZONE`을 추가하고 Docker Compose에서 기본 활성화
- **검증**: Scheduler 위임·오류 격리, timestamp 갱신, 비활성화·재활성화와 과거 데이터 보호 테스트 추가
- **검증 결과**: `./scripts/check-backend.sh`, `./scripts/check-all.sh` 전체 통과 및 실행 중 컨테이너에서 `enabled=true`, `cron=0 0 3 * * *`, `zone=Asia/Seoul` 확인

## [2026-09-18] KOMSCO 강남구 음식점 원본 import 구현
- **외부 수집**: 한국조폐공사 모바일 가맹점기본정보 API를 14개 강남구 법정동별로 끝까지 pagination하고, 전체 수집 성공 후에만 DB 저장을 시작하도록 구현
- **정제 정책**: `alt_text`별 최신 `crtr_ymd`를 먼저 선택한 뒤 제공기관 `I0000002`, `ksic_cd=561`, `bzmn_stts_nm=계속사업자`, 강남구 증거를 순서대로 검증
- **DB**: 기존 V1~V3를 유지하고 V4에서 KOMSCO 원본 컬럼, `recommendation_ready`, `(source_provider, external_merchant_id)` unique 제약을 추가
- **추천 경계**: 메뉴·가격·영업시간이 없는 KOMSCO 행은 `recommendation_ready=false`로 저장해 보강 전 추천 후보에서 제외
- **실행 방식**: 공개 API와 Scheduler 없이 opt-in one-shot `ApplicationRunner`로 구현하고 `.env`의 키를 local 실행 환경 또는 Docker Compose가 명시적으로 주입
- **실제 적재**: 61,941건 조회 → 최신화 30,783건 → 필터 통과 및 신규 적재 3,272건; DB에서 KOMSCO 3,272행과 distinct ID 3,272개 확인
- **전체 교체**: 사용자 승인 후 전체 조회 성공 시에만 기존 KOMSCO 행을 삭제·재삽입하는 트랜잭션 교체 모드를 추가하고 3,272건으로 재적재; 샘플 음식점 3건 보존
- **검증**: `./scripts/check-backend.sh` 및 `./scripts/check-all.sh` 전체 통과, 실제 MySQL Flyway V4 적용 성공
- **안전 규칙**: 이후 공공데이터·유료 API의 실제 호출 전 redacted URL/query를 사용자에게 제시하고 명시적 승인을 받도록 `AGENTS.md`에 추가

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
