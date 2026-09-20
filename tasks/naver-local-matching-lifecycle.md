# Task: naver-local-matching-lifecycle

# Goal
NAVER Local 매칭을 검증하고 점수 근거를 보존하며, 명시적 전체 실행 및 변경 기반 증분 갱신을 안전하게 지원합니다.

# Scope
- 표본 추출 및 CSV 검증 리포트 (점수 breakdown 포함)
- 이름·주소 정규화 및 프랜차이즈 지점 충돌 방어 로직
- `--limit`, `--incremental`, `--all` 실행 모드 지원
- 증분 실행용 source hash, refresh TTL, retry 처리
- 주 1회 incremental Scheduler(일요일 04:00 Asia/Seoul)와 ShedLock
- Flyway V6 마이그레이션 및 자동 테스트

# Read First
- `backend/AGENTS.md`
- `docs/database.md`

# Constraints
- KOMSCO가 원본이며 NAVER 데이터가 이를 덮어쓰지 않습니다.
- 외부 API 자동 호출은 명시적으로 활성화한 Scheduler에서만 수행하며, local/test 기본값은 비활성입니다. 전체 실행은 CLI 등 수동으로만 수행합니다.
- 기존 가중치(40/30/20/10), MATCHED 하드 게이트(70점, Gap 8점)와 거리 제외(300m) 기준을 유지합니다.
- 상세 안전/DB/API 규칙은 중복 기술하지 않고 `backend/AGENTS.md`를 참조합니다.

# Definition of Done
1. Normalization, 지점명, 증분 조건, 실패 보존 및 멱등성 테스트 통과.
2. 실행 시 CSV 리포트와 통계가 정확히 생성됨.

# Validation
- `./scripts/check-backend.sh`

# Report
- 갱신된 DB 통계 및 생성된 CSV 리포트 경로

# Reference / History
- **상태**: 완료. 3,272건 전체 매칭 및 오프라인 재검증 적용 완료.
- **주요 결과 요약 (2026-09-19)**:
  - 3,272건 기준: MATCHED 1,982, AMBIGUOUS 163, UNMATCHED 1,127
  - Address Parser 도입으로 인한 추가 격상 등 과거 세부 결과는 `AI_CHANGELOG.md` 참조.
