# Grounded LLM Recommendation Explanation — 구현 및 제한 Pilot 검토

## Executive Summary

Spring의 기존 추천 목록을 변경하지 않고 최종 선택·순위·Venue dedup·max-3 뒤에 설명을 덧붙이는 API/Client 경로를 구현했다. FastAPI 계약, Spring 단위 검증, 전체 AI/Backend Harness는 통과했다. 다만 제한된 실제 Qwen 파일럿 3건 모두 ZeroPay 사용 가능을 “무상/무비자 결제”로 잘못 표현해 최종 품질 판정은 **UNSUPPORTED / 배포 승인 불가**다. 원인을 제거하는 최소 수정과 회귀 테스트는 추가했지만 호출 제한을 지키기 위해 재검증은 하지 않았다.

실제 결과는 [recommendation_explanation_pilot_results.json](recommendation_explanation_pilot_results.json)에 보존했다.

## 1. 기존 추천 흐름 및 연결 위치

기존 Spring 흐름에서 Hard Filter 이후 candidate-scoped semantic retrieval을 하고 결정론 점수, 의미 유사도 tie-break, CONFIRMED+ACTIVE Venue dedup 및 최대 3개 제한을 수행한다. 새 `RecommendationExplanationEnricher`는 이 최종 리스트가 생성된 뒤 호출된다. 반환 시 `RecommendationItem.reason`만 교체하며 ID, 개수, 순서는 유지한다. FastAPI는 Restaurant 선택/순위 조정을 수행하지 않는다.

`reason`은 이미 Recommendation DTO 및 기존 Chat persistence 계약에 존재하여 응답 필드나 Schema Migration은 추가하지 않았다. 이번 검증에서는 Chat/SSE 경로를 실행하지 않았고 DB 쓰기도 없었다.

## 2. Request/Response와 Grounded Context

`POST /internal/v1/recommendation-explanations`는 최대 3개 Restaurant를 한 번에 받는다. 각 항목은 ID, 표시 이름, 최대 10개의 matched Claim(`claimType`, Claim text, match type, Evidence IDs), deterministic fact를 포함한다. 응답은 각 Restaurant ID, 한 문장 설명, 사용 Evidence ID, `LLM`/`DETERMINISTIC_FALLBACK` 출처다.

Python은 schema, ID의 정확한 목록·순서, 중복, 비어 있지 않은 설명, 320자 제한, 식당별 허용 Evidence subset 및 알려진 미근거 표현을 검증한다. 실패하면 Claim Type에 맞는 결정론 문구로 대체한다. Spring Client는 DTO 및 ID/순서/Evidence/길이를 재검증하고, 호출 실패 시 기존 reason 리스트를 원형 그대로 반환한다.

## 3. Prompt 및 수정된 grounding 정책

별도 system prompt는 선택/순위 변경, 메뉴·가격·영업·거리·인기·평점·분위기 추론과 과장을 금지한다. 초기에 Restaurant 이름과 `zeroPayAvailable`/`budgetMatched`를 FastAPI request에 포함했고 모델에도 제공했다. 실제 출력은 `제로페이 사용 가능`을 “무상 결제”, “무비자 결제”로 잘못 바꿔 썼다.

확인된 원인을 반영해 LLM 입력은 query, opaque Restaurant ID, 승인 matched Claims로 축소했다. 이름은 Claim 근거가 아니므로 prompt에서 제거했고, ZeroPay/예산 fact는 기존 Spring deterministic reason에서 계속 표현한다. “무료/무상/공짜/무비자” 등 검증된 오표현 및 기타 금지 assertion은 Python 검증에서 fallback 처리한다. 이 수정은 실행되지 않은 실제 재생성 성공으로 간주하지 않는다.

## 4. 실제 제한 LLM Pilot

로컬 `qwen3.5:9b`와 기존 `zeropay_semantic_claim_pilot_v12` (40 points, 1024 dimensions, Cosine)을 사용했다. FastAPI intent → candidate-scoped retrieval(9617만 전달) → explanation을 세 query에 각 한 번씩 실행했다. 총 3 Qwen 호출, retry 0, 측정 총 elapsed는 각 API 흐름 기준 7.840s, 3.570s, 3.716s다. 입력 Claim과 Evidence ID는 실제 검색 응답 그대로 기록했다.

| Query | 생성 결과 | 판정 |
|---|---|---|
| 떡볶이 먹고 싶어 | 메뉴 근거와 함께 “무상 결제”를 주장 | UNSUPPORTED |
| 혼밥하면서 떡볶이 먹고 싶어 | 메뉴 Claim만 전달되어 혼밥은 주장하지 않았으나 “무비자 결제”를 주장 | UNSUPPORTED; 맥락 근거 누락도 확인 |
| 가성비 좋은 곳 | TASTE Claim과 맞는 평가를 표현했으나 “무비자 결제”를 주장 | UNSUPPORTED |

세 건 모두 model이 고른 ID·Evidence trace 구조는 맞았지만, 의미적 정합성 검토에서 실패했다. UI에 노출 가능한 GROUNDED 응답은 0/3이다. 이 파일럿은 Spring 공개 Chat/SSE 또는 실 DB를 호출하지 않았다.

## 5. Timeout, fallback, feature flag

Ollama는 기존 `OllamaClient`를 재사용하고 Semantic Profile 전용 설정으로 기본 24초 timeout(허용 1–60초), `num_predict=256`, retry 없음으로 실행한다. 모델명은 `RECOMMENDATION_EXPLANATION_MODEL`을 지정하지 않으면 기존 `QWEN_MODEL`/기본 Qwen 설정을 사용한다. Spring explanation response timeout은 `AI_EXPLANATION_RESPONSE_TIMEOUT` 기본 27초다.

설명은 `AI_SEMANTIC_RUNTIME_ENABLED`에 묶였다(기본 false). OFF이면 Intent/Semantic/Explanation AI 호출이 없고 기존 추천 reason을 유지한다. ON일 때 설명 endpoint 장애·timeout·schema 오류는 기존 추천 전체를 실패시키지 않고 원래 reason과 추천 목록을 보존한다. Qwen 오류/JSON/grounding 오류는 FastAPI 내 deterministic fallback으로 처리된다. 설명은 기존 reason 필드에만 반영된다.

## 6. 테스트 및 검증

- FastAPI targeted tests: 정상 schema, ID/Evidence 불일치, unsupported 표현, invalid JSON, timeout, empty evidence, 3건 상한 및 endpoint 응답 검증.
- AI Harness: **213 passed, 1 skipped** (opt-in live test), 1 upstream Starlette deprecation warning.
- Backend targeted tests: FastAPI Client, explanation enricher, recommendation ordering/limit 테스트 통과.
- Backend Harness: **BUILD SUCCESSFUL** (compile, tests, build).
- `git diff --check`: 실행 완료.
- Spring→실제 FastAPI explanation의 end-to-end 실행은 하지 않았다. 실험 상한 3회가 실제 FastAPI Qwen 호출에 사용되었으며, DB write 또는 Chat/SSE는 수행하지 않았다.

## 7. 불변성 및 안전

이번 작업은 코드/문서 및 테스트만 변경했다. MySQL, Qdrant, Place ID, Venue, Profile 및 Detail 데이터에 쓰지 않았고, React, Migration, public Chat/SSE 전체 E2E, 배포, LangGraph는 수행하지 않았다. 기존 dirty working tree는 보존했으며 Git add/commit/push는 하지 않았다.

## 8. 결론 및 다음 단계

구현된 책임 경계와 fallback 테스트는 통과했으나 **완료 기준의 실제 local LLM 품질 검증은 실패**했다. 기능은 현재 feature flag 기본 OFF를 유지해야 한다. 다음 별도 확인 단계에서는 새 prompt 입력 계약과 validator를 offline fixture로 검증한 뒤, 새 실행 승인 범위에서 1–3건 이하의 capped live test를 수행한다. 혼합 음식·이용맥락 query에서 retrieval이 DINING_CONTEXT Claim을 전달하도록 기존 router/retrieval 계약을 별도로 점검한다. 검증 전 FastAPI/Spring 기능 flag를 켜거나 React에 표시하지 않는다.
