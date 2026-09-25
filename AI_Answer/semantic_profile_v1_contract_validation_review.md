# ZeroPay Lunch AI — Semantic Profile v1 계약 수정 및 최종 검증

## 1. 결론

Evidence ID 기반 계약으로 9617을 1회 재생성했다. Qwen 응답은 JSON Schema 및 Evidence ID 존재 검증을 통과했고, Python이 입력 hash·버전·원본 source field를 부여했다.

모델이 반환한 5개 claim 중 근거 의미까지 대조한 결과 3개만 승인용 Profile에 포함했다. 2개는 Evidence ID 자체는 유효했지만 claim 내용이 근거보다 강하거나 일부 근거가 잘못 연결되어 제외했다.

따라서 **검증 가능한 Profile 1건은 확보했지만, 사업자/운영자 확인까지 완료된 최종 서비스 Profile은 아니다.** DB 저장·Embedding·Qdrant 적재는 하지 않았다.

## 2. Evidence Catalog

파일: [semantic_profile_v1_evidence_catalog_9617.json](semantic_profile_v1_evidence_catalog_9617.json)

* Catalog version: `semantic-profile-evidence-catalog-v1`
* 항목: 61개
* menu 20, keyword 35, representative review 3, business hours 1, identity 2
* catalog hash: `f02c59ad6d64b1b04da1b854875e65cab2ae1e85c128e68b36fd7b4cb77df64a`
* 각 항목은 Evidence ID, 원본 sourceField, 실제 content, section 상태, evidenceType을 가진다.

중복 메뉴는 compact 단계에서 합쳐졌지만 원본 메뉴 index를 sourceFields에 남겼다. 키워드는 항목별 mention count를 유지했다.

## 3. 변경된 출력 계약

LLM은 다음만 출력한다.

```json
{"profileStatus":"READY|PARTIAL|UNKNOWN","claims":[{"claimType":"...","text":"...","confidence":"...","evidenceIds":["E..."]}]}
```

LLM은 promptVersion, inputHash, source path를 출력하지 않는다. Python이 다음을 직접 부여한다.

* `profileVersion`: `semantic-profile-output-v2-evidence`
* compact input version/hash
* catalog version/hash
* restaurant/venue identity

허용 claim type은 `FOOD_TYPE`, `MENU_CHARACTERISTIC`, `TASTE`, `DINING_CONTEXT`, `VENUE_CHARACTERISTIC`이며 claim 유형별 허용 evidenceType도 Validator에서 제한한다.

## 4. Qwen 실행

* 모델: `qwen3.5:9b`
* 호출: 1회 / 최대 2회
* 응답 시간: 약 27.3초
* 결과: JSON 반환 및 Evidence ID 자동 검증 PASS
* Entity Resolution prompt/설정: 변경 없음

원본 실행 결과: [semantic_profile_v1_shadow_results.json](semantic_profile_v1_shadow_results.json)

## 5. Claim별 검증

| Claim | Evidence ID | 자동 검증 | 의미 검토 | 최종 |
|---|---|---|---|---|
| 김밥·떡볶이 음식 종류 | E003, E011 | PASS | 메뉴명이 직접 지지 | 승인 |
| 혼밥·빠른 식사 맥락 | E023, E058 | PASS | keyword와 대표 리뷰가 지지 | 승인 |
| 맛있음·가성비 고객 평가 | E024, E027 | PASS | 고객 언급으로 제한해 표현 | 승인 |
| 넓은 매장·역 위치 | E028, E057 | PASS | E057은 위치 근거가 아님 | 제외 |
| 다양한 튀김 메뉴 | E008, E014 | PASS | 근거가 ‘튀김’ 표현을 충분히 지지하지 않음 | 제외 |

`HIGH` confidence는 자동 승인 조건으로 사용하지 않았다. 승인된 TASTE도 모든 고객의 객관적 사실이 아니라 keyword 기반 고객 평가로 표현했다.

승인 Profile: [semantic_profile_v1_approved_9617.json](semantic_profile_v1_approved_9617.json)

Claim 검증 결과: [semantic_profile_v1_claim_validation_9617.json](semantic_profile_v1_claim_validation_9617.json)

사람인 사업자/운영자 검토는 수행하지 않았으며, 결과 파일에 명시했다.

## 6. 오프라인 검증 및 테스트

추가한 검증:

* Evidence Catalog 생성 및 hash
* Evidence ID 존재성
* Evidence ID → 원본 sourceField 매핑
* claim 유형별 evidence type 제한
* `PROFILE_READY` gate
* 메뉴/리뷰 근거 누락 차단
* compact dedup 및 source trace
* 기존 PARTIAL/LEGACY gate 유지

결과:

* Semantic Profile targeted tests: 6 passed
* AI Harness: PASS, 172 passed, 1 warning
* DB/Detail/Provider/NAVER 변경: 없음

## 7. 다음 단계

9617은 Evidence 기반 자동·의미 검토를 통과한 3개 claim으로 소규모 Profile 입력 후보가 되었다. 다만 human business-owner review는 별도 절차로 남아 있다.

9731 `ABSENT_CONFIRMED` 메뉴 및 9561 lifecycle 없는 legacy gate는 해제하지 않는다. Embedding/Qdrant는 승인 Profile의 품질 기준과 운영자 검토가 정해진 뒤 별도 실행한다.

## 8. 안전 및 Git

* DB 원본/Profile 저장: 없음
* Place ID/Venue/Detail 변경: 없음
* Provider Entity Resolution 변경: 없음
* 전체 Batch: 미실행
* Qwen 호출: 1회
* 기존 산출물: 보존
* commit/push/staging: 없음
