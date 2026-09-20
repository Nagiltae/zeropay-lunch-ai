# AI 서버

이 서비스는 자연어 의도 분석, 의미 기반 검색, 워크플로 조정, LLM 호출, 추천 설명 생성과 같은 AI 전용 기능을 담당합니다.

애플리케이션 아키텍처에서 이 서비스는 Spring Boot만 호출할 수 있습니다. 프런트엔드에서 직접 호출해서는 안 됩니다.

현재 1단계 범위는 상태 확인 엔드포인트로 제한됩니다. LangGraph, LangChain, 모델 SDK, 벡터 저장소, 관측성 관련 의존성은 해당 기능을 구현할 때만 추가합니다.

## NAVER Place ID Resolver PoC

`app.place_resolver_cli`는 논현동 KOMSCO 원천 음식점만 조회해 Playwright로 공개 PCMap 화면을 읽고 명시적인 Place ID 후보만 판정합니다. NAVER Local API나 저장된 NAVER 매칭을 입력으로 사용하지 않습니다. 기본 실행은 CSV-only이고 결과를 한 건씩 flush하여 `--resume`으로 중단된 배치를 이어갈 수 있습니다.

```bash
cd ai
# preflight + 5건 CSV 검증
poetry run python -m app.place_resolver_cli --limit 5 --dry-run --output build/reports/naver-place-resolver/komsco-local-5.csv

# 전체 CSV 수집(기본적으로 DB 미변경)
poetry run python -m app.place_resolver_cli --output build/reports/naver-place-resolver/komsco-nonhyeon.csv

# 중단된 CSV 재개
poetry run python -m app.place_resolver_cli --output build/reports/naver-place-resolver/komsco-only.csv --resume
```

실행 전 Python/Playwright Chromium/Ollama 모델/MySQL 네트워크를 preflight로 확인합니다. 결과는 처리 즉시 `ai/build/reports/naver-place-resolver/`에 CSV로 저장되며 기본 모드에서는 MySQL을 쓰지 않습니다. CAPTCHA, 403/429 또는 서비스 접근 제한이 감지되면 즉시 중단합니다. 로그인·CAPTCHA·anti-bot 우회와 NAVER 내부 API 사용은 하지 않습니다.

RESOLVED이고 detail validation이 `PASS`인 결과만 검토 후 다음처럼 명시적으로 DB 반영할 수 있습니다. 기존 `restaurant_external_places`의 NAVER row는 `external_place_id`/검증 정보를 update하고, KOMSCO-only 음식점은 NAVER row를 insert합니다. AMBIGUOUS/NOT_FOUND/ERROR/BLOCKED는 쓰지 않습니다.

```bash
cd ai
poetry run python -m app.place_resolver_cli --output build/reports/naver-place-resolver/komsco-only.csv --resume --write-db
```

중단 시 이미 저장된 CSV는 보존되며, 터미널에 표시된 `--resume` 명령으로 재개합니다. CSV의 `final_status`, `place_id`, `reason`, `elapsed_ms`와 종료 summary의 상태별 수치를 검토합니다.
과거 NAVER Local 기반 CSV와 legacy fallback CSV는 새 KOMSCO-only 입력으로 재사용하지 않습니다. 새 결과는 `source_type=KOMSCO_ONLY`입니다.
`--resume --write-db`는 검토된 CSV만 DB에 반영하고 즉시 종료합니다. 새로운 음식점 수집을 함께 실행하지 않으므로 CSV 반영 명령과 수집 명령을 분리할 수 있습니다.

로컬 벡터 저장소는 Qdrant로 결정했으며 Docker Compose에서 `http://qdrant:6333`으로 접근합니다. 아직 검색 기능을 구현하지 않았으므로 Qdrant Python 클라이언트 의존성은 추가하지 않았습니다.

```bash
poetry install
poetry run uvicorn app.main:app --reload --port 8001
poetry run ruff check .
poetry run pytest
```
## Place detail pipeline

로컬에서 KOMSCO 대상의 PCMap resolve와 공개 상세 HTML 파싱을 소규모로 확인할 때:

```bash
poetry run python -m app.place_pipeline_cli --limit 20 --report-only \
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
poetry run python -m app.komsco_batch_manifest_cli --size 100 \
  --output-dir build/reports/naver-place-pipeline/manifests
```

```bash
cd ai
# 고정 manifest 한 batch 실행(실제 DB 반영)
poetry run python -m app.place_pipeline_cli \
  --manifest build/reports/naver-place-pipeline/komsco-batch-0001.manifest \
  --limit 100 --write-db --resume \
  --output build/reports/naver-place-pipeline/komsco-batch-0001.csv \
  --ledger build/reports/naver-place-pipeline/komsco-batch-0001.ledger.csv

# 중단 후 같은 batch 재개
poetry run python -m app.place_pipeline_cli \
  --manifest build/reports/naver-place-pipeline/komsco-batch-0001.manifest \
  --limit 100 --write-db --resume \
  --output build/reports/naver-place-pipeline/komsco-batch-0001.csv \
  --ledger build/reports/naver-place-pipeline/komsco-batch-0001.ledger.csv

# 특정 음식점만 실행
poetry run python -m app.place_pipeline_cli --restaurant-id 4280 \
  --write-db --output build/reports/naver-place-pipeline/restaurant-4280.csv

# ledger 상태만 확인(네트워크/DB 작업 없음)
poetry run python -m app.place_pipeline_cli --status \
  --ledger build/reports/naver-place-pipeline/komsco-batch-0001.ledger.csv

# terminal 결과를 명시적으로 다시 처리
poetry run python -m app.place_pipeline_cli \
  --manifest build/reports/naver-place-pipeline/komsco-batch-0001.manifest \
  --write-db --resume --force-resolve \
  --output build/reports/naver-place-pipeline/komsco-batch-0001-force.csv \
  --ledger build/reports/naver-place-pipeline/komsco-batch-0001-force.ledger.csv
```

기본 pacing은 `NAVER_NAVIGATION_DELAY_SECONDS=2.5`, `NAVER_RESTAURANT_DELAY_SECONDS=5`입니다. 429/403 또는 BLOCKED는 즉시 현재 batch를 종료하며 자동 retry하지 않습니다. checkpoint는 임시 파일 flush 후 atomic replace로 갱신됩니다.
