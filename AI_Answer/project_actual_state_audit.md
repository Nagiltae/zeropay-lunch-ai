# ZeroPay Lunch AI — Actual Project State Audit

- Audit date: 2026-09-25 (Asia/Seoul)
- 기준: 현재 소스·현재 설정·현재 read-only DB/Qdrant 조회·보존된 실행 artifact
- 이번 audit에서 수행하지 않음: 코드/기능 변경, DB write, provider/NAVER/Kakao 요청, Qwen/Gemini 생성, embedding, Qdrant write, 테스트/E2E 재실행
- 상태 표기: `ACTIVE`는 실행 경로가 연결된 상태(기본 flag OFF일 수 있음), `IMPLEMENTED_NOT_WIRED`는 코드만 있고 현재 실행 흐름에는 미연결, `HISTORICAL_EXPERIMENT`는 과거 실험, `PLANNED`는 구현 전 계획, `UNKNOWN`은 증거 부족

## 1. Executive Summary

현재 제품의 공개 요청 경로는 React → 인증된 Spring Boot Chat/SSE → Spring 추천 서비스 → 선택적으로 FastAPI → Spring 최종 추천/설명 → SSE → React다. 다만 실제 개발 Compose의 Spring 환경에는 `AI_SEMANTIC_RUNTIME_ENABLED`가 주입되지 않아 `application.yml` 기본값 `false`가 적용된다. 따라서 현재 기본 요청은 Spring deterministic intent/recommendation이며, FastAPI semantic 호출은 opt-in이다. 별도 격리 E2E artifact는 flag ON으로 Browser 전체 경로를 3개 Query에서 과거 검증했다(`PAST VERIFIED`).

현재 DB SELECT 결과는 Restaurant 517, ACTIVE 517, `ELIGIBLE` 405, legal dong 11680108 514, ACTIVE+ELIGIBLE+논현동 402다. 최신 공통 `ProfileReadinessPolicy`로 NAVER numeric MATCHED 대상 360개를 재평가한 결과 strict-ready 26개다. 이 26개는 Semantic Profile 입력 품질 조건 통과 수이지, 서비스가 추천할 수 있는 전체 수가 아니다. 실제 추천은 별도로 `recommendation_ready`, ZeroPay, 현재 운영 스케줄/휴무 및 Spring filter에 종속된다.

Qdrant read-only 조회에서 v12는 실제 존재하며 40 points / 10 Restaurant / 1024 dimensions / Cosine이다. Type별 point 수는 FOOD_MENTION 16, TASTE 7, MENU_CHARACTERISTIC 5, FOOD_TYPE 4, DINING_CONTEXT 4, VENUE_CHARACTERISTIC 4다. Expanded Shadow collection은 현재 목록에 없다. v12 10개 ID는 최신 strict-ready 26개와 다른 고정 pilot cohort다.

현재 가장 큰 blocker는 Semantic Profile의 의미 검증이다. 확장 계획은 신규 19개 생성이었으나 Qwen 3회 후 strict validation 3회 실패, semantic overclaim 표본 발견으로 자동 중단됐다. 승인 가능한 신규 Profile 0, embedding 0, expanded collection 미생성, expanded benchmark 미실행이다. 기존 v12 검색 artifact와 별도 full-stack E2E는 과거 검증으로 보존되며, 확장 검색 품질을 증명하지 않는다.

Gemini API는 실제 사용 코드/SDK가 확인되지 않았고 현재 사용자 runtime에서도 호출하지 않는다. LangGraph는 `NOT_USED`. Intent Analysis는 FastAPI Python 규칙 기반 코드이며 LLM 호출이 아니다. Qwen은 Provider Entity Resolution 및 별도 legacy resolver/semantic profile/explanation 실험에서 사용되고, embedding은 별도 `qwen3-embedding:0.6b`다.

## 2. Current Project Architecture

### 실제 사용자 요청 흐름

```text
Browser / React
  → Spring POST /api/conversations/{id}/messages (authenticated SSE)
  → ChatStreamService
  → RecommendationContextService + Intent analyzer
  → RestaurantJpaRepository: active/recommendation_ready/ELIGIBLE/ZeroPay/
     논현동/current schedule/open period 필터
  → recent-meal 및 category/budget/dislike 필터, deterministic sort
  → (AI_SEMANTIC_RUNTIME_ENABLED=true일 때만)
     Spring FastAPI client → FastAPI deterministic intent
     → Spring Hard Filter 결과 ID 범위의 semantic retrieval
     → Ollama query embedding → Qdrant configured collection
  → Spring deterministic ranking (semantic cosine은 tie-breaker)
  → CONFIRMED + ACTIVE Venue dedup → 최대 3
  → FastAPI explanation 요청(semantic wiring이 켜진 경우)
     → Safe Fact deterministic 설명 기본, LLM은 별도 opt-in
  → Spring recommendation persistence + recommendations SSE event
  → React stream parser/state → Recommendation cards 및 reason
```

기본 flag OFF에서는 FastAPI intent/retrieval/explanation 경로가 Spring configuration에서 생성되지 않으며 Spring fallback 분석과 deterministic recommendation을 사용한다. `recommendation_ready`는 Recommendation DB query 조건이고, `strict-ready`는 Python Semantic Profile 생성 품질 gate다.

### 실제 데이터 준비 흐름

```text
KOMSCO Open Data API
  → Spring pagination (논현동 법정동 + provider institution 조건)
  → 최신 external merchant record dedup
  → KSIC 561 / 계속사업자 / 기관 / 법정동·강남 증거 필터
  → restaurants master upsert/sync (KOMSCO 원천 필드)
  → Python official Kakao + NAVER Local 후보 retrieval
  → Qwen3.5 provider-candidate Entity Resolution (공식 Provider fusion 경로)
  → verification/eligibility report 및 선택된 provider evidence 상태
  → 별도 PCMap/NAVER Maps UI allSearch 기반 numeric Place ID 연결
     (결정론적 exact name/address; Qwen 미사용)
  → PCMap HOME/MENU/HOURS/REVIEW DOM detail crawl
  → detail tables + section lifecycle persistence (opt-in write-db)
  → Python ProfileReadinessPolicy
  → Compact Input + Evidence Catalog
  → Qwen Semantic Profile 생성 및 Claim 검증 (실험/품질 중단 상태)
  → 승인 Claim + 유효 FOOD_MENTION을 embedding
  → Qdrant shadow collection (v12 pilot만 현재 확인됨)
```

## 3. Current Data Preparation Pipeline

KOMSCO ingestion은 Python이 아니라 Spring Boot `restaurant/importer`가 소유한다. `KomscoMerchantHttpClient.fetchPage()`가 configured base URL에 page/perPage, `cond[emd_cd::EQ]`, `cond[pvsn_inst_cd::EQ]=I0000002`를 전달한다. `KomscoMerchantClient`가 법정동의 모든 페이지를 가져오며 현재 `GangnamLegalDong`는 `11680108` 논현동만 정의한다. `RestaurantImportService`가 최신 external merchant별 dedup 후 업종 `561`, `계속사업자`, `I0000002`, 논현동 및 강남 증거를 확인한다. `RestaurantImportWriter`가 KOMSCO source row를 transaction 단위로 upsert/synchronize한다. 주간 scheduler도 같은 service를 사용한다.

Restaurant master에는 상호/주소/상세주소/우편번호/좌표/법정동/업종/ZeroPay 기관/사업 상태/외부 merchant ID/source provider/sync 시점 등 KOMSCO snapshot이 저장된다. 메뉴, NAVER 리뷰, NAVER 운영시간은 KOMSCO 원본이 아니라 별도 Detail 파이프라인이다.

근거: `backend/.../restaurant/importer/KomscoMerchantHttpClient.java` `fetchPage`; `KomscoMerchantClient.fetchAllGangnamMerchants`; `KomscoMerchantFilter.isActiveGangnamRestaurant`; `RestaurantImportService.synchronizeRestaurants`; `RestaurantImportWriter`; `KomscoRestaurantSyncScheduler`. DB 수치는 2026-09-25 current MySQL SELECT.

### 현재 DB 규모 (SELECT-only)

| 조건 | 건수 | 의미 |
|---|---:|---|
| Restaurant 전체 | 517 | `restaurants` row |
| ACTIVE | 517 | master 운영 상태 |
| `recommendation_eligibility=ELIGIBLE` | 405 | entity/recommendation eligibility 상태 |
| legal dong 11680108 | 514 | 현재 저장된 논현동 master |
| ACTIVE + ELIGIBLE | 405 | 전체 dong |
| ACTIVE + ELIGIBLE + 논현동 | 402 | 추천 영역/eligibility만 적용한 모집단 |
| `recommendation_ready=true` | 4 | Spring repository의 상세 준비 gate |
| ACTIVE + ELIGIBLE + 논현동 + recommendation_ready + ZeroPay | 1 | 현재 DB snapshot상 정적 조건 교집합; 운영 스케줄도 추가 적용 |

위 수치는 의미가 다른 컬럼을 분리한 것이다. `ELIGIBLE`만으로 현재 영업/추천 가능을 뜻하지 않는다.

## 4. KOMSCO → NAVER/Kakao → Qwen 상세

### 공식 NAVER Local과 Kakao 검색

현재 Python `place_provider.py`에는 두 공식 검색 API가 있다.

| Provider | 실제 방식 | 결과 |
|---|---|---|
| Kakao | `https://dapi.kakao.com/v2/local/search/keyword.json`, keyword query, size 기본 15, 좌표가 있을 때 x/y 및 distance sort | `PlaceSearchCandidate(provider=KAKAO)` |
| NAVER Local | NCP Local Search `https://naverapihub.apigw.ntruss.com/search/v1/local`, query, display 기본 5, start 1, random sort. 좌표 center 검색은 사용하지 않음 | `PlaceSearchCandidate(provider=NAVER_LOCAL)` |

query는 provider retrieval CLI의 KOMSCO manifest row 기반으로 만들어지고 Kakao/NAVER 결과는 report/fusion artifact로 기록된다. 이 단계는 후보 수집이지 numeric PCMap Place ID 연결이 아니다. `provider_candidate_retrieval_cli.py`는 report-only 후보 비교이고, `provider_entity_resolution_cli.py`는 두 Provider 결과를 합쳐 판정한다.

### Qwen Entity Resolution

공식 provider fusion 경로에서는 Qwen3.5가 Kakao와 NAVER Local 양쪽에서 온 후보를 기준 KOMSCO restaurant와 비교한다. 기준 입력은 KOMSCO 이름/주소 및 manifest의 선택적 좌표/법정동, 후보는 provider명·상호·주소·카테고리·좌표 등 candidate evidence다. Qwen 구조화 출력은 후보 rank와 `entity_match`, `business_type`, `location_scope`, `final_decision` 및 근거를 반환한다. `verification_quality_gate.py`와 CLI가 schema/quality status를 평가해 ACCEPT/REJECT/UNCERTAIN(기술 오류 UNKNOWN)으로 보존한다. Qwen은 Place ID를 생성하지 않고 최종 물리 장소 검증 단계도 대체하지 않는다. model config는 `QWEN_MODEL`, fallback `LOCAL_LLM_MODEL`, default `qwen3.5:9b`.

근거: `ai/app/providers/place_provider.py`의 `KakaoPlaceSearchProvider.search`, `NaverPlaceSearchProvider.search`; `ai/app/entity_resolution/provider_entity_resolution_cli.py`의 후보 결합 및 matcher 호출; `qwen_candidate_matcher.py` prompt/schema; `verification_quality_gate.py`.

### 과거 NAVER match 실험과 현재 flow

세 가지 서로 다른 것을 구분해야 한다.

1. **Historical NAVER deterministic match**: 기존 저장된 Local/NAVER 행의 상호·주소로 정합성을 판별한 과거 로직/실험. 현재 official-provider Qwen fusion과 동일하지 않다.
2. **Historical Place Resolver PoC**: `place_resolver_cli.py`는 Maps UI allSearch 후보에서 애매한 후보 ranking에 Qwen을 선택적으로 썼고 detail HOME 검증도 수행했다. 이는 현재의 official Local provider fusion과 별도의 대체/초기 경로다.
3. **현재 provider Entity Resolution**: Kakao+NAVER 공식 검색 후보를 Qwen으로 함께 평가. 그러므로 “결정적 NAVER numeric linking”과 “NAVER Local 후보를 포함하는 Qwen provider resolution”은 동시에 참일 수 있다. 첫 문장은 Place ID linker를, 두 번째는 Provider fusion을 가리킨다.

과거 실험 상태는 `HISTORICAL_EXPERIMENT`; current provider fusion 구현은 `ACTIVE`인 bounded data-preparation CLI이지만 사용자 recommendation runtime에서 실행되는 것은 아니다.

## 5. NAVER Place ID 상세

공식 NAVER Local Search 응답의 `external_place_id`는 numeric PCMap Place ID와 동일한 보장이 없다. numeric Place ID는 PCMap restaurant detail URL을 식별하는 숫자 ID다. 현재 `place_id_linker_cli.py`는 visible NAVER Maps UI 입력으로 발생한 `allSearch` 구조화 응답만 관찰하고 candidate `place_id` 숫자형을 추출한다. query는 보통 `논현동 {NAVER 외부 상호 또는 canonical 상호}`다. resolver는 `is_exact_match()`로 normalized name의 같음/포함과 address pair의 `EXACT`/`STRONG_MATCH`를 요구한다. 유일한 candidate만 연결 대상이다. 이 경로에 Qwen 호출은 없다.

동일 Place ID를 다른 restaurant가 소유 중이면 `_external_place_id_conflict()`가 거부한다. DB는 INSERT-only/unique conflict 보호라 기존 owner mapping을 다른 restaurant로 덮어쓰지 않는다. 같은 restaurant가 이미 numeric ID를 보유한 경우 CLI query selection에서 완료 대상으로 제외하며, alternate `place_resolver_cli.py`도 기존 다른 ID를 교체하지 않는다. numeric ID 연결과 Qwen의 사업체 동일성 verdict는 별도 provenance/상태이며 자동 동일시하면 안 된다.

관련 데이터는 `restaurant_external_places`(provider/ID/match status/query), `restaurant_naver_verifications`(verification status/reason/fingerprint/model/time)이다. 현재 SELECT 집계는 KAKAO MATCHED 367, NAVER MATCHED 360, NAVER AMBIGUOUS 3, NAVER UNRESOLVED 27, NAVER_LOCAL MATCHED 328 mapping rows다. 이 row 수들은 서로 다른 provider namespace라 합계가 unique Restaurant 수는 아니다.

근거: `ai/app/naver/place_id_linker_cli.py` `parse_allsearch_candidates`, `is_exact_match`, `_external_place_id_conflict`, candidate selection/persistence; `restaurant_external_places` 및 verification migrations.

## 6. Detail Crawl / Persistence

numeric Place ID 이후 `PlaceDomDetailCrawler`는 실제 PCMap rendered DOM만 처리하고 internal NAVER API/Apollo data는 사용하지 않는다.

| Section | 수집 및 변환 | 저장 |
|---|---|---|
| HOME | rendered HOME의 name/category/address/phone/conveniences | detail input/evidence에 활용; 별도 HOME lifecycle은 현 readiness 필수 section이 아님 |
| MENU | `/menu/list` DOM card, name/description/price text/parsed numeric price | `restaurant_menus` |
| BUSINESS_HOURS | HOME hours 펼침, 요일+시간 regex parser가 `BusinessHour(day, open_time, close_time, description)` 구성 | `restaurant_business_hours` |
| REVIEW | visitor review UI 초기 렌더링, summary visitor/blog count, review keyword/menu mentions/themes, 대표 리뷰(전체 pagination 아님) | `restaurant_review_summaries`, `restaurant_review_keywords`, `restaurant_representative_reviews` |

`place_detail_enrichment_cli.py`는 기본 report-only/dry-run과 선택 section, freshness/retry 경로를 제공하며 `--write-db`에서만 `PlaceDetailPersistence` 실행한다. lifecycle은 restaurant/provider/placeId/section 단위다. `SUCCESS`는 section을 정상 읽고 계약 데이터가 확보됨, `ABSENT_CONFIRMED`는 정상 페이지 접근 후 해당 정보가 실제 없음, `FAILED`는 수집/파싱 실패다. parser failure를 absence로 바꾸지 않는다. persistence는 `SUCCESS`/`ABSENT_CONFIRMED`만 해당 섹션 stale row reconcile/deactivate 대상으로 삼고, `FAILED`는 기존 정상 데이터 덮어쓰기를 피한다. 재실행은 freshness 기반 preexisting skip; section 단위 강제 지정도 있다.

현재 DB의 관련 read-only 수: lifecycle가 있는 Restaurant 35; menu lifecycle SUCCESS row 32, hours SUCCESS 35, review SUCCESS 35; NAVER 메뉴가 있는 Restaurant 325, review keyword 344, business-hour rows 360. “행 존재”는 lifecycle SUCCESS나 fresh를 뜻하지 않는다.

근거: `ai/app/naver/place_dom_detail_crawler.py`; `place_detail_enrichment_cli.py`; `place_detail_persistence.py`.

## 7. Data Quality / Profile Readiness

현재 공통 Policy는 `ai/app/profile_readiness.py::assess_profile_readiness()`이며 audit와 Profile input 양쪽에서 호출된다. 조건: active 및 ELIGIBLE, MENU/BUSINESS_HOURS/REVIEW 각각 SUCCESS 및 기존 TTL freshness(기본 30일), 가격이 있는 메뉴 최소 1개, 원문 설명에서 요일과 같은 open/close 시간대가 직접 맞는 구조화 영업시간 최소 1개, numeric Place ID, owner count 정확히 1, 최신 verification VERIFIED 및 Place ID 일치다. 이유는 다중 발생 가능하다.

### ProfileReadiness audit 재계산

| 값 | 이번 audit 결과 | Source |
|---|---:|---|
| 모집단 | 360 | current DB SELECT; active + ELIGIBLE + 논현동 + NAVER MATCHED numeric |
| READY | 26 | 같은 DB row + 현재 `ProfileReadinessPolicy` |
| NOT_READY | 334 | 위 집합 중 Policy 불통과 |
| `NO_MENU_SUCCESS` | 328 | Restaurant reason 발생 횟수 |
| `NO_BUSINESS_HOURS_SUCCESS` | 325 | 동일 |
| `NO_REVIEW_SUCCESS` | 325 | 동일 |
| `NO_PRICED_MENU` | 40 | 동일 |
| `NO_STRUCTURED_HOURS` | 332 | 동일 |

reason count는 Restaurant별 중복을 포함하므로 합이 334가 아니다. 이 조회에서 별도 stale/identity conflict/no numeric/not verified reason은 0이었다. 이는 audit 모집단에서 선행한 matched numeric/verification 조건의 결과이기도 하다.

### 영업시간 원문 검증과 9590

기존 parser가 한 페이지 텍스트에서 날짜/시간 패턴을 독립적으로 찾아 서로 다른 요일의 시간 값을 잘못 짝지을 수 있었다. parser를 요일 token 뒤의 range만 연결하도록 보완하고, readiness는 DB row의 day/open/close가 같은 raw `description` 안에 실제 표현되는지 다시 확인한다(`is_source_grounded_hour`). `9590`은 토요일 휴무 원문인데 저장 row가 토요일 영업시간으로 만들어져 있던 불일치 때문에 전 기준선에서 제외됐다. 수정 후에도 `9590`은 현재 26 READY 목록에 없다. 현재 보존된 backfill report는 원문 기반 재정규화 27건, 외부 요청 0회라고 기록한다.

## 8. strict-ready 26의 정확한 의미

`26`은 **2026-09-25 현재 readiness query가 선택한 360개 NAVER matched-numeric 논현동 Restaurant 중 Semantic Profile generation에 필요한 identity + detail evidence gate를 통과한 수**다. 다음을 뜻하지 않는다.

- Spring 전체 recommendation candidate 수가 26이라는 뜻이 아니다.
- 26개 모두 Semantic Profile/승인 Claim이 존재한다는 뜻이 아니다.
- 26개 모두 Qdrant v12에 색인됐다는 뜻이 아니다.
- 26개가 지금 영업 중이라는 뜻이 아니다.

숫자 A/B/C를 분리하면:

- **A. 일반 후보 모집단**: DB의 ACTIVE+ELIGIBLE+논현동은 402. 이것은 실제 응답 수가 아니라 상위 schedule/ZeroPay/recommendation_ready/사용자 조건을 적용하기 전 모집단이다.
- **B. Detail row 보유**: 대상 360에서 NAVER menu rows가 있는 Restaurant 325, review keyword가 있는 344, hours rows가 있는 360; lifecycle 검증 대상은 35. section별 distinct 수이며 모두 완전한 detail이라고 합산하지 않는다.
- **C. Semantic Profile 입력 READY**: 26.

따라서 “현재 서비스가 추천할 식당이 26개뿐인가?”의 답은 **아니다**. 추천 pool은 Spring `recommendation_ready`와 현재 영업/ZeroPay/정책이 결정한다. 다만 현재 DB의 `recommendation_ready=true` 자체가 4개뿐이고 논현동+ACTIVE+ELIGIBLE+ZeroPay와 교집합은 1개다(현재 read-only DB snapshot). 운영 스케줄 필터를 통과하는 실시간 결과는 시각/요일에 따라 더 줄거나 0일 수 있다. 이 사실도 “strict-ready 26”과 다른 병목이다.

## 9. Semantic Profile / Claim 구조

Semantic Profile은 Restaurant master를 대체하는 source of truth가 아니라, 현재 Compact Input의 메뉴·리뷰·hours evidence를 검색에 쓸 간결한 특징 Claim으로 표현한 versioned artifact다. 현재 생성기 `semantic_profile_shadow.py`의 profile schema에는 `profileStatus` (`READY|PARTIAL|UNKNOWN`), `claims[]`, `sectionEvidence`, `inputVersion`, `promptVersion`, `inputHash`가 있다. Evidence 기반 v2 output은 Claim당 `claimType`, `text`, confidence (`HIGH|MEDIUM|LOW|UNKNOWN`), `evidenceIds`를 가진다. 외부 source path/version/hash/Evidence ID/approval은 Python catalog/provenance 측에서 관리해야 하며 Qwen이 만들지 않는다.

Claim은 “Restaurant 하나에 대해 AI 검색에 쓰는 한 가지 특징 정보”다. profile generation에서 validator가 허용하는 LLM Claim type은 실제 현재 코드 기준 다섯 가지다.

| Claim Type | 용도 | 정책 핵심 |
|---|---|---|
| `FOOD_TYPE` | 메뉴에 확인된 음식 종류 | review keyword만으로 공식 메뉴라고 만들면 reject |
| `MENU_CHARACTERISTIC` | 메뉴 자체의 구성/특징 | 직접 menu evidence만 허용 |
| `TASTE` | 맛/가성비 등 review 평가 | 성공 keyword/review Evidence 필요; keyword count threshold 적용 |
| `DINING_CONTEXT` | 혼밥/단체 등 이용 맥락 | 리뷰 evidence 기반 |
| `VENUE_CHARACTERISTIC` | 공간/서비스 관련 리뷰 특징 | 리뷰 evidence 기반 |

`FOOD_MENTION`은 현재 LLM profile schema의 허용 type이 아니다. 별도 `build_food_mention_points()`가 review keyword에서 반복 음식 term을 추출해 만든 검색용 point다. 공식 menu type으로 취급하지 않으며 payload에 `sourceKind=review_keyword_only`, mentionTerm/count, Evidence ID를 둔다. Qdrant v12는 위 여섯 검색 Claim Type을 모두 가지고 있다.

## 10. Qwen Profile 품질 문제

확장 계획 artifact는 최신 READY 26, existing artifact 재사용 7 (`9568,9569,9570,9571,9574,9580,9617`), 신규 생성 계획 19로 기록한다. 기존 profile artifact는 덮어쓰지 않고 현재 evidence에 대조한 별도 결과를 만들었다. 그러나 “재사용 7”은 품질이 완전히 승인됐다는 뜻이 아니다. 자동 Evidence/type/lifecycle 검증과 표본 의미 검토는 다른 단계며, sample review에서 기존 AUTO claim 일부도 원문보다 강한 표현으로 확인됐다.

신규 Profile batch는 configured `qwen3.5:9b`를 대상으로 19 planned 중 앞의 3개만 호출했다. 성공 0, 실패 3, pending 16, retry 없이 `PAUSED_QUALITY_FAILURE`; validation 연속 실패 stop 조건에서 멈췄다. 승인 가능한 신규 Profile 0이다. 신규 확장용 Embedding 0, Shadow index 생성 0이다.

실제 보존 artifact에서 확인한 overclaim 예시(원문 번역 요약):

1. **9559**: `음식이 맛있어요` keyword → “고기가 풍부한 육즙과 부드러움”을 주장; 맛 keyword는 육즙/식감을 뒷받침하지 않는다.
2. **9559**: 단체모임 keyword → 기업/가족 행사·연회에 적합하다고 확장.
3. **9603**: 메뉴에 없는 “Octopus Kimchi Juk” 조합과 “Beef Stew Bibimbap”을 생성.
4. **9603**: 혼밥/청결 evidence를 하나의 DINING_CONTEXT 주장으로 묶음.
5. **9639**: 단체/대화 키워드 → 넓은 공간·배치까지 추론; 맛있다 keyword → 조리 품질까지 덧붙임.

9559 sample에서 일부 Claim은 자동 분류 `AUTO_APPROVED`였지만 whole-profile evidence validation은 실패했다. 이는 evidence ID 존재/section/type 규칙만으로 Claim 문장의 의미 직접 지지를 보증할 수 없다는 증거다. 현재 profile expansion은 품질 stop으로 중지; 재개 승인 상태가 아니다.

근거: `AI_Answer/semantic_profile_expansion_v2/*/{qwen_raw_output,claim_validation}.json`, `semantic_profile_expansion_sample_review.json`, `semantic_expansion_review_v2.md`; 생성 코드는 `ai/app/semantic_profile_expansion.py` 및 `semantic_profile_shadow.py`.

## 11. Embedding / Qdrant

Embedding은 문장을 의미를 나타내는 숫자 배열로 바꿔 비슷한 의미를 검색하는 표현이다. Pilot 코드가 `qwen3-embedding:0.6b`로 Ollama `/api/embed`를 호출하며, indexing/query는 동일 model, 1024 dimensions, Cosine을 계약으로 사용한다. Runtime query embedding은 `semantic_runtime.py::SemanticRetrievalService.retrieve()`에서 수행한다. Generation model `qwen3.5:9b`와 embedding model은 다른 역할이다.

현재 Qdrant:

| Collection | 실제 상태 |
|---|---|
| `zeropay_semantic_claim_pilot_v12` | 존재, 40 points, 1024, Cosine, status green |
| v12 Restaurant | 10: 9567, 9568, 9569, 9570, 9571, 9574, 9580, 9590, 9617, 9731 |
| expanded v1 | 현재 collection list에 없음 |
| 기타 | `zeropay_semantic_claim_pilot_v1`~`v12`, `zeropay_semantic_profile_pilot_v1` 존재 |

v12 claim type count: `FOOD_MENTION=16`, `TASTE=7`, `MENU_CHARACTERISTIC=5`, `FOOD_TYPE=4`, `DINING_CONTEXT=4`, `VENUE_CHARACTERISTIC=4`. 이는 Qdrant API read-only collection info + payload scroll 결과다. `indexed_vectors_count=0`이라는 Qdrant metric도 응답됐지만 `points_count=40`이고 points/query가 사용되는 구성이다. 해당 metric을 point/vector 누락으로 해석하지 않는다.

v12의 10개는 historical benchmark/pilot에 선택된 ID cohort이며 현재 strict-ready 26 중 subset이라고 단정할 수 없다. 특히 9590과 9731은 현 26 목록 밖이며, 최신 신규 ID들은 v12에 없다. Qdrant는 파생 검색 저장소고 MySQL source of truth를 대체하지 않는다.

## 12. Runtime Recommendation Flow

실제 공개 API는 인증된 `POST /api/conversations/{conversationId}/messages` SSE다. FastAPI endpoint는 `/health`, `POST /internal/v1/intent-analysis`, `/semantic-retrieval`, `/recommendation-explanations`가 실제 구현됐다.

Spring `RestaurantRecommendationService.recommend()`는 context/intent를 만든 뒤 `findOpenRestaurants()` 결과에 active, recommendation_ready, ELIGIBLE, ZeroPay, legal dong 11680108, weekday/open-close/closed-day/closed-hours 조건을 적용한다. 이후 budget, category, disliked category, recent meal을 필터한다. semantic enricher가 있으면 이 hard-filtered ID 목록을 FastAPI에 보낸다. AI 결과는 hard-filter 통과 후보만 enrich하고, 응답에 없는 restaurant도 후보에서 제거하지 않는다.

Spring 최종 정렬의 1차 key는 기존 deterministic score다. semantic score는 `semanticSimilarity`만 [0,1]로 clamp해 동점에서 tie-breaker로 사용한다. `retrievalScore` (lexical priority tier를 포함한 내부값)는 Spring rank에 더하지 않는다. 이후 CONFIRMED association + ACTIVE Venue로 dedup, max3. 따라서 final rank ownership은 Spring이다.

FastAPI retrieval request에는 query, `candidateRestaurantIds`, topK가 있다. candidate IDs가 비면 dependency를 호출하지 않는다. collection은 `QDRANT_SEMANTIC_COLLECTION`; query embed dimension 검증 후 Qdrant pre-TopK filter가 restaurantId AND routed claimTypes를 적용한다. 반환 payload도 scope/type/evidenceId/claimId 검사한다. 현재 runtime retrieval은 query마다 Qdrant query를 사용한다. Explanation의 supplemental evidence lookup은 최종 선택 ID scope에서 별도 query일 수 있다.

`candidateRestaurantIds`는 영업/지역/ZeroPay/예산 등 Spring의 Hard Filter를 통과한 후보 안에서만 의미 근거를 찾도록 해, 전체 Qdrant TopK가 필터 탈락 업체로 가득 차 적격 결과를 밀어내지 않게 한다.

## 13. Spring Hard Filters / Ranking

실제 구현 기준:

- DB query: ACTIVE, `recommendation_ready`, `recommendation_eligibility=ELIGIBLE`, ZeroPay, 논현동 `11680108`, 해당 요일 운영 일정 및 현재 영업시간, closed day, closed period.
- service filter: ZeroPay, explicit/default budget, parsed category, disliked categories, recent restaurant IDs.
- confirmed active Venue 기반 최근 식사 중복 방지 및 최종 dedup.
- ranking: deterministic integer score, average price, restaurant ID; Semantic cosine은 deterministic 점수 동률일 때만 보조 정렬 key.
- 최대 3개 (`MAX_RECOMMENDATIONS=3`).

실제 코드에서 거리/500m 계산은 없다. 과거 radius는 historical schema/changelog로 남아 있을 수 있으나 current repository query/filter에 사용되지 않는다. 현재 서비스 지역은 법정동 논현동이다.

Semantic index에 없는 후보도 hard filter를 통과하면 유지되고 semantic signal null/0으로 deterministic ranking에 남는다. FastAPI 장애 시 `AI_FALLBACK_ENABLED` 기본 true가 설정된 경우 후보 ID를 보존한 채 fallback한다.

근거: `backend/.../RestaurantJpaRepository.findOpenRestaurants`; `RestaurantRecommendationService.recommend/matches/score/semanticRelevance`; `SemanticCandidateEnricher.enrich`.

## 14. FastAPI 역할

FastAPI는 MySQL에 직접 접근하지 않는다. liveness `/health`는 Qdrant/Ollama를 호출하지 않는다. Intent API는 `semantic_runtime.py::analyze()` deterministic regex/map 처리로 FOOD/DINING_CONTEXT/TASTE/TASTE_QUANTITATIVE/VENUE trait/category/budget fields를 생성한다. LLM은 호출하지 않는다.

Semantic retrieval은 query vector 생성과 candidate-scoped Qdrant search, shared hybrid policy ranking, evidence trace response를 담당한다. Explanation endpoint는 전달된 최종 Spring candidates 및 claims/Safe Fact로 deterministic explanation을 반환할 수 있고, Qwen은 Spring의 llm flag와 FastAPI `AI_LLM_EXPLANATION_ENABLED=true`가 모두 허용한 요청에서만 활성화된다.

Spring과 FastAPI 사이의 timeout/error/fallback/contract test 코드가 존재한다. 현재 실행 중인 개발 Compose 컨테이너에서 Spring env에는 `SPRING_PROFILES_ACTIVE=dev`, `AI_BASE_URL`, timeouts/fallback 등이 있지만 semantic/LLM flags는 absent라 YAML default false다. AI 컨테이너에서도 AI_LLM flag env는 absent이며 코드 default false다. `.env.example`도 양쪽 기본값 false, default collection v12를 지정한다.

## 15. Qwen 역할 전체

| 목적 | 코드/모델 | 실제 상태 |
|---|---|---|
| 공식 Kakao+NAVER 후보 동일성 판단 | `provider_entity_resolution_cli.py` + Ollama `QWEN_MODEL` (`qwen3.5:9b`) | `ACTIVE` bounded data-preparation CLI; 이번 audit 호출 안 함 |
| Historical PCMap resolver 후보 ranking/detail semantic 검토 | `place_resolver_cli.py`, `place_pipeline_cli.py` alternate path + configured Qwen | `HISTORICAL_EXPERIMENT`/별도 CLI; current numeric `place_id_linker_cli`는 Qwen 미사용 |
| Semantic Profile Claim 후보 생성 | `semantic_profile_shadow.py`, `semantic_profile_expansion.py` + `qwen3.5:9b` | `ACTIVE` experiment code, 품질상 expansion paused; 과거 3 calls fail, 이번 호출 0 |
| User query embedding | `semantic_runtime.py` → Ollama `/api/embed`, `qwen3-embedding:0.6b` | opt-in semantic runtime; past isolated E2E verified; 이번 호출 0 |
| Claim indexing embedding | `semantic_embedding_qdrant_pilot.py`/claim index tooling, same embed model | historical shadow index build; current expansion index build blocked/not run |
| Recommendation explanation generation | `recommendation_explanation.py` configured Qwen model | implemented, double opt-in; 3-call revalidation was 1 GROUNDED/2 PARTIAL, so feature quality NO-GO/default OFF |
| Gemini | 없음 | `NOT_IMPLEMENTED`, runtime call 없음 |
| LangGraph | dependency/node/graph 없음 | `NOT_USED` |

`qwen3.5:9b`는 text generation/structured decisions이고 `qwen3-embedding:0.6b`는 vector embedding 전용이다. 모델 역할과 API endpoint가 다르다.

## 16. Gemini 실제 현황

Source/dependency search에서 Gemini/Google Generative AI client, API key configuration, Spring AI Gemini, Vertex AI call path는 확인되지 않았다. Repository의 `GEMINI.md`는 Gemini CLI용 project entry/instruction 문서이지 Gemini API integration이 아니다. 따라서 Gemini는 `NOT_IMPLEMENTED`; 현재 사용자 요청 runtime call은 0이다. 이번 audit에서 외부 호출은 하지 않았다.

## 17. LangGraph 실제 현황

`ai/pyproject.toml`에 LangGraph dependency가 없고 repository source에 `StateGraph`, graph compile/node/edge/checkpoint runtime 구현이 없다. 판정은 `NOT_USED`. AI flow는 일반 고정 서비스 호출과 Python functions/Spring service orchestration이다. 현재 Runtime의 Intent→Filter→Retrieval→Rank→Explain은 ordinary code flow다.

## 18. Explanation

Spring은 우선 `RecommendationItem.reason`을 deterministic facts로 채운다. Semantic runtime wiring ON이면 Spring이 final shortlist 이후 explanation API를 호출한다. FastAPI는 evidence-derived Safe Facts를 만들고 deterministic template를 기본으로 반환한다. Qwen explanation은 LLM flag true일 때 선택적으로 호출되고 response validator/fallback이 있다. LLM은 restaurant 선택/순위 변경 권한이 없다.

최신 preserved revalidation artifact는 Qwen 3회, retry 0, 반환 explanation 판정 `GROUNDED=1`, `PARTIAL=2`, `UNSUPPORTED=0`; ID/evidence errors 0, rank changes 0이다. 승인 기준 3/3 grounded 미달로 Spring semantic runtime 기본 false 유지. 즉 “LLM 코드가 있다”와 “사용자 default에서 LLM explanation이 활성”은 다르다.

## 19. React / SSE

React는 Spring API만 호출한다. 인증, signup/login, 채팅/대화복원, preferences, 최근 meal 기록, stream 중단/재시도 및 recommendation cards가 존재한다. `frontend/src/api/chat.ts`는 POST 응답 ReadableStream SSE 이벤트(`accepted`, `progress`, `recommendations`, `assistant_delta`, `completed`, `error`)를 파싱한다. `useChatStream`가 `recommendations.items`를 assistant message에 넣고 `MessageList`가 name/category/representative menu/average price/ZeroPay/reason/address 및 “먹었어요” 액션을 렌더한다.

추천 응답 event 이름은 `recommendations`; item DTO에 `reason`이 포함된다. React가 AI reason을 새로 생성하지 않는다. UI의 existence와 current runtime semantic activation은 별도다.

## 20. Full-stack E2E

`AI_Answer/mvp_full_stack_e2e_results.json` 및 review는 Browser Playwright 1 test / 3 Query의 `PAST VERIFIED`를 기록한다. Environment는 isolated DB, Semantic Runtime true, LLM explanation false. 각 query recommendation ID 9617, reason 표시; semantic requests 3, Qdrant queries 6, explanation generation 0, dev MySQL writes 0, Qdrant writes 0, Browser E2E PASS. E2E DB는 test 후 제거됐다. 의미 범위는 하나의 추천 Restaurant fixture 기반의 full-stack smoke test이며 검색 품질 확대 benchmark가 아니다.

Gemini NO, LangGraph NO, Qwen explanation generation NO, Qwen query embedding YES(과거 E2E). 이번 audit에서는 Browser E2E 재실행하지 않음(`NOT_RUN`).

## 21. Harness Engineering

현재 존재:

- Root 및 module `AGENTS.md` instruction files.
- `scripts/setup.sh`, `check-format.sh`, `check-lint.sh`, `check-frontend.sh`, `check-backend.sh`, `check-ai.sh`, `check-integration.sh`, `check-all.sh`.
- 별도 `scripts/check-mvp-e2e.sh`, Playwright browser test 및 E2E isolation/read-only proxy assets.
- Python provider/detail/semantic batch의 bounded limit, progress, checkpoint/resume/failure isolation 코드가 각 파이프라인에 존재.
- Profile readiness audit은 SELECT-only 정책 실행; detail persistence CLI는 dry-run/write-db 분리.
- E2E에 MySQL disposable DB guard와 Qdrant/Ollama read-only guard가 과거 검증 artifact에 기록됨.

이번 audit에서는 scripts를 실행하지 않았다. 특히 `check-integration.sh`/full E2E는 test data write/외부 dependency 사용 가능성이 있어 수행하지 않았다. Harness inventory는 파일 존재 및 코드 확인이며 이번 실행 PASS 의미가 아니다.

## 22. CI / Docker / Deployment

### CI

`.github` workflow 파일이 확인되지 않았다. 판정: GitHub Actions CI 없음(현재 저장소 탐색 기준). local check scripts는 있으나 자동 CI와 동일하지 않다.

### Docker

현재 실행 중 Compose 서비스 read-only 확인: MySQL 8.4, Qdrant 1.19.1, FastAPI, Spring backend, frontend nginx. Ollama는 Compose 서비스가 아니라 host/local dependency로 연결한다. 현재 Docker 컨테이너 status는 모두 healthy였다. 격리 MVP E2E용 별도 compose 파일도 있지만 지금 실행하지 않았다.

### AWS / 배포

`docs/deployment.md`는 profile/compose 및 향후 배포 방향을 설명하지만 실제 AWS 배포 resource, pipeline, IaC/runtime deployment가 구현됐다는 근거는 찾지 못했다. AWS deployment는 `PLANNED`, 현재 배포 여부는 `NOT_IMPLEMENTED/UNKNOWN`으로 기록한다. 계획 문서를 배포 완료로 해석하지 않는다.

## CURRENT — 현재 실제 구현 / PLANNED — 향후 방향

**CURRENT:** opt-in FastAPI Intent/Semantic Retrieval 및 explanation 코드, Spring Client/추천 연결, React SSE 카드, v12 shadow collection, deterministic explanation 경로가 구현돼 있다. 개발/default semantic flag는 OFF이고, expanded Semantic Profile은 의미 품질 실패로 중단됐다. Gemini API와 LangGraph는 구현되지 않았다.

**PLANNED:** 사용자가 밝힌 다음 방향은 Gemini 외부 API를 실제 AI 기능에 적용해 1차 AI 서비스를 완성한 뒤, 실질적 분기/재질의가 필요할 때 LangGraph를 도입하는 것이다. 이는 현재 구현이 아니다. AWS/운영 배포 역시 문서상 계획이지 실제 배포로 검증되지 않았다.

## 23. 문서 vs 코드 불일치

| 항목 | 문서/오래된 설명 | 실제 코드/상태 | 판정 |
|---|---|---|---|
| Root `AGENTS.md` architecture summary | FastAPI는 health/contract 중심이며 실제 Spring→FastAPI 호출 미구현이라고 요약 | 실제 endpoint/client/wiring 및 past live/browser E2E가 있음; 현재는 Spring flag default OFF | 현재 코드보다 뒤처진 요약 |
| FastAPI scope | `ai/README.md`는 1단계를 health only, Qdrant 검색 미구현이라고 설명 | `main.py`에 intent/retrieval/explanation endpoints, runtime service 및 Qdrant/Ollama call 있음 | README stale |
| AI workflow | `docs/ai-flow.md` 현재 구현 절은 연동을 설명하면서 뒤에서 Qdrant/retrieval/LLM 제공자 구현 예정이라고 적음 | retrieval와 explanation 코드 및 Spring wiring 구현, opt-in | 동일 문서 내부 stale historical text |
| Architecture | `docs/architecture.md` 일부 문구는 LLM explanation 미구현으로 서술 | explanation endpoint/client/service 구현, 다만 quality approval 미달/default OFF | “구현”과 “사용 승인/default”를 혼합한 stale summary |
| README | LangGraph/LLM explanation 미구현으로 요약 | LangGraph 미사용은 맞지만 Qwen explanation 구현은 있고 opt-in | explanation 표현 부정확 |
| Testing | harness 설명은 FastAPI/Qdrant가 아직 연결되지 않았다고 요약하는 부분 | live contract와 isolated browser E2E artifacts 존재 | stale summary; past verification과 current flag 분리 필요 |
| Profile 확장 | 이전 작업 문서는 READY 26에 따라 expansion 시작 가능 | 현재 artifact는 19 planned, 3 실패 후 PAUSED, 16 pending, embedding/index 중단 | 계획을 완료로 볼 수 없음 |
| Readiness 26 | backfill 산출물은 strict-ready 26 | 이번 DB SELECT + same policy 재실행도 26 | 현재 수치 확인됨; 의미는 semantic input gate에 한정 |
| NAVER Qwen | 과거 resolver 설명은 NAVER에 Qwen 사용으로 읽힐 수 있음 | official Local 후보 fusion은 Qwen 사용; numeric Place ID linker는 deterministic only | 서로 다른 단계 설명 필요 |
| 500m | historical migration/changelog에 radius 흔적 | 현재 recommendation runtime에 거리 계산 없음 | historical only |

## 24. Current Blockers

1. **Semantic claim quality (P0)**: 3/3 신규 Profile whole-output validation fail; AUTO classification이 과장 표현을 차단하지 못함. 신규 embedding/indexing은 stop 상태.
2. **Recommendation-ready data coverage (P0 runtime breadth)**: 402 eligible Nonhyeon source candidates 대비 `recommendation_ready` 4개, 그중 current static intersection 1개. strict-ready 26은 Spring serving coverage가 아님.
3. **Semantic index coverage (P1)**: v12는 고정 10개/40 claims; strict-ready 26과 확장 cohort를 반영하지 않음. expanded collection 없음.
4. **LLM explanation quality (P1, optional)**: revalidation 1/3 GROUNDED; LLM mode는 승인 불가, deterministic reason은 fallback/default.
5. **Semantic benchmarking**: v12 frozen pilot benchmark는 보존됐지만 expanded GTv3/index benchmark는 blocked/not run; 그 수치로 확장 품질을 주장할 수 없음.
6. **Observability / CI / Deploy (P2)**: local harness는 있지만 CI workflow 미확인, production observability와 AWS deployment 구현 없음.
7. **Documentation drift (P2)**: AI README/flow/architecture/testing에 FastAPI retrieval 및 explanation의 구현 상태가 이전 문구로 남음.

## 25. Recommended Next Development Order

이는 현재 구현이 아니라 audit 후의 권고다.

1. **추천 가능 data gate 확인/보강**: `recommendation_ready`가 4뿐인 이유를 deterministic schedule/menu 입력 기준으로 조사하고 serving 후보 범위를 실제 요구사항과 정렬한다. readiness 수치를 user-facing coverage로 혼동하지 않는다.
2. **Claim 의미 validation 개선**: Qwen profile expansion을 재개하기 전에 evidence-to-claim 직접 지지 검사/human review threshold/schema/prompt version을 별도 설계하고, 이미 보존한 실패 3건을 회귀 fixture로 사용한다. 같은 실패 입력을 무분별하게 재호출하지 않는다.
3. **Strict-ready 26 중 유효 Claim을 안전하게 확정**: 기존 7 artifacts를 “현재 source-compatible”와 “semantic claim quality approved”로 나눠 재검토한다. 승인 전 Qdrant 신규 index 금지.
4. **문서 동기화 + CI**: health-only/Qdrant-not-implemented 등 stale statements 정리하고 check scripts를 CI에서 실행할 수 있도록 범위를 정한다.
5. **확장 index/benchmark**: quality gate를 통과한 실제 profile만 shadow index에 올리고, Ground Truth를 검색 전 freeze해 v12와 비교한다. Runtime collection 교체는 별도 승인/isolated E2E 뒤.
6. **Gemini 도입**: 사용자가 원하는 1차 AI service 범위가 확정되면 우선 deterministic intent가 아니라 explanation 또는 특정 LLM task를 대상으로 작은 interface/provider adapter부터 도입; 실제 API key/비용/timeout/fallback/data policy를 준비한다. Gemini를 추가해도 Hard Filter/Rank는 Spring 소유.
7. **LangGraph는 조건 발생 뒤**: 추가 질문, 제약 완화 후 재검색, 검색전략 fallback처럼 실질적인 branch/state가 필요해질 때 orchestration node로 도입한다. 현재 fixed flow를 graph로 옮기는 것만으로는 가치가 낮다.
8. **관측성/운영 배포**: request correlation, Qdrant/model dependency latency/errors, fallback ratio 및 safe logging부터 마련한 뒤 Docker/AWS deployment.

## 26. Q1~Q10 명시적 답변

### Q1. KOMSCO → NAVER/Kakao 과정에서 Qwen은 어디에 쓰이나?

현재 공식 provider fusion에서는 Kakao 및 NAVER Local 후보들을 모은 뒤 KOMSCO 기준 정보와 후보를 비교하는 Entity Resolution에 Qwen3.5:9b가 사용된다. 이후 numeric PCMap Place ID 연결은 별도 UI allSearch와 deterministic name/address 판정이며 Qwen이 사용되지 않는다.

### Q2. NAVER에서 Qwen을 사용하는가?

- NAVER **Local candidate resolution**: Kakao와 합쳐진 official Provider fusion에서는 Qwen이 후보 판정에 포함된다.
- **Numeric NAVER Place ID resolution**: current `place_id_linker_cli.py`는 Qwen 미사용, exact normalized name + address evidence 규칙이다.
- 과거 `place_resolver_cli.py` 경로에는 선택적 Qwen ranking이 있지만 현재 linker와 다른 historical/alternate path다.

### Q3. strict-ready 26은 무슨 뜻인가?

현재 360개 matched-numeric 논현동 대상 중 Profile input 생성에 필요한 identity, three section lifecycle/freshness, priced menu, 원문 근거 구조화 hours 조건을 모두 통과한 26개다. 승인 Profile/Claim 26개가 아니라 입력 데이터 readiness다.

### Q4. 서비스가 추천할 수 있는 Restaurant가 26뿐인가?

아니다. Spring source population은 402 ACTIVE+ELIGIBLE 논현동이고 semantic readiness와 별개다. 다만 DB snapshot상 `recommendation_ready=true` 4개, 그중 active/eligible/nonhyeon/ZeroPay intersection은 1개뿐이다. 이 gate와 운영시간이 실제 serving breadth를 더 직접적으로 제한한다.

### Q5. 사용자 질문 분석은 무엇으로 하는가?

FastAPI `analyze()` deterministic regex/lexical taxonomy code다. Spring은 semantic flag OFF면 `TemporaryIntentAnalyzer`; ON이면 FastAPI adapter를 쓴다. 사용자 질문 분석에 Gemini/Qwen LLM은 사용하지 않는다.

### Q6. Gemini API가 실제 사용되는가?

아니다. client/dependency/config/call path가 확인되지 않았다. `GEMINI.md`는 instruction entry file일 뿐이다.

### Q7. LangGraph가 실제 사용되는가?

아니다. 판정 `NOT_USED`; graph dependency/state/node/edge/compile path 없음.

### Q8. 현재 Qwen은 어디서 사용되는가?

Provider Entity Resolution, 별도 legacy/alternate NAVER resolver, Semantic Profile Claim generation 실험, opt-in Recommendation Explanation generation. Query/document embedding은 Qwen generation model이 아니라 `qwen3-embedding:0.6b`다. 이번 audit 중 실제 Qwen/embedding 호출은 0회.

### Q9. Qdrant에 몇 Restaurant/Point가 있는가?

v12 read-only scroll 기준 10 Restaurant / 40 points. 차원 1024, Cosine. expanded Shadow collection은 현재 없음.

### Q10. 가장 먼저 해결할 기술 문제는?

**Semantic Profile Claim의 의미적 직접 근거 검증**이다. 현재 구조 검증은 Evidence ID와 type/status를 확인하지만, 9559/9603/9639의 실제 사례처럼 내용 과장을 막지 못해 expansion이 중단됐다. 동시에 서비스 추천 폭을 실제 제한하는 `recommendation_ready=4`도 데이터 coverage blocker로 별도 확인해야 한다. 둘을 혼동해 Qdrant/Profile 작업만 늘리면 user serving coverage는 해결되지 않는다.

## Evidence / 실행 구분

- Current DB counts: MySQL SELECT-only, 2026-09-25; secret/credential 출력 없음.
- Profile readiness: `ProfileReadinessPolicy`와 현재 DB audit 재실행.
- Qdrant: local collection metadata GET + v12 payload-only scroll, no vectors/write.
- Current running containers: `docker compose ps`; backend/AI environment flags read-only.
- E2E and Qwen results: past saved artifacts, not re-run.
- Gemini API/provider API/crawler/Qwen generation/embedding/Browser E2E/test harness: `NOT_RUN` in this audit.
- Working tree: existing modifications/untracked artifacts preserved; no Git mutation.
