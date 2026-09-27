# 프로젝트 학습 2 — Spring 추천과 채팅 스트림

## Spring이 소유하는 것

Spring은 사용자와 데이터의 신뢰 경계다. 인증된 공개 HTTP API, conversation/history persistence, preference/meal history, ZeroPay·영업시간·budget 기반 후보 제한, 최종 순위와 Venue dedup을 소유한다. FastAPI는 내부 AI signal만 반환한다.

## 요청 진입부터 추천까지

| 단계 | 코드 | 역할 |
|---|---|---|
| 인증된 입력 | `chat/api/ChatController.java::sendMessage` | `/api/conversations/{conversationId}/messages`, `Authentication` principal, trim된 message를 전달 |
| PENDING 생성·SSE | `chat/application/ChatStreamService.java::streamReply/emitReply` | 대화 소유권 확인 후 user/assistant 메시지를 저장, 진행 이벤트 발행, 추천 호출 |
| 사용자 context | `recommendation/application/RecommendationContextService.java::build` | default budget, spice, preferred/disliked categories, allergies, recent meals로 요청 구성; intent 분석 |
| AI client | `recommendation/ai/FastApiSemanticClient.java` | intent/retrieval HTTP POST, request/response 계약 검증, candidate scope 밖 ID 거부 |
| AI 실패 처리 | `FallbackAwareIntentAnalyzer`, `SemanticCandidateEnricher` | 설정된 fallback이 켜진 경우 deterministic fallback 또는 signal 없는 원 후보 유지 |
| 추천 orchestration | `restaurant/application/RestaurantRecommendationService.java::recommend` | DB 조회, hard filter, semantic enrichment, final order, Venue dedup, 3개 제한 |
| 메시지 완료 | `ChatPersistenceService::completeExchange` | assistant content와 `message_recommendations` 저장 |

## 실제 hard filter

Repository의 open-restaurant query는 active, `recommendation_ready`, `recommendation_eligibility='ELIGIBLE'`, ZeroPay, `legal_dong_code='11680108'`, 주간 운영시간, closed day/hour를 확인한다. Java `matches`는 다음을 보탠다.

- `zeroPayAvailable` 재확인
- 명시 budget이 있으면 평균가격 null 또는 초과를 fail-closed
- intent category가 있고 Restaurant category가 분류되어 있으면 일치 여부
- 사용자 disliked category
- recent restaurant ID

Verified NAVER-serving 경로는 fresh menu/hours state, unique external place mapping과 `VerifiedHoursPolicy`/`ServingReadinessPolicy`를 통해 추가 후보를 낼 수 있다. `VerifiedNaverServingCandidateService`는 현재 budget 입력이 있으면 price basis 미확정으로 빈 목록을 반환한다. 최종 merge 뒤에도 `matches`가 적용된다.

recent meal을 단순 Restaurant ID로만 제외하지 않는다. `confirmedVenueIds`가 반환한 CONFIRMED + ACTIVE Venue ID로 recent와 candidate를 정규화하므로 같은 장소의 연결된 다른 지점/레코드도 제외할 수 있다. association이 확인되지 않으면 기존 Restaurant ID로 호환된다.

### AI에 맡기지 않는 이유

ZeroPay, 영업시간, 가격, service-area, 사용자 최근 식사는 결과를 설명할 수 있는 authoritative data와 명확한 비교 규칙이 있다. Vector similarity나 LLM 답변에 맡기면 동일 질문에 따라 가맹/영업 자격이 바뀔 수 있다. 반면 “혼밥하기 좋은” 같은 표현은 열거식 코드 규칙이 쉽게 커지므로 semantic retrieval signal로 다룬다.

## AI 후보 보강과 최종 순위

`SemanticCandidateEnricher.enrich(message, candidateIds)`는 hard-filtered 목록을 전달한다. 응답 결과가 일부 후보만 포함하더라도 Spring은 원 후보 전체를 유지하고 있는 신호만 붙인다. FastAPI 응답을 후보 생성기로 쓰지 않는다.

현재 `RestaurantRecommendationService` 코드에서 semantic signal이 하나 이상 있으면 ordering은:

1. `retrievalScore` 내림차순
2. `semanticSimilarity` 내림차순
3. 기존 deterministic score 내림차순
4. 더 낮은 가격, Restaurant ID 순

이다. 이는 일부 root/current-state 문서의 “semantic tie-break only” 설명과 다르다. 실제 코드와 `hybridSemanticRelevanceCanOutrankDeterministicPreferenceScore` 테스트를 기준으로 학습해야 한다. AI 신호가 없으면 deterministic 순서를 사용한다. Spring은 어떤 경우에도 최종 ordering owner다.

그 다음 confirmed active Venue를 기준으로 중복 제거하고 `.limit(3)` 한다. 그러므로 FastAPI 검색 순서가 최종 화면 순서와 같다고 가정하면 안 된다.

## 장애 시 fallback

`AI_SEMANTIC_RUNTIME_ENABLED=false`면 AI bean을 연결하지 않아 Spring analyzer와 deterministic ranking을 사용한다. ON인데 intent API가 실패하면 `FallbackAwareIntentAnalyzer`가 `AI_FALLBACK_ENABLED` 설정에 따라 기존 `TemporaryIntentAnalyzer`로 넘어간다. Retrieval 실패 시 `SemanticCandidateEnricher`는 fallback 설정이 켜져 있으면 hard-filtered ID들을 모두 signal 없이 돌려준다. 이때 deterministic ordering이 계속된다. fallback이 꺼져 있으면 예외가 상위로 전파되어 SSE 오류 이벤트가 될 수 있다.

`application.yml`/`AiIntegrationProperties`에는 `AI_MAX_ATTEMPTS` 기본 1 설정이 있지만, 현재 `FastApiSemanticClient.post`는 이 값을 사용해 재시도 loop를 돌지 않는다. 실제 Spring HTTP client는 한 번 요청한다. semantic retrieval의 transient retry는 FastAPI graph가 소유한다. 설정 필드가 있다는 사실을 실제 retry 동작으로 오해하지 않는다.

## SSE 응답

`ChatStreamService`는 `accepted`, 두 `progress`, `recommendations`, `assistant_delta`(텍스트를 12 codepoint 단위로 분할), `completed`를 보낸다. 실패하면 교환을 FAILED로 저장하고 `error` event를 보낸다. 이것은 token-by-token LLM generation stream이 아니라, 추천을 계산한 뒤 결과/답변을 단계 이벤트로 보내는 SSE다.

React의 `frontend/src/api/chat.ts::streamChatMessage`는 fetch stream reader로 SSE block을 parse하고, `useChatStream.handleStreamEvent`가 추천과 텍스트 상태를 업데이트한다. 카드 렌더링은 `components/chat/MessageList.tsx`에 있다.

## Spring에서 다시 읽을 경로

`RecommendationContextService.build` → `RestaurantRecommendationService.recommend` → `RestaurantJpaRepository.findOpenRestaurants` 및 `VerifiedNaverServingCandidateService` → `FastApiIntentAnalysisAdapter` / `FastApiSemanticClient` → `SemanticCandidateEnricher` → `confirmedVenueIds`와 final sort → `ChatStreamService` → `ChatPersistenceService`.

### 내가 이해했는지 확인

- 명시 예산에서 null 가격이 왜 통과하지 않는가?
- retrieval 결과에 없는 Spring candidate가 왜 사라지지 않는가?
- Venue dedup은 recent meal과 최종 출력에서 각각 어떻게 쓰이는가?
- SSE가 생성형 LLM token streaming과 다른 점은 무엇인가?
