# 검증 및 통합 테스트 전략

## When to read
- 새로운 통합 테스트 작성
- 테스트 환경(Mocking, Testcontainers) 설정 변경
- Check script 원리 확인


> **Harness Role:** 어떤 변경에 어떤 검사가 필요하고 현재 통합 테스트가 어디까지 보장하는지 정의합니다. Agent는 구현 계획과 완료 판단 시 읽습니다. 이 문서가 없으면 단위 테스트만 통과하고 서비스 간 흐름도 검증됐다고 오판할 수 있습니다. `scripts/check-*.sh`, Docker Compose와 `AGENTS.md`의 Definition of Done을 연결합니다.

## 목적

검증은 코드를 작성했다는 사실이 아니라 관찰 가능한 동작을 기준으로 완료 여부를 판단하기 위해 사용합니다. 가장 좁은 대상 검사를 먼저 실행하고, 여러 서비스나 실행 환경에 영향을 주는 변경은 `./scripts/check-all.sh`로 최종 확인합니다.

## 검사 진입점

| 명령 | 범위 |
| --- | --- |
| `./scripts/check-format.sh` | tracked 변경과 untracked 텍스트 파일의 공백 오류, AI Ruff 포맷 |
| `./scripts/check-lint.sh` | React ESLint, AI Ruff lint |
| `./scripts/check-frontend.sh` | npm 의존성 상태, TypeScript를 포함한 프로덕션 빌드, 존재하는 경우 테스트 |
| `./scripts/check-backend.sh` | Gradle compiler lint(`-Xlint:all,-serial -Werror`), 테스트, 패키징 |
| `./scripts/check-ai.sh` | Poetry 메타데이터, FastAPI import, Pytest |
| `./scripts/check-integration.sh` | Docker health, 인증·세션·대화 소유권과 Nginx→Spring SSE 흐름 |
| `./scripts/check-all.sh` | 위 검사의 canonical 전체 실행 |

프런트엔드는 Vitest로 인증 API의 CSRF 헤더와 401 처리, 취향·식사 기록 요청, 대화 생성 요청, 청크 경계가 나뉜 SSE 추천 이벤트 파싱을 검증합니다. jsdom 컴포넌트 테스트는 선호·비선호 상호 배제와 저장, 추천 카드의 명시적인 `먹었어요` 동작을 검증합니다. 실제 브라우저 자동화는 아직 없습니다.

## Progressive integration levels

통합 검사는 실제 기능이 존재하는 단계까지만 확장합니다.

### Level 1 — service health and current authenticated flow

현재 구현되어 있습니다.

- Docker Compose 구성 검증
- MySQL과 Qdrant를 포함한 컨테이너 health 대기
- Nginx `/healthz`
- Spring Boot `/actuator/health`
- FastAPI `/health`
- Nginx `/api/` 프록시를 통한 회원가입·로그인·현재 사용자 조회
- 인증된 대화 생성과 Spring Boot SSE 이벤트 완료

`check-integration.sh`는 전체 이미지를 조용한 출력으로 빌드한 뒤 `docker compose up -d --wait`로 스택을 기동합니다. 검사 후 컨테이너와 볼륨을 삭제하지 않습니다. 실패 시 `docker compose ps`와 관련 서비스의 최근 로그를 출력합니다.

### Level 2 — backend dependencies

MySQL 대화 흐름은 현재 구현되어 있습니다.

- Flyway가 실제 MySQL에 공통 스키마와 dev 샘플 데이터를 적용
- 사용자 취향 저장과 고정 제로페이 정책 확인
- 추천 메시지에 연결된 식사 기록의 명시적·멱등 저장과 최근 조회
- Spring Boot가 대화, 메시지와 추천 결과를 저장하고 조회
- 대화 비활성화 후 `active=false` 확인
- 영업시간과 휴무시간 native query를 H2와 실제 MySQL 흐름에서 검증

FastAPI가 Qdrant 컬렉션을 생성하거나 검색하는 검사는 아직 구현되지 않았습니다.

단순히 컨테이너 포트가 열렸다는 검사로 이 단계를 통과했다고 판단하지 않습니다.

### Level 3 — service-to-service

Spring Boot가 실제 FastAPI 내부 API를 호출하는 기능이 생길 때 다음을 검증합니다.

- Spring Boot 요청이 FastAPI 계약에 맞게 전달됨
- FastAPI 오류와 잘못된 응답을 Spring Boot가 검증하고 변환함
- 타임아웃 또는 연결 실패 처리

현재 `AI_BASE_URL` 환경변수만 있고 실제 호출 코드는 없으므로 이 단계의 검사는 만들지 않습니다.

### Level 4 — user flow

대화와 추천 기능이 구현되는 순서에 맞춰 확장합니다.

현재 Docker 통합 검사에는 다음 사용자 흐름의 서버/API 부분이 포함됩니다.

1. 회원가입과 로그인
2. 세션 쿠키 발급과 현재 사용자 조회
3. 인증된 대화 생성과 MySQL `user_id` 저장 확인
4. 다른 사용자의 대화 조회 및 메시지 전송 거부
5. 사용자 메시지 전송
6. 구조화된 추천 및 SSE 답변 수신
7. USER 및 ASSISTANT 메시지 저장
8. 추천 결과가 포함된 대화 기록 조회
9. 대화 비활성화
10. 사용자 취향 저장과 고정 제로페이 정책 확인
11. 추천 카드에 대한 명시적·멱등 식사 기록과 최근 기록 조회
12. 로그아웃 후 인증 API 및 대화 접근 거부

백엔드 자동 테스트는 취향 충돌 검증, 최근 72시간 식사 범위, 다른 사용자의 추천 기록 차단, 제로페이 불가 음식점 제외, 기본 예산·비선호·최근 식사 필터와 AI 분석 fallback을 포함합니다.

KOMSCO import 자동 테스트는 외부 API를 호출하지 않고 JSON/nullable 매핑, 14개 법정동 pagination, 필수 필드 제외, `alt_text`별 최신 기준일자, 최신 폐업 상태 우선, 계속사업자·KSIC 561·강남구·제공기관 필터, 최초 insert, 동일 실행 중복 방지, 같은 날짜 변경, 최신/과거 날짜 upsert, API 실패 전 무쓰기와 기존 KOMSCO snapshot 트랜잭션 교체를 검증합니다. H2 테스트는 V4 migration과 JPA 매핑까지 확인하며 실제 MySQL 문법은 Docker 통합 검사에서 확인합니다.

일일 동기화 테스트는 새벽 3시 cron 설정, Scheduler의 서비스 호출과 오류 격리, 동일 원본의 timestamp 갱신, 폐업·부적격 가맹점 비활성화, 조건 복구 시 재활성화, 더 오래된 원본으로 상태를 되돌리지 않는 정책을 검증합니다. 자동 테스트에서는 실제 공공데이터 API를 호출하지 않습니다.

NAVER Local 테스트는 실제 외부 API를 호출하지 않고 JSON/nullable 필드, HTML·괄호·지점명과 주소 정규화, 소수점 및 `10^7` 배율 좌표 변환, Haversine 거리, 가장 좋은 후보와 runner-up gap, 다른 프랜차이즈 지점·비음식점 category·최소 이름 증거 미달 제외, 300m 초과 제외, MATCHED strong evidence, 모호한 후보와 미매칭 판정, 법정동별 deterministic 표본, 2차 강남구 query 상한, 상태별 증분 선택, 인증/개별 장애 정책, 기존 매칭의 API 실패 보존과 `(restaurant_id, provider)` 기반 반복 upsert를 검증합니다. 음식점/비음식점/미분류 category와 ELIGIBLE/INELIGIBLE/UNKNOWN 판정, 추천 조회의 ELIGIBLE 강제, KOMSCO 매칭 입력 변경 시 UNKNOWN 초기화도 검증합니다. 수미초밥과 구야네 실제 검증 사례도 회귀 테스트로 고정합니다. 실제 외부 호출은 redacted 요청 범위를 사용자에게 보여주고 승인받은 경우에만 별도로 실행합니다.

브라우저 자동화와 실제 AI 추천 결과 검증은 아직 포함하지 않습니다.

Compose에서 Spring Boot는 아직 호출하지 않는 FastAPI를 시작 조건으로 요구하지 않으며, FastAPI도 아직 사용하지 않는 Qdrant를 시작 조건으로 요구하지 않습니다. 전체 통합 검사는 저장소에 정의된 각 서비스의 health를 확인하지만 이 독립성 자체를 장애 시나리오로 검증하지는 않습니다.
통합 검사 실행 중에는 KOMSCO import/Scheduler와 NAVER enrichment를 강제로 비활성화해 사용자 승인 없는 외부 API 호출을 방지합니다.

브라우저 자동화나 대규모 E2E 도구는 이 흐름이 안정된 뒤 실제 필요가 있을 때만 추가합니다.

## Failure handling

- 실패한 명령의 출력과 컨테이너 로그를 먼저 확인합니다.
- 테스트를 삭제하거나 검증을 약화해 통과시키지 않습니다.
- 외부 런타임 부족으로 실행하지 못한 검사는 `[PASS]`로 보고하지 않습니다.
- 통합 실패 후 데이터 보존을 위해 자동으로 `docker compose down -v`를 실행하지 않습니다.
