# ZeroPay Lunch AI — NAVER Coverage Targeted Pilot Review

## 1. Executive Summary

현재 활성 DB는 517건이며, 그중 VERIFIED는 401건이다. Numeric NAVER Place ID가 없는 VERIFIED는 41건으로 집계됐다.

| 그룹 | 정의 | 대상 수 |
|---|---|---:|
| A | NAVER_LOCAL mapping 존재 + numeric NAVER ID 없음 | 13 |
| B | NAVER_LOCAL mapping 없음 + numeric NAVER ID 없음 | 28 |

비교 대상은 기존 실패/AMBIGUOUS 대상을 제외하고 A 2건(9619, 9695), B 2건(9604, 9627)으로 선정했다.

실험 결과:

- NAVER Local API 4회: 모두 `HTTP_401`. 인증 실패이므로 후보 0건으로 분류하지 않았다.
- NAVER Maps UI dry-run 4회: 9619·9695 MATCHED, 9604·9627 UNRESOLVED.
- 추가 외부 요청: 8회(제한 12회).
- Qwen 호출: 0회.
- DB write: 0회.
- Numeric ID 저장: 0건.
- 전체 Batch: 실행하지 않음.

이번 표본에서는 그룹 A 2건이 UI에서 MATCHED되었고 그룹 B 2건은 UNRESOLVED였지만, NAVER Local 요청이 인증 실패했으므로 Local evidence의 인과 효과는 검증하지 못했다. 또한 표본 4건으로 전체 517건의 성공률을 추정할 수 없다.

## 2. 현재 전체 DB 분류

읽기 전용 개발 DB 집계 기준:

- 활성 KOMSCO: 517건
- 활성 VERIFIED: 401건
- 활성 VERIFIED + numeric NAVER MATCHED: 360건
- 활성 VERIFIED + numeric ID 없음: 41건
- 그중 NAVER_LOCAL mapping 보유: 13건
- 그중 NAVER_LOCAL mapping 미보유: 28건

기존 수치 513/401은 현재 DB와 달라졌으므로 이번 보고서는 현재 517건을 기준으로 한다. 검색 정책 버전은 대부분 보존되어 있지 않다. `restaurant_naver_verifications.search_policy_version`은 512건 NULL, `provider-search-v2`는 1건이었다.

현재 DB만으로는 그룹 B가 과거 Kakao-only ACCEPT였다고 확정할 수 없다. Provider별 후보와 accepted provider provenance가 대부분 과거 DB에 보존되지 않았기 때문이다.

## 3. 관측성 개선

Provider/Qwen 쪽 기존 report에는 이미 다음이 있었다.

- Kakao/NAVER 후보 수
- Round 1/2 request count
- dedup 전/후 수
- Qwen choose/validate/validate_many/fallback
- 선택 후보의 provider/external ID
- cache skip 및 reason count
- search policy version

이번에 부족했던 Place ID report만 최소 보강했다.

추가 필드:

- `place_id_queries`
- `place_id_local_evidence`
- `place_id_canonical_fallback`
- `place_id_raw_candidates`
- `place_id_numeric_candidates`
- `place_id_rejected_candidates`

이 필드는 검색 기준이나 MATCHED 조건을 변경하지 않고, raw 후보 → numeric 후보 → 이름/주소 검증 통과 후보의 수만 집계한다. 후보 원문이나 인증정보는 report에 저장하지 않는다.

주의: 이번 실제 dry-run은 관측성 패치 이전 실행이므로 새 Place ID 필드는 해당 runtime JSON에 아직 없다. 후속 실행부터 기록된다.

## 4. 비교 대상과 가설

| ID | 그룹 | 상태 | 가설 |
|---:|:---:|---|---|
| 9619 | A | 우정양곱창 | NAVER_LOCAL mapping은 있으나 numeric ID가 없으므로 Local evidence가 UI 연결에 유리할 수 있음 |
| 9695 | A | 현대순대국 | 동일 |
| 9604 | B | 지유가오카핫쵸메7호점 | Local evidence가 없고 Canonical fallback만으로는 UI matching이 어려울 수 있음 |
| 9627 | B | 파니나로 | 동일 |

기존 9576·9599는 기본 및 주소 보강 UI 검색 결과 0건이 이미 보존되어 있어 반복하지 않았다. 9610 AMBIGUOUS도 제외했다.

## 5. 음식점별 실제 결과

### 9619 — 그룹 A

- NAVER Local query: `논현동 우정양곱창`
- NAVER Local: `HTTP_401`, 후보 판정 불가
- Maps UI query: `논현동 우정양곱창`
- 결과: MATCHED
- Numeric ID: `1921750340`
- DB 저장: 하지 않음

MATCHED는 기존 Linker의 이름·주소 EXACT/STRONG_MATCH 계약을 통과했다는 실행 결과다. 다만 이 실행은 dry-run이고, raw candidate 상세를 이전 report가 보존하지 않아 독립적인 수동 동일지점 검토에는 제한이 있다.

### 9695 — 그룹 A

- NAVER Local query: `논현동 현대순대국`
- NAVER Local: `HTTP_401`, 후보 판정 불가
- Maps UI query: `논현동 현대순대국`
- 결과: MATCHED
- Numeric ID: `19882368`
- DB 저장: 하지 않음

### 9604 — 그룹 B

- NAVER Local query: `논현동 지유가오카핫쵸메7호점`
- NAVER Local: `HTTP_401`, 후보 판정 불가
- Maps UI query: `논현동 지유가오카핫쵸메 7호점`
- 결과: UNRESOLVED
- Numeric ID: 없음
- DB 저장: 하지 않음

### 9627 — 그룹 B

- NAVER Local query: `논현동 파니나로`
- NAVER Local: `HTTP_401`, 후보 판정 불가
- Maps UI query: `논현동 파니나로`
- 결과: UNRESOLVED
- Numeric ID: 없음
- DB 저장: 하지 않음

## 6. 실패 원인 분류

| 분류 | 이번 대상 결과 |
|---|---|
| A. Local/Maps 모두 결과 없음 | 판정 불가. Local은 HTTP_401이므로 실제 0건이 아님 |
| B. Local 후보는 있으나 Maps 없음 | 판정 불가 |
| C. Maps 결과는 있으나 numeric 추출 실패 | 확인되지 않음 |
| D. numeric ID 후 이름/주소 탈락 | 9604·9627에는 후보 결과가 없어 확인되지 않음 |
| E. 유효 후보 여러 개/AMBIGUOUS | 이번 4건에서 없음 |
| F. 원본/Canonical 품질 문제 | 이번 실험만으로 확인되지 않음 |
| G. 동일 지점 numeric ID 확인 | 9619·9695는 기존 Linker 계약상 MATCHED |

9576·9599의 과거 결과는 별도 보고서와 같이 NAVER Maps UI 응답 자체가 0건이었다. 이번 비교 결과와 합쳐도 Local API 인증이 복구되기 전에는 Local evidence 유무에 따른 원인 비교를 완료할 수 없다.

## 7. 기존 Batch 최적화의 영향

코드상 Kakao-only ACCEPT 후 NAVER_LOCAL 0건으로 Round 2가 생략될 수 있고, VERIFIED cache가 이후 Entity Resolution을 skip할 수 있다는 coverage 위험은 기존 분석에서 확인됐다.

그러나 이번 4건에 대해서는:

- Provider/Qwen 재실행을 하지 않았다.
- 과거 accepted provider provenance가 없다.
- NAVER Local API가 인증 실패했다.

따라서 이번 실패를 Adaptive Search 조기 종료의 결과라고 확정하지 않는다. 이번 UI 결과만으로는 그룹 B의 Local 근거 부족이 원인인지, NAVER Maps 색인/검색어 문제인지 분리할 수 없다.

## 8. 외부 요청 및 처리시간

| 항목 | 수량/결과 |
|---|---:|
| NAVER Local 요청 | 4회, 모두 HTTP_401 |
| NAVER Maps UI 요청 | 4회 |
| 총 신규 외부 요청 | 8회 |
| Qwen | 0회 |
| DB write | 0회 |
| UI MATCHED | 2건 |
| UI UNRESOLVED | 2건 |
| UI AMBIGUOUS | 0건 |

Place ID dry-run runtime report:

`ai/build/reports/naver-place-pipeline/e2e/20260924-coverage-025415-place_id.json`

- run_id: `20260924-coverage-025415`
- target: 4
- processed: 4
- matched: 2
- unresolved: 2
- ambiguous: 0
- blocked: 0
- elapsed: 16.011초
- 평균: 4.003초/건

실제 DB 저장은 하지 않았으므로 해당 numeric ID는 DB에 반영되지 않았다.

## 9. 확인된 코드 결함과 수정

새로운 매칭 알고리즘 결함은 확인되지 않았다.

수정한 관측성:

- `ai/app/batch/batch_progress.py`
- `ai/app/naver/place_id_linker_cli.py`
- `ai/tests/batch/test_batch_progress.py`

추가 테스트:

- Local evidence 사용/Canonical fallback 집계
- raw/numeric/rejected 후보 수 집계
- 음수 후보 수 방지

검색 순서, query, 이름·주소 검증 기준, AMBIGUOUS 보호, DB 저장 조건은 변경하지 않았다.

## 10. NAVER 데이터 부족 대상 처리 정책

이번 작업에서 새 상태나 DB 컬럼은 추가하지 않았다.

현재 권장 정책:

1. NAVER Local API 인증을 먼저 복구한다. HTTP_401 상태에서는 후보 0건으로 분류하지 않는다.
2. Local 후보 0건, Maps UI 0건, parser 실패, 주소 검증 탈락을 서로 다른 runtime reason으로 기록한다.
3. Numeric ID가 없으면 UNRESOLVED/AMBIGUOUS를 유지하고 다른 지점 ID를 추측하지 않는다.
4. VERIFIED cache를 전체 무효화하지 말고, Local 근거 없음·numeric 미확보 대상만 명시적으로 제한해 보강한다.
5. 9599처럼 KOMSCO/Canonical 주소가 다른 경우에는 매칭 완화가 아니라 source/canonical 품질 검토 대상으로 분리한다.

## 11. 다음 DB 저장 대상

현재 비교 결과만으로 DB 저장을 승인할 대상은 없다.

- 9619·9695: MATCHED 실행 결과는 있으나 이번 작업 요구상 DB 저장을 하지 않았고, raw UI 후보 상세가 보존되지 않아 다음 단계에서 독립 확인 후 저장해야 한다.
- 9604·9627: UNRESOLVED이므로 저장하지 않는다.
- Local API 인증 복구 전에는 Local mapping 보유 여부에 따른 비교 결론을 확정하지 않는다.

## 12. 테스트

- Targeted tests: 16 passed
- AI Harness: 162 passed, 1 warning
- 외부 Provider/Qwen: Qwen 미실행
- NAVER Local: 4회, 모두 HTTP_401
- NAVER Maps UI: 4회 dry-run
- Backend/Integration: 소스/스키마 변경이 없어 실행하지 않음

## 13. 보존 파일 및 안전 확인

- 진단 결과: `AI_Answer/naver_coverage_targeted_pilot_raw_results.json`
- Place ID runtime report: `ai/build/reports/naver-place-pipeline/e2e/20260924-coverage-025415-place_id.json`
- 보고서: `AI_Answer/naver_coverage_targeted_pilot_review.md`

```text
DB write: 없음
기존 Verification/Canonical/Detail 변경: 없음
기존 AMBIGUOUS 강제 재검증: 없음
전체 Batch: 실행하지 않음
git add: 안 함
commit: 안 함
push: 안 함
```

