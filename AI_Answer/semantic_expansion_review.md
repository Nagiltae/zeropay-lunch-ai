# Semantic Coverage Expansion 검토

## 판정

**SEMANTIC EXPANSION BLOCKED BY DETAIL COVERAGE**. 신규 strict-ready Restaurant가 0곳이어서 stop condition에 따라 Qwen Profile 생성, Embedding, 신규 Qdrant Collection, Ground Truth v3 검색 및 expanded benchmark를 실행하지 않았다.

## 감사 범위와 기준

2026-09-25 개발 MySQL을 SELECT 전용으로 조사했다. 모집단은 ACTIVE, ELIGIBLE, 논현동 법정동 코드 11680108, NAVER MATCHED, 숫자 Place ID다. 결과 모집단은 360곳이다.

실제 기준 코드는 ai/app/semantic_profile_shadow.py의 build_input이며 다음 다섯 조건으로 strictProfileReady를 산출한다.

- MENU / BUSINESS_HOURS / REVIEW Lifecycle 모두 SUCCESS
- 가격 숫자 또는 가격 텍스트가 있는 활성 메뉴 1개 이상
- open_time과 close_time이 모두 있는 활성 영업시간 row 1개 이상

기준 코드 자체는 Place ID ownership, verification identity, freshness를 판정하지 않는다. 보고서와 코드 간 차이를 기록하고 독립 점검으로 보완했다. strict-ready 5곳은 모두 Numeric Place ID owner가 유일하고 NAVER verification이 VERIFIED이며, 가장 오래된 section checked_at도 30일 freshness 정책 안(최대 2일)이었다.

## 실제 Coverage

| 항목 | 건수 |
|---|---:|
| 전체 Restaurant / ACTIVE | 517 / 517 |
| ACTIVE + ELIGIBLE | 405 |
| 논현동 ACTIVE + ELIGIBLE | 402 |
| 논현동 Numeric NAVER MATCHED + ELIGIBLE | 360 |
| 세 Lifecycle SUCCESS + 가격 메뉴 | 12 |
| 위 조건 + 구조화 반복 영업시간 | 5 |
| 소유권 충돌 | 0 |
| identity/freshness 추가 점검 통과 strict-ready | 5 |
| 이미 Profile artifact가 있는 strict-ready | 5 |
| 신규 strict-ready / 신규 생성 가능 | **0 / 0** |

Strict-ready 기존 대상은 9568 청기와, 9571 피자스쿨 강남논현점, 9574 청담머구리, 9590 마츄피츄, 9617 (주)에스지푸드 논현역 마성떡볶이다. 기존 산출물은 재생성하지 않았다.

## 제외 사유와 Restaurant 목록

- Lifecycle 없는 Legacy: **345곳**. 정확한 ID 전체를 coverage audit JSON의 noLifecycleRows.restaurantIds에 보존했다. 기존 detail row 존재를 성공 Lifecycle로 간주하지 않았다.
- 구조화 반복 영업시간 부재: **7곳** — 9559, 9560, 9562, 9567, 9569, 9570, 9580.
- MENU ABSENT_CONFIRMED 및 가격 메뉴 없음: **3곳** — 9654, 9731, 9750.
- 기존 strict-ready Profile 재사용: **5곳** — 9568, 9571, 9574, 9590, 9617.

이는 360곳의 disjoint partition이다: Legacy 345 + 구조화 시간 부족 7 + 메뉴 ABSENT 3 + strict-ready 5.

## Batch 및 Retrieval 단계

- 계획 Batch 상한: 25. 적격 신규 수가 0이므로 시작하지 않았다.
- checkpoint/resume: 현재 단일 Restaurant CLI이며 resumable Profile batch runner는 확인되지 않았다. batch/resume 테스트를 실행하지 않았다.
- Profile Qwen 호출: **0**
- 신규 Profile 성공/실패: **0 / 0**
- 기존 strict-ready 재사용 후보: **5**
- Embedding 호출: **0**
- 신규 Claim Point 및 Qdrant writes: **0**
- 신규 Shadow Collection: 생성하지 않음
- Ground Truth v3: 실제 query/정답을 만들거나 frozen 처리하지 않았다. 상태 stub만 생성.
- Expanded benchmark: 실행하지 않음; 수치는 계산하지 않음.
- TASTE quantitative: 평가하지 않음.

## 기존 v12와 artifact 보호

v12를 READ-ONLY로 조회했다: zeropay_semantic_claim_pilot_v12, 40 points, 1024 dimensions, Cosine. Collection write endpoint를 호출하지 않았다. 기존 Ground Truth v2와 benchmark artifact를 변경하지 않았다.

기존 frozen v2 기준은 10 Restaurant / 22 Query, Hybrid P@1 0.9545, Hit@3 1.0000, Evidence Trace 100%, leakage 0이다. 이는 기존 artifact 참조이며 이번에 재계산하지 않았다.

## 산출물

- [Coverage audit](/Users/nagiltae/IdeaProjects/zeropay-lunch-ai/AI_Answer/semantic_expansion_coverage_audit.json)
- [Profile batch manifest](/Users/nagiltae/IdeaProjects/zeropay-lunch-ai/AI_Answer/semantic_expansion_profile_batch_manifest.json)
- [Index manifest (blocked)](/Users/nagiltae/IdeaProjects/zeropay-lunch-ai/AI_Answer/semantic_expansion_index_manifest.json)
- [Ground Truth v3 status (blocked)](/Users/nagiltae/IdeaProjects/zeropay-lunch-ai/AI_Answer/semantic_retrieval_ground_truth_v3.json)
- [Benchmark results (blocked)](/Users/nagiltae/IdeaProjects/zeropay-lunch-ai/AI_Answer/semantic_expansion_benchmark_results.json)
- [Benchmark metrics (not computed)](/Users/nagiltae/IdeaProjects/zeropay-lunch-ai/AI_Answer/semantic_expansion_benchmark_metrics.json)

## 검증과 안전

- Targeted profile/retrieval tests: **14 passed**
- AI Harness: **228 passed, 1 skipped** (live runtime test)
- MySQL: SELECT only; DB writes 0
- Qdrant: v12 metadata/count read-only 조회; writes 0
- Qwen Profile calls 0; Embedding calls 0
- Git add/commit/push 미실행
- v12 Collection, GT v2, prior benchmark artifact 변경 없음

## 다음 단계

Coverage를 넓히려면 별도 Detail Quality Backfill이 필요하다. 이번 범위에서는 crawler, Provider lookup, Place ID 변경, Detail persistence를 실행하지 않았다. 다음 Backfill도 section validation, freshness, ownership/identity 보호를 유지한 채 제한적으로 수행한 후 재감사해야 한다. Runtime collection은 v12로 유지한다.
