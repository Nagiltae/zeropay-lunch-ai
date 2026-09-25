# Recommendation Explanation Grounding Revalidation

## 결론

Safe Fact 변환, 최종 Restaurant ID 범위 내 보조 Evidence 조회, 출력 Validator 및 deterministic fallback을 구현했다. 동일 3개 질의를 Qwen에 각 한 번 실행했다. 이전에 나타난 결제 관련 오표현은 반환 응답에서 0건이며 Restaurant/Evidence ID 오류도 0건이다. 다만 최종 결과는 **GROUNDED 1, PARTIAL 2, UNSUPPORTED 0**으로 승인 조건인 3/3 GROUNDED를 충족하지 못했다. `AI_SEMANTIC_RUNTIME_ENABLED=false`를 유지하고 LLM 설명 기능은 품질 승인하지 않는다.

기계 판독 결과는 [revalidation results JSON](recommendation_explanation_revalidation_results.json)에 기록했다. 이전 파일럿 산출물은 덮어쓰지 않았다.

## 1. 기존 실패 원인 및 현재 코드 확인

기존 파일럿의 세 응답은 ZeroPay 사용 가능을 “무상 결제/무비자 결제”로 표현했다. 당시 LLM prompt에 Restaurant name과 `zeroPayAvailable`/`budgetMatched` deterministic fact가 들어가 있었다.

이번 구현에서는 FastAPI가 기존 요청 Contract에서 승인 Claim만 추려 Query와 함께 검토하고, Restaurant label, 원문 Claim 및 deterministic operational facts는 LLM 입력에서 제거한다. Qwen은 opaque Restaurant ID와 Safe Fact만 받는다. System Prompt 및 출력 Validator에서 결제, ZeroPay, 가격, 예산, 영업, 위치/거리, 인기/평점과 Safe Fact에 없는 음식·취향·맥락 표현을 금지하고 위반 시 deterministic fallback을 반환한다.

## 2. Safe Fact 변환

`FOOD_TYPE`/`MENU_CHARACTERISTIC`은 Query의 음식 term이 해당 Claim 본문에도 있을 때만 `FOOD` fact를 만든다. `FOOD_MENTION`은 공식 메뉴가 아닌 리뷰 언급 Fact로 구분한다. 같은 음식 term의 메뉴 근거가 있으면 중복되는 리뷰 언급 Fact를 우선 제거한다. `DINING_CONTEXT`, `TASTE`, `VENUE_CHARACTERISTIC`은 Query가 요구하고 Claim 본문에 대응 개념이 명시된 경우만 정해진 표현으로 변환한다. 모든 Fact는 원 Claim의 Evidence ID를 유지한다.

LLM 입력은 `{query, restaurants:[{restaurantId, facts:[{factType,fact,evidenceIds}]}]}` 형태다. raw Claim text, 가게 이름, 결제·예산 사실, similarity/retrieval score, input/catalog hash는 보내지 않는다.

## 3. 복합 Query의 보조 Evidence

기존 Query Router는 `혼밥하면서 떡볶이 먹고 싶어`를 주 intent인 FOOD로 검색해 DINING_CONTEXT Claim을 explanation에 전달하지 못했다. Ranking 흐름은 변경하지 않고, Spring이 최종 추천·Venue dedup·max3를 끝낸 다음 FastAPI explanation 서비스가 최종 ID만 scope로 보조 Qdrant 조회를 수행한다. Query의 secondary `diningContexts`가 있으면 DINING_CONTEXT, 명시된 taste trait이 있으면 TASTE를 함께 조회한다. 후보 추가·순위변경은 불가능하다.

실제 복합 Query에서 primary Claim은 FOOD_TYPE/E003·E011이었고, 보조 조회에서 동일 Restaurant 9617의 DINING_CONTEXT/E023·E058이 추가됐다. 최종 explanation은 두 fact를 모두 참조했다. 다른 Restaurant ID가 scope에 포함되지 않음을 회귀 테스트로 확인했다.

재검토 중 Spring Client가 설명 Evidence ID를 원 요청의 primary Claim ID와만 대조하는 계약 불일치를 추가 발견했다. FastAPI는 response에 Safe Fact 구성에서 검증된 `availableEvidenceIds`를 함께 반환하고, Spring은 `usedEvidenceIds`가 그 subset인지 검증하도록 계약을 보완했다. 이로써 최종 후보의 보조 E023/E058 인용을 Spring이 정상 수용할 수 있다. Java regression fixture로 확인했다.

## 4. Prompt, Validator 및 deterministic fallback

Prompt는 새 사실 추론 대신 Safe Fact 문장화만 요청한다. 출력은 기존 Structured Output 계약을 유지하며 restaurant ID/order, Evidence subset, 중복·빈 설명·길이를 검증한다. 금지 operational phrase 및 입력 Safe Fact에 존재하지 않는 음식/맛/맥락 marker도 차단한다.

모델 실패/검증 거부/empty evidence에는 Safe Fact template를 사용한다. 예를 들어 메뉴와 혼밥 근거가 모두 있으면 `떡볶이 메뉴가 확인되고 혼밥하기 좋다는 고객 평가가 확인돼 추천했어요.`로 반환한다. 단일 menu/taste/review fact도 각 유형에 맞는 deterministic 문구를 사용한다.

## 5. 실제 Qwen 재검증 결과

`qwen3.5:9b`, 기존 읽기 전용 Qdrant `zeropay_semantic_claim_pilot_v12`를 사용했다. 최종 후보 scope는 각 query마다 `[9617]`이었다. intent → primary candidate-scoped retrieval → explanation 요청에서 query당 최대 한 번, 총 3회 호출했고 retry는 0회다. 기록된 latency는 intent/retrieval/explanation 전체 흐름이며 순수 Qwen 생성 시간으로 오인하면 안 된다.

| Query | Safe Evidence | 최종 반환 / 출처 | 판정 |
|---|---|---|---|
| 떡볶이 먹고 싶어 | 메뉴: E003, E011 | `떡볶이 메뉴가 확인되어 추천했어요.` / deterministic fallback | GROUNDED. Qwen 응답은 API에서 fallback 처리됐으며 내부 실패 subtype은 노출하지 않아 원인을 추정하지 않음. |
| 혼밥하면서 떡볶이 먹고 싶어 | 메뉴 E003/E011, 혼밥 평가 E023/E058 | `떡볶이 메뉴가 확인된 식당에서 혼밥하기 좋다는 고객 평가가 확인됨` / LLM | PARTIAL. 두 사실 및 ID는 맞지만 문장이 부자연스럽고 추천 문구로 완결되지 않음. |
| 가성비 좋은 곳 | 고객 평가 E024, E027 | `가성비가 좋다는 고객 평가가 확인됨` / LLM | PARTIAL. 근거는 맞지만 문장 조각이며 사용자-facing 자연스러운 추천 문장 기준 미달. |

반환된 세 설명에는 “무료/무상/공짜/무비자/제로페이” 오표현, 다른 ID, scope 밖 Evidence가 없었다. 단, 첫 Query의 원본 Qwen 텍스트와 내부 fallback 원인은 API 응답에 포함되지 않아 보존되지 않았다. 현재 평가는 최종 사용자에게 반환된 결과 기준이며, 원본 생성문을 GROUNDED로 간주하지 않는다.

## 6. 기존 파일럿과 비교 및 승인

| 구분 | 이전 | 재검증 |
|---|---:|---:|
| Qwen 시도 | 3 | 3 |
| GROUNDED 최종 설명 | 0 | 1 |
| PARTIAL | 0 | 2 |
| UNSUPPORTED 반환 | 3 | 0 |
| 오표현 누출 | 3 | 0 |

사용자에게 반환되는 안전성은 개선됐고 복합 intent Evidence 전달도 동작했다. 그러나 한 건은 fallback이고 두 건의 문장 품질이 미달이므로 명시적 승인 기준 3/3 GROUNDED는 실패다. Runtime **NO-GO**, feature flag 기본 OFF 유지. 실제 Qwen 재호출은 3회 상한을 지키기 위해 수행하지 않았다.

## 7. Recommendation 불변성과 테스트

설명 단계는 Spring 최종 ID 목록을 보존하고 기존 `reason`만 교체한다. 보조 Qdrant 조회는 그 최종 ID와 query-implied Claim Types로 제한되며 ranking 결과에 다시 반영하지 않는다. 기존 Spring recommendation ordering/max3 회귀 테스트를 통과했다. 이번 실제 LLM 실험은 FastAPI local endpoint에서 수행했으며 public Spring Chat/SSE는 실행하지 않았다.

- Targeted FastAPI tests: **41 passed**.
- AI Harness: **225 passed, 1 skipped** (opt-in live test), upstream Starlette deprecation warning 1건.
- Backend Harness: **BUILD SUCCESSFUL**. 이번 변경은 Python explanation/retrieval 범위여서 Spring 소스는 바꾸지 않았으나 기존 Backend 계약 회귀 확인을 재실행했다.
- `git diff --check`: PASS.
- MySQL write 0, Qdrant write 0, 신규 embedding/indexing 0.

## 8. Feature flag, 미완료 및 다음 단계

`AI_SEMANTIC_RUNTIME_ENABLED`의 기본값은 계속 `false`다. 설명 품질이 승인되기 전 React나 public Chat/SSE에 노출하지 않는다. 다음 후보 작업은 deterministic fallback을 MVP 설명으로 사용하는 방안, validator 거부의 안전한 비민감 진단 code, 완결된 한 문장 형태의 output validation이다. 후속 재검증은 별도 호출 예산 아래 fixture를 먼저 통과시키고 최대 3회로 수행한다.

기존 Place ID, Detail, Venue, MySQL/Qdrant collection은 변경하지 않았다. 기존 Working Tree를 보존했고 Git add/commit/push는 하지 않았다.
