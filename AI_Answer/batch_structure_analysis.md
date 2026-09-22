# ZeroPay Lunch AI Python Batch 구조 분석

> 이 문서는 코드를 처음 읽는 사람도 전체 흐름을 따라갈 수 있도록 작성한 학습용 설명서입니다. 기술 용어가 나오면 이 문서의 용어 해설을 먼저 확인하면 됩니다.

## 먼저 읽는 용어 해설

| 용어 | 쉬운 뜻 | 이 프로젝트에서의 의미 |
|---|---|---|
| Batch | 여러 건의 데이터를 한꺼번에 처리하는 작업 | 음식점 목록을 하나씩 검증하고 상세 정보를 모으는 작업 |
| Orchestrator | 여러 작업의 순서를 조정하는 관리자 | 각 Python 단계를 순서대로 실행하는 `e2e_pipeline_orchestrator.py` |
| Source of Truth | 최종적으로 믿는 기준 데이터 | 이 프로젝트에서는 주로 MySQL |
| Provider | 외부 데이터를 제공하는 서비스 | Kakao API와 NAVER Local API |
| Candidate | 후보 | 외부 검색 결과 중 원본 음식점과 같을 가능성이 있는 장소 |
| Fusion | 여러 출처의 결과를 합치는 것 | Kakao와 NAVER 후보를 하나의 Qwen 입력으로 합침 |
| Dedup | 중복 제거 | 완전히 같은 provider 후보를 한 번만 남김 |
| Entity Resolution | 두 데이터가 같은 대상을 가리키는지 판단하는 작업 | KOMSCO 음식점과 Kakao/NAVER 후보가 같은 음식점인지 확인 |
| Semantic | 단순 문자열 비교를 넘어선 의미 판단 | 지점명, 주소, 업종 등을 종합해 같은 업체인지 판단하는 것 |
| Qwen | 이 프로젝트에서 사용하는 로컬 언어 모델 | 후보 순위와 동일 업체 여부를 판단하는 Ollama 모델 |
| Structured Output | 정해진 JSON 형식으로 받는 답변 | Qwen이 `ACCEPT`, `REJECT` 같은 정해진 필드를 반환하는 방식 |
| Quality Gate | 다음 단계로 보낼지 결정하는 문 | 검증 결과를 ACCEPT/REJECT/UNKNOWN으로 정리하는 코드 |
| Canonical | 대표·표준 데이터 | 여러 출처의 정보를 합친 내부 기준 음식점 정보 |
| Provenance | 데이터가 어디서 왔는지에 대한 출처 기록 | Kakao인지 NAVER인지, 어떤 모델이 판단했는지 기록 |
| Fingerprint | 데이터 내용의 요약 지문 | KOMSCO 원본이 바뀌었는지 비교하는 SHA-256 값 |
| Manifest | 이번 실행에서 처리할 대상 목록 | 음식점 ID, 이름, 주소 등을 담은 CSV 목록 |
| Resume | 중단된 작업을 이어서 하는 것 | 이미 끝난 음식점은 건너뛰고 미완료 음식점부터 처리 |
| Cache | 이전 결과를 임시·재사용하는 저장소 | 같은 원본 fingerprint의 REJECT 결과를 재사용 |
| Upsert | 있으면 수정하고 없으면 추가하는 저장 방식 | 같은 데이터를 여러 번 실행해도 중복 row를 만들지 않음 |
| Transaction | 여러 DB 작업을 하나의 묶음으로 처리하는 단위 | 중간 실패 시 전체를 취소할 수 있게 하는 DB 기능 |
| Rollback | transaction을 취소하고 이전 상태로 되돌리는 것 | Canonical 저장 중 오류가 나면 부분 저장을 취소 |
| Place ID | NAVER 장소의 숫자 식별자 | NAVER Maps 상세 페이지를 다시 찾기 위한 숫자 ID |
| NAVER_LOCAL | NAVER 공식 Local API의 검색 결과 | 장소 후보 evidence이며 numeric Place ID와는 다름 |
| allSearch | NAVER Maps 화면이 검색할 때 받는 결과 | Playwright로 화면 검색을 수행한 뒤 캡처하는 응답 |
| Playwright | 실제 브라우저를 코드로 조작하는 도구 | NAVER Maps 화면을 열고 결과를 읽는 데 사용 |
| DOM | 브라우저 화면을 구성하는 HTML 구조 | HOME/MENU/REVIEW 화면에서 보이는 정보를 읽는 대상 |
| Persistence | 데이터를 DB에 저장하는 작업 | CSV나 화면 결과를 MySQL table에 upsert하는 과정 |
| Detail Enrichment | 상세 정보 보강 | 메뉴, 가격, 영업시간, 리뷰를 추가로 수집하는 단계 |
| Stale | 너무 오래되어 다시 수집해야 하는 상태 | 기본 30일이 지난 detail section |
| Rate Limit | 외부 서비스에 요청하는 속도 제한 | NAVER 차단을 피하기 위해 요청 사이에 기다리는 정책 |
| Retry | 실패한 작업을 다시 시도하는 것 | timeout 같은 일시 오류에만 제한적으로 적용 |
| Cooldown | 차단 후 다시 시도하기 전 기다리는 시간 | 429/403 이후 기본 30분 대기 |
| Runtime Report | 실행 결과 기록 | 처리 수, 실패 수, 시간, 마지막 성공 ID를 담은 JSON |
| API | 프로그램끼리 통신하는 약속된 접점 | Python이 Kakao/NAVER/Ollama와 통신하는 HTTP 경로 |
| Endpoint | API의 구체적인 요청 주소 | 예: Kakao keyword search URL |
| JSON / CSV | 데이터 파일 형식 | JSON은 구조화 응답, CSV는 처리 목록·결과 파일 |

### 이 문서를 읽을 때 기억할 핵심

1. **KOMSCO**는 원본 음식점 목록입니다.
2. **Kakao/NAVER Local**은 후보를 찾아오는 검색 서비스입니다.
3. **Qwen**은 후보가 같은 음식점인지 의미를 판단합니다.
4. **Canonical**은 검증된 음식점을 내부 대표 데이터로 만든 것입니다.
5. **NAVER numeric Place ID**는 Maps 상세 페이지를 찾기 위한 별도 식별자입니다.
6. **Detail**은 Place ID가 확정된 뒤 메뉴·영업시간·리뷰를 채우는 작업입니다.
7. **MySQL**은 모든 단계가 공유하는 기준 저장소입니다.

## 전체 흐름

```text
KOMSCO API
  ↓
Spring Boot KOMSCO importer
  ↓
MySQL restaurants
  ↓
Python E2E orchestrator
  ↓
Kakao + NAVER Local 후보 조회
  ↓
후보 dedup / fusion
  ↓
Qwen choose → validate
  ↓
ACCEPT / REJECT / UNKNOWN
  ↓
verification 저장
  ↓
ACCEPT만 Canonical/provider mapping 저장
  ↓
NAVER Maps UI 검색
  ↓
allSearch 응답에서 numeric Place ID 추출
  ↓
HOME / MENU / HOURS / REVIEW 수집
  ↓
MySQL detail table upsert
  ↓
Spring 추천 query 소비
```

Python E2E는 KOMSCO API를 직접 호출하지 않는다. KOMSCO 원본 적재는 Spring Boot importer가 담당하고, Python Batch는 MySQL에 적재된 KOMSCO 행을 읽어 후속 검증을 진행한다.

## 1. Batch Orchestrator

> **쉽게 말하면:** 여러 작업을 직접 처리하는 요리사가 아니라, `1번 끝나면 2번`, `2번 끝나면 3번`을 지시하는 작업 관리자입니다.

핵심 파일:

```text
ai/app/batch/e2e_pipeline_orchestrator.py
```

실행 단계:

1. KOMSCO 대상 DB 조회
2. Entity Resolution
3. Canonical persistence
4. NAVER Place ID Linking
5. Detail Enrichment

Orchestrator는 `subprocess.Popen`으로 하위 CLI를 실행하고 stdout을 실시간 전달한다. 각 child CLI가 실패하면 즉시 종료하며 뒤 단계는 실행하지 않는다.

대상 조건:

- `active = 1`
- `source_provider = 'KOMSCO'`
- `legal_dong_code = '11680108'`
- `provider_institution_code = 'I0000002'`
- `industry_code = '561'`
- `business_status_name = '계속사업자'`

### Resume 기준

다음 조건이면 기존 검증을 재사용한다.

```text
verification_status == VERIFIED
AND 저장된 source_fingerprint == 현재 fingerprint
```

그 외에는 Entity Resolution 대상이다.

실행 중 manifest, CSV, stage별 JSON report는 다음 위치에 생성된다.

```text
ai/build/reports/naver-place-pipeline/e2e/
```

## 2. KOMSCO 원본과 fingerprint

> **쉽게 말하면:** 먼저 믿을 수 있는 원본 명단을 만들고, 지난번 명단과 달라진 음식점만 다시 검사합니다.

Spring 관련 파일:

```text
backend/src/main/java/.../restaurant/importer/RestaurantImportService.java
backend/src/main/java/.../restaurant/importer/KomscoMerchantClient.java
backend/src/main/java/.../restaurant/importer/KomscoMerchantFilter.java
backend/src/main/java/.../restaurant/importer/RestaurantImportWriter.java
```

Spring importer는 KOMSCO API pagination, 중복 제거, 최신 기준일자 선택, 논현동·업종·기관·계속사업자 필터, `restaurants` upsert와 stale inactive 처리를 담당한다.

Python Orchestrator는 이미 저장된 `restaurants`를 조회해 manifest를 만든다. Python이 KOMSCO API를 직접 호출하는 구조는 아니다.

`ai/app/entity_resolution/verification_quality_gate.py`의 `source_fingerprint()`는 다음 값을 SHA-256으로 만든다.

- external merchant ID
- 이름
- 주소와 상세 주소
- 좌표
- 법정동 코드
- 업종 코드
- 사업 상태
- 기관 코드

원천 필드가 변경되면 fingerprint가 달라져 재검증 대상이 된다.

런타임 처리 이유는 DB enum을 늘리지 않고 다음처럼 report에 기록한다.

- `NEW_SOURCE`
- `SOURCE_CHANGED`
- `RETRY_UNKNOWN`
- `REJECT_CACHE_CANDIDATE`
- `VERIFICATION_PENDING`
- `UNCHANGED_VERIFIED`

## 3. Kakao / NAVER Local 후보 수집

> **쉽게 말하면:** KOMSCO 이름을 검색창에 넣어 비슷한 장소 후보를 가져오는 단계입니다. 아직 같은 음식점이라고 확정하지는 않습니다.

핵심 파일:

```text
ai/app/providers/place_provider.py
ai/app/providers/provider_candidate_retrieval_cli.py
ai/app/providers/provider_input.py
```

### Kakao

클래스는 `KakaoPlaceSearchProvider`이며 endpoint는 다음과 같다.

```text
https://dapi.kakao.com/v2/local/search/keyword.json
```

인증은 `KakaoAK {KAKAO_REST_API_KEY}` 헤더를 사용한다.

후보에서 사용하는 값:

- external ID
- 장소명
- 카테고리
- 주소와 도로명 주소
- 좌표
- 전화번호
- 상세 URL
- 거리

### NAVER Local

클래스는 `NaverPlaceSearchProvider`이며 endpoint는 다음과 같다.

```text
https://naverapihub.apigw.ntruss.com/search/v1/local
```

인증은 `X-NCP-APIGW-API-KEY-ID`, `X-NCP-APIGW-API-KEY`를 사용한다.

NAVER Local 응답에는 numeric NAVER Maps Place ID가 없으므로 `external_place_id`는 비워 두고 link는 `detail_url`로만 보존한다.

음식점마다 검색어는 다음 두 가지다.

```text
원본 음식점명
논현동 원본 음식점명
```

Kakao는 좌표가 있으면 좌표와 거리 정렬을 사용하고, NAVER Local은 중심 좌표 검색을 사용하지 않는다.

Provider HTTP client는 batch 동안 재사용된다. Provider 단계는 Kakao와 NAVER를 bounded worker로 병렬 조회하고, 다음 음식점 결과를 prefetch할 수 있다. Qwen inference 자체는 단일 순차 흐름이다.

## 4. Candidate Dedup / Fusion

> **쉽게 말하면:** 검색 결과에 같은 후보가 여러 번 나오면 정리하지만, 서로 다른 업체를 같은 업체라고 판단하지는 않습니다.

핵심 파일:

```text
ai/app/entity_resolution/provider_entity_resolution_cli.py
```

주요 함수:

- `_candidate_key()`
- `_merge_with_stats()`

동일 provider 안에서 다음 순서로 중복을 판단한다.

1. provider + external place ID
2. provider + detail URL
3. provider + 이름 + 주소 + 도로명 주소 + 카테고리 + 좌표

Kakao와 NAVER 후보는 provider가 다르면 합치지 않는다. 이 정책은 provenance를 보존하고 코드가 semantic 동일성 판단을 대신하지 않도록 하기 위한 것이다.

Dedup은 구조적으로 동일한 후보 제거만 수행하며, 같은 업체인지 여부는 Qwen이 판단한다.

## 5. Qwen Entity Resolution

> **쉽게 말하면:** 여기서 처음으로 “이 검색 결과가 원본 음식점과 같은 곳인가?”를 본격적으로 판단합니다. 단순히 글자가 같은지만 보는 것이 아니라 주소·지점·업종을 함께 봅니다.

핵심 파일:

```text
ai/app/entity_resolution/qwen_candidate_matcher.py
ai/app/entity_resolution/provider_entity_resolution_cli.py
ai/app/entity_resolution/verification_quality_gate.py
```

전체 흐름:

```text
Provider candidates
  ↓
Qwen choose
  ↓
상위 후보 순위
  ↓
Qwen validate
  ↓
ACCEPT / REJECT / UNKNOWN
```

### choose

후보 전체를 전달하고 상위 최대 5개 후보 index와 confidence를 받는다.

```json
{
  "candidateIndices": [0, 2, 1],
  "confidence": "HIGH"
}
```

### validate

각 후보에 대해 다음을 구조화된 JSON으로 판단한다.

- `entity_match`: MATCH / NO_MATCH / UNCERTAIN
- `business_type`: FOOD / NON_FOOD / UNKNOWN
- `location_scope`: IN_SCOPE / OUT_OF_SCOPE / UNKNOWN
- `final_decision`: ACCEPT / REJECT / UNCERTAIN
- 이름·주소·카테고리·좌표 evidence
- reason

논리적인 Qwen 호출 수는 후보가 있는 경우 최소 `choose 1회 + validate 1회`, 최대 `choose 1회 + validate 5회`다. 구조화 응답 오류가 나면 각 호출은 1회 재시도한다.

Kakao와 NAVER 양쪽에서 ACCEPT가 나오면 더 이상 후보를 검증하지 않는다.

### 책임 경계

코드가 담당하는 것:

- 후보 조회
- 후보 구조화
- 구조적 중복 제거
- fingerprint
- JSON schema 검증
- 기술 오류 처리
- 상태 매핑

Qwen이 담당하는 것:

- 같은 업체·지점인지
- 음식점인지
- 논현동 범위인지
- semantic 최종 결정
- reason과 evidence

현재 일반 코드가 이름 유사도나 주소 점수로 Qwen semantic 결과를 다시 veto하는 경로는 확인되지 않는다.

## 6. Verification 상태 저장

> **쉽게 말하면:** Qwen의 판단을 DB에서 사용할 수 있는 세 가지 결과로 번역하는 단계입니다.

`verification_quality_gate.py`의 상태 매핑은 다음과 같다.

| Semantic 결과 | 쉬운 의미 | DB verification_status | recommendation_eligibility |
|---|---|---|---|
| ACCEPT | 같은 음식점으로 확인됨 | VERIFIED | ELIGIBLE |
| REJECT | 다른 업체·지점이거나 음식점이 아님 | REJECTED | INELIGIBLE |
| UNKNOWN | 정보 부족 또는 기술 오류로 확정하지 못함 | ERROR | UNKNOWN |

DB에는 semantic `UNKNOWN` 대신 `ERROR`가 저장되고, `verification_reason`으로 세부 사유를 보존한다.

주요 reason:

- `SEMANTIC_UNCERTAIN`
- `NO_CANDIDATE`
- `STRUCTURED_OUTPUT_ERROR`
- `NETWORK_ERROR`
- `QWEN_TIMEOUT`
- `HTTP_*`

Reject Cache는 다음 조건에서 동작한다.

```text
기존 decision = REJECT
AND 기존 fingerprint == 현재 fingerprint
```

이 경우 Kakao, NAVER Local, Qwen을 호출하지 않는다. fingerprint가 바뀌면 다시 검증한다.

UNKNOWN/ERROR는 확정 결과로 취급하지 않아 다음 실행에서 재검증한다.

## 7. Canonical Restaurant

> **쉽게 말하면:** 여러 출처에서 모은 정보를 음식점 하나의 대표 카드로 합치는 단계입니다.

핵심 파일:

```text
ai/app/canonical/canonical_builder.py
ai/app/canonical/canonical_persistence_cli.py
ai/app/naver/place_detail_persistence.py
```

Canonical은 KOMSCO 원본과 provider evidence를 내부 대표 음식점으로 정규화하기 위해 필요하다.

ACCEPT row에서 선택된 Kakao/NAVER 후보를 복원하고, NAVER 후보가 있으면 대표값에 우선 사용한다. 없으면 Kakao 후보를 사용한다.

저장 대상:

- `canonical_restaurants`
- `restaurant_external_places`
- `restaurant_naver_verifications`
- `restaurants.recommendation_eligibility`

REJECT와 UNKNOWN은 Canonical을 만들지 않고 verification만 저장한다.

음식점 하나의 persistence는 다음 transaction으로 묶인다.

```text
START TRANSACTION
  canonical_restaurants upsert
  restaurant_external_places upsert
  restaurant_naver_verifications upsert
  restaurants.recommendation_eligibility update
COMMIT
```

중간 SQL 오류가 발생하면 COMMIT되지 않고 CLI가 실패 종료하며 Orchestrator는 다음 단계로 진행하지 않는다.

## 8. NAVER Numeric Place ID Linking

> **쉽게 말하면:** NAVER 검색 결과의 이름·주소 정보와 NAVER Maps 상세 페이지를 연결하는 단계입니다. Local API 결과만으로는 상세 페이지 번호를 알 수 없기 때문에 별도로 수행합니다.

핵심 파일:

```text
ai/app/naver/place_id_linker_cli.py
ai/app/naver/place_allsearch.py
ai/app/naver/playwright_lifecycle.py
ai/app/naver/place_resolver_cli.py
```

NAVER Local evidence와 numeric NAVER Maps ID는 별개다.

```text
NAVER_LOCAL = 공식 Local API 검색 evidence
NAVER = Maps numeric Place ID mapping
```

실제 흐름:

```text
canonical_restaurants
  + restaurant_external_places(provider=NAVER_LOCAL)
  ↓
Playwright NAVER Maps UI 검색
  ↓
UI navigation 중 발생한 allSearch response capture
  ↓
parse_allsearch_candidates()
  ↓
numeric Place ID + 이름/주소 비교
  ↓
MATCHED / UNRESOLVED / AMBIGUOUS
```

`place_allsearch.py`는 이미 UI navigation으로 얻은 payload를 parsing한다. direct allSearch API replay 경로는 확인되지 않는다.

- MATCHED: 숫자형 ID가 하나의 후보와 일치
- UNRESOLVED: 일치 후보 없음
- AMBIGUOUS: 일치 후보가 둘 이상

기존 numeric MATCHED row는 기본 재처리하지 않는다. UNRESOLVED는 다시 시도할 수 있고, AMBIGUOUS는 기본 제외되며 `--force-retry`에서 명시적으로 재시도할 수 있다.

## 9. Detail Enrichment

> **쉽게 말하면:** 장소를 찾은 뒤 그 장소의 메뉴판, 영업시간표, 리뷰 요약을 채워 넣는 단계입니다.

핵심 파일:

```text
ai/app/naver/place_detail_enrichment_cli.py
ai/app/naver/place_dom_detail_crawler.py
ai/app/naver/place_detail_models.py
ai/app/naver/place_detail_persistence.py
```

진입 조건:

- Canonical 존재
- `restaurant_external_places.provider = 'NAVER'`
- `match_status = 'MATCHED'`
- numeric `external_place_id`
- `recommendation_eligibility = 'ELIGIBLE'`

수집 흐름:

```text
HOME → MENU → BUSINESS HOURS → REVIEW → PlaceDetail → section별 upsert
```

수집하는 주요 데이터:

- HOME: 이름, 카테고리, 주소, 전화번호, 편의시설, 영업시간
- MENU: 메뉴명, 설명, 가격, 메뉴 수, 썸네일
- HOURS: 요일, 영업시간, 휴무, 브레이크 관련 정보
- REVIEW: 방문자·블로그 리뷰 수, keywords, 메뉴 언급, 대표 리뷰

저장 테이블:

```text
restaurant_menus
restaurant_business_hours
restaurant_review_summaries
restaurant_review_keywords
restaurant_representative_reviews
```

완료 여부는 review summary 하나만으로 판단하지 않는다.

- review summary 존재
- 활성 메뉴와 유효 가격 존재
- 영업시간 row 존재
- section별 `crawled_at`이 stale인지

기본 stale 기간은 `NAVER_DETAIL_STALE_AFTER_SECONDS=2592000`이다. `--force-refresh`는 fresh section도 다시 수집한다.

기존 정상 section은 보호한다. 메뉴 가격이 새 결과에서 NULL이면 기존 가격을 유지하며, HOME 실패 시 기존 detail을 보존하고 persistence를 건너뛴다.

## 10. Rate Limit / BLOCKED / Retry

> **쉽게 말하면:** 외부 사이트에 너무 빠르게 요청하지 않도록 속도를 조절하고, 차단 신호가 나오면 억지로 계속하지 않는 안전장치입니다.

| 오류 | 처리 |
|---|---|
| HTTP 403 | BLOCKED, 즉시 중단 |
| HTTP 429 | BLOCKED, 즉시 중단 |
| CAPTCHA | 즉시 중단 |
| timeout | 제한적 retry 대상 |
| connection error | 제한적 retry 대상 |
| browser/page/context 종료 | lifecycle 복구 후 현재 항목 처리 |
| Qwen structured output 오류 | 호출별 1회 재시도 후 UNKNOWN |

`BATCH_TRANSIENT_MAX_RETRIES` 기본값은 0회이며 코드상 최대 2회다. backoff 기본값은 10초이고 지수 backoff를 사용한다.

BLOCKED report에는 `resume_not_before`가 기록된다. 기본 cooldown은 `NAVER_BLOCK_COOLDOWN_SECONDS=1800`이다.

## 11. Progress / Runtime Report / Resume

> **쉽게 말하면:** 작업 중에는 현재 몇 번째인지 보여주고, 끝나거나 중단되면 나중에 확인할 수 있는 실행 기록을 남깁니다.

핵심 파일:

```text
ai/app/batch/batch_progress.py
```

`BATCH_PROGRESS_EVERY` 기본값은 10이다.

stdout과 JSON report에는 다음 정보가 포함된다.

- current / total
- restaurant ID와 이름
- success / failed / skipped
- retry / blocked / HTTP 429
- elapsed / 평균 / ETA
- Kakao/NAVER request 수와 latency
- Qwen choose/validate 호출 수와 latency
- candidate dedup 통계
- prefetch hit/wait
- browser start/restart/page recreate
- 마지막 성공·실패 restaurant ID
- 중단 원인

현재 E2E manifest는 해당 실행 대상과 processing reason을 전달하는 입력이다. DB resume의 핵심 기준은 verification fingerprint, Reject Cache, numeric Place ID mapping, detail section 상태다.

과거 build 산출물에 남아 있는 manifest/checkpoint/ledger와 현재 실행에서 생성되는 runtime report는 서로 구분해야 한다.

## 12. 핵심 MySQL 테이블

> **쉽게 말하면:** 각 table은 음식점 처리 과정의 서로 다른 서랍입니다. 원본, 검증 결과, 대표 정보, 외부 ID, 상세 정보가 섞이지 않도록 나누어 저장합니다.

### `restaurants`

KOMSCO 원본 음식점과 active, recommendation eligibility, recommendation ready를 저장한다. Orchestrator와 Spring 추천이 읽는다.

### `restaurant_naver_verifications`

Entity Resolution 상태, reason, model, fingerprint, 시각을 저장한다. Orchestrator resume과 Reject Cache가 사용한다.

### `canonical_restaurants`

ACCEPT된 음식점의 정규화 대표 데이터다. Place ID와 Detail 단계가 읽는다.

### `restaurant_external_places`

provider별 외부 evidence와 mapping을 저장한다.

```text
NAVER_LOCAL → 공식 Local evidence
NAVER       → numeric NAVER Maps mapping
```

### Detail tables

```text
restaurant_menus
restaurant_business_hours
restaurant_review_summaries
restaurant_review_keywords
restaurant_representative_reviews
```

Python Detail persistence가 쓰고, Detail 대상 선정과 데이터 보강에 사용한다.

현재 Spring의 추천 query는 주로 `restaurants`와 schedule 관련 테이블을 사용하며, 메뉴·리뷰 table을 직접 join하는 구조는 확인되지 않는다.

## 13. Python 파일 지도

> 아래 파일을 한 번에 모두 외우기보다, 위에서 아래 순서로 한 파일씩 열어 호출 관계를 따라가면 됩니다.

| 기능 | 먼저 볼 파일 | 역할 |
|---|---|---|
| 전체 Batch | `ai/app/batch/e2e_pipeline_orchestrator.py` | 전체 stage 실행 |
| 진행률/report | `ai/app/batch/batch_progress.py` | stdout/JSON report |
| Provider 조회 | `ai/app/providers/place_provider.py` | Kakao/NAVER HTTP와 parsing |
| Provider 입력 | `ai/app/providers/provider_input.py` | manifest 로딩 |
| Entity Resolution | `ai/app/entity_resolution/provider_entity_resolution_cli.py` | fusion, dedup, Qwen 실행 |
| Qwen | `ai/app/entity_resolution/qwen_candidate_matcher.py` | choose/validate, Ollama 연결 |
| Quality Gate | `ai/app/entity_resolution/verification_quality_gate.py` | 상태 매핑 |
| Canonical | `ai/app/canonical/canonical_builder.py` | Canonical SQL 생성 |
| Canonical 저장 | `ai/app/canonical/canonical_persistence_cli.py` | transaction persistence |
| Place ID | `ai/app/naver/place_id_linker_cli.py` | UI 검색과 numeric ID 연결 |
| allSearch parser | `ai/app/naver/place_allsearch.py` | UI 응답 parsing |
| Detail | `ai/app/naver/place_detail_enrichment_cli.py` | 대상 선정과 section resume |
| Detail crawler | `ai/app/naver/place_dom_detail_crawler.py` | DOM 수집 |
| Detail 저장 | `ai/app/naver/place_detail_persistence.py` | detail upsert |
| Rate Limit | `ai/app/batch/place_request_limiter.py` | delay/retry/backoff |

## 14. 코드 읽는 순서

1. `e2e_pipeline_orchestrator.py` — 전체 순서와 DB skip
2. `provider_input.py` — manifest와 reference 구조
3. `place_provider.py` — Kakao/NAVER 후보 구조
4. `provider_entity_resolution_cli.py` — 병렬화, prefetch, dedup
5. `qwen_candidate_matcher.py` — choose/validate 책임
6. `verification_quality_gate.py` — DB 상태 매핑
7. `canonical_builder.py` — Canonical 변환
8. `canonical_persistence_cli.py` — transaction 저장
9. `place_id_linker_cli.py` — numeric Place ID 연결
10. `place_allsearch.py` — allSearch parsing
11. `place_detail_enrichment_cli.py` — stale/partial resume
12. `place_dom_detail_crawler.py` — HOME/MENU/HOURS/REVIEW 수집
13. `place_detail_persistence.py` — section별 upsert
14. `place_request_limiter.py` — retry와 pacing

## 15. Spring / Python Batch / FastAPI 관계

| 구성요소 | 현재 역할 |
|---|---|
| Spring Boot | KOMSCO import, 웹 API, 추천 business rule, MySQL persistence |
| Python Batch | Provider, Qwen, Canonical, Place ID, Detail 및 MySQL 직접 저장 |
| FastAPI | 현재 `/health` 중심의 내부 AI 경계 |
| MySQL | Spring과 Python이 공유하는 source of truth |

Python Batch는 Spring API를 거치지 않고 `docker compose exec mysql mysql ...` 방식으로 MySQL에 직접 접근한다.

FastAPI는 현재 Python Batch에서 Entity Resolution 호출에 사용되지 않는다. Qwen은 Python Batch가 `OLLAMA_BASE_URL`의 Ollama HTTP endpoint를 직접 호출한다.

Spring 추천은 Batch 결과 중 현재 코드상 다음을 소비한다.

- `restaurants`
- `recommendation_eligibility`
- `recommendation_ready`
- 영업시간 schedule tables
- ZeroPay 여부
- 카테고리와 평균 가격
- 사용자 preference와 meal history

## 현재 Main Batch

```text
Spring KOMSCO importer
→ restaurants 저장
→ Python DB 대상 선정
→ Kakao/NAVER Local
→ candidate dedup/fusion
→ Qwen choose/validate
→ verification
→ ACCEPT Canonical
→ NAVER Maps UI/allSearch
→ numeric Place ID
→ HOME/MENU/HOURS/REVIEW
→ MySQL detail upsert
→ Spring 추천 query
```

## 현재 사용하지 않는/과거 경로

- 과거 PCMap-only resolver의 독립 실행 경로
- 과거 Local API fallback 결과 파일
- `place_pipeline_cli.py`의 수동 checkpoint/ledger 기반 단독 실행 경로
- `place_resolver_cli.py`의 수동 CSV resolver 경로

단, `place_resolver_cli.py`의 일부 UI 검색 helper는 현재 Place ID linker가 import하므로 파일 전체를 단순 legacy로 보아서는 안 된다.

## 전체 흐름에서 아직 미구현인 부분

- Spring → FastAPI 실제 HTTP AI 연동
- LangGraph 추천 workflow
- Qdrant 검색/embedding 연동
- Batch 결과를 활용한 최종 AI ranking
- 메뉴·리뷰 기반 Spring 추천 ranking
- 사용자 GPS·거리 기반 추천 확대

이번 분석에서는 코드·설정·Flyway·문서만 읽었으며 API, DB write, Qwen, Playwright, Batch, 테스트, 빌드는 실행하지 않았다.
