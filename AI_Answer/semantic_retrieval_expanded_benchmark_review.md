# ZeroPay Lunch AI — Semantic Retrieval Expanded Benchmark & Runtime Readiness

## 1. 결론

기존 4건 benchmark 이후 최대 15건 확장을 시도했지만, 안전하게 승인 가능한 추가 Profile을 확보하지 못해 확장 Retrieval을 실행하지 않았다. 현재 최종 Runtime 판단은 **NO-GO**다.

기존 4건에서 측정된 Claim Vector 결과는 유지된다.

| 방식 | Precision@1 | Hit@3 |
|---|---:|---:|
| Restaurant Vector baseline | 0.40 | 0.95 |
| Claim Vector + Router | 0.90 | 1.00 |
| Claim Vector + 최소 taxonomy 보정 | 0.90 | 1.00 |

그러나 이 수치는 4개 Restaurant에 대한 결과이며, 10개 이상 표본으로 재검증되지 않았다.

## 2. READ-ONLY DB 조사

개발 MySQL을 읽기 전용으로 확인했다.

* restaurants: 517건
* NAVER numeric MATCHED: 360건
* Lifecycle이 존재하는 ELIGIBLE/MATCHED 모집단: 8건
* 기존 제외 목록을 적용하면 안전하게 재사용 가능한 Semantic Profile 산출물: 기존 4건

새 Profile/Evidence Catalog가 없는 Legacy 대상은 Lifecycle이 없으므로 기존 품질 Gate를 통과하지 못한다. 이를 무시하고 Embedding 대상에 추가하지 않았다.

## 3. 제한적 Detail dry-run

추가 후보에 대해 7건의 bounded dry-run을 수행했다. DB write는 수행하지 않았다.

| ID | 결과 | 관찰 |
|---:|---|---|
| 9562 | SUCCESS | 메뉴 4, 영업시간 1, 리뷰 35 visitor/14 blog |
| 9564 | FAILED | 리뷰 없음; 저장/승격 불가 |
| 9568 | SUCCESS | 메뉴 22, 영업시간 1, 리뷰 268 visitor/27 blog |
| 9569 | SUCCESS | DOM 수집 성공 |
| 9570 | SUCCESS | DOM 수집 성공 |
| 9571 | SUCCESS | DOM 수집 성공 |
| 9574 | SUCCESS | 메뉴 12, 영업시간 1, 리뷰 108 visitor/18 blog |

Runtime report는 `ai/build/reports/naver-place-pipeline/e2e/semantic-benchmark-dryrun-*-detail.json`으로 보존했다.

## 4. 추가 Semantic Profile 시도

9562·9568·9569에 대해서만 Qwen Semantic Profile을 각 1회 실행했다. 총 Qwen 호출은 3회이며 retry는 없었다.

세 대상 모두 기존 Validator가 다음 사유로 `strictProfileReady=false`를 반환했다.

* Section Lifecycle 부재
* Evidence section 상태가 SUCCESS로 확인되지 않음
* 일부 Claim의 evidence type/status 불일치

9564는 리뷰 부재로 Profile 대상에서 제외했다. 9570·9571·9574는 Profile 생성까지 진행하지 않았다. 따라서 신규 Claim Point는 0개이며, 기존 REJECTED/REVIEW_REQUIRED Claim을 자동 승인하지 않았다.

상세 결과: [semantic_retrieval_expanded_benchmark_results.json](semantic_retrieval_expanded_benchmark_results.json)

## 5. 음식 taxonomy 및 ranking 판단

기존 taxonomy는 유지했다.

* 스시 ↔ 초밥: synonym
* 일식 → 초밥·우동·후토마끼: category
* exact > synonym > category 원칙을 테스트 구조에 반영

하지만 확장 표본이 생성되지 않아 `일식` category 개선 여부와 `맛있다는 평가가 많은 곳`의 mention count ranking을 10개 이상 표본에서 검증하지 못했다.

기존 4건에서 확인된 실패는 그대로 남아 있다.

* 일식 Query에서 category와 embedding 순위가 충돌할 수 있음
* 정량 맛 Query에서 mention count 739인 9731보다 9580이 높게 나오는 사례가 있음

Raw count, `log1p(count)`, 상대비중 후보를 운영 weight로 확정하지 않았다. 실제 denominator가 확인된 데이터만으로 별도 비교해야 한다.

## 6. GO/NO-GO

사전 기준은 Precision@1 0.80 이상, Hit@3 0.90 이상, leakage 0, Evidence Trace 100%였다. 기존 4건 Claim Vector는 이를 충족했지만, 현재 작업의 최소 10 Restaurant 조건을 충족하지 못했다.

따라서 수치만으로 Runtime 연결을 승인하지 않고 **NO-GO**로 판정한다. FastAPI/Spring Runtime API 초안은 구현하지 않았으며 기존 draft는 설계 자료로만 보존했다.

## 7. 다음 단계 조건

1. Lifecycle 없는 Legacy 대상은 Detail persistence 또는 승인된 재검증 절차로 먼저 품질 상태를 확정한다.
2. 최소 10개 이상의 Profile-ready 또는 Claim-level 승인 가능한 Restaurant를 확보한다.
3. 일식 exact/synonym/category Query와 정량 TASTE Query의 Ground Truth를 사전 고정한다.
4. mention count의 분모가 있는 경우에만 정규화 비율을 비교한다.
5. 확장 Benchmark가 기준을 충족한 뒤 FastAPI contract test를 별도 수행한다.

## 8. 안전·테스트

* Qwen 호출: 3회, 재시도 0회
* Detail dry-run: 7건, persistence 0건
* Provider/Qwen Entity Resolution: 미실행
* Place ID 탐색/교체: 미실행
* MySQL 원본 변경: 없음
* 기존 Qdrant Collection 삭제/수정: 없음
* AI Harness: 180 passed, 1 warning
* `git diff --check`: PASS
* Git add/commit/push: 없음

기존 Working Tree 및 모든 dry-run/profile 산출물을 보존했다.
