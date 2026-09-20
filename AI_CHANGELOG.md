# AI Agent Work History

## [2026-09-20] KOMSCO-only PCMap resolver 정리
- Place ID Resolver 입력을 KOMSCO reference로 단일화하고 stored NAVER MATCHED fallback 및 legacy checkpoint 자동 사용을 제거
- 좌표가 없는 KOMSCO row도 name/address 기반 PCMap 검색 대상에 포함
- 신규 기본 checkpoint를 `verified-place-ids-komsco-only.csv`로 통일하고 Local API credential 의존성을 최종 pipeline에서 제거
- PCMap DOM/Detail 흐름과 rate limit 정책은 유지하고 관련 테스트·문서를 갱신

## [2026-09-20] KOMSCO 초기 cleanup 경로 및 주간 동기화
- KOMSCO source 전용 1회성 cleanup/dry-run service를 추가하고 사용자 meal/recommendation 참조 restaurant는 보호
- FK child를 고려한 transaction 삭제 순서를 정의했으며 실제 cleanup/import는 실행하지 않음
- 명시적 `APP_KOMSCO_CLEANUP_ENABLED=true` one-shot runner를 추가하고 `--execute` 없이는 dry-run만 수행
- 전체 fetch 성공 후 논현동(11680108) scope에서 API에 사라진 merchant를 삭제하지 않고 `active=false`로 stale 처리
- 기본 KOMSCO scheduler를 Asia/Seoul 기준 매주 일요일 03:00으로 변경
- weekly sync는 cleanup 없이 기존 upsert/deactivate 동작을 유지

## [2026-09-20] 논현동 고정 위치 서비스 계약
- Frontend 위치 선택 UI와 localStorage 상태를 제거하고 대화 생성 요청을 빈 payload로 변경
- Spring 추천 후보를 `legal_dong_code=11680108`로 제한하고 역·반경 hard filter 및 런타임 의존성을 제거
- 기존 conversations 위치 컬럼·좌표·station historical 데이터는 schema 변경 없이 보존
- 신규 대화 문구와 API 문서를 강남구 논현동 고정 범위로 갱신

## [2026-09-20] KOMSCO 논현동 단일 모집단 및 NAVER Local 제거
- KOMSCO API 요청/필터를 법정동 `11680108`(논현동), 업종 `561`, 계속사업자로 제한하고 제공기관 코드는 필터에서 제외
- 신규 Resolver는 KOMSCO reference만 사용하며 stored NAVER MATCHED fallback과 NAVER Local API 의존성을 제거
- NAVER Local 전용 백엔드 코드·설정은 제거했지만 historical DB/report/checkpoint는 보존
- Frontend 위치 선택과 Spring 거리 계약은 이번 단계에서 유지

## [2026-09-20] KOMSCO 조회 법정동 범위 제한
- 원천 API 요청과 응답 필터 모두 법정동 코드 `11680108`(논현동)만 사용하도록 제한
- 기존 제공기관/업종/상태 필터 정책 중 제공기관 제거 상태 유지
- 백엔드 검증 통과

## [2026-09-20] KOMSCO API 제공기관 query 조건 제거
- KOMSCO 원천 API 요청에서 `cond[pvsn_inst_cd::EQ]=I0000002` 파라미터를 제거하고 읍면동 코드 조회만 유지
- 후처리 제공기관 필터와 기존 저장 데이터는 변경하지 않음
- 백엔드 검증 및 `git diff --check` 통과

## [2026-09-20] KOMSCO 100건 batch 오류 격리 및 resume
- **4375**: HOME 주소 locator `TimeoutError`를 candidate-level `LOCATOR_TIMEOUT`으로 audit하고 Top-K 다음 후보 검증을 계속하도록 변경; 단건 재검증 결과 `AMBIGUOUS`(rank 1 timeout, rank 2~3 address mismatch)
- **7422**: Place ID `36398774`가 기존 7316에 매핑된 충돌을 persistence 전에 감지; 기존 mapping을 덮어쓰지 않고 7422 checkpoint/상세 저장을 추가하지 않음
- **오류 정책**: DOM timeout/parse failure는 restaurant 결과로 기록하고 continue, 429/403·BLOCKED는 stop, 매핑 충돌은 persistence ERROR로 기록
- **resume**: 100건 manifest 최종 100건 처리 완료(RESOLVED 57 / AMBIGUOUS 19 / NOT_FOUND 24); 전체 KOMSCO 모집단은 실행하지 않음
- **검증**: `./scripts/check-ai.sh` 50 tests, `./scripts/check-backend.sh`, `git diff --check` 통과
- **checkpoint**: 충돌 없는 신규 RESOLVED 56건만 atomic 반영; 총 125 rows/restaurant_id unique 125/place_id unique 125. 7422는 제외

## [2026-09-20] KOMSCO 신규 100건 batch 실행 제어 검증
- **manifest**: checkpoint·기존 보고서 대상과 겹치지 않는 KOMSCO ID 100건을 `ai/build/reports/naver-place-pipeline/komsco-batch-100-20260920.manifest`에 고정
- **실행**: 75건 저장 후 프로세스가 중단되어 7422 단건과 남은 일부를 이어서 실행; 누적 83건(RESOLVED 49 / AMBIGUOUS 14 / NOT_FOUND 20), HTTP 429/403은 관찰되지 않음
- **안전**: 명시적 transaction rollback, 2.5초 navigation·5초 restaurant pacing, DB write는 처리된 RESOLVED에만 수행; 전체 KOMSCO 모집단은 실행하지 않음
- **중단 원인**: 남은 항목 처리 중 Resolver 상세 주소 locator `TimeoutError`가 발생해 자동 우회하지 않고 중단; 미처리 17건은 재실행하지 않음
- **품질**: 처리된 RESOLVED DB에서 메뉴명/설명 길이 초과와 가격 파싱 실패 0, review keyword 중복 및 Place ID 다중 매핑 0

## [2026-09-20] Batch 50 checkpoint 반영 및 5608 메뉴 parser 진단
- **5608 원인**: `a[data-nlog-area="plc_bmv.menu"]` 카드의 전체 `inner_text`를 이름으로 저장해 상품 설명/스펙이 name에 섞였고 `varchar(255)`를 초과
- **parser 보강**: 카드 줄 구조에서 첫 비가격 줄을 name, 이후 줄을 description, 가격 줄을 price로 분리
- **checkpoint**: Batch 50 RESOLVED 29건을 추가해 69개 unique mapping으로 반영
- **transaction**: 기존 transaction 경계와 255자 schema guard를 유지; 전체 KOMSCO 실행은 하지 않음

## [2026-09-20] 5608 persistence transaction 및 Batch 50 resume
- **원인**: `restaurant_menus.name`이 V13의 `varchar(255)`를 초과해 MySQL `ERROR 1406` 발생
- **수정**: detail persistence 전체를 `START TRANSACTION`/`COMMIT` 경계로 묶고 실패 시 연결 종료 rollback; DB 오류 메시지를 예외에 포함; menu name을 schema 길이(255)에 맞게 제한
- **결과**: 5608 checkpoint Place ID 재사용 재실행 성공; 기존 미처리 9건 resume 완료
- **집계**: 고정 50건 기준 RESOLVED 29 / AMBIGUOUS 11 / NOT_FOUND 10 / BLOCKED 0 / ERROR 0; 신규 checkpoint는 아직 반영하지 않음

## [2026-09-20] KOMSCO 50건 batch 제어 검증
- **checkpoint**: 직전 live10 RESOLVED 6건을 checkpoint에 추가해 총 40개 unique mapping으로 확인
- **batch control**: `--include-unmatched`와 반복 `--restaurant-id`로 KOMSCO 기준 50건을 명시적으로 고정; 기존 MATCHED-only 축소 문제를 방지
- **실행**: 40건 처리 후 `5608` persistence 오류에서 중단; 429/403은 발생하지 않았고 이후 요청은 없음
- **안전**: Resolver/Qwen/comparator/DOM 정책 변경 없음; 미처리 9건은 자동 재시도하지 않음

## [2026-09-20] 신규 batch checkpoint 및 보수적 PCMap pacing
- **checkpoint**: 신규 batch에서 RESOLVED된 17건만 `verified-place-ids.csv`에 추가; AMBIGUOUS/NOT_FOUND/BLOCKED는 제외
- **rate limiting**: Playwright navigation 간 기본 2.5초, restaurant 완료 후 5초 대기를 주입 가능한 `NavigationRateLimiter`로 추가; 429/403 기존 즉시 중단 정책은 유지
- **검증**: 4288/4294 checkpoint 재사용 upsert idempotency 확인; 신규 20건 표본은 4331의 HTTP 429에서 즉시 중단
- **안전**: Resolver/Qwen/comparator 정책과 KOMSCO 전체 모집단 실행은 변경하지 않음

## [2026-09-20] Live PCMap 주소 section parser 확인
- **실제 DOM contract**: `span.place_blind`의 `주소` → 두 단계 상위 section → `a[role=button][aria-haspopup=true]` 조건부 1회 click → semantic `도로명`/`지번` row 추출
- **route 분리**: 주소 펼침으로 DOM index가 변하므로 `찾아가는길` label을 재탐색하고 별도 section에서만 route text 추출
- **live 확인**: 38648810 HOME road/jibun/route, MENU 40개 및 REVIEW keyword/menu/theme/review DOM을 실제 URL에서 확인; HTML 저장·Apollo·DB write·전체 실행 없음
- **검증**: AI 테스트 35개와 `./scripts/check-ai.sh`, `git diff --check` 통과

## [2026-09-20] Address Validator live 제한 검증 및 semantic label locator 보강
- **범위**: offline `STRONG_MATCH`·미검증 대상 중 1건만 report-only live 확인; 후보 선택/Qwen/Top-5/threshold/hard gate는 변경하지 않음
- **진단**: `선02`에서 detail DOM 주소가 누락되어 `DETAIL_ADDRESS_MISSING`으로 종료됨
- **보강**: `주소` semantic label의 상위 row와 exact text/aria-label 경로를 bounded하게 탐색; 길찾기 문구는 계속 주소로 사용하지 않음
- **안전**: 추가 live 요청은 429 방지를 위해 실행하지 않았고, DB write·전체 실행은 없음

## [2026-09-20] Place Detail 주소 Best-Evidence 비교 및 semantic 주소 파서 보강
- **offline 우선**: 기존 `top-k-detail-validation-diagnostics-20-final.csv`만 재평가해 KOMSCO/NAVER 주소와 detail 도로명·지번의 모든 조합 중 최강 evidence를 사용하도록 변경
- **주소 evidence**: `EXACT > STRONG_MATCH > PARTIAL > UNKNOWN > DIFFERENT`; 도로명 건물번호·지번 동/본번 조합과 trailing 층/상호 표현을 허용
- **파서**: `span.place_blind`의 `주소` semantic row만 primary 주소로 사용하고 역/출구 길찾기 문구는 주소로 취급하지 않음
- **결과**: 기존 20회 시도 오프라인 재평가에서 `STRONG_MATCH 12 / DIFFERENT 7 / UNKNOWN 1`; live NAVER 재실행은 하지 않음

## [2026-09-20] Place Resolver TOP_K 상세 검증 진단 리포트
- **진단**: 후보별 Place ID, detail URL/name/address, 정규화 name/address evidence와 정확한 validation 실패 사유를 append CSV/Markdown으로 기록
- **분류**: `ADDRESS_MISMATCH`, `NAME_AND_ADDRESS_MISMATCH`, `DETAIL_ADDRESS_MISSING` 및 주소 파싱 의심을 구분; Resolver 선택·Qwen·threshold 정책은 변경하지 않음
- **범위**: 기존 MATCHED 20건만 report-only로 확인하고 DB write·NAVER Local API·전체 실행은 수행하지 않음; 마지막 추가 요청은 HTTP 429에서 즉시 중단

## [2026-09-20] Place Resolver optional evidence 및 Top-5 검증 보강
- **감사/수정**: 좌표·category·부분 주소 누락은 mismatch가 아닌 UNKNOWN으로 유지하고, 명백한 비음식점 또는 이름·주소 동시 불일치만 hard reject하도록 정리
- **순위/검증**: deterministic evidence로 후보를 안정 정렬한 뒤 Qwen schema를 `min(5, candidate_count)` 전체 순위로 제한하고, 반환 순위를 최대 5개까지 상세 페이지에서 순차 검증
- **추적**: 후보 DOM의 place_id 누락·비음식점·명백한 불일치 사유를 report 필드에 기록; 기존 checkpoint·Place ID 출처·DB write 안전장치는 유지
- **검증**: AI 테스트 31개 및 `./scripts/check-ai.sh` 통과; KOMSCO 전체 모집단·NAVER Local API·DB write는 실행하지 않음

## [2026-09-20] Place Resolver NAVER fallback을 저장 데이터 재사용으로 전환
- **조회**: KOMSCO 모집단 query가 기존 NAVER MATCHED row의 external_name, address, road_address, category, latitude, longitude를 함께 읽음
- **fallback**: PCMap 최초 결과가 `AMBIGUOUS`/`NOT_FOUND`일 때 저장된 NAVER reference가 충분한 경우에만 PCMap을 1회 재시도
- **제거**: Place ID pipeline의 `NaverLocalFallbackClient`와 NAVER Local API 재호출 경로 제거; NAVER Local deterministic Match는 재실행하지 않음
- **분리**: KOMSCO reference를 유지하고 저장 NAVER 값은 별도 reference로 구성
- **검증**: AI 테스트 24개 및 `./scripts/check-ai.sh` 통과; 전체 Place ID 수집·NAVER API 호출·DB write는 실행하지 않음

## [2026-09-19] NAVER deterministic Match 실행 정리
- **resume**: `naver-deterministic-validation-*.csv`를 전용 checkpoint로 사용하고 semantic/Qwen/Embedding 컬럼이 있는 실험 CSV는 자동 선택에서 제외
- **명시적 재개**: 필요하면 `--resume-source`로 deterministic checkpoint를 지정하며, 파일 헤더가 AI 실험 결과이면 거부
- **진행률**: `--all`에서 설정 limit이 아니라 실제 KOMSCO 처리 대상(재개 시 미처리 대상) 수를 total로 사용
- **정리**: NAVER Local Match의 semantic ranker/scorer, Ollama 설정, Qwen/Embedding metrics와 CSV 컬럼 제거
- **보존**: Place Resolver의 `ai/app/place_resolver_cli.py` 및 Qwen 코드는 별도 실행 경로로 유지; 기존 전체 Match 결과와 실험 CSV는 삭제하지 않음
- **검증**: NAVER matcher/runner 테스트 및 `./scripts/check-backend.sh` 통과; 전체 NAVER Match·DB write는 실행하지 않음

## [2026-09-19] NAVER Local Matcher deterministic-only 전환
- **실행 경로**: NAVER Local 매칭에서 Qwen semantic ranking과 Qwen embedding 호출을 제거하고 기존 score/hard gate/strong evidence만 사용
- **보존**: report-only, CSV append/flush, resume, progress/ETA, 기존 deterministic 전체 결과와 Place Resolver 코드는 유지
- **검증**: 기존 45건을 재실행하지 않고 deterministic unit/service 테스트로 AI 호출 0 경로를 확인; 중단된 LLM 전체 CSV는 삭제하지 않음
- **주의**: `backend/build/reports/naver-all-20260919-033129.csv`를 기존 deterministic 전체 결과로 재사용하며, 비음식점 hard gate 재검토 후보는 별도 식별

## [2026-09-19] Qwen semantic 생성 재현성 설정
- **생성 옵션**: Ollama semantic 요청에 `temperature=0`, `think=false`, 고정 `seed`(기본 42), `num_predict=80`을 적용
- **설정**: `LOCAL_LLM_SEED` 환경변수로 seed를 조정할 수 있으며 prompt/threshold/hard gate/embedding/fallback 정책은 변경하지 않음
- **반복 검증**: 동일 3건 report-only 표본을 2회 실행해 final status, ranking, decision, evidence/conflicts가 모두 일치함
- **범위**: 전체 데이터·DB write·Place ID Resolver·crawler는 실행하지 않음

## [2026-09-19] NAVER semantic 실행 안정성 검증 보강
- **Qwen 결과 분류**: 호출 결과를 SUCCESS, ABSTAIN, EMPTY_RESPONSE, INVALID_JSON, SCHEMA_VALIDATION_FAILED, TIMEOUT, HTTP_ERROR, MODEL_ERROR로 구분하고 `qwen_result_status`를 validation CSV에 기록
- **Hard gate metrics**: 비음식점 후보 차단 수와 전 후보가 비음식점인 음식점 수를 별도로 집계
- **Resume 회귀**: validation CSV만 source로 완료 restaurant ID를 읽고 중복/검토 CSV 오인식을 막는 테스트 추가
- **범위**: 매칭 정책·threshold·prompt/category 정책은 변경하지 않았고, 전체 데이터는 실행하지 않음

## [2026-09-19] NAVER report-only 실행 Harness 안정화
- **중간 보존**: report-only CSV를 음식점 단위로 append/flush하여 중단 시 완료 결과 보존
- **재개**: `--resume`가 최신 CSV의 `restaurant_id`를 읽어 완료 항목을 건너뜀
- **진행률**: current/total, 퍼센트, 음식점명, 상태, item/total elapsed, ETA 로그 추가
- **metrics**: NAVER/embedding/Qwen 호출 수와 누적 latency 기록; embedding은 KOMSCO+후보를 단일 `/api/embed` batch 요청
- **검증**: 동일 45건 report-only 실행에서 45행 CSV 생성, DB write 0, NAVER 70회/12,295ms, embedding 17회/1,302ms, Qwen 17회/18,758ms
- **전체 실행**: 중간 저장 기능이 없는 기존 전체 실행은 중단했으며, 전체 재실행은 추가 승인 전 수행하지 않음

## [2026-09-19] NAVER semantic matcher 2차 PoC
- **Hard gate**: 기업·빌딩, 서비스·산업, 편의시설, 쉼터, 종합복지관 등 명백한 비음식점 category를 Qwen 이전에 제외
- **Embedding**: Ollama `qwen3-embedding:0.6b`로 후보 cosine similarity를 메모리에서 계산하고, 장애 시 Rule + Qwen으로 fallback
- **Qwen schema**: `candidateIndexes`, `decision`, enum evidence/conflicts를 검증하고 `AMBIGUOUS`/`INSUFFICIENT_EVIDENCE` abstain을 허용
- **동일 45건 PoC**: initial 15/15/15, 최종 MATCHED 20 / AMBIGUOUS 8 / UNMATCHED 17; Qwen 10건, embedding 10건, DB write 0건
- **리포트**: `backend/build/reports/naver-enrichment/naver-validation-20260919-220103.csv`; 태화기독교사회복지관은 비음식점 hard gate 후 AMBIGUOUS 처리

## [2026-09-19] NAVER semantic matcher report-only PoC
- **안전 실행**: `--report-only`에서 NAVER Local/Ollama와 DB read만 허용하고 enrichment upsert·실패 상태 기록을 차단; 기존 기본 실행은 유지
- **표본**: 기존 DB 상태를 기준으로 MATCHED/AMBIGUOUS/UNMATCHED 각 15건, 총 45건을 deterministic 선택
- **결과**: initial 15/15/15, rule-only MATCHED 18, semantic 최종 MATCHED 21, AMBIGUOUS 9, UNMATCHED 15; Qwen 호출 12건(26.7%), DB write 0건
- **리포트**: `backend/build/reports/naver-enrichment/naver-validation-20260919-214553.csv`; `elapsed_ms`, 기존 상태, rule-only/semantic 상태를 포함
- **주의**: `태화기독교사회복지관`이 비음식점 계열 후보로 MATCHED된 의심 사례로 확인되어 운영 반영 전 정책 검토 필요

## [2026-09-19] NAVER Local Qwen semantic ranking (기본 비활성)
- **구조**: 기존 hard filter/결정론적 매칭을 유지하고, 확정되지 않은 후보만 mock 가능한 Qwen 랭커 포트로 전달
- **안전**: Qwen은 후보 index 순위만 반환하며 Place ID·내부 ID를 전달하지 않음; 최종 상태는 기존 strong-evidence 규칙으로 재검증
- **설정**: `NAVER_SEMANTIC_MATCHING_ENABLED=false`, Ollama 기본 `http://localhost:11434` / `qwen3:8b`; 구조화 schema와 index 범위·중복 검증 적용
- **검증**: 실제 NAVER/Ollama 호출 없이 matcher mock 테스트 및 backend build/test 통과. 30~50건 실데이터 PoC는 외부 호출 승인 후 수행하지 않음

## [2026-09-19] Place Resolver write-db apply-only regression guard
- **안전장치**: `--resume --write-db`를 CSV apply-only 모드로 고정해 기존 `RESOLVED + PASS` 결과만 반영하고 PCMap/NAVER/Ollama resolver를 시작하지 않음
- **CSV-only**: `--dry-run`은 DB apply 함수를 호출하지 않음
- **검증**: apply-only·CSV-only·insert/update/conflict 경로를 포함한 AI 테스트 24개 통과; 동일 CSV 반복 후 NAVER mapping 18개, distinct Place ID 18개, 중복 0건 유지

## [2026-09-19] Place ID 전용 저장·NAVER fallback 조건 제한
- **DB**: 기존 `restaurant_external_places`를 재사용해 V12 `external_place_id`와 `(provider, external_place_id)` unique index를 추가; 현재 local Flyway version 12 적용 확인
- **write-db**: `RESOLVED + detail_validation=PASS + numeric place_id`만 매핑을 upsert하며, 기존 NAVER row는 update하고 KOMSCO-only row는 insert; 다른 상태와 invalid ID는 저장하지 않음
- **안전장치**: `--resume --write-db`는 검토 CSV만 반영한 뒤 즉시 종료하도록 변경해 추가 크롤링을 막음
- **fallback**: 초기 `AMBIGUOUS`/`NOT_FOUND`이면서 기존 NAVER 상태가 `MATCHED`인 경우에만 Local fallback을 호출; 비매칭/미조회는 `SKIPPED_NO_NAVER_MATCH`
- **검증**: AI 22개 테스트 통과, backend build/test 통과, V12 Flyway 적용 및 schema/index 확인. 검증 중 잘못된 resume 명령으로 32건이 추가 처리되었고 11건이 DB에 반영되어 `komsco-direct-fallback-interrupted-52.csv`로 보존함; 전체 실행은 중단했고 추가 실행하지 않음

## [2026-09-19] KOMSCO-direct Place Resolver NAVER Local 1회 fallback
- **흐름**: KOMSCO-direct가 `AMBIGUOUS`/`NOT_FOUND`일 때만 NAVER Local을 1회 호출하고, KOMSCO를 덮어쓰지 않는 별도 enriched reference로 같은 PCMap Resolver를 단 1회 재실행
- **불변**: Qwen prompt/Top-K, hard prefilter, DOM `data-nlog-params` Place ID, detail validation, PCMap direct-only 정책은 변경하지 않음
- **20건**: 최초 `RESOLVED 3 / AMBIGUOUS 14 / NOT_FOUND 3`, NAVER Local 17회 호출 후 최종 `RESOLVED 7 / AMBIGUOUS 10 / NOT_FOUND 3 / ERROR 0 / BLOCKED 0`; fallback recovery 4건
- **그룹**: 기존 NAVER MATCHED 10건은 `3→7 RESOLVED`(recovery 4), 비매칭/미조회 10건은 recovery 0; 회수 4건은 모두 KOMSCO/NAVER 도로명·건물번호 일치로 evidence상 SAFE
- **리포트**: `ai/build/reports/naver-place-resolver/komsco-direct-fallback-20.csv`; 전체 3,251건 실행·DB write 없음

## [2026-09-19] Place Resolver KOMSCO-direct 입력 전환
- **대상**: NAVER Local `MATCHED + ELIGIBLE` 선행 게이트를 제거하고 MySQL `restaurants`에서 KOMSCO, active, 제로페이 `I0000002`, KSIC `561`, 계속사업자, 강남구 법정동, 이름·주소·좌표 조건을 직접 조회
- **모집단**: 실제 대상 3,251건; 기존 NAVER MATCHED 1,980건, 그 외/미조회 1,271건. KOMSCO 3,272건 중 좌표 누락 21건은 제외
- **표본**: 20건은 기존 MATCHED 10건과 그 외 상태 10건을 법정동 round-robin으로 선정; 전체 실행 및 DB write 없음
- **PoC**: `RESOLVED 3 / AMBIGUOUS 14 / NOT_FOUND 3 / ERROR 0 / BLOCKED 0`, Qwen 7건, 평균 1,715.25ms. RESOLVED 3건은 모두 기존 MATCHED 그룹이며 명백한 오매칭 증거는 없음
- **안전**: CSV에 `source_type=KOMSCO_DIRECT`와 이전 NAVER 상태를 기록하고, 구 NAVER Local 모집단 CSV의 resume을 거부
- **회귀**: PCMap direct, DOM `data-nlog-params`, Place ID 비노출 Qwen Top-K, sequential detail validation 정책은 변경하지 않음
- **리포트**: `ai/build/reports/naver-place-resolver/komsco-direct-20.csv`

## [2026-09-19] Place Resolver 로컬 전체 배치 실행 Harness
- **CLI**: `--limit`, `--resume`, `--dry-run`, `--write-db`, `--output` 옵션과 전체 `MATCHED + ELIGIBLE` 입력 처리를 추가했으며 Resolver 매칭 정책은 변경하지 않음
- **Preflight**: Python, Playwright Chromium, Ollama `qwen3:8b`, MySQL 네트워크, 출력 디렉터리를 수집 전에 확인하고 secret 값은 출력하지 않음
- **Checkpoint/진행률**: 결과 CSV를 건별 flush/fsync하고 완료 `restaurant_id`를 resume에서 skip; 상태 누계, ETA, 안전 종료 안내를 터미널에 표시
- **DB 안전성**: 기본 CSV-only, `--write-db`에서만 `RESOLVED + valid place_id`의 기존 NAVER enrichment link를 갱신하고 다른 상태는 쓰지 않음
- **실행 검증**: 5건 CSV-only `RESOLVED 5 / AMBIGUOUS 0 / NOT_FOUND 0 / ERROR 0 / BLOCKED 0`, DB writes 0; 같은 파일 `--resume`에서 5건 skip 확인
- **문서**: `ai/README.md`, `docs/ai-flow.md`에 Mac 로컬 실행·중단·resume·CSV 검토 순서를 기록

## [2026-09-19] Qwen Top-K 고정 길이 스키마 재검증
- **스키마**: 후보 1개는 Qwen을 호출하지 않고, 후보 2개는 `candidateIndices` 2개, 후보 3개 이상은 3개를 `minItems`/`maxItems`와 `uniqueItems`로 강제; 실제 후보 index만 `enum`으로 허용하고 코드 범위·중복 검증과 1회 retry를 유지
- **프롬프트**: 후보 중 상위 `min(3, 후보 수)`개를 순위대로 모두 반환하도록 명시; Place ID는 계속 전달하지 않음
- **동일 20건 결과**: `RESOLVED 17 / AMBIGUOUS 2 / NOT_FOUND 1 / BLOCKED 0 / ERROR 0`; `SINGLE_CANDIDATE 16 / QWEN 4`; Qwen 응답 4건 모두 Top-3 배열
- **순차 검증**: Top-1에서 `RESOLVED 17`, Top-2 추가 `0`, Top-3 추가 `0`; 상세 검증 실패 2건, Place ID 누락 1건
- **주요 사례**: `광부`는 상세 주소 불일치로 AMBIGUOUS, `전라도밥집 순천댁`은 후보 DOM Place ID 누락으로 NOT_FOUND, `미가 부대찌개`는 Top-3 전체가 상세 검증을 통과하지 못해 AMBIGUOUS
- **성능**: detail validation 시도 19회/20건(평균 0.95회), elapsed 평균 1,315.75ms, 중앙값 920ms, 최소 572ms, 최대 3,322ms; 명백한 신규 오매칭 증거 없음
- **리포트**: `ai/build/reports/naver-place-resolver/naver-place-resolver-20260919-182714.csv`, `ai/build/reports/naver-place-resolver/naver-place-resolver-audit-20260919-182714.csv`
- **검증**: `poetry run pytest tests/test_place_resolver.py` 13개 및 `./scripts/check-ai.sh` 전체 14개 통과, `git diff --check` 통과

## [2026-09-19] Qwen Top-K 후보 검증 회귀
- **구조**: Qwen이 최대 3개 candidate index를 순위 배열로 반환하고, 각 후보 DOM Place ID를 순서대로 상세 검증해 첫 PASS에서 종료하도록 확장
- **schema**: 후보 수별 `candidateIndices.items.enum`, `minItems=1`, `maxItems<=3`, `uniqueItems=true`와 코드 범위 검증 유지
- **동일 20건 결과**: `RESOLVED 17 / AMBIGUOUS 2 / NOT_FOUND 1 / BLOCKED 0 / ERROR 0`; Qwen `HIGH 8 / LOW 12`, Top-3 응답 1건
- **주요 사례**: `광부`는 주소 불일치로 AMBIGUOUS, `전라도밥집 순천댁`은 Place ID 누락으로 NOT_FOUND, `미가 부대찌개`는 Top-K 상세 검증 실패로 AMBIGUOUS
- **회귀**: 기존 RESOLVED 18건 중 17건 유지(미가 1건 하락); 명백한 오매칭 증거는 없음
- **성능**: detail validation 시도 19회/20건(평균 0.95회), elapsed 평균 2,425.3ms, 중앙값 2,200.5ms, 최소 1,423ms, 최대 4,802ms
- **리포트**: `ai/build/reports/naver-place-resolver/naver-place-resolver-20260919-181644.csv`, `ai/build/reports/naver-place-resolver/naver-place-resolver-audit-20260919-181644.csv`
- **검증**: AI 테스트 13개, `./scripts/check-ai.sh`, `git diff --check` 통과

## [2026-09-19] Place Resolver deterministic 원인 분석 및 Qwen schema 보강
- **원인 분석**: 기존 20건은 후보 DOM의 축약/부가 문구로 일반 matcher의 강한 name·address 조합을 충족하지 못해 DETERMINISTIC 0건이었음. threshold 완화는 하지 않음
- **fast-path**: 단일 후보 + normalized name EXACT + address EXACT/PARTIAL + 음식점 category만 허용하는 보수적 경로를 추가했으며 branch conflict와 runner-up은 제외
- **Qwen schema**: 후보 수에 맞춰 `candidateIndex.enum=[0..n-1]`을 동적으로 전달하고, malformed/schema/range 오류는 동일 요청 1회만 retry 후 ERROR 처리
- **재검증**: 동일 20건에서 `DETERMINISTIC 0 / QWEN 20`, `RESOLVED 18 / NOT_FOUND 2 / AMBIGUOUS 0 / ERROR 0 / BLOCKED 0`; 광부의 out-of-range 오류는 사라지고 주소 불일치 NOT_FOUND로 처리됨
- **Risk audit**: SAFE 14, REVIEW 6, SUSPICIOUS 0
- **리포트**: `ai/build/reports/naver-place-resolver/naver-place-resolver-20260919-180659.csv`, `ai/build/reports/naver-place-resolver/naver-place-resolver-audit-20260919-180659.csv`
- **검증**: AI 테스트 13개, `./scripts/check-ai.sh`, `git diff --check` 통과

## [2026-09-19] Place Resolver 직접 PCMap + fallback 20건 검증
- **검색 진입점**: `pcmap.place.naver.com/place/list?query=`를 primary로 사용하고, 직접 결과에서 명시적 Place ID를 얻지 못할 때만 기존 `map.naver.com → #searchIframe` 경로로 fallback
- **보고서**: deterministic `MATCHED + ELIGIBLE` 법정동 round-robin 20건을 순차 실행해 `ai/build/reports/naver-place-resolver/naver-place-resolver-20260919-163854.csv`에 저장
- **결과**: `RESOLVED 10 / AMBIGUOUS 1 / NOT_FOUND 3 / BLOCKED 0 / ERROR 6`; 오류 6건은 fallback iframe 로딩 timeout이며 차단 신호는 아님
- **안전**: 동시성 1, 요청 간 2초 지연, 공개 UI DOM/URL만 사용; DB/API 쓰기, 내부 API, CAPTCHA·로그인 우회 없음
- **검증**: Place URL parser/Resolver 테스트, `./scripts/check-ai.sh`, `git diff --check` 통과

## [2026-09-19] Place Resolver 신규 표본 20건 감사 실행
- **범위**: 기존 3건을 제외한 `MATCHED + ELIGIBLE` deterministic 표본 20건; 코드·threshold·prompt는 실행 전에 변경하지 않음
- **결과**: `RESOLVED 18 / AMBIGUOUS 0 / NOT_FOUND 1 / ERROR 1 / BLOCKED 0`; `DETERMINISTIC 0 / QWEN 20`, Qwen `HIGH 19`
- **상세 검증**: Qwen 선택 후 RESOLVED 18건, 실패 2건; NOT_FOUND는 후보 DOM Place ID 누락, ERROR는 Qwen candidateIndex 범위 오류
- **Risk audit**: SAFE 14, REVIEW 6, SUSPICIOUS 0. Human-labeled ground truth가 아닌 evidence 기반 검토로 정확도/false-positive 비율로 해석하지 않음
- **성능**: elapsed 합계 46,116ms, 평균 2,305.8ms, 중앙값 2,322ms, 최소 1,513ms, 최대 2,840ms
- **리포트**: `ai/build/reports/naver-place-resolver/naver-place-resolver-20260919-175901.csv`, `ai/build/reports/naver-place-resolver/naver-place-resolver-audit-20260919-175901.csv`
- **검증**: `./scripts/check-ai.sh`, `git diff --check` 통과; 전체 데이터 실행 없음

## [2026-09-19] PCMap 직접 Place Resolver + Qwen 후보 선택 PoC
- **검색 경로**: `pcmap.place.naver.com/place/list?query=`만 사용하도록 Resolver를 정리하고 `map.naver.com`/`searchIframe` fallback을 제거
- **Place ID**: 선택된 후보 DOM 내부 `data-nlog-params`를 HTML entity decode·JSON parse하여 유일한 numeric `place_id`만 `DOM_DATA_NLOG`로 인정; 후보 간 ID 혼합과 다중 ID는 fail-closed
- **LLM**: deterministic matcher가 확정하지 못할 때만 `OLLAMA_BASE_URL`/`LOCAL_LLM_MODEL`의 Qwen3 8B를 호출하고 candidateIndex·confidence 구조만 검증; prompt에는 Place ID를 포함하지 않음
- **상세 검증**: 선택된 ID로 `/restaurant/{placeId}/home`에 직접 접근해 이름·주소·category를 재검증
- **실제 3건**: `RESOLVED 0 / AMBIGUOUS 3 / NOT_FOUND 0 / ERROR 0 / BLOCKED 0`; Qwen은 3건 모두 호출되어 LOW/null로 보수적으로 AMBIGUOUS 처리
- **리포트**: `ai/build/reports/naver-place-resolver/naver-place-resolver-20260919-175119.csv`
- **검증**: 9개 AI 테스트, `./scripts/check-ai.sh`, `git diff --check` 통과

## [2026-09-19] Qwen 후보 랭커 정책 보정
- **역할 변경**: Qwen을 동일 매장 최종 판정기가 아닌 deterministic prefilter 후보 중 최상위 후보를 고르는 랭커로 변경
- **출력 정책**: 후보가 있으면 `candidateIndex` 정수와 confidence를 반드시 반환하도록 schema/prompt를 변경; null은 invalid response로 처리하고 LOW도 선택을 계속 진행
- **최종 판정**: 선택 후보 DOM의 `DOM_DATA_NLOG` Place ID와 `/restaurant/{id}/home` 상세 이름·주소 검증만 RESOLVED를 결정
- **실제 3건**: Qwen 3건 호출, `HIGH 2 / LOW 1`; `RESOLVED 3 / AMBIGUOUS 0 / NOT_FOUND 0 / ERROR 0 / BLOCKED 0`
- **리포트**: `ai/build/reports/naver-place-resolver/naver-place-resolver-20260919-175504.csv`

## [2026-09-19] searchIframe 기반 Place ID 1건 검증
- **원인 수정**: PC 지도 `#searchIframe` 내부 `li`/role 버튼에서 후보를 읽고, 검색 결과 첫 항목이 아닌 NAVER Local 상호 evidence가 가장 높은 후보를 선택
- **URL 추출**: 후보 href → 클릭 후 frame URL/iframe src → navigation URL 순서로 명시적 ID만 추출; marker image/data overlay 값은 사용하지 않음
- **실제 1건**: query `매봉역 선02`, iframe 로드 성공, 후보 9개, `집밥식당 선02 플레이스 플러스 한식` 클릭 후 `/place/1793398137` 발견. 주소 evidence가 충분하지 않아 `NOT_FOUND`이며 ID는 저장하지 않음
- **검증**: parser 회귀 테스트, `./scripts/check-ai.sh`, `git diff --check` 수행 예정; 20건 실행하지 않음

## [2026-09-19] NAVER Place ID PC Map 1건 검증
- **Parser**: 기존 `/place`·`/entry/place`에 `pcmap.place.naver.com/restaurant/{id}` 패턴을 추가하고 `1126763661` 회귀 테스트를 추가
- **검색 흐름**: 모바일 UI를 제거하고 PC 지도에서 가장 가까운 역명→법정동→강남구 순으로 query fallback; 공개 DOM href와 클릭 후 frame/navigation URL만 확인
- **실제 1건**: `매봉역 선02` 검색에서 `선라이프` 후보의 `https://pcmap.place.naver.com/restaurant/1793398137/home...` href를 발견했으나 상호 불일치로 `NOT_FOUND` 처리. ID는 추출했지만 채택하지 않음
- **검증**: `RESOLVED 0 / AMBIGUOUS 0 / NOT_FOUND 1 / BLOCKED 0 / ERROR 0`; 20건 실행하지 않음

## [2026-09-19] NAVER Place ID Resolver PoC
- **구조**: `ai/app/place_resolver.py`에 URL 기반 Place ID 추출, 이름·주소·거리 근거와 보수적 상태 판정을 추가하고 `place_resolver_cli.py`에서 Playwright 공개 화면만 사용
- **범위**: 기존 NAVER Local `MATCHED + ELIGIBLE` CSV에서 법정동 round-robin 20건만 선택; DB/Flyway 변경 없음
- **실행**: `ai/build/reports/naver-place-resolver/naver-place-resolver-20260919-153106.csv` 생성, `RESOLVED 0 / AMBIGUOUS 0 / NOT_FOUND 20 / BLOCKED 0 / ERROR 0`
- **안전**: 모바일 공개 UI에서 서비스 접근 제한 문구를 확인해 추가 외부 호출을 중단; 내부 API·로그인·CAPTCHA·anti-bot 우회 없음

## [2026-09-19] Station provenance 감사 및 반경 경계 명시
- **Provenance**: 공식 서울교통공사/서울시 데이터셋 URL과 좌표 메타데이터를 `docs/database.md`에 기록하고, V11의 `SEOUL_OPEN_DATA` 라벨은 원본 매핑 증거가 없어 검증되지 않은 내부 라벨임을 명시
- **Radius 테스트**: 100m·500m 경계(부동소수점 안전 fixture)와 초과값의 포함/제외 의도를 테스트에 명시
- **범위 제한**: migration, 애플리케이션 로직, 외부 API, Scheduler는 변경하지 않음

## [2026-09-19] Local Flyway 11·역 API·Scheduler 인프라 정리
- **DB 적용**: local MySQL에 애플리케이션 기동으로 V8~V11을 적용하고 ShedLock, conversations 반경, subway_stations 스키마를 검증
- **Scheduler**: `@EnableScheduling`을 개별 KOMSCO/NAVER job 조건에서 분리하고 NAVER 기본 비활성 설정을 추가; Sunday 04:00 Asia/Seoul, ShedLock 1h/1m, DB time 유지
- **Station API**: 인증된 `GET /api/stations`가 active 역만 이름·호선 순으로 반환하도록 추가
- **Radius 검증**: 100m/500m 경계, 초과, 좌표 누락, 잘못된 반경, inactive station과 deterministic ranking 테스트 추가
- **정리**: Naver matcher의 임시 DEBUG 출력과 AddressDebug/PolicyInvestigateTest를 제거하고 trailing whitespace 정리
- **문서**: station API, `distanceMeters`, V11 source/source_updated_at 의미를 API·DB 문서에 반영

## [2026-09-19] Address Parser 오프라인 검증 및 리포트 도출
- **검증 환경**: Python 에뮬레이션의 Regex 파싱 차이와 CSV 빈 컬럼 분리 버그를 배제하고, 실제 Java NaverRestaurantMatcher와 NaverAddressParser 컴포넌트를 직접 사용해 naver-all.csv를 재평가
- **재현 결과**: 기존 Python 분석에서 보고된 "AMBIGUOUS → MATCHED 71건, MATCHED → AMBIGUOUS 2건"을 정확히 동일하게 재현 성공
- **결과 원인**: Address Parser의 100% 일치(30점) 기준이 충족되면서 address_score가 기존 토큰 유사도 점수(예: 15점)에서 30점으로 대폭 상승해 총점(70 이상) 및 Gap(8 이상) 하드 게이트를 돌파함
- **Risk 도출**: 30점 만점을 받았으나 상호명 점수가 낮거나(40 미만) 거리가 먼(30m 이상) 케이스 등, Address 비중이 비정상적으로 높아 승인된 71건 전체를 분류해 새 리포트에 risk_flags로 기록
- **검증 패스**: 임시 검증 코드를 제거하고 ./scripts/check-backend.sh 통과 확인


이 파일은 AI 에이전트들이 작업한 내역과 시스템 변경 사항을 기록하여, 이후에 투입되는 다른 에이전트가 프로젝트 문맥을 빠르게 파악할 수 있도록 돕는 파일입니다.

새로운 작업을 완료할 때마다 이 파일의 최상단에 작업 내역을 추가합니다.

## [2026-09-19] NAVER Local Address Matching 개선
- **목표**: NAVER Local 매칭 중 실제 같은 주소이나 띄어쓰기/상세주소 차이로 점수가 낮게 나오는 문제 해결 및 지번 번호가 다른 거짓 양성(False Positive) 방어
- **백엔드 (Spring Boot)**
  - `NaverAddressParser` 컴포넌트 추가: 정규식을 이용해 서울특별시/강남구 접두어를 제거하고, 순수 도로명(공백 제거)과 건물 본번/부번을 분리하여 파싱
  - `NaverRestaurantMatcher`의 `singleAddressScore` 로직 개선: 도로명이 정확히 일치할 때, 건물 번호가 같으면 즉시 `addressExactScore(30)` 부여, 다르면 `0.0`으로 처리하여 부당한 강한 일치(Strong Match) 승격 차단
  - 지번/도로명 혼용으로 파싱 불가능한 경우 기존의 `tokenSimilarity` 백폴백(fallback) 로직 정상 유지
- **DevOps / Testing**
  - `NaverRestaurantMatcherTests`에 도로명/건물번호 일치/불일치 관련 회귀 테스트 케이스 추가 및 생성자 의존성 주입 반영
  - 오프라인 스크립트를 통해 3,272건의 데이터를 NAVER API 재호출 없이 재평가 수행
  - 재평가 결과 MATCHED 69건 순증 (AMBIGUOUS 71건 승격, 거짓 양성 의심 MATCHED 2건 강등)
- **결과**: `check-backend.sh` 통과. NAVER API 호출 없이 오프라인 재평가 완료.

## [2026-09-19] NAVER Local 최초 전체 3,272건 매칭
- **실행 승인**: MATCHED 20건 인간 검토 후 사용자의 명시적 승인으로 `--all` 1회 실행; 주 1회 Scheduler는 미구현·미활성
- **실행 결과**: processed 3,272, MATCHED 1,982, AMBIGUOUS 163, UNMATCHED 1,127, API_ERROR 0; inserted 3,172, updated 100, skipped 0
- **추천 상태**: ELIGIBLE 1,939, INELIGIBLE 0, UNKNOWN 1,333; MATCHED+UNKNOWN 43건은 현재 category 정책에서 음식점임을 확정할 수 없어 추천에서 제외
- **무결성**: NAVER 3,272행/서로 다른 restaurant 3,272건, duplicate 0, 명시적 비음식점 category+ELIGIBLE 0, 모든 마지막 API 시도 SUCCESS
- **KOMSCO 보존**: 원본 필드 checksum이 실행 전·후 `XOR=1973841089`, `SUM=6969399285795`로 일치
- **리포트**: 전체 `backend/build/reports/naver-enrichment/naver-all-20260919-033129.csv`, 복합 위험 상위 50건 `naver-full-review-20260919-033129.csv`

## [2026-09-19] Restaurant 추천 가능 상태 분리
- **상태 설계**: KOMSCO 원본을 유지하면서 `restaurants.recommendation_eligibility`에 ELIGIBLE/INELIGIBLE/UNKNOWN을 저장하는 Flyway V7 추가
- **공유 정책**: NAVER category를 FOOD/NON_FOOD/UNKNOWN으로 분류하는 정책을 Candidate Hard Gate와 추천 가능 판정에서 공유
- **추천 안전성**: 추천 repository는 기존 `recommendation_ready` 조건과 함께 ELIGIBLE만 반환하고, KOMSCO 매칭 입력 변경·API_ERROR는 UNKNOWN으로 되돌림
- **실제 100건 재실행**: 사용자 승인 후 MATCHED 60, AMBIGUOUS 8, UNMATCHED 32, API_ERROR 0; ELIGIBLE 60, INELIGIBLE 0, UNKNOWN 40
- **DB 검증**: NAVER enrichment 100행/서로 다른 restaurant 100건으로 중복 없음; 전체 3,272건은 실행하지 않음
- **검토 리포트**: `backend/build/reports/naver-enrichment/naver-validation-20260919-030231.csv`, MATCHED 20건 `naver-matched-review-20260919-030231.csv`
- **검증**: eligibility/category/repository/writer/report 회귀 테스트, `./scripts/check-backend.sh`, `./scripts/check-all.sh` 통과

## [2026-09-19] NAVER Matching false-positive Hard Gate 보정
- **근거 분석**: 기존 MATCHED 중 주소 점수 25 미만 20건은 거리 30m 이내 15건, 30~50m 3건, 50m 초과 2건으로 확인
- **거리 결정**: 기존 최고 거리점수 경계와 실제 분포를 근거로 strong evidence 거리 기준을 50m로 선택; 기존 300m 후보 제외는 유지
- **Candidate Hard Gate**: 명시된 NAVER category가 음식점 계열이 아니거나 이름 점수가 22점 미만인 후보를 점수 경쟁에서 제외
- **MATCHED Gate**: 기존 70점·runner-up gap 8점에 더해 주소 25점 이상 또는 이름 32점 이상+50m 이내를 요구하고, 근거가 부족하면 AMBIGUOUS 처리
- **정책 유지**: 기존 이름/주소/거리/category 40/30/20/10 가중치와 viable 45점은 변경하지 않음
- **오프라인 재평가**: API 재호출 없이 기존 100건 CSV/DB로 MATCHED 63→59, AMBIGUOUS 9→8, UNMATCHED 28→33 확인
- **핵심 사례**: 수미초밥 MATCHED→AMBIGUOUS, 구야네·열린약국 MATCHED→UNMATCHED; 수미초밥과 구야네를 실제 값 기반 회귀 테스트로 고정
- **실행 범위**: 전체 3,272건 NAVER 호출 및 기존 DB status 일괄 갱신은 수행하지 않음

## [2026-09-19] NAVER Local 100건 검증·증분 갱신 기반
- **검증 표본**: 활성 KOMSCO 음식점을 법정동 코드별 ID 순서로 round-robin 선택해 14개 동이 7~8건씩 포함되는 deterministic 100건 모드 구현
- **판정 근거**: 기존 40/30/20/10점, MATCHED 70점, gap 8점, 300m 기준은 유지하고 점수 breakdown, runner-up, gap, 실제 query를 DB와 CSV에 기록
- **정규화 보강**: HTML·공백·특수문자·괄호·띄어쓰기 차이를 정리하고 양쪽의 명시적 프랜차이즈 지점명이 다르면 후보에서 제외
- **실행 안전성**: 검증 `--limit=100`, 제한 증분 `--incremental --limit=<n>`, 명시적 전체 `--all`을 분리하고 순차 호출·timeout·제한 retry 유지
- **증분 정책**: enrichment 부재, 상호·주소·좌표 등 source hash 변경, 상태별 retry 도래, MATCHED refresh TTL 만료만 재조회; KOMSCO sync는 변경 ID를 반환하되 NAVER를 자동 호출하지 않음
- **장애 보존**: `API_ERROR` 시도 상태와 다음 retry를 분리하고 기존 정상 MATCHED 후보·점수·동기화 시각은 유지
- **DB**: V1~V5를 유지하고 V6에 점수 상세, source hash, 마지막 시도 상태·시각, 다음 retry 시각 및 조회 index 추가
- **실제 검증**: 사용자 승인 100건에서 MATCHED 63, AMBIGUOUS 9, UNMATCHED 28, API_ERROR 0; 80건 insert, 기존 20건 update, restaurant/provider 중복 0
- **리포트**: `backend/build/reports/naver-enrichment/naver-validation-20260919-023530.csv`에 header 포함 101행 생성
- **검증**: `./scripts/check-backend.sh`, `./scripts/check-all.sh` 전체 통과, 실제 MySQL Flyway V6 적용 및 기존 NAVER 20행 보존 확인

## [2026-09-18] NAVER Local 음식점 매칭 및 보강
- **외부 연동**: NAVER API HUB 지역 검색을 opt-in 수동 runner로 연결하고 활성 KOMSCO 음식점을 기본 20개까지만 순차 처리
- **검색 정책**: `상호명+법정동`과 제한된 `상호명+강남구` fallback, 검색당 최대 5개 후보, 429·5xx 제한 재시도와 401/403 fast-fail 적용
- **결정론적 매칭**: HTML/공백 상호 정규화, 주소 토큰, Haversine 거리와 음식점 category를 100점 정책으로 합산해 MATCHED/AMBIGUOUS/UNMATCHED 분류
- **좌표 호환**: 실제 API 진단에서 확인한 WGS84 `10^7` 배율 정수와 소수점 좌표를 모두 decimal degree로 변환
- **DB**: 기존 V1~V4를 유지하고 V5 `restaurant_external_places`를 추가해 KOMSCO 원본과 NAVER 보강을 분리; `(restaurant_id, provider)` unique upsert 적용
- **환경**: 기존 `.env`의 `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`을 local 프로세스 또는 Compose가 주입하며 기본 실행은 비활성
- **실제 검증**: 사용자 승인 범위 20건에서 MATCHED 14, AMBIGUOUS 2, UNMATCHED 4, API 실패 0; 수정 전 생성된 같은 20행을 전부 update해 총 20행/음식점 20개 유지
- **자동 검증**: NAVER 파싱, nullable, 정규화, 좌표, 거리, 후보 선택, 상태 판정, fallback, 장애 격리, 인증 실패와 idempotent upsert 테스트 추가; `check-backend.sh`와 최종 `check-all.sh` 통과

## [2026-09-18] KOMSCO 음식점 일일 동기화 Scheduler 추가
- **실행 시간**: Spring Scheduler가 `Asia/Seoul` 기준 매일 새벽 3시에 승인된 KOMSCO 강남구 전체 조회를 실행
- **상태 동기화**: 기존 행은 매 실행마다 `last_synced_at`, `updated_at`과 원본 필드를 갱신하고, 계속사업자·KSIC 561·강남구·제공기관 조건에서 벗어나면 `active=false`, 다시 만족하면 `active=true`로 복구
- **신규 데이터**: 모든 저장 조건을 만족하는 신규 `alt_text`만 삽입하고, 응답에서 완전히 사라진 ID는 임의 비활성화하지 않음
- **장애 안전성**: 전체 pagination·최신화 성공 후에만 DB 동기화를 시작하며 API 실패 시 기존 DB를 유지
- **설정**: `KOMSCO_SCHEDULER_ENABLED`, `KOMSCO_SCHEDULER_CRON`, `KOMSCO_SCHEDULER_ZONE`을 추가하고 Docker Compose에서 기본 활성화
- **검증**: Scheduler 위임·오류 격리, timestamp 갱신, 비활성화·재활성화와 과거 데이터 보호 테스트 추가
- **검증 결과**: `./scripts/check-backend.sh`, `./scripts/check-all.sh` 전체 통과 및 실행 중 컨테이너에서 `enabled=true`, `cron=0 0 3 * * *`, `zone=Asia/Seoul` 확인

## [2026-09-18] KOMSCO 강남구 음식점 원본 import 구현
- **외부 수집**: 한국조폐공사 모바일 가맹점기본정보 API를 14개 강남구 법정동별로 끝까지 pagination하고, 전체 수집 성공 후에만 DB 저장을 시작하도록 구현
- **정제 정책**: `alt_text`별 최신 `crtr_ymd`를 먼저 선택한 뒤 제공기관 `I0000002`, `ksic_cd=561`, `bzmn_stts_nm=계속사업자`, 강남구 증거를 순서대로 검증
- **DB**: 기존 V1~V3를 유지하고 V4에서 KOMSCO 원본 컬럼, `recommendation_ready`, `(source_provider, external_merchant_id)` unique 제약을 추가
- **추천 경계**: 메뉴·가격·영업시간이 없는 KOMSCO 행은 `recommendation_ready=false`로 저장해 보강 전 추천 후보에서 제외
- **실행 방식**: 공개 API와 Scheduler 없이 opt-in one-shot `ApplicationRunner`로 구현하고 `.env`의 키를 local 실행 환경 또는 Docker Compose가 명시적으로 주입
- **실제 적재**: 61,941건 조회 → 최신화 30,783건 → 필터 통과 및 신규 적재 3,272건; DB에서 KOMSCO 3,272행과 distinct ID 3,272개 확인
- **전체 교체**: 사용자 승인 후 전체 조회 성공 시에만 기존 KOMSCO 행을 삭제·재삽입하는 트랜잭션 교체 모드를 추가하고 3,272건으로 재적재; 샘플 음식점 3건 보존
- **검증**: `./scripts/check-backend.sh` 및 `./scripts/check-all.sh` 전체 통과, 실제 MySQL Flyway V4 적용 성공
- **안전 규칙**: 이후 공공데이터·유료 API의 실제 호출 전 redacted URL/query를 사용자에게 제시하고 명시적 승인을 받도록 `AGENTS.md`에 추가

## [2026-09-17] Harness 학습 설명과 저장소 기반 학습 가이드 추가
- 핵심 정책·계약·환경 문서에 Harness Role, Agent Usage, Why와 Connection 관점의 짧은 설명 추가
- setup과 모든 check script에 실행 시점, 실패 방지 목적과 연결 관계를 설명하는 주석 추가
- 현재 실제 파일, 추천 읽기 순서, Agent 실행 흐름, feedback loop, guardrail과 애플리케이션 코드의 구분을 `docs/harness-study.md`에 정리
- 실행 명령, 설정값과 비즈니스 로직은 변경하지 않음

## [2026-09-17] 현재 코드 기준 로컬 Harness 정합성 개선
- **문서·명세**: 인증, 개인화, 식사 기록과 현재 FastAPI/Qdrant 미연동 상태를 README, 아키텍처, 배포, 테스트 및 task 상태에 반영
- **Flyway 안전성**: 적용된 V1~V3 불변과 이후 스키마 변경 시 신규 migration 추가 규칙을 Agent 정책과 DB 문서에 명시
- **Docker**: Spring Boot의 미사용 FastAPI 시작 의존성과 FastAPI의 미사용 Qdrant 시작 의존성을 제거하고 환경변수 설명을 실제 Compose 동작과 일치시킴
- **검증**: tracked 변경 전체와 untracked 텍스트 파일의 공백 검사를 추가하고 Java compiler lint를 warning-as-error로 적용
- **프런트엔드 테스트**: 선호·비선호 상호 배제·저장과 명시적 `먹었어요` 흐름의 jsdom 컴포넌트 테스트 추가
- **검증 결과**: `./scripts/check-all.sh`의 Format, Lint, Frontend, Backend, AI, Integration 전체 통과
- **제외 범위**: 사용자 지시에 따라 GitHub Actions 및 CI/CD는 후속 작업으로 유지

## [2026-09-17] FastAPI 이전 개인화 추천 기반 완성
- **정책 결정**: 제로페이는 선택 설정이 아닌 모든 추천의 필수 조건이며, 식사 기록은 사용자가 `먹었어요`를 누를 때만 생성하고 최근 72시간만 추천에 사용
- **백엔드**:
  - 사용자 기본 예산, 매운맛, 선호·비선호 카테고리와 알레르기 저장 API 구현
  - 추천 메시지 소유권을 검증하는 멱등 식사 기록 API와 Flyway V3 스키마 구현
  - `RecommendationContextService`가 취향과 최근 식사를 조립하고 예산·비선호·최근 식사·제로페이 조건을 결정론적 추천에 반영
  - `AiIntentAnalyzer`, 내부 요청·응답 계약, 임시 분석기와 장애 fallback 경계 구현
  - FastAPI 연결·응답 timeout, 최대 시도와 fallback 환경설정 계약 추가
- **프런트엔드**:
  - React Query 기반 취향 설정 화면과 저장 기능 구현
  - 추천 카드에 최근 3일 반영 안내와 `먹었어요` 버튼 및 기록 상태 표시
- **검증**:
  - 취향, 72시간 식사 범위, 추천 소유권, 제로페이 강제, 개인화 필터와 fallback 자동 테스트 추가
  - Docker 통합 검사에 취향 저장과 명시적·멱등 식사 기록 흐름 추가
- **제외 범위**: FastAPI 의도 분석 엔드포인트, 실제 HTTP 클라이언트, LLM과 Qdrant 검색은 다음 단계

## [2026-09-17] 인증·세션 보안 경계 및 검증 보완
- **목표**: 최초 인증 구현 검토에서 확인된 대화 소유권 누락, 세션 고정 방어 누락과 불완전한 통합 검사를 보완
- **백엔드**:
  - 모든 대화 API를 로그인 필수로 제한하고 서비스 계층에서 `conversations.user_id` 소유권 검증
  - 로그인 성공 시 `ChangeSessionIdAuthenticationStrategy`로 세션 ID 교체 후 보안 컨텍스트 저장
  - 중복 이메일을 `409 EMAIL_ALREADY_IN_USE`로 변환하고 인증 입력 길이 및 BCrypt 72바이트 제한 검증
  - 인증·세션 교체·대화 소유권 통합 테스트 추가
- **프런트엔드**:
  - 인증 확인 전 저장된 대화 이력 요청을 차단하고 로그아웃 시 메모리와 localStorage의 대화 상태 제거
  - 인증 API의 CSRF 헤더, 401 처리와 로그아웃 요청 테스트 추가
  - 임시 렌더링 로그 제거
- **검증 하네스**:
  - 임시 Puppeteer 프로젝트와 고정 `/tmp/cookies.txt` 제거
  - 통합 검사를 실제 회원가입→로그인→세션→대화 소유자 DB 저장→타 사용자 접근 거부→로그아웃 흐름으로 확장
- **문서화**: API 인증 조건, 대화 소유권, 세션 고정 방어와 통합 테스트 범위를 관련 문서에 반영

## [2026-09-17] 프런트엔드 인증 가드 무한 루프 버그 수정
- **목표**: 프런트엔드 초기 진입 시 "로딩 중..." 화면에서 무한 루프에 빠지는 이슈 해결
- **문제 원인**: React Query v5 환경에서, 인증되지 않은 상태(401 에러)일 때 렌더링된 `AuthScreen` 컴포넌트가 전역 훅인 `useAuth`를 다시 호출하면서 만료된(stale) 쿼리의 재요청을 유발. 이로 인해 로딩 상태(`isPending`)가 계속 `true`로 바뀌어 `App` 컴포넌트가 `AuthScreen`을 언마운트하고 다시 "로딩 중..."을 렌더링하는 현상이 초당 수천 번 발생(Nginx 502/401 무한 요청).
- **해결 방안**:
  - `frontend/src/hooks/useAuth.ts` 파일을 분리.
  - 전역 인증 상태를 조회하는 역할은 `useCurrentUser`로 분리하여 `App.tsx`에서만 호출하도록 변경.
  - 로그인/회원가입 등의 사이드 이펙트(Mutation) 기능은 `useAuthMutations`로 분리하여 `AuthScreen.tsx`에서만 호출하도록 변경.
- **결과**: 브라우저 렌더링 무한 루프 해결 및 정상적인 로그인/회원가입 모달 노출 확인. 프런트엔드 컨테이너 리빌드 완료.

## [2026-09-17] 사용자 인증 및 세션 시스템 구현
- **목표**: 사용자를 식별하여 개인화된 AI 추천을 제공하기 위한 기반 마련
- **백엔드 (Spring Boot)**
  - `User`, `UserCredentials` JPA 엔티티 및 DB 마이그레이션(V2) 작성
  - Spring Session JDBC 연동 및 MySQL 기반 세션 스토리지 적용
  - Spring Security를 활용하여 폼/베이직 인증 비활성화, `/api/auth/signup, login, logout, me, csrf` 엔드포인트 구현
  - `CookieCsrfTokenRepository` 설정 및 React 등 SPA 호환성을 위한 `CsrfTokenRequestAttributeHandler` 패치
  - `Conversation` 엔티티에 인증된 `userId`를 매핑하도록 구조 변경
- **프런트엔드 (React)**
  - `@tanstack/react-query`를 통한 전역 인증 상태(`useAuth`) 구현
  - `fetchWithAuth` API 래퍼를 통해 모든 요청 시 자동으로 `X-XSRF-TOKEN` 헤더와 인증 쿠키를 주입하도록 구성
  - `AuthScreen` 컴포넌트(로그인/회원가입 모달) 제작 및 `App.tsx` 인증 가드(미인증 시 채팅 제한) 적용
- **DevOps / Testing**
  - 통합 테스트 스크립트(`check-integration.sh`)에서 CSRF 토큰을 미리 발급받아 POST 요청 시 헤더에 첨부하도록 보강하여 통과 확인.
- **문서화**: `docs/api-contract.md`, `docs/database.md`, `docs/architecture.md`에 변경 사항 갱신 완료.
## 2026-09-20 — PCMap detail pipeline foundation

- Added public Apollo-state parser and typed detail models for place basics, hours, menus and review aggregates.
- Added conditional `/menu/list` and optional representative-review crawling over public HTTP.
- Added V13 normalized tables and idempotent Python persistence for menus, hours and review data.
- Added resumable CSV-first `app.place_pipeline_cli` (DB writes require explicit `--write-db`).
## 2026-09-20 — Playwright Apollo detail verification

- Reused the Place Resolver Playwright page/context for detail `/home` access and Apollo-state evaluation.
- Distinguished HTTP/Playwright Apollo absence and parse failures; missing identity is never reported as success.
- Added MATCHED-only 20-case report-only verification and retry-aware checkpoint filtering.
## 2026-09-20 — Apollo versus rendered DOM experiment

- Added a semantic-text DOM evidence parser and a CSV-only comparison CLI.
- Compared Apollo state and rendered DOM on the deterministic MATCHED 20-case sample without DB writes.
- Kept both parsers diagnostic; neither is promoted to full-detail success until menu/hour/review coverage is demonstrated.
## 2026-09-20 — Contract-based PCMap DOM collection

- Added selectors based on the supplied `data-nlog-area`, semantic labels, review list and `data-pui-click-code` contracts.
- Added actual 3-case deep check and repeated MATCHED 20-case report-only comparison.
- Kept Apollo as an observation channel; DOM output remains PARTIAL unless base, hours, menu and review semantic data are present.
## 2026-09-20 — STRONG_MATCH 제한 live Resolver 검증

- 기존 offline `STRONG_MATCH`이면서 verified checkpoint에 없던 12건만 report-only로 순차 검증했다.
- `--restaurant-id` 실행에서 모집단을 먼저 1건으로 자르던 하네스 오류를 수정해 지정 ID를 정확히 선택하도록 했다.
- Playwright PCMap 요청은 12건 범위에서만 수행했으며, DB write/NAVER Local API/full batch는 실행하지 않았다.
- 결과 CSV는 `ai/build/reports/naver-place-pipeline/strong-live-*-final.csv`에 보존했다.
## 2026-09-20 — report-only Place pipeline DOM detail 통합

- report-only 통합 pipeline의 상세 수집을 `PlaceDomDetailCrawler`로 전환했다.
- Resolver가 검증한 동일 Playwright page를 HOME 수집에 재사용하고, 같은 page에서 `/menu/list`와 `/review/visitor`로 이동한다.
- 메뉴 preview/booking 링크 대신 안정적인 public menu URL을 직접 사용한다.
- HOME/hours/menu/review section 상태와 개별 카운트를 CSV에 기록한다.
- Apollo는 report-only detail 경로에서 호출하지 않으며, 기존 write-db 호환 경로 외에는 사용하지 않는다.
## 2026-09-20 — write-db DOM 결과 매핑 통합

- report-only와 `--write-db`가 모두 `PlaceDomDetailCrawler`와 동일한 DOM 결과를 사용하도록 통합했다.
- DOM 결과를 공통 `PlaceDetail` persistence 모델로 변환하는 매핑을 추가했다.
- 메뉴/영업시간/리뷰 요약/키워드/대표 리뷰 upsert와 idempotency preview를 유지·확장했다.
- 이번 작업에서는 `--write-db`를 실행하지 않았고, 실제 DB와 checkpoint는 변경하지 않았다.
## 2026-09-20 — 단건 write 사전검증 중단

- restaurant 4280/Place 1618902912의 read-only 사전 snapshot을 수행했다.
- `restaurant_external_places`는 존재했지만 `restaurant_business_hours`가 로컬 DB에 없어 `ERROR 1146`로 실제 write 전에 중단했다.
- Flyway 이력은 V12까지이며 V13 detail tables가 적용되지 않은 상태였다.
- DB write, checkpoint write, 재실행, 나머지 음식점 처리는 수행하지 않았다.
## 2026-09-20 — V13 적용 및 4280 단건 write/idempotency 검증

- 기존 Spring Boot startup Flyway 경로로 V13을 적용했다.
- `restaurant_business_hours`, `restaurant_menus`, `restaurant_review_summaries`, `restaurant_review_keywords`, `restaurant_representative_reviews` 생성과 unique/FK 구조를 실제 MySQL에서 확인했다.
- 4280/Place 1618902912에 대해서만 DOM pipeline `--write-db`를 2회 실행했다.
- 두 번째 실행에서도 row count 증가 없이 upsert가 유지됨을 확인했다.
- verified checkpoint는 임시 checkpoint만 사용했으며 저장소의 checkpoint는 수정하지 않았다.
## 2026-09-20 — RESOLVED 11건 DB write 및 429 중단

- 신규 RESOLVED 11건에 대해 첫 번째 DOM pipeline `--write-db` pass를 완료했다.
- 두 번째 동일 pass는 4283 이후 PCMap HTTP 429가 발생해 즉시 중단했다.
- 성공한 DB 결과는 보존했으며, `verified-place-ids.csv`는 수정하지 않았다.
- 429 이후 재시도와 나머지 처리는 수행하지 않았다.
## 2026-09-20 — 11건 write 보존 및 429 batch stop/checkpoint

- 신규 RESOLVED 11건의 1차 DOM pipeline DB write 결과를 보존했다.
- pipeline이 `BLOCKED: HTTP 429`를 만나면 현재 batch를 즉시 중단하고 이후 대상을 처리하지 않도록 제어를 추가했다.
- 11건의 Place ID RESOLVED checkpoint를 반영했다. detail idempotency가 끝나지 않은 4288, 4294도 Place ID 상태만 반영했다.
- 2차 idempotency는 429 이후 중단됐으며 추가 live 요청은 수행하지 않았다.
## 2026-09-20 — 429 stop/resume control regression tests

- `BLOCKED:` 예외를 batch control에서 즉시 중단하고 exit code 2로 반환하도록 보강했다.
- 첫 BLOCKED 이후 다음 handler가 호출되지 않는 mock test를 추가했다.
- verified checkpoint가 `--force-resolve` 없이 Place ID를 재사용하는 control test를 추가했다.
- 보고 문구에서 고정 표본 크기 표현을 `KOMSCO 전체 모집단`으로 정리했다.
- 이번 작업에서는 NAVER live 요청, DB write, checkpoint 추가 변경을 수행하지 않았다.
