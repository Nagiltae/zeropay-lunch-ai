# ZeroPay Lunch AI Batch 최종 READ-ONLY Audit

## 1. Batch 한눈에 보기

현재 Batch는 Spring Boot 웹 추천 경로와 분리된 Python CLI pipeline이다.

```text
KOMSCO source in MySQL
  → e2e_pipeline_orchestrator.py
  → Kakao/NAVER Local API
  → candidate dedup
  → Qwen choose/validate
  → ACCEPT/REJECT/UNKNOWN
  → Canonical/verification persistence
  → Playwright NAVER Maps UI/allSearch
  → numeric Place ID
  → HOME/MENU/HOURS/REVIEW DOM
  → MySQL detail tables
```

Spring Boot는 현재 Kakao/NAVER/Qwen Batch를 호출하지 않는다. 웹 추천은 React → Spring Boot → MySQL 경로이고, Batch는 `ai/` Python CLI가 별도로 수행한다.

## 2. E2E 실행 흐름

`ai/app/e2e_pipeline_orchestrator.py`의 실제 순서는 다음과 같다.

1. MySQL에서 KOMSCO 대상 조회
2. verification 상태와 source fingerprint 비교
3. 미처리 대상 manifest 생성
4. `provider_entity_resolution_cli` 실행
5. `canonical_persistence_cli` 실행
6. `place_id_linker_cli` 실행
7. `place_detail_enrichment_cli` 실행
8. console 요약과 각 stage runtime report 저장

주요 child command:

```bash
poetry run python -u -m app.provider_entity_resolution_cli \
  --manifest <manifest> --output <csv> \
  --db-reject-cache --preexisting-skipped <count>

poetry run python -u -m app.canonical_persistence_cli --csv <csv>
poetry run python -u -m app.place_id_linker_cli --limit <limit>
poetry run python -u -m app.place_detail_enrichment_cli --limit <limit>
```

각 child process는 unbuffered로 실행되고 stdout/stderr가 실시간 전달된다. Stage 실패 시 다음 단계로 진행하지 않으며 이미 저장된 상태는 유지된다.

## 3. 상태 모델

### Verification

`restaurant_naver_verifications`에는 `VERIFIED`, `REJECTED`, `ERROR`, `UNRESOLVED`, `BLOCKED`가 사용된다.

### Semantic 결과

Provider/Qwen CSV에는 `ACCEPT`, `REJECT`, `UNKNOWN`이 사용된다.

```text
ACCEPT  → VERIFIED + ELIGIBLE
REJECT  → REJECTED + INELIGIBLE
UNKNOWN → ERROR + UNKNOWN
```

Semantic `UNKNOWN`이 DB에서는 `ERROR`로 저장되는 점은 상태 이름이 혼합된 부분이다.

### External Place

`restaurant_external_places.match_status`에는 `MATCHED`, `UNRESOLVED`, `AMBIGUOUS`가 사용된다. `NAVER_LOCAL + MATCHED + external_place_id NULL`은 공식 Local evidence는 확인됐지만 numeric Place ID가 아직 없는 정상 intermediate 상태다.

### Detail

`COMPLETE`, `PARTIAL`, `STALE`, `pending`은 대부분 DB enum이 아니라 실행 시 `crawled_at`, menu, price, hours, review summary를 이용해 계산되는 상태다.

## 4. Incremental / Resume

| 경우 | 다음 실행 동작 |
|---|---|
| 신규 음식점 | verification부터 실행 |
| ACCEPT + fingerprint 동일 | verification skip/reuse, 이후 상태 확인 |
| REJECT + fingerprint 동일 | Reject Cache로 Provider/Qwen 0회 |
| fingerprint 변경 | `SOURCE_CHANGED`로 재검증 |
| UNKNOWN | 재검증 |
| numeric Place ID 있음 | Place ID 기본 skip |
| UNRESOLVED | 재시도 가능 |
| AMBIGUOUS | 기본 재시도 제외, `--force-retry` 가능 |
| Detail complete + fresh | Detail skip |
| Detail partial | 부족한 section만 수집 |
| Detail stale | 오래된 section 재수집 |
| Ctrl+C | 처리된 DB 상태와 runtime report 보존 시도 |
| HTTP 429 | 즉시 중단, cooldown 후 재실행 |

REJECT는 `_pending()`에서 다시 선택될 수 있지만, 동일 fingerprint면 DB Reject Cache가 Provider와 Qwen 호출을 차단한다.

## 5. Provider

### Kakao

파일:

```text
ai/app/place_provider.py
```

클래스:

```text
KakaoPlaceSearchProvider
```

endpoint:

```text
https://dapi.kakao.com/v2/local/search/keyword.json
```

인증은 `Authorization: KakaoAK {KAKAO_REST_API_KEY}`다.

### NAVER Local

파일:

```text
ai/app/place_provider.py
```

클래스:

```text
NaverPlaceSearchProvider
```

endpoint:

```text
https://naverapihub.apigw.ntruss.com/search/v1/local
```

인증은 `X-NCP-APIGW-API-KEY-ID`, `X-NCP-APIGW-API-KEY`다.

두 Provider 모두 `ProviderHttpClient`를 사용해 stdlib HTTPS connection을 재사용한다. Query variant는 음식점명과 `논현동 음식점명`이다. Kakao와 NAVER는 bounded thread pool로 병렬 실행되며 Qwen inference는 단일 흐름이다.

Prefetch는 다음 음식점 Provider 결과를 제한된 queue에 미리 준비한다. 429 발생 시 이미 시작된 소수의 future가 완료될 수는 있으나 queue와 concurrency는 제한되어 있다.

## 6. Candidate Dedup

`provider_entity_resolution_cli.py`의 `_candidate_key()`와 `_merge_with_stats()`가 담당한다.

기준:

1. provider + external ID
2. provider + detail URL
3. provider + 정규화된 name/address/road address/category/coordinates

Provider를 key에 포함하므로 Kakao와 NAVER provenance를 합치지 않는다. semantic 유사도로 후보를 제거하지 않고 첫 등장 순서를 유지한다.

## 7. Qwen Entity Resolution

```text
evaluate_reference()
  → matcher.choose()
  → ranking indices
  → matcher.validate()
  → provider별 ACCEPT 수집
  → ACCEPT/REJECT/UNKNOWN
```

- 후보 없음: Qwen 0회, `UNKNOWN/NO_CANDIDATE`
- 후보 있음: `choose` 최소 1회
- `validate` 최소 1회, 후보 수와 결과에 따라 여러 회
- structured output 오류: 논리 호출 내부 제한 retry
- Qwen 오류: 최종적으로 UNKNOWN

`choose`는 후보 순위를 정하고, `validate`는 entity match, business type, location scope, final decision, evidence, reason을 판단한다.

현재 코드가 Qwen semantic 결과를 별도 name/address similarity rule로 뒤집는 deterministic veto 경로는 확인되지 않았다. 코드는 후보 수집·dedup·JSON validation·기술 안전장치만 담당한다.

Ollama는 `OllamaClient`에서 HTTP connection을 재사용하며 Qwen inference는 병렬화하지 않는다.

## 8. Verification / Canonical

`canonical_persistence_cli.py`는 `ACCEPT` row만 Canonical 생성 대상으로 처리한다.

저장 정보:

- verification status
- reason
- model name
- source fingerprint
- recommendation eligibility
- attempt timestamps
- `canonical_restaurants`
- accepted `restaurant_external_places`

Canonical과 provider mapping은 upsert와 unique key를 사용한다. REJECT/UNKNOWN은 canonical을 새로 생성하지 않는다.

주의할 점은 `canonical_persistence_cli.py`의 `_execute_sql()`이 전체 canonical/mapping SQL을 명시적인 `START TRANSACTION ... COMMIT`으로 감싸지 않는다는 것이다. 중간 실패 시 일부 SQL만 반영될 가능성이 있으며, 재실행 upsert로 복구될 수 있지만 원자성은 부족하다.

Source 변경 후 REJECT/UNKNOWN이 되더라도 기존 canonical row를 삭제하지는 않는다. 대신 recommendation eligibility가 `INELIGIBLE` 또는 `UNKNOWN`으로 바뀌어 Spring 추천 query에는 노출되지 않는다.

## 9. NAVER Place ID

```text
Canonical + NAVER_LOCAL evidence
  → Playwright NAVER Maps UI
  → visible search input
  → UI-generated /api/search/allSearch capture
  → parse_allsearch_candidates()
  → numeric ID
  → is_exact_match()
  → provider='NAVER' mapping 저장
```

현재 `/api/search/allSearch`를 직접 요청하거나 replay하지 않는다. `place_allsearch.py`는 JSON의 명시적인 `placeId`, `businessId`, `sid`, `id` 등 숫자 field만 읽는다.

이미 numeric `external_place_id`가 있으면 기본 대상에서 제외된다. `--force-retry`도 numeric MATCHED 보호 조건을 제거하지 않는다.

## 10. Playwright Lifecycle

Place ID와 Detail 모두 다음 구조를 사용한다.

```text
batch 시작
  → browser 1개
  → context 1개
  → page 1개
  → 여러 restaurant 재사용
  → batch 종료 close
```

browser/context/page closed 또는 connection closed일 때만 recovery한다. 403/429/CAPTCHA/BLOCKED를 browser restart로 우회하지 않는다.

CLI의 `finally`에서 `session.close()`를 호출한다. 다만 orchestrator 차원의 명시적인 SIGINT child termination은 부족하고, terminal signal 전달과 child finally에 의존한다.

## 11. Detail Enrichment

대상 조건:

```text
provider = 'NAVER'
match_status = 'MATCHED'
external_place_id = numeric
recommendation_eligibility = 'ELIGIBLE'
```

현재 구형의 `review summary 존재 = 전체 완료` 판정은 제거되어 있다.

section별로 다음을 확인한다.

- Review: summary 존재 및 `crawled_at`
- Menu: active menu 및 유효한 가격
- Business Hours: hour row 및 `crawled_at`

menu/price/hours/review가 없거나 stale이면 해당 section을 재수집한다. `--force-refresh`는 fresh row도 재수집한다.

HOME 실패 시 persistence를 생략하고 기존 정상 데이터를 보호한다. Detail persistence는 `INSERT ... ON DUPLICATE KEY UPDATE`와 transaction을 사용하며 NULL price로 기존 가격을 덮어쓰지 않는다.

다만 최신 crawl에서 사라진 menu/hour/keyword row를 적극적으로 inactive/delete하는 구조는 제한적이어서 오래된 detail row가 남을 가능성은 있다.

## 12. 403/429/Retry

| 오류 | Retry | 중단 | 다음 실행 |
|---|---:|---:|---|
| 429 | 아니오 | 즉시 중단 | cooldown 후 resume |
| 403 | 아니오 | 즉시 중단 | cooldown 후 resume |
| CAPTCHA/BLOCKED | 아니오 | 즉시 중단 | cooldown 후 resume |
| timeout | 제한 retry | 한도 초과 시 실패 | resume 가능 |
| connection error | 제한 retry | 한도 초과 시 실패 | resume 가능 |
| browser closed | lifecycle recovery | recovery 실패 시 중단 | resume 가능 |
| Qwen JSON 오류 | 제한 retry | UNKNOWN 처리 | 재검증 |

`TransientRetryPolicy` 기본 max retry는 0, 코드상 최대 2이며 backoff 기본값은 10초다. 무한 retry 경로는 확인되지 않았다.

## 13. Runtime Report

`batch_progress.py`는 다음을 저장한다.

- run ID
- stage
- 시작/종료 시각
- target/processed/success/failed/skipped
- retry/blocked/HTTP 429
- provider 요청 수와 latency
- prefetch hit/wait
- Qwen calls/choose/validate/latency
- candidate dedup 전후 수
- browser starts/restarts/page recreates
- elapsed/평균/ETA
- processing reason
- interruption reason
- cooldown 시각
- 마지막 성공/실패 restaurant ID

stage별 JSON report는 충분한 운영 정보를 제공한다. 다만 orchestrator 전체를 하나의 통합 JSON으로 저장하지 않고 console summary와 stage report가 분리되어 있다.

## 14. DB Persistence

Python Batch는 Spring Repository를 사용하지 않는다.

```text
subprocess.run()
  → docker compose exec -T mysql
  → mysql CLI
  → 직접 SQL
```

주요 접근:

- Provider CLI: Reject Cache SELECT
- Canonical CLI: canonical/mapping/verification write
- Place ID linker: mapping SELECT/UPSERT
- Detail persistence: detail transaction/upsert

Detail/verification persistence에는 transaction이 있으나 canonical persistence 전체에는 명시적 transaction wrapper가 없다.

Python SQL과 Spring JPA가 같은 Flyway schema를 공유하므로 다음 결합을 주의해야 한다.

- status enum 차이
- provider 값 차이
- nullable contract
- unique key 가정
- Python SQL의 compile-time schema 검증 부재

## 15. Code Cleanup 품질

현재 active source에서 과거 Apollo runtime path와 direct allSearch replay path는 확인되지 않았다. 현재 Place ID/Detail 경로는 `place_id_linker_cli.py`, `place_resolver_cli.py`, `place_allsearch.py`, `playwright_lifecycle.py`, `place_dom_detail_crawler.py`, `place_detail_enrichment_cli.py`, `place_detail_persistence.py`다.

남은 중복/결합:

- 여러 CLI의 `docker compose exec mysql` helper 중복
- CLI별 block detection과 failure handling 중복
- `e2e_pipeline_orchestrator.py`의 대상 선별·subprocess·집계 책임 혼합
- `place_detail_enrichment_cli.py`의 selection·crawler·retry·persistence 책임 혼합

현재 active import 기준으로 명백한 Apollo 코드나 old direct replay가 실행 경로에 남아 있다고 판단할 근거는 없다. Dynamic/manual CLI 사용 여부는 코드 검색만으로 완전히 확정할 수 없다.

## 16. 모듈 책임

| 모듈 | 책임 |
|---|---|
| `e2e_pipeline_orchestrator.py` | stage 순서·대상 선별·child 실행 |
| `batch_progress.py` | progress·runtime report |
| `place_provider.py` | Kakao/NAVER HTTP·candidate parsing |
| `provider_entity_resolution_cli.py` | fusion·prefetch·dedup·Qwen orchestration |
| `qwen_candidate_matcher.py` | Ollama HTTP·prompt·structured output |
| `verification_quality_gate.py` | fingerprint·결과 mapping |
| `canonical_builder.py` | canonical/mapping SQL 생성 |
| `canonical_persistence_cli.py` | canonical·verification persistence |
| `place_id_linker_cli.py` | numeric ID selection/linking |
| `playwright_lifecycle.py` | browser/context/page lifecycle |
| `place_dom_detail_crawler.py` | DOM detail parsing |
| `place_detail_enrichment_cli.py` | detail selection·freshness·crawl |
| `place_detail_persistence.py` | detail SQL transaction/upsert |
| `place_request_limiter.py` | delay·transient retry |

현재 가장 책임이 많은 파일은 orchestrator, detail CLI, canonical persistence CLI다.

## 17. Config / ENV

| 설정 | 기본값 | 역할 |
|---|---:|---|
| `QWEN_MODEL` | `LOCAL_LLM_MODEL` 또는 `qwen3.5:9b` | Qwen 모델 |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama 주소 |
| `KAKAO_REST_API_KEY` | 빈 값 | Kakao 인증 |
| `NAVER_CLIENT_ID` | 빈 값 | NAVER 인증 |
| `NAVER_CLIENT_SECRET` | 빈 값 | NAVER 인증 |
| `PROVIDER_CONCURRENCY` | 1, 최대 2 | Provider worker |
| `PROVIDER_PREFETCH_SIZE` | 2, 최대 4 | prefetch 크기 |
| `BATCH_PROGRESS_EVERY` | 10 | summary 주기 |
| `BATCH_TRANSIENT_MAX_RETRIES` | 0, 최대 2 | 제한 retry |
| `BATCH_TRANSIENT_RETRY_BACKOFF_SECONDS` | 10 | backoff |
| `NAVER_BLOCK_COOLDOWN_SECONDS` | 1800 | BLOCKED cooldown |
| `NAVER_NAVIGATION_DELAY_SECONDS` | 2.5 | navigation delay |
| `NAVER_RESTAURANT_DELAY_SECONDS` | linker 3, detail 5 | 음식점 간 delay |
| `NAVER_DETAIL_STALE_AFTER_SECONDS` | 2592000 | detail freshness |

코드와 `.env.example`의 주요 기본값은 대체로 일치한다. Provider concurrency/prefetch는 환경변수 외에 코드상 최대값도 적용한다.

## 18. 한글 주석 품질

핵심 주석은 단순 코드 번역이 아니라 다음을 설명한다.

- NAVER Local과 numeric Place ID가 별도인 이유
- Qwen semantic 판단과 코드 안전장치의 경계
- 429를 우회하지 않는 이유
- Detail section과 verification fingerprint를 독립적으로 유지하는 이유
- Playwright가 내부 state가 아니라 DOM contract를 읽는 이유
- DB 상태를 새 enum으로 늘리지 않고 runtime reason으로 기록하는 이유

현재 주석은 핵심 흐름과 안전 경계 중심이며 모든 줄에 과도하게 작성된 형태는 아니다.

## 19. Harness / 전체 Batch 실행 방법

관련 명령:

- `check-ai.sh`: Poetry/import/pytest
- `check-integration.sh`: Docker/MySQL/Flyway/health/auth/SSE/meal contract
- `check-all.sh`: Format/Lint/Frontend/Backend/AI/Integration
- E2E orchestrator: 실제 음식점 Batch

전체 Batch 실행 형태:

```bash
poetry run python -u -m app.e2e_pipeline_orchestrator --limit 513
```

필요 조건:

- Docker Compose와 MySQL
- Flyway schema
- KOMSCO source rows
- Poetry environment
- Kakao API key
- NAVER Client ID/Secret
- Ollama와 Qwen model
- Playwright Chromium
- cooldown 종료
- 기존 DB 상태 확인

이 명령의 Step 1은 KOMSCO API를 호출하지 않고 MySQL의 KOMSCO source rows를 SELECT한다. KOMSCO import/scheduler는 별도 Spring 경로다.

## 20. 전체 Batch 예상 동작

`--limit 513` 실행 시:

1. 조건에 맞는 전체 source population을 조회한다.
2. VERIFIED + fingerprint 동일 row를 skip count로 분리한다.
3. 나머지 pending을 최대 513건 manifest로 만든다.
4. 신규·변경·UNKNOWN만 Provider/Qwen 대상이 된다.
5. 동일 REJECT fingerprint는 API/Qwen을 호출하지 않는다.
6. ACCEPT만 Canonical을 생성·갱신한다.
7. Place ID 단계는 DB 전체에서 numeric ID가 없는 eligible row를 조회한다.
8. 이미 numeric MATCHED인 row는 skip한다.
9. Detail 단계는 numeric ID + ELIGIBLE 중 partial/stale만 처리한다.
10. fresh complete detail은 skip한다.

따라서 513건 전체에 대해 매번 Provider/Qwen/Playwright/Detail을 모두 다시 실행하는 구조는 아니다. 다만 Place ID와 Detail stage는 이번 verification target 외에 기존 pending 대상도 함께 조회할 수 있다.

## 21. Batch 실행 전 위험도

### A. 반드시 검토·수정 권장

1. **Canonical persistence transaction 부족**

canonical insert와 provider mapping 사이의 실패가 부분 persistence를 남길 수 있다. 재실행 upsert로 복구할 수 있지만 대량 Batch 원자성이 부족하다.

2. **UNKNOWN과 ERROR 상태명 혼합**

semantic UNKNOWN이 DB verification에서는 ERROR로 저장되어 운영자가 기술 오류와 의미 불확실을 혼동할 수 있다.

### B. Batch 실행은 가능하지만 이후 수정 권장

- orchestrator의 명시적 Ctrl+C child cancellation 부족
- 429 직후 이미 시작된 prefetch future
- 최신 crawl에서 사라진 detail row 정리 부족
- stage별 report는 있으나 통합 E2E JSON 부족
- Python SQL command/helper 중복
- Step 2 verification 대상과 Step 4/5 전체 pending 대상의 correlation 부족

### C. 현재 유지해도 되는 항목

- bounded Provider concurrency/prefetch
- Qwen 단일 흐름
- numeric Place ID 보호
- direct allSearch replay 금지
- semantic deterministic veto 부재
- Reject Cache
- section별 Detail resume
- 403/429/CAPTCHA 즉시 중단
- Playwright lifecycle reuse/recovery
- Flyway append-only

## 22. Codex 개선 의견

효과가 큰 순서:

1. Canonical SQL transaction 보강 — Batch 전 필수에 가까움
2. UNKNOWN/ERROR 상태 계약 명확화 — Batch 전 또는 직후
3. orchestrator SIGINT와 child cancellation 명시화 — Batch 후
4. BLOCKED 발생 시 prefetch future 취소 정책 강화 — Batch 후
5. Detail에서 사라진 row의 inactive/freshness 정책 정의 — Batch 후
6. stage report를 통합 E2E report로 연결 — Batch 후
7. Python MySQL command helper 공통화 — Batch 후
8. Provider 요청 variant/in-flight 관측성 강화 — Batch 후
9. Step별 대상 correlation reason 강화 — Batch 후

이번 단계에서 Qwen 병렬화, Playwright concurrency, 모델 변경, Prompt 실험, RAG/Qdrant/LangGraph 추가는 필요하지 않다.

## 23. 포트폴리오/면접 포인트

실제 설명 가치가 높은 부분:

- Multi-provider retrieval
- Provider I/O 병렬화와 bounded prefetch
- Structured Output 기반 Qwen Entity Resolution
- semantic 판단과 deterministic safety guard 분리
- source fingerprint와 Reject Cache
- ACCEPT/REJECT/UNKNOWN quality gate
- Canonical entity 통합
- NAVER_LOCAL과 numeric Place ID 분리
- UI-generated allSearch capture
- numeric ID 보호
- section별 Detail resume
- idempotent upsert
- 403/429/CAPTCHA 안전 중단
- cooldown 기반 resume
- Playwright lifecycle reuse/recovery
- runtime progress/report

현재 웹 요청에서 Qwen·FastAPI·Qdrant가 사용된다고 설명하면 안 된다.

## 24. 사용자 직접 리뷰 파일

1. `AGENTS.md`
2. `ai/app/e2e_pipeline_orchestrator.py`
3. `ai/app/provider_entity_resolution_cli.py`
4. `ai/app/place_provider.py`
5. `ai/app/qwen_candidate_matcher.py`
6. `ai/app/verification_quality_gate.py`
7. `ai/app/canonical_builder.py`
8. `ai/app/canonical_persistence_cli.py`
9. `ai/app/place_id_linker_cli.py`
10. `ai/app/place_resolver_cli.py`
11. `ai/app/place_allsearch.py`
12. `ai/app/playwright_lifecycle.py`
13. `ai/app/place_detail_enrichment_cli.py`
14. `ai/app/place_detail_persistence.py`
15. `ai/app/batch_progress.py`

## 25. 최종 판단

현재 Batch 구조는 전체 검증을 수행할 수 있는 형태이며, 다음 기능은 코드상 보호되고 있다.

- fingerprint 기반 resume
- 동일 REJECT cache skip
- ACCEPT-only Canonical
- numeric Place ID 보호
- direct allSearch replay 금지
- section별 Detail resume
- fresh Detail skip
- 403/429/CAPTCHA 안전 중단
- Playwright lifecycle reuse
- Qwen semantic 결과의 deterministic veto 부재

다만 전체 Batch 전에는 다음 두 항목을 반드시 확인하는 것이 바람직하다.

1. Canonical persistence 전체 transaction 보강 여부
2. Semantic UNKNOWN과 DB ERROR 상태 계약 확정

따라서 최종 판정은 **조건부 NOT READY**다. 위 두 항목을 허용할지 또는 보완한 뒤 전체 Batch를 실행하는 것이 안전하다.

## READ-ONLY 확인

이번 감사에서 코드와 설정을 읽고 검색만 수행했다.

- 코드 변경 0개
- 파일 생성 0개
- 파일 삭제 0개
- DB 변경 0건
- API 호출 0회
- Ollama/Qwen 호출 0회
- Playwright 실행 0회
- Batch 실행 0회
- 테스트 실행 0회
- build 실행 0회
- commit/push 0회
