# ZeroPay Lunch AI — Semantic Profile v1 Shadow Evaluation 보고서

## 1. Executive Summary

실제 MySQL의 9617 데이터를 읽어 `semantic-profile-input-v1` 입력을 생성하고, 입력 hash·품질 gate·sourceFields 검증기를 구현했다. 입력 생성은 성공했지만 Qwen Profile 결과는 생성되지 않았다. 설치된 `qwen3.5:9b`에 대해 제한된 호출 2회가 각각 30초 timeout으로 끝났으며, 다른 모델로 대체하지 않았다.

이번 실험은 report-only였다. Profile, Verification, Detail, Venue, Embedding, Qdrant 및 원본 DB에는 쓰지 않았다.

| 대상 | 입력 품질 판정 | Profile 호출 결과 |
|---:|---|---|
| 9617 | `PROFILE_READY` | Qwen timeout 2회, Profile 미생성 |
| 9731 | `PARTIAL_DATA` / 메뉴 `ABSENT_CONFIRMED` | quality gate 차단 |
| 9561 | `LEGACY_UNVERIFIED` / lifecycle 없음 | legacy gate 차단 |

## 2. 실제 입력 생성

생성기: `ai/app/semantic_profile_shadow.py`

9617 입력은 다음 실제 값을 포함한다.

* Restaurant: 9617, `(주)에스지푸드 논현역 마성떡볶이`
* Canonical: `마성떡볶이 논현역점`
* Canonical 주소: `서울특별시 강남구 학동로 지하 102 (논현동)` 및 도로명 상세 주소
* Numeric NAVER Place ID: `1987855627`, `MATCHED`
* Venue ID: `null` — 현재 확정·활성 Venue association이 없음
* 메뉴 24건, 가격 필드 원본 포함
* 영업시간 1건, lifecycle `SUCCESS`
* Review summary 1건, keywords 35건, 대표 리뷰 10건
* MENU/HOURS/REVIEW lifecycle 3건 모두 `SUCCESS`

입력 파일: [semantic_profile_v1_input_9617.json](semantic_profile_v1_input_9617.json)

정규화 JSON의 SHA-256 hash는 `21e99218d0088822128b821f5dc7f77ac3cf95d9ebd22b14e32a75c9fadf07c9`이다. SQL NULL은 JSON `null`로 보존했으며, 가격·영업시간을 추론하지 않았다.

## 3. 계약과 품질 Gate

Profile 입력 버전은 `semantic-profile-input-v1`, Prompt 버전은 `semantic-profile-prompt-v1`, 출력 계약은 `semantic-profile-output-v1`이다.

출력은 `profileStatus`, `claims[]`, `confidence`, `sourceFields`, `evidence`, `sectionEvidence`, 입력/Prompt 버전, `inputHash`를 요구한다. Python 검증기는 다음을 검사한다.

* Pydantic 구조 및 필수 필드
* 실제 입력에 존재하는 구체적인 `sourceFields` 경로
* 메뉴가 없는 경우 메뉴 claim 차단
* 입력 hash·버전 일치

이 검증은 Qwen의 의미 판단을 대체하지 않는다. claim이 실제 리뷰 문맥과 의미적으로 일치하는지, confidence가 적절한지는 수동 검토가 필요하다.

## 4. PARTIAL 및 LEGACY 검사

### 9731

입력 파일: [semantic_profile_v1_input_9731.json](semantic_profile_v1_input_9731.json)

MENU는 0건이며 앞선 수집 결과의 `ABSENT_CONFIRMED` lifecycle을 반영한다. Review keywords 39건과 대표 리뷰 10건은 입력 가능하므로 리뷰에 명시적으로 존재하는 표현만 claim 후보로 수동 검토할 수 있다. 메뉴 기반 특성·가격 claim은 생성 대상에서 제외한다. 자동 `PROFILE_READY` 승격은 하지 않았다.

### 9561

입력 파일: [semantic_profile_v1_input_9561.json](semantic_profile_v1_input_9561.json)

메뉴·시간·리뷰 row는 일부 존재하지만 lifecycle section이 없다. 따라서 legacy 데이터의 row 존재만으로 수집 성공을 확정하지 않고 Semantic Profile 자동 생성을 차단했다.

## 5. Qwen3 8B Shadow 실행

설정 모델은 `qwen3.5:9b`이며 Ollama `/api/tags`에서 설치 상태를 확인했다. 요청은 기존 Ollama HTTP client의 연결 재사용과 `num_predict=1024` 설정을 사용했으며 Entity Resolution prompt는 재사용하지 않았다.

* 호출 수: 2회 / 허용 최대 4회
* 결과: 2회 `LlmUnavailable: timed out`
* latency: 약 30,004ms, 30,003ms
* 구조화된 Profile output: 0건
* 실제 Profile 생성·저장: 하지 않음

원본 실행 결과: [semantic_profile_v1_shadow_results.json](semantic_profile_v1_shadow_results.json)

## 6. 결과 검증 및 재현성

입력 hash는 실제 DB snapshot을 정규화한 값이며 동일 입력 식별에 사용한다. 자동 테스트는 동일 계약, absent menu gate, lifecycle 부재 gate, sourceFields 미존재 경로 차단을 검증한다.

이번에는 Qwen output이 없으므로 claim의 의미적 일관성이나 동일 입력 재실행 간 Profile 의미 일관성은 검증되지 않았다. Timeout을 이유로 빈 결과를 READY로 보정하지 않았다.

상세 구조화 결과: [semantic_profile_v1_validation_results.json](semantic_profile_v1_validation_results.json)

## 7. 품질 Gate와 다음 계획

* `PROFILE_READY`: lifecycle 3개 `SUCCESS`, 가격이 확인된 메뉴, 구조화된 시작·종료 시간이 모두 있어야 shadow Profile 호출을 허용한다. 현재 표본은 9617 한 건이다.
* `PARTIAL_DATA`: ABSENT section은 결측으로 유지한다. 리뷰 근거가 명시적인 경우 claim 후보를 별도 수동 검토할 수 있지만 자동 Profile 승인은 하지 않는다.
* `LEGACY_UNVERIFIED`: lifecycle 없는 legacy row는 representative sampling으로 실제 DOM 재확인 후에만 재분류한다. 354건 전체 재수집은 하지 않는다.
* Embedding/Qdrant: Profile output이 계약·source evidence·수동 품질 검토를 모두 통과한 경우에만 후속 단계로 진행한다.

권장 다음 표본은 legacy 중 Numeric ID 소유권이 명확하고 메뉴·리뷰·시간의 과거 row가 모두 존재하는 소수 표본, 그리고 ABSENT_CONFIRMED의 대표 표본이다. 실제 재수집 예산과 승인 후 진행한다.

## 8. 변경 파일 및 테스트

변경/추가:

* `ai/app/semantic_profile_shadow.py` — 읽기 전용 입력 생성, 품질 gate, shadow client 호출, output validator
* `ai/tests/test_semantic_profile_shadow.py` — 입력 계약/hash, sourceFields, absent/legacy gate 회귀 테스트
* `AI_Answer/semantic_profile_v1_input_9617.json`
* `AI_Answer/semantic_profile_v1_input_9731.json`
* `AI_Answer/semantic_profile_v1_input_9561.json`
* `AI_Answer/semantic_profile_v1_shadow_results.json`
* `AI_Answer/semantic_profile_v1_validation_results.json`

테스트:

* Semantic Profile targeted: PASS, 4 tests
* AI Harness: PASS, 170 passed, 1 warning
* Backend/Integration: 이번 변경은 Python report-only 경로이며 실행하지 않음
* 외부 Provider/NAVER/Detail: 실행하지 않음

## 9. 안전 및 Git

* DB 영속 데이터 변경: 없음
* Profile 저장: 없음
* Embedding/Qdrant: 없음
* Provider Entity Resolution 및 매칭 정책 변경: 없음
* 기존 Detail/Place ID/Venue 변경: 없음
* 전체 Batch: 실행하지 않음
* 기존 산출물: 보존
* source/test/migration 변경: source 1개, test 1개 추가; migration 없음
* commit: 안 함
* push: 안 함
* staged: 없음
