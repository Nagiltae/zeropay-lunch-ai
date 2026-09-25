# ZeroPay Lunch AI — Semantic Profile v1 Small Pilot 보고서

## 1. Executive Summary

9617은 기존 승인 Profile을 재사용했고, 신규 Qwen 호출을 하지 않았다. PARTIAL_DATA 9731과 재검증한 LEGACY_UNVERIFIED 표본 9567·9580에 대해 Detail dry-run/제한 저장 후 Evidence ID Profile shadow를 각각 1회씩 실행했다.

| 대상 | Detail 결과 | Profile claim 결과 |
|---:|---|---|
| 9617 | 기존 승인 Profile 재사용 | 재호출 없음 |
| 9731 | 기존 PARTIAL, 메뉴 `ABSENT_CONFIRMED` 유지 | AUTO 1 / REVIEW 2 / REJECT 2 |
| 9567 | dry-run·저장 성공, lifecycle 생성 | AUTO 1 / REVIEW 3 / REJECT 1 |
| 9580 | dry-run·저장 성공, lifecycle 생성 | AUTO 3 / REVIEW 1 / REJECT 1 |

이번 결과는 claim 단위 정책이 확장 가능함을 보여주는 제한적 증거다. 운영 자동 승인은 아직 활성화하지 않았고, DB에 Profile을 저장하거나 Embedding/Qdrant를 실행하지 않았다.

## 2. Pilot 대상 선정

READ-ONLY SQL로 활성·ELIGIBLE·numeric NAVER MATCHED·기존 메뉴/시간/리뷰 row 보유·lifecycle 없음 조건을 확인했다. 제외 목록과 기존 충돌/Venue 검토 대상은 제외했다.

선정 대상:

* 9567 한정식애덕 — 메뉴 35, hours 1, summary 1, keywords 33, reviews 10
* 9580 빨간모자피자 논현점 — 메뉴 55, hours 1, summary 1, keywords 17, reviews 10
* 9590 마츄피츄 — 메뉴 102, hours 1, summary 1, keywords 36, reviews 10

세 건 모두 Detail dry-run은 성공했지만 실제 저장은 9567·9580 두 건으로 제한했다. 9590은 dry-run 결과만 보존했다.

## 3. Detail 재검증 및 저장

Dry-run report: `ai/build/reports/naver-place-pipeline/e2e/20260924-110309-242366-detail.json`

* 9567: DOM 성공, 메뉴 35, 영업시간 1, visitor 418/blog 62
* 9580: DOM 성공, 메뉴 55, 영업시간 1, visitor 76/blog 24
* 9590: DOM 성공, 메뉴 102, 영업시간 1, visitor 426/blog 313
* 실패/차단/429: 없음

실제 저장 report: `ai/build/reports/naver-place-pipeline/e2e/20260924-110359-364438-detail.json`

* 저장 대상: 9567·9580 두 건
* 두 대상 모두 persistence 성공
* Provider/Qwen Entity Resolution 호출: 0

Freshness 재실행 report: `ai/build/reports/naver-place-pipeline/e2e/20260924-110428-409619-detail.json`

* `preexisting_skipped=2`
* 추가 browser/navigation 및 중복 저장 없음

영업시간은 두 저장 대상 모두 상태 문구 row라 strict Profile gate를 충족하지 않는다. Profile claim은 영업시간을 의미 정보로 자동 생성하지 않았다.

## 4. Evidence Catalog 및 입력

대상별 산출물:

* `AI_Answer/semantic_profile_pilot_9731/`
* `AI_Answer/semantic_profile_pilot_9567/`
* `AI_Answer/semantic_profile_pilot_9580/`

각 디렉터리에는 compact input, Evidence Catalog, Qwen shadow result가 있다. 메뉴·키워드·대표 리뷰마다 Evidence ID와 원본 sourceField를 유지한다.

9731은 메뉴 0건과 `ABSENT_CONFIRMED`를 유지하므로 공식 메뉴 claim을 자동 승인하지 않는다. 리뷰 keyword/review에 기반한 의미 claim만 별도 평가한다.

## 5. Qwen 결과 및 Claim 정책

신규 Profile 호출은 정확히 3회였다.

| 대상 | 호출 | latency | Schema/Evidence | 비고 |
|---:|---:|---:|---|---|
| 9731 | 1 | 25.6초 | 구조 PASS, strict false | 메뉴 부재 반영 |
| 9567 | 1 | 29.8초 | 구조 PASS, strict false | hours 상태 문구 |
| 9580 | 1 | 26.8초 | 구조 PASS, strict false | hours 상태 문구 |

모델은 일부 대상에서 `profileStatus=READY`를 반환했지만 Python quality/claim gate가 이를 그대로 신뢰하지 않았다.

분류 기준:

* `AUTO_APPROVED`: Evidence ID 존재, 허용 type, section SUCCESS, 낮은 mention count 없음, 직접적인 claim 근거
* `REVIEW_REQUIRED`: 대표 리뷰 해석, 낮은 언급 수, 복합 의미 조합 등 수동 의미 검토 필요
* `REJECTED`: 메뉴 부재인데 공식 메뉴처럼 표현, 허용되지 않은 evidence type, 근거 불일치

현재 표본 집계는 9617의 기존 3개 승인 claim과 비교해 신규 3건에서 AUTO 5건, REVIEW 6건, REJECT 4건이다. Claim 개수가 많다고 품질이 높다고 판단하지 않았다.

상세 결과:

* `AI_Answer/semantic_profile_pilot_9731_claim_validation.json`
* `AI_Answer/semantic_profile_pilot_9567_claim_validation.json`
* `AI_Answer/semantic_profile_pilot_9580_claim_validation.json`

## 6. 품질 차이와 오류 사례

* 9731: 메뉴가 없어서 음식 종류를 공식 메뉴로 표현한 claim은 거절됐다. 맛 claim은 keyword 근거로 자동 후보가 되었고, 특별한 날/오마카세/혼밥 맥락은 mention count 또는 의미 해석 때문에 review가 필요하다.
* 9567: 음식 종류는 직접 메뉴 근거가 있어 자동 후보가 되었으나, 리뷰와 keyword를 합친 메뉴 특성·맛·이용 맥락은 review가 필요하다. 주소를 포함한 venue claim은 identity evidence를 허용하지 않아 거절됐다.
* 9580: 메뉴 기반 음식/메뉴 특성 및 keyword 기반 맛·서비스 claim 일부가 자동 후보가 되었고, 단일 낮은 언급의 혼밥 claim은 review가 필요하다.

이번 pilot에서 확인한 hallucination/evidence mismatch 유형은 모델이 메뉴 부재 표본에서 공식 메뉴처럼 음식명을 표현한 경우, 허용되지 않은 evidence type을 MENU_CHARACTERISTIC에 사용한 경우, 위치·메뉴 표현을 evidence보다 넓게 일반화한 경우다. 모두 최종 승인 Profile에서 제외했다.

## 7. Embedding 입력 계약

향후 Embedding 후보는 승인된 `FOOD_TYPE`, `MENU_CHARACTERISTIC`, `TASTE`, `DINING_CONTEXT`, `VENUE_CHARACTERISTIC` claim과 Evidence ID/catalog hash를 함께 보존한다.

Embedding에서 제외한다:

* 정확한 가격
* 현재 영업 여부 및 반복 시간 계산
* 거리
* ZeroPay eligibility
* Numeric NAVER Place ID

위 값은 Spring/MySQL 결정론적 필터·식별 경로에서 관리한다. Qdrant 적재는 자동 승인 기준과 운영자 검토 정책을 별도 확정한 뒤 진행한다.

## 8. 다음 수집 정책

* PROFILE_READY: 현재 9617 기준 계약을 재사용하되 Evidence ID 검증 후 생성
* PARTIAL_DATA: section별 claim eligibility를 적용하고 메뉴 부재는 공식 메뉴 claim을 금지
* LEGACY_UNVERIFIED: 최대 3건 대표 표본만 DOM 재검증하고 lifecycle 생성 후 claim 단위 재평가
* COLLECTION_FAILED/IDENTITY_CONFLICT: Profile 생성 금지, 원인 검토 우선

이번 pilot 결과만으로 수백 건 자동 승인이나 전체 재수집을 시작하지 않는다.

## 9. 테스트 및 안전

* Semantic Profile targeted tests: 7 passed
* AI Harness: PASS, 173 passed, 1 warning
* Detail 외부 실행: dry-run 3건, 실제 저장 2건, freshness 재실행 2건
* 신규 Profile Qwen 호출: 3회 / 최대 3회
* Provider/Qwen Entity Resolution: 미실행
* DB Profile 저장/Embedding/Qdrant: 미실행
* 기존 9617 재생성: 미실행
* 기존 Place ID/Venue/Provider 정책 변경: 없음
* 기존 산출물: 보존
* commit/push/staging: 없음

실제 저장 전 별도 pre-write snapshot 파일은 생성하지 못했으므로, persistence 전후의 완전한 row-level snapshot 비교는 미완료로 기록한다. runtime report와 저장 후 입력/결과 산출물은 보존했다.
