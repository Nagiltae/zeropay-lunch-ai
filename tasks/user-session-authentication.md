# Task: user-session-authentication

## Status

일부 완료. 회원가입, 로그인, 로그아웃, 세션·CSRF와 대화 소유권은 구현되었습니다. 아래 요구사항 7의 회원 탈퇴 API와 상태 전환은 아직 구현하지 않았습니다.

## Goal

Spring Security, Spring Session JDBC, MySQL을 기반으로 사용자 인증 시스템(회원가입, 로그인, 로그아웃)과 CSRF 보호, React Query를 이용한 인증 상태 관리를 구현합니다. 향후 AI 추천을 위한 사용자 컨텍스트(취향, 식사 기록)의 기반을 마련합니다.

## Background

작성 당시 프런트엔드와 백엔드 간에는 익명 상태의 임시 대화 및 추천 흐름만 구현되어 있었습니다. 현재는 세션 인증과 사용자별 대화 소유권이 구현되었고, 취향과 최근 식사 기록에도 사용자 식별을 사용합니다.
React와 Spring Boot가 동일한 Nginx 경로(`/api`)를 통해 통신하고 있으므로, 불필요한 JWT 복잡성 없이 안전하고 단순한 서버 세션 쿠키 방식(Spring Session JDBC)을 채택합니다.

## In scope

- `users`, `user_credentials`, Spring Session(MySQL) 테이블 스키마 구성 (Flyway)
- 기존 `conversations` 테이블에 `user_id` 컬럼 확장
- Spring Boot 4 기준의 Spring Security 설정 (세션, CSRF, BCrypt 비밀번호 해시 적용)
- 사용자 회원가입, 로그인, 로그아웃, 현재 사용자 정보(`/api/auth/me`), CSRF 토큰 발급 API 구현
- React 프런트엔드의 로그인/회원가입 화면 및 인증 상태(React Query) 연동
- 대화 생성 시 인증된 `user_id`를 연결

## Out of scope

- 카카오, 네이버, 구글 등 OAuth2 기반 소셜 로그인 (추후 확장을 고려한 설계만 적용)
- JWT (JSON Web Token) 및 Refresh Token 인프라 도입
- Redis 등 외부 세션 스토리지 추가 (MySQL로 대체)
- 이메일 인증 발송 처리 (현재는 단순 이메일 형식 가입)
- 비밀번호 찾기, 사용자 프로필 이미지 수정 등 세부 회원 관리 기능
- 관리자(ADMIN) 권한 전용 화면

## Functional requirements

1. 비밀번호는 평문으로 저장되지 않으며 반드시 BCrypt 해시 처리를 거쳐 단방향 암호화하여 저장합니다.
2. 회원가입 시 이메일은 소문자로 정규화되며, 중복된 이메일로 가입할 수 없습니다.
3. 로그인 실패와 존재하지 않는 이메일의 경우 외부에서 계정 존재 여부를 유추할 수 없도록 "이메일 또는 비밀번호가 올바르지 않습니다."라는 동일한 오류 메시지를 반환합니다.
4. HTTP 요청(POST, PUT, DELETE 등) 수행 시 쿠키 기반의 CSRF 토큰 검증이 필수로 동작해야 합니다.
5. 세션 쿠키는 `HttpOnly=true`, `SameSite=Lax`, `Path=/` 설정으로 브라우저에 저장되며, 운영(prod) 프로필에서는 `Secure=true`가 강제되어야 합니다.
6. 대화 API는 로그인을 요구하며 생성 시 `conversations.user_id`에 현재 사용자를 매핑하고 이후 모든 접근에서 소유권을 검증합니다.
7. 회원 탈퇴 시 즉각 물리적으로 삭제(DELETE)하지 않고 `status`를 `WITHDRAWN`으로 논리 삭제 처리합니다.

## API contract

### 1. CSRF 토큰 조회
- `GET /api/auth/csrf`
- 브라우저 쿠키(CSRF 토큰) 갱신 용도, 비로그인 허용

### 2. 회원가입
- `POST /api/auth/signup`
- 요청: `{"email": "user@example.com", "password": "...", "displayName": "..."}`
- 비로그인 허용

### 3. 로그인
- `POST /api/auth/login`
- 요청: `{"email": "user@example.com", "password": "..."}`
- 응답 `200`: `{"userId": "UUID", "email": "user@example.com", "displayName": "..."}`
- 응답 `401`: `{"code": "INVALID_CREDENTIALS", "message": "이메일 또는 비밀번호가 올바르지 않습니다."}`
- 비로그인 허용

### 4. 현재 사용자 조회
- `GET /api/auth/me`
- 로그인 필요 (미인증 시 401 반환)
- 응답: 현재 로그인된 사용자 정보 반환

### 5. 로그아웃
- `POST /api/auth/logout`
- 세션 및 쿠키 파기

## Data model impact

### 신규 테이블 (Flyway)
1. `users`
   - `id` (CHAR(36), PK): UUID
   - `email` (VARCHAR, UNIQUE)
   - `display_name` (VARCHAR)
   - `status` (VARCHAR): ACTIVE / LOCKED / WITHDRAWN
   - `role` (VARCHAR): USER / ADMIN
   - `created_at`, `updated_at`, `last_login_at`
2. `user_credentials`
   - `user_id` (CHAR(36), FK): users 테이블 참조
   - `password_hash` (VARCHAR)
   - `password_changed_at`, `failed_login_count`, `locked_until`
3. `SPRING_SESSION`, `SPRING_SESSION_ATTRIBUTES`
   - Spring Session JDBC의 공식 스키마 적용 (스프링 자동 생성 옵션 비활성화, Flyway로 직접 관리)

### 기존 테이블 변경
1. `conversations`
   - `user_id` (CHAR(36), NULL): 인증된 사용자의 식별자 저장

## Architecture constraints

- React는 브라우저 저장소(localStorage 등)에 세션이나 비밀번호를 절대 저장하지 않습니다.
- 프런트엔드의 인증 상태는 오직 `GET /api/auth/me` 조회 결과와 React Query를 통해 관리됩니다.
- 세션 유지를 위해 추가적인 인프라(Redis 등)를 도입하지 않고 현재의 MySQL 8.4를 사용합니다.

## Acceptance criteria

1. 앱 접속 시 미인증 상태일 경우 로그인/회원가입 화면이 정상적으로 표시된다.
2. 회원가입 후 이메일과 비밀번호로 정상적으로 로그인할 수 있으며, 로그인 실패 시 보안을 고려한 동일한 에러 메시지가 표시된다.
3. 로그인한 사용자는 `GET /api/auth/me` 를 통해 자신의 정보를 확인할 수 있으며, 새로고침 후에도 세션이 유지된다.
4. 로그인 상태에서 채팅방 생성 시 `conversations` 테이블에 `user_id`가 저장된다.
5. 로그아웃 수행 시 세션 쿠키가 만료되고, 로그인 화면으로 돌아간다.
6. 백엔드 빌드, 테스트, 프런트엔드 테스트, 전체 통합 검사가 통과한다.
7. 다른 사용자는 대화 ID를 알아도 해당 대화를 조회, 변경하거나 메시지를 보낼 수 없다.

## Verification

- `./scripts/check-backend.sh` (Spring Security, CSRF 필터 및 세션 통합 테스트 포함)
- `./scripts/check-frontend.sh` (인증 관련 React 컴포넌트 린트/빌드 검증)
- `./scripts/check-integration.sh` (실제 로그인-세션 쿠키 발급-대화 생성-로그아웃 연동 테스트)
- `./scripts/check-all.sh`

## Documentation updates

- `docs/api-contract.md` (신규 `/api/auth/*` API 추가)
- `docs/database.md` (`users`, `user_credentials`, Spring Session 테이블 및 `conversations` 수정 내역 반영)
- `docs/architecture.md` (인증 및 세션 처리 아키텍처 항목 보강)
