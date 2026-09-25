# Detail Quality Backfill Review

## 판정

**DETAIL QUALITY BACKFILL = READY FOR SEMANTIC EXPANSION**

원문에 요일과 시간 범위가 함께 명시되는지 검증하는 정책으로 최종 audit했다. 유효 기준선 4곳에서 최종 strict-ready 26곳으로 증가했고 신규 READY는 22곳으로 목표인 10곳 이상을 충족했다. 이전 audit의 기준선 5곳 중 9590은 원문에 토요일 휴무가 있는데 저장 row가 토요일 영업으로 되어 있어 검증 기준선에서 제외했다. 이번 단계에서는 Semantic Profile/Qwen generation, Embedding, Qdrant 작업은 실행하지 않았다.

## 작업 전 상태와 공통 정책

Coverage audit은 논현동 ACTIVE + ELIGIBLE + Numeric NAVER MATCHED 360곳을 대상으로 수행했다. 기존 strict-ready는 `[9568, 9571, 9574, 9590, 9617]`이었다. 기존 생성 코드와 Coverage audit의 판정이 다르던 부분을 `ai/app/profile_readiness.py`의 단일 fail-closed 정책으로 통합했다.

READY 조건은 모두 충족되어야 한다.

- ACTIVE + ELIGIBLE
- MENU, BUSINESS_HOURS, REVIEW 각각 Lifecycle `SUCCESS`
- 가격이 확인된 메뉴 1개 이상
- `open_time`과 `close_time`이 모두 있는 구조화 영업시간 1개 이상
- 시간 row의 요일·open/close가 같은 원문 description에서 직접 확인됨
- 숫자형 NAVER Place ID 및 단일 owner
- Provider verification `VERIFIED`이며 명시된 Place ID가 현재 mapping과 일치
- 기존 `NAVER_DETAIL_STALE_AFTER_SECONDS` freshness 정책 이내

불충족 이유는 `NO_MENU_SUCCESS`, `NO_BUSINESS_HOURS_SUCCESS`, `NO_REVIEW_SUCCESS`, `NO_PRICED_MENU`, `NO_STRUCTURED_HOURS`, `NO_NUMERIC_PLACE_ID`, `PLACE_ID_CONFLICT`, `NOT_VERIFIED`, `STALE`로 반환한다. 별도 freshness 기간을 추가하지 않았다. Backfill 중 페이지 전체 텍스트에서 요일과 다른 요일의 시간을 잘못 짝지을 수 있는 파서 결함을 발견했다. 파서는 같은 요일 토큰 바로 다음 시간 범위만 읽도록 수정했고, 저장된 27개 대상의 시간도 snapshot 원문으로 재정규화했다. 재정규화 중 외부 요청은 0회다.

## 선정 및 Dry-run

Group A는 요청된 정확한 allowlist 7곳만 사용했다.

`9559, 9560, 9562, 9567, 9569, 9570, 9580`

이 그룹은 영업시간의 구조화 데이터만 부족한 대상으로 계획했다. 실제 계획 검사에서도 각 항목 사유가 `only NO_STRUCTURED_HOURS remains`인지 확인하도록 write gate를 강화했다.

Group B는 lifecycle이 없는 345곳 전체를 재수집하지 않고, 기존 가격 메뉴·영업시간·리뷰 summary/keyword/대표 리뷰 신호로 최대 20곳을 정렬했다. Numeric Place ID, VERIFIED 상태, owner 충돌 및 알려진 identity/detail 제외 목록을 사전 검사했다. `9654, 9731, 9750`의 `MENU ABSENT_CONFIRMED`와 `9582, 9619, 9661, 9695, 9610, 9564`는 제외했다.

선정된 Group B:

`9865, 9659, 10021, 9904, 9715, 9996, 9662, 9976, 9791, 10042, 9639, 9954, 9801, 9603, 9759, 9826, 9973, 9839, 9853, 10053`

Dry-run은 Group A hours-only와 Group B MENU/HOURS/REVIEW로 각각 실행했다. 결과는 27/27 성공, 실패 0, 차단 0, 재시도 0이었다. Dry-run은 DB write를 하지 않았다. 403/429/CAPTCHA는 관찰되지 않았다.

## DB guard, snapshot 및 persistence

쓰기 직전 환경을 재확인했다. 대상은 Compose project `zeropay-lunch-ai`, DB `zeropay_lunch`, Spring profile `dev`였다. Credential은 artifact/report에 기록하지 않았다. Group A/B allowlist, 총 대상 수 27 이하, 제외 ID, Place ID identity/ownership, 허용 write-table 집합을 코드에서 다시 검증했다.

대상 27곳의 row-level before snapshot을 저장한 뒤 Restaurant별 persistence를 순차 실행했다. Group A는 BUSINESS_HOURS만, Group B는 MENU/BUSINESS_HOURS/REVIEW만 처리했다. 결과는 성공 27, 실패 0, blocked 0, skipped 0이다. 리뷰 전문은 snapshot에 저장하지 않고 SHA-256 및 길이만 보존했다.

Before/after snapshot 비교:

| Table | Before rows | After rows | Delta |
|---|---:|---:|---:|
| `restaurant_menus` | 1552 | 1558 | +6 |
| `restaurant_business_hours` | 30 | 112 | +82 |
| `restaurant_review_summaries` | 27 | 27 | 0 |
| `restaurant_review_keywords` | 906 | 906 | 0 |
| `restaurant_representative_reviews` | 266 | 266 | 0 |
| `restaurant_detail_section_states` | 21 | 81 | +60 |

27개 모든 대상에서 기존 메뉴/시간/리뷰 row가 after snapshot에도 존재했다. 기존 priced-menu row의 가격 정보 손실은 0건이었다. 잘못 짝지어진 시간 row는 삭제하지 않고 inactive 처리했으며, 원문과 직접 일치하는 요일 row만 활성화했다. Restaurant master, external Place ownership, NAVER verification snapshot은 대상 전체에서 전후 동일했다. 관측된 DB write 범위는 Detail 및 Section Lifecycle 테이블에 한정됐다.

## Lifecycle 및 결과

대상 27곳 모두 MENU, BUSINESS_HOURS, REVIEW Lifecycle이 `SUCCESS`다. Group A는 기존 MENU/REVIEW 상태를 유지하고 BUSINESS_HOURS만 갱신했다. Group B는 세 Section Lifecycle을 생성했다.

단, Lifecycle `SUCCESS`는 구조화 영업시간 존재와 동일하지 않다. DOM에서 영업시간 문구를 확인했더라도 `open_time`/`close_time`으로 파싱되지 않은 곳은 임의 추론하지 않았고, 공통 Policy에서 `NO_STRUCTURED_HOURS`로 계속 제외했다.

정규화 후 Group A 중 READY가 된 곳은 `9559, 9569, 9570, 9580`이다. `9560, 9562, 9567`은 요일·시간이 직접 대응하는 반복 시간표를 확인하지 못해 추론 없이 NOT_READY로 유지했다.

Group B 중 READY가 된 18곳:

`9603, 9639, 9659, 9715, 9759, 9791, 9801, 9826, 9839, 9853, 9865, 9904, 9954, 9973, 9996, 10021, 10042, 10053`

따라서 신규 READY는 총 22곳:

`9559, 9569, 9570, 9580, 9603, 9639, 9659, 9715, 9759, 9791, 9801, 9826, 9839, 9853, 9865, 9904, 9954, 9973, 9996, 10021, 10042, 10053`

strict-ready 총계는 26곳이다. 전체 모집단에서 남은 미충족 이유 건수는 `NO_MENU_SUCCESS=328`, `NO_BUSINESS_HOURS_SUCCESS=325`, `NO_REVIEW_SUCCESS=325`, `NO_PRICED_MENU=40`, `NO_STRUCTURED_HOURS=332`이며 사유는 Restaurant별 중복 집계다. 첫 after snapshot은 파서 보정 전 상태로 `detail_quality_backfill_after_pre_hours_reconcile.json`에 보존했다.

## Checkpoint, 호출 및 쓰기 요약

- Dry-run: Group A 7 + Group B 20, 각 Restaurant 결과를 checkpoint에 기록
- Persistence: 동일하게 Restaurant별 `SUCCESS` 기록 후 재실행 시 완료 대상을 건너뛰는 기존 checkpoint/resume 경로 사용
- Dry-run 네비게이션: Group A 7 + Group B 60 = 67
- Persistence 네비게이션: Group A 7 + Group B 60 = 67
- 총 브라우저 페이지 탐색: 134 (전체 사이트 하위 resource request 수와는 구분)
- 원문 기반 시간 재정규화: 27곳, 외부 요청 0회
- direct NAVER HTTP API request metric: 0; DOM/browser 경로 사용
- 403/429/CAPTCHA: 0; retry: 0
- Qwen/Provider Entity Resolution: 0
- Semantic Profile 생성: 0
- Embedding 생성: 0
- Qdrant write: 0
- DB write: Detail/Lifecycle만 허용; 총 27 Restaurant 대상으로 실행

Resume 동작은 checkpoint identity/scope 검증과 terminal status skip 단위 테스트로 확인했다. 성공한 대상은 같은 checkpoint 실행에서 다시 처리하지 않으며, target/section/mode가 바뀌면 checkpoint 재사용을 거부한다.

## 테스트 및 안전 확인

- Readiness, Detail checkpoint/resume, crawler/lifecycle targeted tests: **36 passed after parser refinement**
- Ruff: **passed**
- AI Harness `./scripts/check-ai.sh`: **240 passed, 1 skipped** (live runtime test skipped by harness), 1 dependency deprecation warning
- `git diff --check`: **passed**
- Backend/Integration Harness: **NOT_RUN** (Spring/schema 코드를 변경하지 않음)
- MySQL/Place ID/Venue/User/Conversation/Recommendation 변경: 없음
- Qdrant/Profile/Embedding 변경: 없음
- Git add/commit/push: 수행하지 않음

## 다음 단계

목표 신규 strict-ready 10곳 이상을 충족했으므로 다음 별도 단계에서 신규 READY Restaurant만 Semantic Profile 생성 후보로 평가할 수 있다. 이번 Backfill에서 성공한 모든 Restaurant를 자동 Profile 생성 대상으로 보지 말고 최신 input/evidence와 기존 Claim 승인 정책을 다시 적용해야 한다. `NO_STRUCTURED_HOURS`가 남은 3개 Group A와 나머지 모집단에 대한 추가 대량 재수집은 실행하지 않았다.
