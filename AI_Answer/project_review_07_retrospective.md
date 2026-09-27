# 프로젝트 학습 7 — 설계 회고

## 잘한 설계

### 1. AI는 후보 적격성을 결정하지 않는다

Spring의 repository query와 `RestaurantRecommendationService.matches`가 service area, serving/open, ZeroPay, explicit budget, dislike/recent 조건을 먼저 적용한다. 그 ID scope 안에서만 FastAPI가 Qdrant를 검색한다. FastAPI 결과를 받는 Java client도 scope 밖 ID를 거부한다. 안전한 경계가 여러 계층에 걸쳐 테스트된다.

### 2. 최종 선택권이 Spring에 남는다

`SemanticCandidateEnricher`는 신호를 붙이고 후보를 유지한다. `RestaurantRecommendationService`가 final ordering, confirmed Venue dedup, max 3을 소유한다. Java business rule과 Python semantic retrieval을 결합하면서 authority가 모호해지지 않는다.

### 3. 실패 경로도 1급 설계로 다뤘다

FastAPI unavailable 시 fallback flag를 통해 deterministic recommendation을 이어갈 수 있고, intent 실패 fallback과 retrieval 실패 fallback을 분리했다. LangGraph는 transient retry를 한 번으로 제한하며 429/다른 4xx를 재시도하지 않는다. 실패 시 무한 호출이나 hard filter 완화가 없다.

### 4. Evidence provenance를 검색 안전성에 포함했다

Evidence ID, exact quote, atomic assertion, independent semantic verifier, source-derived scope는 “AI가 그럴듯하게 쓴 문장”과 “검색에 넣어도 되는 Claim”을 분리한다. `semanticApproved`와 `indexable`을 나눈 것은 안전한 모델링이다. 다만 이 guard가 legacy v12를 소급 안전하게 만들지는 않는다.

### 5. 재현 가능한 격리 검증

Graph path unit test, API 계약 test, disposable database/browser E2E를 둬 query별 실제 SSE와 candidate scope를 확인했다. Source artifact를 저장해 결과와 실행 환경을 사후 확인할 수 있다.

## 과하게 복잡해진 부분

### 1. Profile quality 실험의 반복 루프

Generator/Atomicizer/Verifier의 여러 버전과 수많은 retry/stability/diagnostic artifact가 남아 있다. 근거 품질을 끌어올리려는 의도는 타당했지만, 40 legacy points와 작은 frozen fixture에 많은 반복이 소비됐다. Data Pipeline이 결국 experimental/frozen으로 종료돼, 투자한 offline 품질 도구가 production profile pipeline으로 완결되지는 않았다.

### 2. 같은 intent 분석을 두 경계에서 한다

현재 Spring은 `/internal/v1/intent-analysis`를 호출해 filter context에 사용하고, 이후 graph의 intent node도 `analyze(originalQuery)`를 다시 실행한다. 같은 deterministic logic이어서 모델 latency는 아니지만, contract/logic 중복과 변경 동기화 지점이 생긴다. 단순화 시 Spring에 필요한 authoritative field와 retrieval routing field를 구분한 단일 계약을 설계하거나, 중복 계산의 비용을 명확히 측정할 수 있다.

### 3. 오프라인 실험 스크립트와 runtime 자원이 한 module에 공존

`semantic_embedding_qdrant_pilot.py`의 `embed()`는 runtime에서 재사용되지만 같은 module의 `main()`은 embedding과 Qdrant collection/point write를 한다. 함수 재사용은 실용적이나 “runtime helper를 import하는 것”과 “indexer를 실행하는 것”의 위험이 가깝다. Data Pipeline이 frozen이라면 장기적으로 runtime client와 offline writer를 패키지/권한/CLI 경계로 더 분리하는 편이 안전하다. 지금 코드는 변경하지 않는다.

### 4. 전체 시스템에 비해 LangGraph workflow는 작다

8개 node로 skip/retrieval/retry/fallback을 표현한다. 흐름이 드러나는 장점은 있지만 지속 checkpoint, human approval, multi-agent, 모델 planning은 없다. 똑같은 제어 흐름은 일반 async function으로도 충분히 표현 가능했을 수 있다. 포트폴리오에서는 graph의 conditional path와 bounded retry를 설명하고, 프레임워크 자체가 AI reasoning을 제공한다고 과장하지 않는다.

### 5. 응답/설명 코드 경계

추천 뒤 별도 explanation endpoint/enricher가 있다. LLM explanation은 evidence gating과 별도 flag로 통제하고 실제 품질 미달 기록도 남겼다. 그러나 설명은 retrieval/추천과 다른 품질 문제라서 사용자에게 보이는 안전한 deterministic reason을 기본으로 하고 LLM 문장은 좁은 별도 기능으로 관리해야 한다.

## React → Spring → FastAPI가 필요했나?

이 코드베이스에서는 Spring이 이미 auth/session, MySQL, conversation persistence, schedules, hard filters, SSE를 가진다. React→FastAPI로 직접 바꾸면 내부 AI endpoint 노출, 인증/사용자 DB 접근 이중화, hard filter의 Python 재구현 또는 Spring 우회, final order 책임 혼합이 생긴다. FastAPI는 Python embedding/Qdrant/LangGraph 생태계를 독립 경계로 제공한다. 그러므로 기존 서비스의 bounded AI integration에는 현재 3-tier 구조가 합리적이다.

새 greenfield가 React + FastAPI만으로 충분할 수는 있다. 단 그 경우 FastAPI가 auth, transactional data, business constraints, persistence까지 책임질지 먼저 결정해야 한다. “Java를 없애면 단순하다”는 말만으로 Spring이 해오던 책임이 사라지지는 않는다.

비용은 두 HTTP hop, DTO 계약, 설정·timeout·fallback 관리, 관측성/배포 서비스가 늘어난다는 점이다. 작은 단일 서비스라면 monolith 하나가 더 단순하다. 이번 프로젝트에서 Spring은 비즈니스 authority를 유지하고 Python AI tooling을 제한적으로 끌어들이는 이점을 줬다.

## AI가 필요했던 것과 필요하지 않았던 것

| 문제 | 더 적합한 방법 | 현재 판단 |
|---|---|---|
| ZeroPay/active/open/가격/최근 식사 | 일반 코드 + DB | authoritative, 재현 가능해야 한다 |
| candidate scope·Venue dedup·max3 | Spring deterministic | AI 결과가 무시할 수 없어야 한다 |
| 알려진 query routing/예산 숫자 parse | 현재 regex/rule | runtime intent route는 현재 generative LLM이 아님 |
| 한국어 query와 claim feature의 semantic similarity | embedding + Qdrant | 열려 있는 자연어 관련성 검색 신호로 사용 |
| offline 장소 entity matching | Qwen structured output + deterministic quality gate | 이름/주소의 비정형 일치 판단에 한정 |
| Semantic Profile 문장 생성/검증 | offline local model 실험 | 비용·품질 한계 때문에 pipeline frozen; 전체 production 데이터가 아님 |
| Gemini menu budget classification | 시범 실패 | NO_GO/incomplete, serving logic으로 쓰지 않음 |

## 다시 만든다면

1. 먼저 한 vertical slice와 작은 evidence cohort로 retrieval을 end-to-end 검증한다.
2. DB hard-filter, candidate scope, fallback, final ordering을 처음부터 contract test로 고정한다.
3. Profile schema에서 raw claim, evidence, source scope, index text를 처음부터 분리한다. Provenance를 사후 prefix로 고치는 실험을 줄인다.
4. offline generator/verifier, embedding writer, runtime query client를 더 단단한 실행/권한 경계로 분리한다.
5. LangGraph를 쓰기 전 ordinary async function과 비교해 branching/retry/trace가 실질적 복잡성을 줄이는지 기준을 둔다.
6. 데이터 source quality/coverage가 부족하면 profile expansion을 중단하고, 검색 성능과 profile 품질을 별도 gate로 둔다.
7. runtime 기본 feature flag는 검증과 운영 관측성이 준비되기 전까지 OFF로 둔다.

## 처음부터 다시 한다면 몇 %를 없앨 수 있나?

라인 수를 세어 측정한 결과는 아니지만, 설계 복잡성 기준으로는 **약 25~35%를 제거하거나 통합할 수 있다**고 본다. 주된 대상은 중복 intent call/adapter, 반복 생성된 pilot/diagnostic scripts, 장기간 살아남은 여러 indexing 실험 경로, 작은 orchestration에 대한 과한 artifact/version matrix다. 이 수치는 코드 줄 비율을 분석한 수치가 아니라 회고용 추정이다.

반대로 유지할 부분은 Spring hard-filter와 final ownership, scoped retrieval contract, source/evidence provenance, exact quote, fail-closed fallback, disposable E2E, max 3/Venue dedup이다. 단순화는 안전 경계를 없애는 게 아니라, 경계가 반복 구현된 실험 도구를 줄이는 것이다.

## 포트폴리오 설명과 과장 금지

좋은 설명: “Spring이 authoritative hard filter로 후보 ID를 제한하고, FastAPI가 그 scope 안에서 embedding/Qdrant retrieval과 evidence trace를 반환하며, Spring이 semantic signal과 deterministic fallback을 이용해 최종 순위·Venue 중복·max3를 결정한다.”

정직하게 제한할 표현:

- production-scale/운영 안정성이 입증된 AI 추천이라고 하지 않는다.
- 전체 ProfileReady Restaurant가 검증·indexing됐다고 하지 않는다.
- Source Scope Guard가 legacy v12 collection까지 적용됐다고 하지 않는다.
- Gemini menu-budget classifier가 성공적으로 전면 검증됐다고 하지 않는다.
- LangGraph가 LLM agent나 장기 상태 저장을 한다고 하지 않는다.
- semantic benchmark/E2E를 일반 사용자 전체에 대한 정답률로 해석하지 않는다.

### 내가 이해했는지 확인

- 무엇을 잘못되면 안 되므로 Spring에 남겼는가?
- 현재 retrieval ranking의 1차 signal은 무엇이며 문서 간 설명이 다르면 무엇을 우선하는가?
- Qdrant 40 legacy points의 provenance limitation은 무엇인가?
- 복잡성을 줄인다면 어떤 경계는 반드시 유지해야 하는가?
