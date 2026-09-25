# ZeroPay Lunch AI — NAVER Local 인증 복구 및 Place ID 수집 안정화

## 1. Executive Summary

NAVER Local HTTP 401의 실제 원인은 인증값 자체가 아니라 standalone AI CLI의 env 탐색 경로 불일치였다.

- 저장소 루트 .env에는 NAVER 인증 변수가 존재했다.
- ai/.env는 존재하지 않았다.
- standalone Provider CLI는 root=ai로 계산한 뒤 ai/.env만 읽었다.
- 인증 헤더가 비어 HTTP 401이 발생했다.
- provider_input.load_local_env가 root가 ai일 때 repository parent .env도 읽도록 최소 수정했다.

복구 후 공식 NAVER Local 요청 4회가 정상 처리됐다.

- 9619: 후보 1건
- 9695: 후보 3건
- 9604: 후보 0건
- 9627: 후보 0건

9619와 9695의 Maps UI dry-run은 각각 1921750340, 19882368로 MATCHED됐다. 그러나 9619의 1921750340은 이미 restaurant_id 9582에 매핑되어 있었다. 실제 저장에서 기존 ON DUPLICATE KEY UPDATE가 다른 음식점 mapping을 보호하지 못하는 결함을 발견해 Detail 저장을 중단했다.

## 2. NAVER Local 401 원인과 복구

provider_candidate_retrieval_cli.py와 standalone 진단 경로는 root=ai를 전달했다. 기존 load_local_env는 root/.env 하나만 읽었고 실제 인증값은 repository root .env에 있었다.

수정 파일:

- ai/app/providers/provider_input.py
- ai/tests/providers/test_place_provider.py

수정 내용:

- root가 ai이면 root.parent/.env를 fallback으로 읽음
- setdefault를 유지해 shell/CI 환경변수를 덮어쓰지 않음
- repository parent .env fallback 회귀 테스트 추가

복구 검증:

| 요청 | 결과 | 후보 |
|---|---|---:|
| 9619 논현동 우정양곱창 | HTTP 200, JSON 파싱 성공 | 1 |
| 9695 논현동 현대순대국 | HTTP 200, JSON 파싱 성공 | 3 |
| 9604 논현동 지유가오카핫쵸메7호점 | HTTP 200, JSON 파싱 성공 | 0 |
| 9627 논현동 파니나로 | HTTP 200, JSON 파싱 성공 | 0 |

총 Local 요청은 4회였다. 인증정보와 header는 보고서에 기록하지 않았다.

## 3. 9619·9695 동일 지점 검증

### 9619 우정양곱창

- KOMSCO: 우정양곱창 / 서울시 강남구 도산대로30길 23
- Canonical: 우정양곱창 / 도산대로30길 23
- NAVER_LOCAL: 우정양곱창 / 도산대로30길 23 1층
- Maps UI numeric ID: 1921750340
- raw 후보 1, numeric 후보 1, 검증 탈락 0
- Local evidence 사용
- Canonical fallback 미사용

그러나 ID 1921750340은 이미 restaurant_id 9582에 저장되어 있었다. 9582는 우정 양곱창이며 같은 도산대로30길 주소를 가진다. 따라서 9619를 별도 MATCHED로 저장하지 않았고, 두 KOMSCO row가 같은 실제 사업장을 중복 표현하는지는 별도 품질 검토로 남겼다.

### 9695 현대순대국

- KOMSCO: 현대순대국 / 강남대로124길 20
- NAVER_LOCAL 후보 3건
- Maps UI numeric ID: 19882368
- raw 후보 3, numeric 후보 3, 검증 탈락 2
- Local evidence 사용
- Canonical fallback 미사용
- 기존 Linker 계약상 MATCHED

9695는 이번 작업에서 DB 저장하지 않았다.

## 4. 실제 DB 저장 결과

9619를 저장 대상으로 선택했으나 실제 결과는 다음과 같다.

- 9619 numeric mapping: 저장되지 않음
- 9619 Detail: 실행하지 않음
- 9619 lifecycle: 변경 없음
- 9619 eligibility: ELIGIBLE 유지
- 기존 NAVER_LOCAL mapping: 보존

기존 테이블에는 restaurant_id/provider와 provider/external_place_id 두 unique key가 있다. 기존 Place ID write의 ON DUPLICATE KEY UPDATE는 같은 external_place_id가 다른 restaurant_id에 있어도 충돌을 안전하게 거부하지 못했다.

실제 확인:

- 9619 row 생성/갱신 없음
- 9582 ID/status/query는 유지
- 9582 matched_at/updated_at은 attempted write 시각으로 갱신됨
- Canonical/Verification/Detail 추가 변경 없음

정확한 이전 timestamp를 알 수 있어 임의 복원 SQL은 실행하지 않았다.

최소 수정:

- ai/app/naver/place_id_linker_cli.py
- 동일 NAVER numeric ID가 다른 restaurant_id에 있으면 AMBIGUOUS로 분류
- 해당 실행에서 persist하지 않음
- 기존 mapping을 ON DUPLICATE로 건드리지 않음

회귀 테스트:

- test_external_place_id_conflict_blocks_cross_restaurant_reuse

## 5. Detail Dry-run 및 Freshness

9619는 numeric ID 충돌이 확인되어 Detail 대상에서 제외했다.

- Detail dry-run: 0 targets
- Detail persistence: 실행하지 않음
- Section Lifecycle: 생성하지 않음
- Freshness 재실행: 수행하지 않음

이는 동일 지점이 확정되지 않은 상태에서 Detail을 저장하지 않기 위한 안전한 중단이다. 기존 9619의 Detail/메뉴/영업시간/리뷰 데이터는 없었고, 이번 작업에서 생성하지 않았다.

Snapshot:

- before: AI_Answer/restaurant_9619_snapshot_before.json
- after: AI_Answer/restaurant_9619_snapshot_after.json

## 6. NAVER 근거 부족 대상 보강

인증 복구 후 그룹 B 9604·9627에 Local 요청을 각 1회 수행했다.

| ID | 검색어 | Local 결과 | Maps UI |
|---:|---|---|---|
| 9604 | 논현동 지유가오카핫쵸메7호점 | HTTP 200, 후보 0 | 실행하지 않음 |
| 9627 | 논현동 파니나로 | HTTP 200, 후보 0 | 실행하지 않음 |

새로운 Local evidence가 없으므로 Maps UI를 반복하지 않았다. 두 대상은 UNRESOLVED를 유지했고 DB에는 쓰지 않았다.

## 7. Runtime Report

주요 report:

- ai/build/reports/naver-place-pipeline/e2e/20260924-auth-recheck-030444-place_id.json
  - 2 targets, 2 MATCHED
  - raw 4, numeric 4, rejected 2
  - Local evidence 2, Canonical fallback 0
- ai/build/reports/naver-place-pipeline/e2e/20260924-placeid-write-030533-place_id.json
  - 1 target, MATCHED 1
  - conflict guard 적용 전 실행이므로 충돌 필드는 없음
- ai/build/reports/naver-place-pipeline/e2e/20260924-detail-dry-030550-detail.json
  - 0 targets

구조화 결과:

- AI_Answer/naver_local_auth_placeid_recovery_results.json

## 8. 후속 정책

- NAVER Local/Maps 모두 확인되지 않으면 원본 음식점은 보존한다.
- Numeric ID가 다른 restaurant_id에 이미 있으면 자동 MATCHED하지 않는다.
- 동일 상호라도 주소와 기존 mapping을 함께 확인한다.
- Local 후보 0건은 원본 음식점 부적격을 의미하지 않는다.
- 9619/9582는 중복 사업장 여부를 먼저 검토해야 한다.
- 숫자 ID 충돌이 없는 단일 대상에서 Place ID write와 Detail persistence를 별도로 재검증해야 한다.
- 이번 표본을 전체 성공률로 환산하지 않는다.

## 9. 테스트 및 안전

- Targeted tests: 18 passed
- AI Harness: 164 passed, 1 warning
- git diff --check: PASS
- Backend/Integration: schema 변경 없음으로 실행하지 않음
- Qwen/전체 Batch: 실행하지 않음
- Local 요청: 4회
- Maps UI 요청: 2회
- DB write: 9619 의도 대상에는 없음
- 9582 기존 mapping timestamp/query update 흔적만 확인됨
- git add/commit/push: 안 함

다음 소규모 Pilot은 NAVER 인증 측면에서는 진행 가능하지만, 9619/9582 ID 충돌과 persistence guard가 적용된 dry-run을 먼저 확인한 뒤 진행해야 한다.
