# AI 워크플로

## When to read
- FastAPI 수정
- LLM prompt / 연동 변경
- Embedding / Qdrant 변경
- LangGraph 워크플로 변경


> **Harness Role:** 현재 임시 분석과 향후 FastAPI·LLM 역할을 구분해 AI 변경 범위를 제한합니다. Agent는 추천 분석, fallback 또는 AI 계약을 수정하기 전에 읽습니다. 이 문서가 없으면 미구현 기능을 구현된 것으로 가정하거나 LLM에 필수 필터를 맡길 수 있습니다. `architecture.md`, `api-contract.md`와 AI·백엔드 테스트에 연결됩니다.

## 목표 흐름

```text
사용자 요청
  -> 의도 분석
  -> 사용자 컨텍스트 조회
  -> 강남구 논현동 음식점 후보 조회
  -> 필수 조건 필터링
  -> 의미 기반 검색
  -> 결정론적 순위 결정
  -> 선택적 제약 조건 완화
  -> 추천 설명 생성
  -> 응답 검증
```

## 책임 분리 원칙

거리, 가격, 영업 여부, 제로페이 사용 가능 여부, 최근 기록, 정확한 필터, 최종 수치 기반 순위 결정은 애플리케이션 코드와 데이터베이스가 담당합니다. LLM은 모호한 자연어를 해석하고 이미 선택된 후보를 바탕으로 설명을 생성합니다.

추천 후보는 항상 강남구 소재 음식점으로 제한합니다. LLM이 강남구 밖의 음식점을 새 후보로 생성하거나 지역 제한을 완화해서는 안 됩니다.

LLM 출력이 프로그램 로직에 사용될 때는 반드시 검증된 구조화 스키마를 사용해야 합니다. 자유 형식의 모델 출력이 정확한 필터나 순위 결정을 직접 제어해서는 안 됩니다.

## 현재 구현 상태

현재 FastAPI에는 상태 확인 엔드포인트만 있습니다. Spring Boot의 `RecommendationContextService`가 사용자 메시지, 강남구 위치, 취향과 최근 72시간 식사 기록을 `IntentAnalysisRequest`로 조립합니다. `AiIntentAnalyzer`는 실제 FastAPI 클라이언트가 없는 동안 `TemporaryIntentAnalyzer`를 사용하며, 향후 클라이언트 오류에도 정책이 허용하면 같은 분석기로 대체합니다.

현재 결정론적 추천은 다음을 강제합니다.

1. 영업 중이고 제로페이가 가능한 음식점만 DB에서 조회
2. 명시적 또는 기본 예산 초과 제외
3. 메시지에서 명시한 카테고리와 비선호 카테고리 적용
4. 최근 72시간 내 먹은 음식점 제외
5. 위치, 예산, 카테고리와 선호 카테고리로 점수 계산
6. Spring Boot가 최종 순위를 확정

알레르기와 매운맛은 계약에 포함되지만 음식점 재료·매운맛 데이터가 아직 없으므로 현재 결정론적 필터에는 사용하지 않습니다. 데이터 없이 안전하다고 추론하거나 LLM에 필터를 위임하지 않습니다.

## FastAPI 연동 정책

- 내부 계약: `POST /internal/v1/intent-analysis`
- 연결 제한 시간: 기본 2초
- 응답 제한 시간: 기본 8초
- 최대 시도 횟수: 기본 1회(자동 재시도 없음)
- fallback: 기본 활성화, 임시 결정론적 분석기로 대체
- 응답 enum과 필드 타입은 Spring Boot에서 재검증

현재 timeout과 최대 시도 설정은 계약과 환경설정으로 준비되어 있으며 실제 HTTP 클라이언트가 구현될 때 적용합니다. fallback 선택 로직과 테스트는 이미 구현되어 있습니다.

Qdrant 클라이언트 연동, 컬렉션 구성, 의미 검색, LangGraph, LLM 제공자와 대체 처리 방식은 구현 예정입니다.

## NAVER Place Resolver PoC

Place ID 검증기는 NAVER Map `allSearch` JSON을 읽어 구조화된 후보를 최대 20개 수집합니다. 이름·주소·카테고리 표현 차이는 Qwen 후보 ranking까지 유지하며 최대 12개를 전달하고 Top-5를 반환합니다. 각 상세 HOME의 실제 evidence는 구조화된 Qwen semantic validator가 `MATCH`/`UNCERTAIN`/`NO_MATCH`로 판단합니다. 개발자 코드에는 JSON/HTTP/Place ID/DB 무결성 guard만 남기며 semantic veto는 적용하지 않습니다. Place ID는 allSearch의 구조화된 필드에서만 가져옵니다.

Resolver 입력은 KOMSCO 원천 음식점뿐이다. `source_provider=KOMSCO`, active, zero-pay, KSIC `561`, 계속사업자, 논현동 법정동 `11680108`, 이름·주소 필수 조건을 적용하며 좌표는 보조 evidence다. `restaurant_external_places`의 historical NAVER row는 신규 resolver 입력이나 fallback으로 사용하지 않는다.

```text
NAVER allSearch JSON
  -> structured candidate extraction
  -> soft evidence ordering
  -> Qwen3 8B candidateIndex
  -> structured candidate place_id
  -> PCMap restaurant detail verification
  -> result (no stored NAVER fallback)
```

이 PoC는 `map.naver.com`과 `searchIframe`을 사용하거나 fallback하지 않습니다. Place ID Resolver의 애매한 후보 순위에만 로컬 Qwen3 8B를 사용할 수 있으며, NAVER Local API를 Place ID pipeline의 fallback으로 재호출하지 않습니다. 로컬 실행은 `OLLAMA_BASE_URL`(기본 `http://localhost:11434`)과 `LOCAL_LLM_MODEL`(기본 `qwen3:8b`)을 사용하며, 모델 준비는 `ollama pull qwen3:8b`입니다.

### KOMSCO-only resolver

신규 resolver는 KOMSCO reference로 allSearch 구조화 후보를 검색하고 Qwen 후보 ranking 후 상세 페이지를 검증합니다. NAVER Local API와 저장된 NAVER fallback은 사용하지 않습니다.

### Local Place Resolver Runbook

1. `cd ai && poetry install && poetry run playwright install chromium`으로 환경을 준비하고, Ollama에서 `ollama pull qwen3:8b`를 실행합니다. CLI preflight가 Python, Chromium, Ollama, MySQL 네트워크와 출력 디렉터리를 확인합니다.
2. 먼저 `cd ai && poetry run python -m app.place_resolver_cli --limit 5 --dry-run --output build/reports/naver-place-resolver/komsco-local-5.csv`으로 5건 CSV-only 검증을 수행합니다.
3. 전체 CSV 수집은 `cd ai && poetry run python -m app.place_resolver_cli --output build/reports/naver-place-resolver/komsco-nonhyeon.csv`로 실행합니다. `--write-db`가 없으면 DB는 변경되지 않습니다.
4. 터미널의 현재/전체, 상태별 누적 수, ETA를 확인합니다. Ctrl+C로 종료해도 결과는 건별 flush됩니다.
5. 중단 후에는 같은 KOMSCO-only CSV에 `--resume`을 붙여 이미 완료된 `restaurant_id`를 건너뛰고 재개합니다. 이전 NAVER Local 모집단 CSV는 재사용하지 않습니다.
6. CSV를 검토한 뒤에만 `cd ai && poetry run python -m app.place_resolver_cli --output build/reports/naver-place-resolver/komsco-only.csv --resume --write-db`를 실행합니다. `RESOLVED` + detail validation `PASS` + numeric Place ID만 `external_place_id`/도메인 URL을 upsert하며, 다른 상태는 DB에 쓰지 않습니다. `--resume --write-db`는 CSV 반영 후 즉시 종료하며 추가 PCMap 수집을 실행하지 않습니다.

과거 Local API 검증 CSV와 legacy 결과는 신규 KOMSCO-only 입력으로 재사용하지 않습니다. report-only CSV는 각 음식점 처리 직후 flush되며, `--resume`은 같은 KOMSCO-only 출력의 완료 항목을 건너뜁니다.
## Place detail pipeline

Place ID가 `RESOLVED`된 뒤 `PlaceDomDetailCrawler`가 Resolver에서 재사용한
Playwright page에서 HOME DOM을 읽고, 같은 context로 `/menu/list`와
`/review/visitor`를 방문합니다. 수집 기준은 렌더링된 DOM의 semantic/data-nlog
contract이며 Apollo state와 NAVER 내부 API는 사용하지 않습니다. 전체 리뷰 pagination은
하지 않고 초기 렌더링 대표 리뷰만 수집합니다.

`PlaceDetail`의 수집 상태(`SUCCESS`, `PARTIAL`, `FAILED`)는 Place ID resolve
상태와 분리됩니다. 기본 `place_pipeline_cli.py` 실행은 CSV-only이고,
`--write-db`일 때만 V13 테이블에 idempotent upsert합니다. KOMSCO와 기존 NAVER
deterministic Match는 이 파이프라인에서 덮어쓰지 않습니다. `--resume`은 완료된
행을 건너뛰며, `--retry-failed`는 `PARTIAL`/`FAILED` checkpoint만 재처리합니다.

상세 수집 상태(`SUCCESS`, `PARTIAL`, `FAILED`)는 Place ID resolve 상태와
분리됩니다. `place_pipeline_cli.py`는 기본 CSV-only이며 `--write-db`일 때만
V13 테이블에 idempotent upsert합니다. 생성 CSS class는 parser 계약으로 사용하지 않습니다.

제공된 실제 contract는 `data-nlog-area` 기반으로 유지합니다. 메뉴는
`plc_qmn.tpiratesmore`에서 `/menu/list`로 이동한 뒤 `plc_bmv.menu` 카드를
읽고, 영업시간은 `plc_btp.bzhour`를 펼칩니다. 리뷰는 `plc_rrr.rvmore`,
`plc_rrv.rrvtab`, `plc_rrv.chartmore`, `plc_rrv.menufilter`,
`plc_rrv.filter`, `#_review_list`, `rvshowmore`를 우선 사용합니다.

검증된 Place ID는 `verified-place-ids-komsco-only.csv` checkpoint에 저장하며 다음 실행에서
재검색하지 않고 상세 수집에 재사용합니다. `--force-resolve`가 명시된 경우에만
재검색합니다. Checkpoint와 DB 저장은 독립적이며 report-only 실행도 checkpoint를
생성할 수 있습니다.
