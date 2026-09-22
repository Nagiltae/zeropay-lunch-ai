# Task: NAVER Place ID Resolver PoC

## Goal

MySQL의 KOMSCO 원천 음식점 중 기존 hard filter를 만족하는 대상을 직접 입력으로 사용해, PCMap 공개 DOM에서 Place ID를 보수적으로 추출하고 사람이 검토할 CSV를 만든다. NAVER Local은 필수 선행 게이트가 아니며, KOMSCO-direct 결과가 `AMBIGUOUS` 또는 `NOT_FOUND`일 때만 별도 reference를 만드는 1회성 fallback으로 사용한다. 애매한 PCMap 후보만 로컬 Qwen3 8B에 후보 index 순위를 위임한다.

## Scope

- `ai/app/naver/place_resolver.py`의 정규화·거리·결정론적 판정
- `ai/app/naver/place_resolver_cli.py`의 PCMap 직접 Playwright 실행과 CSV 출력
- `ai/app/entity_resolution/qwen_candidate_matcher.py`의 mock 가능한 Ollama/Qwen adapter
- AI 단위 테스트

## Out of scope

- 20건을 초과한 실행 또는 전체 데이터 실행
- MySQL/Flyway 변경
- 메뉴·리뷰·영업시간·가격 수집
- Backend NAVER Local Matcher, KOMSCO import, FastAPI 추천 로직 변경
- CAPTCHA·로그인·anti-bot 우회와 비공개 API 사용

## Acceptance criteria

1. 입력은 `source_provider=KOMSCO`, active, 제로페이 제공기관 `I0000002`, KSIC `561`, 계속사업자, 강남구 법정동, 이름·주소·좌표 필수 조건으로 직접 조회한다.
2. 제한 표본은 기존 NAVER MATCHED와 그 외 상태를 가능한 한 균등하게 법정동 round-robin으로 선택한다.
3. 검색은 PCMap `/place/list` 직접 접근만 사용하며 `map.naver.com`/`searchIframe` fallback은 사용하지 않는다.
4. 선택 후보 DOM 내부 `data-nlog-params.place_id`의 HTML entity를 decode하고 numeric ID만 인정한다.
5. deterministic matcher가 애매한 경우에만 Qwen이 candidateIndex를 반환하며 Place ID는 프롬프트에 포함하지 않는다.
6. 선택 후보의 Place ID로 `/restaurant/{id}/home` 상세 페이지를 재검증한다.
7. `RESOLVED`, `AMBIGUOUS`, `NOT_FOUND`, `BLOCKED`, `ERROR`를 구분한다.
8. 결과는 기본적으로 DB에 쓰지 않고 durable CSV로 저장하며 KOMSCO-direct가 아닌 기존 CSV는 resume하지 않는다.
9. 최초 KOMSCO-direct가 `RESOLVED`면 NAVER Local을 호출하지 않고, `AMBIGUOUS`/`NOT_FOUND`이면서 기존 NAVER 상태가 `MATCHED`일 때만 최대 1회 호출한 뒤 보강된 별도 reference로 PCMap Resolver를 단 1회 재실행한다. 기존 MATCHED 근거가 없으면 fallback을 생략한다.
10. NAVER Local fallback은 KOMSCO 원천 필드를 덮어쓰지 않으며, CSV에 최초 상태·fallback 사용/결과·회수 여부·최종 상태를 남긴다.

## Verification

- `poetry run pytest`
- 변경 검증의 실제 실행은 최대 20건으로 제한하며 전체 모집단은 사용자 승인 전 실행하지 않는다.
- `OLLAMA_BASE_URL=http://localhost:11434`, `QWEN_MODEL=qwen3.5:9b`; 사전 준비: `ollama pull qwen3.5:9b`
- CAPTCHA, 접근 차단, HTTP 403/429가 감지되면 즉시 중단한다.
