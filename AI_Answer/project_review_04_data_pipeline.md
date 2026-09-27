# 프로젝트 학습 4 — 수집에서 Evidence-Grounded Profile까지

## 데이터 원본과 수집 경로

추천 모집단의 기준은 KOMSCO 공공데이터다. Spring importer(`restaurant/importer/RestaurantImportService.java`, `RestaurantImportWriter.java`)가 pagination/dedup된 KOMSCO merchant snapshot을 service area·industry·status 조건으로 동기화한다. 이 데이터가 provider listing과 같은 것은 아니다.

보강용 Python CLI는 공식 Kakao/NAVER candidate retrieval → dedup → Qwen entity resolution/quality gate → Canonical/provider mapping → PCMap Maps UI의 DOM `data-nlog-params`에서 numeric Place ID linking → HOME/MENU/HOURS/REVIEW DOM detail 수집으로 이어진다. 주요 소유 파일은 `ai/app/providers/provider_candidate_retrieval_cli.py`, `entity_resolution/provider_entity_resolution_cli.py`, `entity_resolution/qwen_candidate_matcher.py`, `canonical/canonical_builder.py`, `canonical/canonical_persistence_cli.py`, `naver/place_id_linker_cli.py`, `naver/place_detail_enrichment_cli.py`, `naver/place_detail_persistence.py`다. Entity resolution은 이름이 비슷하다는 이유만으로 동일 장소를 확정하지 않고, Qwen이 Place ID를 만들어내지도 않는다.

이 파이프라인은 여러 source의 이름·주소와 Place ID를 연결하는 일이 핵심 난제였다. provider 후보는 동일 Restaurant라는 증명이 아니며, detail section별 성공/실패도 Place ID mapping과 별개다. 이 때문에 fingerprint, verification status/reason, lifecycle, source-change 재검증, idempotent persistence 등이 쌓였다.

## Evidence → Claim → 검증

`semantic_profile_shadow.py`는 profile input을 만들고 `build_evidence_catalog`에서 원본별 Evidence ID를 부여한다. Generator V2(`semantic_profile_generator_v2.py`)는 Claim type/text, evidence IDs, `supportQuotes`를 구조화 출력한다. Deterministic validation은 ID 존재/소유자, source/type compatibility, exact quote substring, 중복·빈 문자열 등을 검사한다.

`semantic_profile_quality_gate.py`는 Atomicizer가 Claim을 검증 단위 assertion으로 나누고, Assertion Verifier가 assertion별 Evidence support를 판단한다. Python aggregator가 all supported면 SUPPORTED, 지원·미지원이 섞이면 PARTIAL, 모두 미지원이면 UNSUPPORTED로 계산한다. 실패는 승인되지 않는다. Exact supportQuote는 Evidence 원문에서 그대로 잘라 왔는지 증명하고, Evidence ID만 붙어 있다는 이유로 Claim 의미를 승인하지 않게 한다.

Claim을 만든 이유는 긴 원문 전체를 그대로 벡터화하는 것보다 검색 가능한 짧은 feature와 추적 가능한 근거를 함께 다루기 위해서다. Atomic claim은 복수 사실 중 일부만 맞는 문제를 줄인다. 다만 모델의 entailment 판단 자체가 완전한 증명은 아니므로 원본 snapshot, fixture regression, human review가 계속 필요하다.

## Source Scope Guard

`semantic_profile_source_scope.py`는 Claim 문구를 해석하지 않고 resolve된 source type으로 provenance를 계산한다.

| 실제 Evidence source | derived scope | search text |
|---|---|---|
| MENU만 | `LISTING_FACT` | validated claimText |
| REVIEW / REVIEW_KEYWORD만 | `CUSTOMER_REPORTED` | `고객 리뷰 기반 정보: ` prefix + raw claim |
| MENU + customer source | `MIXED` | non-indexable |
| empty/unknown/unsupported source | `UNKNOWN` | non-indexable |

`semanticApproved`(검증 의미 판단 통과)와 `indexable`(실제로 검색 데이터로 써도 됨)은 다른 상태다. Indexable에는 exact quote, deterministic validation, SUPPORTED, assertion 1개, 알려진 단일 scope, safe searchText가 모두 필요하다. `embedding_text_from_indexable_claims()`는 고객 claim의 raw text를 embedding text로 받지 않고 `searchText`를 검사한다.

이 guard가 필요했던 직접 원인은 keyword evidence `"혼밥하기 좋아요" 이 키워드를 선택한 인원`에서 generator가 `혼밥하기에 좋은 식당입니다.`를 만들고, quote/semantic verifier까지 통과시킨 사례다. 문장 의미는 비슷해도 “고객 평가”가 “객관적으로 확인된 시설 사실”처럼 보일 수 있다. provenance를 LLM 문장 생성에만 맡기지 않도록 scope를 Python이 source ID에서 정하게 했다.

## Frozen 상태와 알려진 한계

`AI_Answer/semantic_profile_source_scope_guard_v1_review.md`는 frozen 11개 source fixture를 재평가해 10개 indexable, 1개 non-atomic 제외, source-scope false acceptance 0을 기록했다. 이는 bounded fixture 결과지 전체 Restaurant cohort의 품질 보증이 아니다. Data Pipeline은 EXPERIMENTAL/FROZEN이며 Profile expansion, document embedding, reindex를 중단했다.

중요한 구분: runtime의 기본 collection `zeropay_semantic_claim_pilot_v12`는 이전 pilot에서 만든 40 legacy points다. `AI_Answer/langgraph_recommendation_v1_compose_e2e.json`의 마지막 기록은 40 points 전후 동일, Qdrant write 0이다. 이것은 Source Scope Guard 적용 후 재생성된 새 collection이 아니다. Guard가 기존 points를 자동으로 고치거나 안전하게 만든 것이 아니다. 현재 runtime semantic quality는 legacy claim 품질에 제한받으며, 새 guard 평가와 별개다.

보존해야 할 limitation: review 기반 Claim은 메뉴 Claim보다 coverage가 약했고, 맛 평가가 mention으로 축소되거나 venue review가 non-atomic이 된 경우가 있었다. 기존 profile은 overclaim이 발견돼 Atomicizer/Verifier와 generator를 여러 번 보강했으나, 전체 26 strict ProfileReady cohort의 profile/indexing은 완료하지 않았다. 그러므로 “전체 음식점 의미 데이터 검증·적재 완료”라고 말하면 안 된다.

### 내가 이해했는지 확인

- Evidence ID 유효성과 Claim의 의미적 지지는 왜 별개인가?
- 고객 리뷰의 raw claim을 그대로 embedding하면 어떤 attribution이 사라지는가?
- `semanticApproved=true`, `indexable=false`가 가능한 이유는 무엇인가?
- Source Scope Guard가 legacy v12 point를 소급 수정했는가?
