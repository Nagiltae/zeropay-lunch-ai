# ZeroPay Lunch AI — Semantic Profile v1 추론 안정화 및 생성 검증

## 1. Executive Summary

9617의 실제 DB 입력으로 Qwen3.5 9B Semantic Profile shadow 추론을 재검증했다. 경량 probe는 성공했고, Compact Input 사용 시 모델이 약 42초에 JSON을 반환했다. 그러나 반환 JSON의 sourceFields와 promptVersion이 계약과 달라 자동 검증에서 차단됐다.

따라서 이번 결과는 **Profile JSON 생성은 성공했지만, 승인 가능한 Semantic Profile 생성은 실패**다. `READY`라는 모델 출력만으로 승인하지 않았으며, DB·Profile 저장·Embedding·Qdrant는 실행하지 않았다.

## 2. Timeout 진단

| 항목 | 결과 |
|---|---|
| 모델 | `qwen3.5:9b`, 설치 확인 |
| Ollama | `localhost:11434` 응답 |
| 호스트 메모리 | 32 GiB |
| 경량 probe | 1.78초, 성공 |
| 모델 load duration | 약 4.8ms |
| 기존 전체 입력 30초 제한 | 2회 timeout |
| Compact 입력 첫 시도 | 약 57.9초 후 JSON 절단 |
| Compact 입력 두 번째 시도 | 약 49.5초 후 JSON 절단 |
| 최종 compact 시도 | 약 42.2초, JSON 반환 |

경량 probe와 모델 load 통계상 Ollama 기동·모델 최초 로딩만으로 30초가 소요된 것은 아니다. 입력/출력 생성과 구조화 응답 길이가 실제 병목으로 관찰됐다. `num_predict=1024`, `think=false`, temperature 0을 사용했으며 Entity Resolution 설정은 변경하지 않았다.

## 3. 입력 최적화

원본 입력은 19,796 bytes였다. Compact Input은 16,888 bytes로 저장됐고, 내부 JSON payload 기준 약 10,093 characters다.

* 메뉴: 24건 → 이름·가격 동일 항목을 합쳐 20건
* 원본 메뉴 ID와 원본 field path를 `sourceFields`에 보존
* 리뷰: 10건 중 의미 있는 길이의 3건 유지; `더보기`와 짧은 무의미 문구 제외
* 키워드: 35건, 중복 문자열 제거
* DB 수집 시각 등 추론에 직접 필요하지 않은 반복 메타데이터 축소

Compact 버전은 `semantic-profile-input-v1-compact-1`, hash는 `8ef69a4076176276a8dc029083f0c29dee9a6c1170615c7398064efeaab6d1a1`이다.

입력 파일: [semantic_profile_v1_input_9617_compact.json](semantic_profile_v1_input_9617_compact.json)

## 4. 실제 생성 결과

모델은 다음 5개 claim을 반환했다.

| Claim | 모델 Confidence | 자동 검증 |
|---|---|---|
| 매일 07:00–20:30 | HIGH | source path는 유효 |
| 논현역 내부 위치 | HIGH | 리뷰 path가 잘못됨 |
| 떡볶이·김밥·튀김 메뉴 | HIGH | 일부 path가 잘못됨 |
| 가성비·빠른 서비스 | HIGH | `review.keywords` 경로가 잘못됨 |
| 양이 많음 | MEDIUM | `review.keywords` 경로가 잘못됨 |

원본 모델 응답: [semantic_profile_v1_generated_output_9617.json](semantic_profile_v1_generated_output_9617.json)

자동 검증은 다음을 발견했다.

* JSON Schema/Pydantic 구조: PASS
* 입력 hash·버전: FAIL — 모델이 `promptVersion: v1.0`을 반환
* sourceFields: FAIL — `review.*`를 사용했으며 실제 계약 경로인 `sections.review.*`와 불일치
* 의미 검토: 자동 승인하지 않음

결론적으로 이 output은 참고용 shadow 결과이며 READY Profile로 승인하지 않았다.

## 5. 구현 및 회귀 테스트

수정 파일:

* `ai/app/semantic_profile_shadow.py`
  * Compact Input 생성
  * 메뉴 구조적 dedup
  * 리뷰/키워드 축약
  * 원본 sourceFields 보존
  * compact hash/version 기록
  * semantic 전용 timeout 120초 경로
  * 구체적 sourceFields 존재 검증
  * 출력 schema enum 및 hash/version 검증
* `ai/tests/test_semantic_profile_shadow.py`
  * compact dedup
  * sourceFields 보존
  * hash/version
  * 누락 source 차단
  * PARTIAL/LEGACY gate

이번 실험에서 Ollama 호출은 총 4회였다. 별도 유료 LLM·Provider·Naver·Detail 호출은 없었다.

## 6. 품질 Gate 결론

9617은 입력 품질 기준으로 계속 `PROFILE_READY`지만, 모델 output 계약 위반 때문에 생성 승인 상태는 `NOT_APPROVED`다. Qwen이 반환한 의미 중 영업시간 claim은 입력과 일치하지만, 나머지는 source path 계약을 고쳐 재생성하거나 수동 검토하기 전까지 승인하지 않는다.

9731 `PARTIAL_DATA`와 9561 `LEGACY_UNVERIFIED`의 gate는 이번에도 해제하지 않았다. 메뉴 부재는 메뉴 claim을 금지하고, lifecycle 없는 legacy row는 자동 Profile 생성을 금지한다.

## 7. 다음 단계

추가 호출 예산을 소진했으므로 같은 입력을 반복 실행하지 않았다. 다음 실행 전에는 다음 계약을 먼저 고쳐야 한다.

1. Prompt에 `sections.review.*` 등 정확한 source path를 예시와 함께 고정
2. 모델 반환 `promptVersion`을 강제 검증하고 불일치 시 UNKNOWN
3. compact sourceFields와 claim path의 매핑을 명시
4. 성공 output 1건을 수동 검토한 후에만 Embedding/Qdrant를 별도 검토

현재 상태에서는 다음 소규모 Profile Pilot을 바로 확대할 수 없다. 9617의 계약 위반을 해결하고 1건 재검증하여 자동·수동 검증을 모두 통과한 뒤 진행해야 한다.

## 8. 테스트 및 안전

* Semantic Profile targeted tests: PASS, 5 tests
* AI Harness: 변경 후 재실행 필요
* DB 변경: 없음
* Profile 영속화: 없음
* Embedding/Qdrant: 미실행
* Provider/Qwen Entity Resolution: 변경 없음
* 전체 Batch/Detail: 미실행
* Git add/commit/push: 안 함

구조화 결과: [semantic_profile_v1_inference_stabilization_results.json](semantic_profile_v1_inference_stabilization_results.json)
