# Task: KOMSCO 음식점 일일 동기화

## Status

완료

## Goal

매일 `Asia/Seoul` 기준 새벽 3시에 KOMSCO 전체 snapshot을 조회해 기존 강남구 음식점 원본을 최신화하고, 더 이상 저장 조건을 만족하지 않는 기존 가맹점은 삭제하지 않고 `active=false`로 전환합니다.

## In scope

- Spring Scheduler와 환경변수 기반 활성화·cron·timezone 설정
- 기존 KOMSCO 조회, pagination, 최신 `crtr_ymd` 선택 재사용
- 신규 적격 가맹점 insert
- 기존 가맹점 원본 및 `last_synced_at`, `updated_at` 갱신
- 최신 상태가 계속사업자가 아니거나 강남구·KSIC 561 조건에서 벗어나면 `active=false`
- 조건을 다시 만족하면 `active=true` 복구
- API 실패 시 DB 무변경
- 자동 테스트와 운영 문서

## Out of scope

- 공개 동기화 API
- 분산 Scheduler lock
- Naver API, FastAPI, Qdrant, LLM
- snapshot에서 완전히 사라진 가맹점의 자동 비활성화
- 영업시간·메뉴·가격 보강

## Functional requirements

1. 기본 cron은 `0 0 3 * * *`, timezone은 `Asia/Seoul`입니다.
2. 전체 페이지 수집과 최신화가 성공한 뒤에만 DB 동기화를 시작합니다.
3. 기존 KOMSCO 행은 같은 `crtr_ymd`여도 동기화 확인 시 `last_synced_at`과 `updated_at`을 갱신합니다.
4. 최신 상태가 계속사업자가 아니면 `active=false`로 저장합니다.
5. 기존 행이 제공기관·KSIC·강남구 조건을 벗어나도 `active=false`로 저장합니다.
6. 조건을 다시 만족하는 기존 행은 `active=true`로 복구합니다.
7. 새 행은 모든 저장 조건을 만족할 때만 삽입합니다.
8. 외부 API 실패 시 기존 DB 상태를 변경하지 않습니다.

## Acceptance criteria

1. Scheduler 시간과 활성화 설정이 테스트됩니다.
2. insert, timestamp update, deactivate, reactivate, old source 보호가 테스트됩니다.
3. `./scripts/check-backend.sh`와 `./scripts/check-all.sh`가 통과합니다.

## Documentation updates

- `README.md`
- `docs/architecture.md`
- `docs/database.md`
- `docs/deployment.md`
- `docs/testing.md`
- `.env.example`
