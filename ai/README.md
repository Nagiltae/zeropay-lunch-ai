# AI 서버

이 서비스는 자연어 의도 분석, 의미 기반 검색, 워크플로 조정, LLM 호출, 추천 설명 생성과 같은 AI 전용 기능을 담당합니다.

애플리케이션 아키텍처에서 이 서비스는 Spring Boot만 호출할 수 있습니다. 프런트엔드에서 직접 호출해서는 안 됩니다.

현재 1단계 범위는 상태 확인 엔드포인트로 제한됩니다. LangGraph, LangChain, 모델 SDK, 벡터 저장소, 관측성 관련 의존성은 해당 기능을 구현할 때만 추가합니다.

## NAVER Place ID Resolver PoC

`app.naver.place_resolver_cli`는 논현동 KOMSCO 원천 음식점만 조회해 Playwright로 공개 PCMap 화면을 읽고 명시적인 Place ID 후보만 판정합니다. NAVER Local API나 저장된 NAVER 매칭을 입력으로 사용하지 않습니다. 기본 실행은 CSV-only이고 결과를 한 건씩 flush하여 `--resume`으로 중단된 배치를 이어갈 수 있습니다.

```bash
cd ai
# preflight + 5건 CSV 검증
poetry run python -m app.naver.place_resolver_cli --limit 5 --dry-run --output build/reports/naver-place-resolver/komsco-local-5.csv

# 전체 CSV 수집(기본적으로 DB 미변경)
poetry run python -m app.naver.place_resolver_cli --output build/reports/naver-place-resolver/komsco-nonhyeon.csv

# 중단된 CSV 재개
poetry run python -m app.naver.place_resolver_cli --output build/reports/naver-place-resolver/komsco-only.csv --resume
```

실행 전 Python/Playwright Chromium/Ollama 모델/MySQL 네트워크를 preflight로 확인합니다. 결과는 처리 즉시 `ai/build/reports/naver-place-resolver/`에 CSV로 저장되며 기본 모드에서는 MySQL을 쓰지 않습니다. CAPTCHA, 403/429 또는 서비스 접근 제한이 감지되면 즉시 중단합니다. 로그인·CAPTCHA·anti-bot 우회와 NAVER 내부 API 사용은 하지 않습니다.

RESOLVED이고 detail validation이 `PASS`인 결과만 검토 후 다음처럼 명시적으로 DB 반영할 수 있습니다. 기존 `restaurant_external_places`의 NAVER row는 `external_place_id`/검증 정보를 update하고, KOMSCO-only 음식점은 NAVER row를 insert합니다. AMBIGUOUS/NOT_FOUND/ERROR/BLOCKED는 쓰지 않습니다.

```bash
cd ai
poetry run python -m app.naver.place_resolver_cli --output build/reports/naver-place-resolver/komsco-only.csv --resume --write-db
```

중단 시 이미 저장된 CSV는 보존되며, 터미널에 표시된 `--resume` 명령으로 재개합니다. CSV의 `final_status`, `place_id`, `reason`, `elapsed_ms`와 종료 summary의 상태별 수치를 검토합니다.
과거 NAVER Local 기반 CSV와 legacy fallback CSV는 새 KOMSCO-only 입력으로 재사용하지 않습니다. 새 결과는 `source_type=KOMSCO_ONLY`입니다.
`--resume --write-db`는 검토된 CSV만 DB에 반영하고 즉시 종료합니다. 새로운 음식점 수집을 함께 실행하지 않으므로 CSV 반영 명령과 수집 명령을 분리할 수 있습니다.

로컬 벡터 저장소는 Qdrant로 결정했으며 Docker Compose에서 `http://qdrant:6333`으로 접근합니다. 아직 검색 기능을 구현하지 않았으므로 Qdrant Python 클라이언트 의존성은 추가하지 않았습니다.

## E2E 배치 관측·재개 계약

`app.batch.e2e_pipeline_orchestrator`는 DB의 KOMSCO 대상에서 fingerprint가 일치하는 VERIFIED를
건너뛰고, Provider/Qwen → Canonical → NAVER Place ID → Detail 순서로 실행합니다.
각 하위 CLI의 진행률은 즉시 stdout에 전달됩니다. 동일 명령 재실행 시 Entity Resolution의
동일 fingerprint REJECT cache, 숫자형 NAVER ID 보호, Detail section 판정은 DB 상태를 사용합니다.

Detail CLI는 `ELIGIBLE + NAVER/MATCHED + 숫자형 Place ID` 중 review summary,
활성 메뉴, 메뉴 가격, 영업시간 **행**의 존재 여부를 각각 확인합니다. 기존 summary만 있고
메뉴·가격·영업시간이 비어 있는 음식점도 재수집 대상입니다. 새 review summary는 HOME과
REVIEW 페이지가 모두 성공했을 때만 저장합니다. 별도 HOME 완료 행이 없으므로 과거 summary로
두 section의 실제 품질을 역추적할 수는 없습니다. 기본적으로 완성되고 fresh한 section은
재수집하지 않고, 불완전하거나 stale인 section만 upsert합니다. 온라인에 메뉴나
가격이 실제로 없으면 계속 부분 완료로 남을 수 있습니다. 영업시간 행의 존재는 구조화된
개점·폐점 시각의 품질을 보장하지 않습니다.

Detail section의 `crawled_at`을 기준으로 `NAVER_DETAIL_STALE_AFTER_SECONDS`(기본
2,592,000초=30일)를 설정할 수 있습니다. `off`/`none`으로 freshness 재수집을 끌 수 있으며,
완료된 전체 section을 명시적으로 다시 수집할 때만 `--force-refresh`를 사용합니다.

Place ID는 numeric `MATCHED`를 기본 skip하고, `UNRESOLVED`는 다음 실행에서 재시도하며,
`AMBIGUOUS`는 자동 재시도하지 않습니다. 검토 후 ambiguous까지 명시적으로 재시도할 때는
`place_id_linker_cli --force-retry`를 사용합니다. 숫자형 Place ID가 이미 있는 mapping은
`--force-retry`에서도 재처리하지 않습니다.

단계별 runtime JSON은 `ai/build/reports/naver-place-pipeline/e2e/`에
`<run-id>-entity_resolution.json`, `<run-id>-place_id.json`, `<run-id>-detail.json`으로 남습니다.
E2E는 동일 run ID를 자식 단계에 전달합니다. JSON에는 처리·성공·실패·skip·retry·BLOCKED,
429 횟수, 경과시간/평균/ETA, 마지막 성공·실패 ID와 중단 사유가 기록됩니다.
`preexisting_skipped`는 이번 실행 전에 DB에서 이미 완성돼 작업 대상에서 제외된 수입니다
(Entity의 VERIFIED, Place ID의 숫자형 MATCHED, Detail의 fresh section 완료).
`reason_counts`에는 `NEW_SOURCE`, `SOURCE_CHANGED`, `RETRY_UNKNOWN`,
`REJECT_CACHE_REUSED`, `UNRESOLVED_RETRY`, `DETAIL_PARTIAL`, `DETAIL_STALE`,
`DETAIL_COMPLETE_SKIPPED` 등의 실제 처리 이유가 stage별로 기록됩니다.

`BATCH_PROGRESS_EVERY` 기본 10건, `BATCH_TRANSIENT_MAX_RETRIES` 기본 0회(최대 2회),
`BATCH_TRANSIENT_RETRY_BACKOFF_SECONDS` 기본 10초(지수 backoff)입니다. 선택적 retry는
Timeout/ConnectionError에만 적용됩니다. 공식 provider 또는 PCMap의
403/429/CAPTCHA/BLOCKED는 **재시도하지 않고 즉시 중단**합니다. 중단 report의
`resume_not_before`는 `NAVER_BLOCK_COOLDOWN_SECONDS` 기본 1800초를 적용한 시각이며,
그 전에는 Entity Resolution·Place ID·Detail 어느 단계도 새 외부 요청을 시작하지 않습니다.
그 후에는 같은 CLI 명령을 재실행해 DB 상태에서 이어갑니다. Ctrl+C 등 정상적인 예외 전파
경로에서는 가능한 범위까지 runtime report를 남기며, 강제 종료(SIGKILL)는 보장하지 않습니다.
Runtime JSON/CSV/manifest는 운영 산출물이므로 Git에 포함하지 않습니다.

Provider 단계는 `PROVIDER_CONCURRENCY` 기본 1(최대 2)로 provider별 worker 수를 제한하고,
`PROVIDER_PREFETCH_SIZE` 기본 2(최대 4)만큼 다음 음식점의 Provider 결과를 준비합니다.
Kakao와 NAVER의 두 query variant는 각 provider worker 내부에서 기존 순서대로 실행되며,
Kakao와 NAVER worker는 서로 병렬입니다. Qwen은 계속 단일 순서로 실행됩니다. Provider
HTTP connection은 provider 인스턴스가 batch 동안 재사용하고 종료 시 닫습니다. Runtime JSON에는
Provider 총 요청·Kakao/NAVER 요청 수, provider latency, prefetch hit/wait가 추가됩니다.

```bash
poetry install
poetry run uvicorn app.main:app --reload --port 8001
poetry run ruff check .
poetry run pytest
```
## Place detail pipeline

로컬에서 KOMSCO 대상의 PCMap resolve와 공개 상세 HTML 파싱을 소규모로 확인할 때:

```bash
poetry run python -m app.naver.place_pipeline_cli --limit 20 --report-only \
  --output build/reports/naver-place-pipeline/pipeline-20.csv
```

`--report-only`가 기본 안전 모드이며 결과는 음식점 단위로 flush됩니다. `--resume`
을 붙이면 같은 CSV의 완료 `restaurant_id`를 건너뜁니다. 검토 후에만
`--write-db`를 명시하며, RESOLVED와 유효한 Place ID만 V13 메뉴/영업시간/리뷰
테이블에 upsert합니다. 전체 대상 실행은 별도 승인 없이는 수행하지 않습니다.

### KOMSCO 100건 batch 실행

전체 모집단을 실행할 때는 먼저 KOMSCO ID manifest를 100건씩 고정하고, audit CSV와 별도 terminal ledger를 함께 사용합니다. `RESOLVED`, `AMBIGUOUS`, `NOT_FOUND`, `PLACE_ID_CONFLICT`는 ledger에서 terminal로 간주해 resume 시 건너뛰며, `ERROR`와 중단된 항목만 재시도합니다.

```bash
# KOMSCO DB read만 수행해 100건 manifest를 생성(네이버 요청 없음)
poetry run python -m app.batch.komsco_batch_manifest_cli --size 100 \
  --output-dir build/reports/naver-place-pipeline/manifests
```

```bash
cd ai
# 고정 manifest 한 batch 실행(실제 DB 반영)
poetry run python -m app.naver.place_pipeline_cli \
  --manifest build/reports/naver-place-pipeline/komsco-batch-0001.manifest \
  --limit 100 --write-db --resume \
  --output build/reports/naver-place-pipeline/komsco-batch-0001.csv \
  --ledger build/reports/naver-place-pipeline/komsco-batch-0001.ledger.csv

# 중단 후 같은 batch 재개
poetry run python -m app.naver.place_pipeline_cli \
  --manifest build/reports/naver-place-pipeline/komsco-batch-0001.manifest \
  --limit 100 --write-db --resume \
  --output build/reports/naver-place-pipeline/komsco-batch-0001.csv \
  --ledger build/reports/naver-place-pipeline/komsco-batch-0001.ledger.csv

# 특정 음식점만 실행
poetry run python -m app.naver.place_pipeline_cli --restaurant-id 4280 \
  --write-db --output build/reports/naver-place-pipeline/restaurant-4280.csv

# ledger 상태만 확인(네트워크/DB 작업 없음)
poetry run python -m app.naver.place_pipeline_cli --status \
  --ledger build/reports/naver-place-pipeline/komsco-batch-0001.ledger.csv

# terminal 결과를 명시적으로 다시 처리
poetry run python -m app.naver.place_pipeline_cli \
  --manifest build/reports/naver-place-pipeline/komsco-batch-0001.manifest \
  --write-db --resume --force-resolve \
  --output build/reports/naver-place-pipeline/komsco-batch-0001-force.csv \
  --ledger build/reports/naver-place-pipeline/komsco-batch-0001-force.ledger.csv
```

기본 pacing은 `NAVER_NAVIGATION_DELAY_SECONDS=2.5`, `NAVER_RESTAURANT_DELAY_SECONDS=5`입니다. 429/403 또는 BLOCKED는 즉시 현재 batch를 종료하며 자동 retry하지 않습니다. checkpoint는 임시 파일 flush 후 atomic replace로 갱신됩니다.
