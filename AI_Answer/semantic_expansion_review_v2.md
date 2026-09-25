# Semantic Profile Expansion v2 — 결과 검토

## 판정

**NO-GO — Profile 품질 stop condition 발동.** 최신 공통 readiness 정책으로 READY 26곳을 확인했고, 기존 Profile 7곳을 현재 Evidence Catalog에 대조해 재사용 후보로 보존했다. 신규 Profile 대상은 19곳이었으나 첫 3개 연속 출력이 strict Evidence validation에 실패했다. 표본 의미 검토에서 validator가 `AUTO_APPROVED`로 분류한 Claim에도 Evidence에 없는 구체화가 반복됐다. 따라서 남은 Qwen 호출, Embedding, 새 Qdrant Collection, Ground Truth v3 freeze, Benchmark는 실행하지 않았다.

## Coverage와 Profile 대상

`ProfileReadinessPolicy` 기반 READ-ONLY 감사 결과 모집단 360, strict-ready 26이다. readiness 기준은 ACTIVE/ELIGIBLE, MENU·BUSINESS_HOURS·REVIEW Lifecycle SUCCESS 및 freshness, 가격 메뉴, 원문이 뒷받침하는 구조화 영업시간, 단일 Numeric NAVER Place ID owner, VERIFIED 상태를 그대로 사용했다. 기준 완화나 DB 쓰기는 없었다.

| 작업 | 건수 | Restaurant ID |
|---|---:|---|
| 최신 READY | 26 | 9559, 9568, 9569, 9570, 9571, 9574, 9580, 9603, 9617, 9639, 9659, 9715, 9759, 9791, 9801, 9826, 9839, 9853, 9865, 9904, 9954, 9973, 9996, 10021, 10042, 10053 |
| 기존 artifact 재사용·현재 Evidence 재검증 | 7 | 9568, 9569, 9570, 9571, 9574, 9580, 9617 |
| 신규 생성 계획 | 19 | 9559, 9603, 9639, 9659, 9715, 9759, 9791, 9801, 9826, 9839, 9853, 9865, 9904, 9954, 9973, 9996, 10021, 10042, 10053 |
| 기존 artifact 충돌/미검증으로 보류 | 0 | — |

기존 7개는 source artifact를 덮어쓰지 않았다. 현재 compact input/catalog를 새로 만들고 각 기존 Claim의 cited Evidence ID, sourceField, content, section, type, SUCCESS 상태를 대조한 뒤 현재 hash로 별도 shadow artifact를 만들었다. 재검증한 AUTO Claim은 총 19개다(9568: 3, 9569: 5, 9570: 2, 9571: 2, 9574: 2, 9580: 3, 9617: 2). 이 수는 자동 validator 상태이며 아래 의미 표본 검토에서 일부는 REVIEW_REQUIRED/REJECTED로 판단했다.

Dry-run에서 compact input 최대 48,407 bytes, 예상 catalog prompt 최대 44,098 bytes로 64,000-byte gate를 통과했다. menu/review/lifecycle/current input 및 catalog hash는 [계획 JSON](semantic_profile_expansion_plan.json)에 기록했다.

## Qwen batch 결과

모델은 기존 설정 `qwen3.5:9b`를 사용했다. 대상별 1회, retry 없이 총 **3회** 호출 후 연속 strict validation 실패 3회 조건으로 자동 정지했다.

| Restaurant | 호출 시간 | strict validation | Claim classifier 결과 | 주요 실패 |
|---:|---:|---|---|---|
| 9559 | 32.5초 | FAIL | AUTO 3 / REVIEW 0 / REJECTED 2 | MENU_CHARACTERISTIC에 review keyword 사용 |
| 9603 | 35.8초 | FAIL | AUTO 4 / REVIEW 1 / REJECTED 0 | VENUE_CHARACTERISTIC에 identity Evidence 사용 |
| 9639 | 35.5초 | FAIL | AUTO 4 / REVIEW 0 / REJECTED 1 | MENU_CHARACTERISTIC에 review keyword 사용 |

총 분류 결과 AUTO 11 / REVIEW_REQUIRED 1 / REJECTED 3이지만, **세 Profile 모두 전체 Evidence validation이 실패했으므로 승인 Profile 0개**다. Classifier 상태만으로 의미 승인하지 않았다. raw 출력, current input/catalog, validation 및 checkpoint는 `AI_Answer/semantic_profile_expansion_v2/<restaurantId>/`에 보존했다. batch manifest는 `PAUSED_QUALITY_FAILURE`; 남은 16개 ID는 pending 상태이며 재호출하지 않았다.

## Sample Review

10개 Restaurant의 34개 Claim을 현재 source Evidence와 대조했다(재사용 19 + 실패 출력 15). 개별 판정 및 근거는 [sample review JSON](semantic_profile_expansion_sample_review.json)에 있다. 이는 과거 산출물을 수정하거나 Claim을 승격하지 않는다.

신규 출력에서 확인한 대표 의미 오류:

- 9559: 일반 `음식이 맛있어요` keyword로 “rich juiciness and tenderness”를 만들고, 단체모임 keyword를 기업·가족 연회로 확장했다. 인테리어 keyword에서 편안한 분위기도 추론했다.
- 9603: 메뉴명에 없는 “Octopus Kimchi Juk” 조합을 생성했다. 혼밥과 청결 Evidence를 하나의 DINING_CONTEXT Claim으로 합쳤다.
- 9639: 대화/단체 키워드만으로 넓은 공간을 덧붙였고, 맛있다는 keyword에 “well-prepared”를 추가했다.

기존 artifact의 재사용 검토에서도 MENU Claim의 가격 평가/범위 과장, 메뉴에 없는 chicken topping/pizza sizes, TASTE에 없는 “satisfying” 등의 문제를 확인했다. 따라서 Evidence ID·허용 Type·section 검증만으로는 Semantic Claim 의미의 직접 지지를 보장하지 못한다.

## Embedding / Qdrant / Benchmark

- Embedding 호출: **0**
- 새 Collection `zeropay_semantic_claim_expanded_v1`: 생성되지 않음
- 기존 v12: 사전·사후 조회에서 40 points, 1024/Cosine. 쓰기·삭제·recreate 없음
- Ground Truth v3 expanded: **작성/freeze하지 않음** — 승인 가능한 신규 Profile 집합이 없으므로 Evidence 기반 완전한 확장 정답표를 만들 단계가 아님
- Expanded retrieval / 기존 22 Query regression: **NOT_RUN**
- P@1, Hit@3, Evidence Trace, leakage metric: **NOT_RUN** (0으로 간주하지 않음)
- Runtime collection 전환: **NO**, runtime 설정 미변경

`semantic_expansion_index_manifest_v2.json`, `semantic_expansion_benchmark_results_v2.json`, `semantic_expansion_benchmark_metrics_v2.json`은 실행하지 않은 단계를 명시한 BLOCKED/NOT_RUN 상태 기록이다. 이전 작업에서 이미 존재하던 `semantic_retrieval_ground_truth_v3.json`은 빈 초안(0 query, 미동결)이어서 덮어쓰지 않았다.

## 안전성 / 검증

- MySQL: 기존 SELECT-only audit/input 사용, write 0
- NAVER/provider/detail crawl: 0
- v12 Qdrant write: 0; 새 Shadow Collection 생성도 중단
- Profile Qwen: 3 calls; Embedding: 0
- checkpoint/resume targeted test: 통과. 완료된 같은 input hash는 재호출하지 않음
- Targeted tests: 16 passed; Ruff check/format: 통과
- `./scripts/check-ai.sh`: **242 passed, 1 skipped**, Poetry check/import 통과. skipped는 기존 live runtime test
- `git diff --check`: 통과
- 기존 dirty working tree 유지, Git add/commit/push 없음

## 다음 조치

Profile 확장을 재개하기 전, semantic validation을 Claim 단위로 강화해야 한다. 최소한 review keyword의 문구를 넘어선 감각·상황 추론, 메뉴 Claim의 메뉴명 외 조합/특성, 한 Claim 안의 서로 다른 속성 결합을 차단하는 검증 또는 human review gate가 필요하다. 이후 새 input hash로 재실행하더라도 이번 3개 실패를 같은 입력에 대해 자동 retry하지 말고, validator 정책과 prompt/schema 변경을 별도 버전으로 검증한 뒤 진행한다. 기존 Profile artifact와 v12는 그대로 유지한다.
