# MVP Recommendation UI 및 결정론 설명 검토

## 결과 요약

Semantic Retrieval과 LLM Explanation의 정책을 분리했다. 두 flag 기본값은 모두 `false`다. Semantic runtime을 켜고 LLM explanation을 끄면 Spring의 최종 추천은 그대로 유지되고, FastAPI가 최종 후보의 Safe Fact로 deterministic `reason`을 만든다. 이 경로에서는 FastAPI가 Ollama client조차 생성하지 않는다.

React는 기존 SSE `recommendations` 이벤트와 `items[].reason` 계약을 재사용한다. 카드 UI에는 이미 reason 표시가 있었으며, legacy 응답에서 reason이 없거나 공백이어도 안전하게 렌더하도록 타입과 조건부 표시를 보강했다.

검증은 AI 228 passed/1 skipped, Backend build 성공, Frontend 11 passed 및 production build 성공이다. 실제 사용자 개발 MySQL을 쓰는 공개 Chat/SSE E2E는 실행하지 않았다. 따라서 UI·SSE·Spring/AI 계약의 격리 테스트는 통과했지만 browser부터 실제 FastAPI/Qdrant까지 이어지는 Local E2E 완료로 간주하지 않는다.

## 1. Feature Flag 및 정책

| Flag | 기본값 | 책임 |
|---|---:|---|
| `AI_SEMANTIC_RUNTIME_ENABLED` | `false` | Spring에서 FastAPI Intent와 candidate-scoped Semantic Retrieval 사용 |
| `AI_LLM_EXPLANATION_ENABLED` | `false` | Qwen 자연어 설명 사용 허용 |

Qwen 설명은 Spring 요청의 `useLlm=true`와 FastAPI 서버의 `AI_LLM_EXPLANATION_ENABLED=true`가 모두 참일 때만 실행된다. 어느 한쪽이라도 false면 Safe Fact 결정론 설명을 반환한다. LLM flag만 true이고 Semantic Runtime이 false이면 관련 Spring AI bean이 등록되지 않으므로 LLM 설명은 비활성 상태다. 운영 기본값은 변경하지 않았다.

권장 local MVP 설정은 다음과 같다.

```text
AI_SEMANTIC_RUNTIME_ENABLED=true
AI_LLM_EXPLANATION_ENABLED=false
```

## 2. Safe Fact 설명 경로

기존 Safe Fact 생성과 query 관련 보조 Evidence 조회를 유지했다. Spring이 확정한 최종 Restaurant ID들에 한해서 FOOD, DINING_CONTEXT, TASTE 등의 Evidence를 보충하고, 요청에 명시된 조건과 해당 claim text가 직접 맞는 경우에만 Safe Fact를 만든다. 보조 retrieval은 최종 ID scope를 벗어나지 않는다.

LLM 비활성 시 출력은 입력된 Safe Fact만 조합한다. 예를 들어 FOOD와 혼밥 fact가 모두 있으면 두 사실을 함께 표현하고, 음식 메뉴 fact만 있으면 메뉴만 설명한다. Evidence가 전혀 없으면 기존의 제한된 일반 fallback을 사용한다. 운영 정보, 결제, 가격, 위치 등은 LLM 입력에 전달하지 않는다.

추가 변경:

- Spring `ExplanationRequest.useLlm`이 LLM flag를 명시적으로 전달한다.
- Spring Client는 `useLlm=false`인데 응답 source가 `LLM`이면 응답을 거부한다.
- FastAPI 기본 설정은 LLM 비활성이고, 비활성일 때 Ollama client를 생성하지 않는다.
- LLM 경로의 기존 validator, timeout, deterministic fallback은 보존했다.
- FastAPI 응답의 source(`LLM` / `DETERMINISTIC_FALLBACK`)는 내부 검증용이며 React에는 노출하지 않는다.

## 3. Recommendation, SSE 및 UI

순위·membership 결정은 기존 Spring 흐름을 유지한다. Explanation enricher는 max 3 및 Venue dedup 이후에만 `reason`을 바꾸며, ID나 순서는 건드리지 않는다. Semantic 결과가 비어 있거나 설명 호출이 실패하면 기존 Spring recommendation과 기존 reason을 보존한다.

Chat API는 기존 `recommendations` SSE event를 사용하고, 각 Recommendation DTO의 `reason`을 함께 보낸다. React SSE parser는 payload를 그대로 message state에 넣으며, `MessageList`가 이름과 reason을 카드에 표시한다. 이벤트 계약을 새로 만들지 않았다.

- 추천 1~3건: 기존 카드 목록을 사용한다.
- 빈 목록: 목록 UI는 렌더하지 않고 Spring assistant 응답을 표시한다.
- reason이 없는 legacy item: reason 문단만 생략하고 나머지 카드는 정상 렌더한다.
- FastAPI 장애: Spring fallback이 후보를 유지하므로 UI에는 내부 AI 오류를 노출하지 않는다.

## 4. 검증 결과

| 검증 | 결과 |
|---|---|
| Safe Fact 및 LLM off/on 조합, multi-intent, validator/fallback | `pytest tests/test_recommendation_explanation.py`: 23 passed (full AI harness에 포함) |
| AI Harness | 228 passed, 1 skipped; skipped 항목은 opt-in live runtime test |
| Backend Harness | `./scripts/check-backend.sh`: BUILD SUCCESSFUL; XML 결과 79 test cases, 1 skipped; H2 test profile 사용 |
| Frontend Harness | `./scripts/check-frontend.sh`: production build 성공, 5 test files / 11 tests passed |
| SSE 추천 payload의 reason 전달 | ChatController MockMvc test에서 확인 |
| Recommendation max3/order, explanation stage | targeted Recommendation service tests 포함 |
| Git diff check | `git diff --check`: PASS |

AI/H2 테스트는 격리된 test 환경이다. 실제 MySQL에는 테스트 데이터를 쓰지 않았다.

## 5. 실제 실행 및 안전성

- 실제 Qwen Explanation 호출: **0회**
- 이번 검증에서 실제 사용자 Query로 실행한 Local E2E: **0건**
- MySQL write: **0건**
- Qdrant write/upsert/delete: **0건**
- 실제 Qdrant retrieval/query embedding: **실행하지 않음**. AI live runtime test는 opt-in 상태로 skip 됨.
- 신규 데이터 수집, Profile/Embedding 생성, Migration, Ranking 변경: **없음**
- `AI_SEMANTIC_RUNTIME_ENABLED` 및 `AI_LLM_EXPLANATION_ENABLED` 기본값: **false 유지**

ChatStreamService는 사용자 메시지/대화 완료 상태를 persistence한다. 실제 공개 Chat/SSE URL에 요청하면 개발 MySQL에 기록될 수 있어 호출하지 않았다. 현재 통합 검증은 MockMvc Chat/SSE, test H2 persistence suite, Spring-FastAPI HTTP contract test, FastAPI unit test, React SSE parser 및 UI 렌더링으로 분리했다. 안전한 격리 전체 stack에서의 브라우저 E2E는 별도 환경 준비 전까지 미완료다.

## 6. 미완료 및 다음 단계

이번 구현으로 LLM을 끈 상태의 deterministic reason과 기존 UI 전달 계약은 검증했다. 다만 실제 Semantic ON 환경에서 사용자 Query가 FastAPI/Qdrant를 거쳐 React에 표시되는 cross-service live E2E는 실행되지 않아, 이 단계 전체를 종단 간 완료로 선언하지 않는다.

다음 검증은 개발 데이터와 분리된 test DB/계정 및 테스트용 Restaurant fixture를 사용하는 전체 local stack에서 진행할 수 있다. 이때 Semantic ON, LLM OFF를 적용하고 최대 3 Query를 확인한다. LLM Explanation은 별도 품질 gate 3/3 GROUNDED 달성 전까지 계속 OFF로 둔다.
