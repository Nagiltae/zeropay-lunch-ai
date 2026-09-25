# ZeroPay Lunch AI — Adaptive Search 및 NAVER 매칭 구조 검증

## 1. Executive Summary

이번 검토는 전체 Batch나 대량 외부 요청 없이 현재 소스, 개발 DB의 읽기 전용 집계, 기존 Runtime/분석 산출물을 대조한 결과다.

| 구분 | 결론 |
|---|---|
| Adaptive Search 조기 종료 | 코드상 가능함. Kakao 후보로 ACCEPT되면 Round 2를 실행하지 않으며, NAVER_LOCAL 0건이어도 최종 ACCEPT가 가능하다. |
| 이번 실패의 직접 원인 | 9576·9599는 기존 NAVER Maps UI 검색 및 주소 보강 검색에서 HTTP 200이지만 `place/bus = null`, 파싱 후보 0건으로 확인됐다. |
| 조기 종료가 이번 실패를 만들었다는 증거 | 확인되지 않음. 두 음식점의 최초 Provider/Qwen 호출 기록이 보존되어 있지 않아 Kakao-only ACCEPT 여부를 입증할 수 없다. |
| NAVER Local 근거와 Place ID | 강한 연관은 관찰되지만 인과관계는 확정할 수 없다. Local mapping 보유 328건 중 numeric MATCHED 315건, Local mapping 미보유 185건 중 numeric MATCHED 45건이다. |
| 코드 수정 | 없음. 현재 확인된 실패는 매칭 기준을 완화하거나 검색어를 무제한 추가할 근거가 아니라 Provider/NAVER 색인 및 데이터 품질 문제로 판단된다. |
| 테스트 | AI Harness `161 passed` 재확인. 외부 Provider/NAVER 요청과 전체 Batch는 실행하지 않았다. |

따라서 현재 상태는 **구조적 coverage 위험은 확인되었으나, 9576·9599의 직접 원인으로 확정할 수 없는 상태**다. 후속 확대 전에는 NAVER Local 근거가 없는 VERIFIED 결과를 별도 관측·보강할 정책을 설계해야 하지만, 이번 검토에서는 그 정책을 구현하지 않았다.

## 2. 확인 범위와 증거 수준

확인한 범위:

- `ai/app/entity_resolution/provider_entity_resolution_cli.py`
- `ai/app/naver/place_id_linker_cli.py`
- 관련 Provider/Qwen/Place ID 테스트
- `AI_Answer/final_5_pilot_validation_review.md`
- `AI_Answer/place_id_matching_root_cause_review.md`
- `AI_Answer/pre_final_e2e_implementation_review.md`와 `AI_Answer/e2e_provider_qwen_stall_diagnostic.md`는 현재 working tree의 `AI_Answer/`에 존재하지 않아 읽을 수 없었다.
- 개발 MySQL의 활성 모집단·verification·external mapping·detail 관련 읽기 전용 집계

증거 표기:

- **확인됨**: 현재 코드, DB 집계, 보존된 실행 결과로 직접 확인한 내용
- **코드상 가능**: 현재 구현으로 발생할 수 있으나 해당 음식점의 과거 실행 증거가 없는 내용
- **미확인**: 로그·DB에 필요한 provenance가 없어 확정할 수 없는 내용

외부 Provider/NAVER 요청, Entity Resolution 재실행, 전체 Batch는 수행하지 않았다.

## 3. 현재 Main 흐름과 Adaptive Search

현재 주요 흐름은 다음과 같다.

```text
KOMSCO reference
  → ProviderPrefetch Round 1
  → Kakao/NAVER Local 후보 merge 및 structural dedup
  → single candidate 또는 Qwen choose
  → validate_many/single fallback
  → Verification decision
  → Canonical persistence
  → Place ID Linker의 NAVER Maps UI 검색
```

핵심 구현은 `provider_entity_resolution_cli.py`의 다음 함수/클래스에 있다.

- `_provider_query_rounds()`: Provider별 Round 1/2 query를 만든다.
- `ProviderPrefetch.submit()`: 지정된 round의 Kakao와 NAVER Local 요청을 병렬 제출한다.
- `evaluate_reference()`: 후보 merge, Qwen 선택/검증, 최종 decision을 계산한다.
- `_should_expand_search()`: `REJECT` 또는 `UNKNOWN`일 때만 추가 검색을 허용한다.
- `place_id_linker_cli.py`: NAVER Local mapping과 무관하게 Canonical 이름/주소를 fallback으로 사용해 Maps UI를 검색한다.

### 3.1 Round별 query

현재 코드 기준으로 다음과 같다.

| Provider | Round 1 | Round 2 |
|---|---|---|
| Kakao | KOMSCO 이름 | `논현동 + 이름` 및 보수적 fallback |
| NAVER_LOCAL | `논현동 + KOMSCO 이름` | KOMSCO 이름 및 보수적 fallback |

`ProviderPrefetch.submit(reference, round_number=1)`은 Round 1에 두 Provider pool을 모두 제출한다. Prefetch가 모든 Round를 미리 요청하는 구조는 아니며, Round 2는 별도 `submit(..., round_number=2)` 호출이 있어야 실행된다.

### 3.2 Kakao-only ACCEPT 경로

현재 `evaluate_reference()`는 후보별 Qwen 결과를 모아 최종 decision을 만들며, Kakao와 NAVER_LOCAL 양쪽 ACCEPT가 반드시 있어야만 ACCEPT하도록 강제하지 않는다. 따라서 다음 경로가 코드상 가능하다.

```text
Kakao 후보 ACCEPT
NAVER_LOCAL 후보 0건
→ 최종 ACCEPT 가능
→ decision이 ACCEPT이면 _should_expand_search() false
→ Round 2 미진입
→ Canonical/VERIFIED 저장 경로 가능
```

이는 semantic 판단을 deterministic 코드가 대신한다는 뜻은 아니다. Qwen의 ACCEPT를 코드가 임의로 뒤집는 문제가 아니라, **NAVER_LOCAL coverage를 ACCEPT의 전제조건으로 두지 않은 현재 orchestration 정책**이다.

## 4. VERIFIED Cache와 NAVER 근거 coverage

Orchestrator selection은 동일 source fingerprint의 확정 결과를 선행 skip한다.

현재 의미는 대략 다음과 같다.

| 상태 | 동일 fingerprint 처리 |
|---|---|
| VERIFIED | Entity Resolution skip |
| REJECTED | 확정 REJECT cache 재사용 및 skip |
| ERROR/UNKNOWN | reason/TTL에 따라 재처리 여부 판단 |
| fingerprint 변경 | cache보다 우선하여 재검증 |

중요한 점은 **VERIFIED에 NAVER_LOCAL 근거가 반드시 포함되어야 한다는 조건이 없다**는 것이다. 따라서 Kakao-only ACCEPT가 실제로 저장되었다면 이후 VERIFIED cache가 Provider 재검색을 막고, NAVER_LOCAL 근거를 사후 보강하지 못할 수 있다.

현재 활성 DB 집계는 이 coverage gap의 규모를 보여준다.

| 항목 | 수량 |
|---|---:|
| KOMSCO 활성 음식점 | 513 |
| VERIFIED | 401 |
| VERIFIED + NAVER_LOCAL mapping | 328 |
| VERIFIED - NAVER_LOCAL mapping | 73 |
| VERIFIED + numeric NAVER MATCHED | 360 |
| VERIFIED + NAVER_LOCAL 없음 + numeric 없음 | 28 |

다만 `restaurant_naver_verifications`의 `search_policy_version`은 전체 512건이 NULL이고 `provider-search-v2`는 1건뿐이다. 또한 과거 후보별 Provider provenance가 DB에 모두 보존되어 있지 않다. 그러므로 VERIFIED 73건이 모두 Kakao-only ACCEPT였다고 해석할 수 없다.

### 4.1 Numeric ID와 Local mapping의 비교

활성 모집단의 external mapping 집계는 다음과 같다.

| 상태 | 수량 |
|---|---:|
| NAVER_LOCAL mapping과 numeric NAVER MATCHED 모두 보유 | 315 |
| NAVER_LOCAL mapping 보유, numeric MATCHED 없음 | 13 |
| NAVER_LOCAL mapping 없음, numeric NAVER MATCHED 보유 | 45 |
| 둘 다 없음 | 140 |

계산상 Local mapping 보유 그룹의 numeric MATCHED 비율은 약 96.0%(315/328), Local mapping 미보유 그룹은 약 24.3%(45/185)다. 이는 NAVER Local evidence가 후속 Place ID 연결에 유용한 신호라는 점을 보여주지만, mapping 생성 시점·데이터 품질·Canonical fallback 차이가 함께 섞여 있으므로 인과관계나 정확도 보장은 아니다.

반대로 Local mapping이 없어도 45건은 numeric MATCHED이므로, Place ID Linker가 Local mapping을 절대 전제하는 구조는 아니다.

## 5. 실패 대상 집중 분석

### 5.1 9576 — 호별관

| 단계 | 확인 결과 |
|---|---|
| KOMSCO | `호별관`, 논현동 대상 원본 주소 |
| Canonical | `호별관`, 원본과 대응하는 주소로 저장됨 |
| Kakao mapping | MATCHED |
| NAVER_LOCAL mapping | 없음 |
| Numeric NAVER mapping | UNRESOLVED |
| Place ID query | `논현동 호별관` 및 보존된 주소 보강 검색 |
| NAVER Maps 결과 | HTTP 200이지만 `rcode=09350720`, `place=null`, `bus=null`; 후보 0건 |

기존 `place_id_matching_root_cause_review.md`에 보존된 결과에서는 기본 query와 주소 보강 query 모두 UI 후보 0건이었다. 따라서 현재 가장 직접적인 증거는 **Numeric ID 추출기에서 후보를 버린 것이 아니라 NAVER Maps UI 검색 결과가 비어 있었다**는 것이다.

과거 Entity Resolution에서 Kakao-only ACCEPT였는지, NAVER_LOCAL Round 1이 0건이었는지, Round 2가 실행되지 않았는지는 현재 DB/보존 report만으로 확인할 수 없다.

### 5.2 9599 — 육덕패밀리

| 단계 | 확인 결과 |
|---|---|
| KOMSCO | `(주)육덕패밀리`, 주소 `학동로4길 45` |
| Canonical | `육덕패밀리`, 도로 주소 `학동로4길 49` |
| Kakao mapping | MATCHED |
| NAVER_LOCAL mapping | 없음 |
| Numeric NAVER mapping | UNRESOLVED |
| Place ID query | `논현동 육덕패밀리` 및 보존된 주소 보강 검색 |
| NAVER Maps 결과 | HTTP 200이지만 `rcode=09350720`, `place=null`, `bus=null`; 후보 0건 |

KOMSCO 주소와 Canonical 도로 주소가 45/49로 다르다는 데이터 품질 신호가 있다. 이것만으로 잘못된 Canonical이라고 확정할 수는 없지만, 주소 일치 검증에 불리한 상태다. 기존 UI 검색 결과가 0건이므로 현재 증거만으로 C형(추출 후 주소 검증 탈락)이라고 분류할 수 없다. 가장 적절한 분류는 **A/E 후보: 검색 결과 부재 또는 NAVER UI 색인/응답 문제; Canonical 주소 불일치는 별도 품질 위험**이다.

### 5.3 9604 — 지유가오카핫쵸메7호점, 9627 — 파니나로

두 대상 모두 최근 Pilot에서 NAVER mapping이 `UNRESOLVED`로 남았다. 이번 검토에서는 기존 보존 자료를 우선 사용했고, 새로운 UI 검색을 반복하지 않았다. 따라서 각 대상의 실패를 A~E 중 하나로 단정할 충분한 raw UI 증거는 없다. 9610 AMBIGUOUS는 사용자 지시대로 이번 검증의 외부 대상에서 제외했다.

## 6. 정상 비교 대상 — 9617

9617은 실패 대상과 달리 다음 단계가 모두 연결된 정상 사례다.

| 단계 | 확인 결과 |
|---|---|
| KOMSCO | `(주)에스지푸드 논현역 마성떡볶이`, 학동로 지하 102 |
| Canonical | `마성떡볶이 논현역점`, 논현역 지하 주소 |
| NAVER_LOCAL | 동일 상호/주소 mapping 저장 |
| Numeric NAVER | `1987855627`, MATCHED |
| Detail | HOME/MENU/HOURS/REVIEW 저장 및 lifecycle 검증 |

9617은 NAVER Local mapping과 Maps numeric ID가 모두 존재해 비교에 유용하지만, 성공 사례 하나만으로 Adaptive Search가 성공 원인이라고 확정할 수 없다. 다만 실패 대상과의 가장 뚜렷한 구조적 차이는 **후속 Place ID 단계에서 사용할 NAVER Local 이름·주소 evidence가 존재한다는 점**이다.

## 7. Place ID Linker의 현재 동작

`ai/app/naver/place_id_linker_cli.py`는 NAVER_LOCAL mapping이 없더라도 다음 fallback을 사용한다.

```text
NAVER_LOCAL external_name/address가 있으면 사용
없으면 canonical name/address 사용
→ 논현동 {target_name} 검색
→ allSearch 응답에서 numeric ID 후보 파싱
→ 이름 및 주소 EXACT/STRONG_MATCH 검증
→ MATCHED/AMBIGUOUS/UNRESOLVED 저장
```

따라서 NAVER_LOCAL 0건 자체가 곧바로 Place ID 실패를 일으키는 필수 조건은 아니다. 그러나 후보 검색어와 검증에 사용할 provider-specific 주소가 줄어들어 recall이 낮아질 수 있다. 9576·9599에서는 fallback Canonical 검색까지 수행했지만 UI 응답 자체가 0건이었으므로, 현재 보존 자료상 실패는 후단 parser 필터보다 앞에서 발생했다.

## 8. 원인 분류

| 원인 후보 | 현재 판단 | 근거 |
|---|---|---|
| A. 검색어 부정확 | 가능성 있음, 확정 불가 | 9599는 법인 표기가 제거된 Canonical query를 사용했지만 UI 0건; 검색어 품질 문제와 색인 문제를 분리할 raw 후보가 부족함 |
| B. 후보는 있으나 numeric ID 추출 실패 | 9576·9599에는 해당 없음 | 보존된 UI 응답에서 `place/bus=null`, 파싱 전 후보 0건 |
| C. ID 추출 후 이름/주소 검증 탈락 | 9576·9599에는 해당 없음 | numeric candidate 자체가 확인되지 않음 |
| D. Canonical/NAVER Local 정보 불일치 | 9599에 위험 신호 | KOMSCO `학동로4길 45` vs Canonical `학동로4길 49`; 실제 지점 불일치는 미확인 |
| E. NAVER UI/DOM/색인 문제 | 9576·9599에서 강한 후보 | HTTP 200이지만 `rcode=09350720`, UI 결과 객체 없음 |

현재 확인된 사실만으로는 성공률을 높이기 위한 matcher 완화, 임의 Place ID 생성, 다른 지점 재사용을 정당화할 수 없다.

## 9. 기존 deterministic Match 결과 활용 가능성

과거 numeric MATCHED 결과와 existing mapping은 읽기 전용 근거로 활용할 수 있다. 다만 현재 정책상:

- Place ID는 Maps UI allSearch 응답의 numeric `place_id`/`data-nlog-params`에서 추출해야 한다.
- URL, 이름 유사도, 주소 일부만으로 numeric ID를 추정하면 안 된다.
- 과거 MATCHED를 신규 실패 대상의 정답으로 전이하면 안 된다.
- 9610 AMBIGUOUS는 재검증 없이 MATCHED로 바꾸면 안 된다.

이번 실패 대상에는 재사용 가능한 동일 지점 numeric ID 근거가 없으므로, 기존 deterministic 결과로 UNRESOLVED를 덮을 수 없다.

## 10. 확인된 결함과 수정 여부

이번 검토에서 새로 확인되어 수정해야 할 명확한 결함은 없었다.

기존 코드에는 다음과 같은 구조적 coverage 위험이 확인된다.

1. Round 1 Kakao-only ACCEPT가 가능하고, 그 경우 Round 2가 끝난 뒤가 아니라 즉시 종료된다.
2. VERIFIED cache는 NAVER_LOCAL evidence 보유 여부를 별도로 요구하지 않는다.
3. DB의 대부분 verification row는 `search_policy_version`이 NULL이고 과거 provider별 provenance가 부족하다.

이 세 가지는 후속 정책 설계 대상이지만, 이번 작업에서 무조건 NAVER 요청을 추가하거나 VERIFIED cache를 일괄 무효화하면 외부 호출량·정확도·기존 데이터 의미를 바꾼다. 따라서 코드 수정 없이 위험과 측정 필요성을 보고한다.

## 11. 제한적 실환경 검증

이번 검토에서는 기존 보존 결과가 9576·9599의 기본 및 주소 보강 UI 검색을 이미 포함하므로 동일 검색을 반복하지 않았다.

| 항목 | 결과 |
|---|---:|
| 추가 Kakao/NAVER Local 요청 | 0 |
| 추가 NAVER Maps UI 요청 | 0 |
| Qwen 호출 | 0 |
| DB write | 0 |
| 전체 Batch | 실행하지 않음 |
| AI Harness | `161 passed`, 1 warning |

## 12. 후속 데이터 수집 정책 제안

이번 보고서는 정책을 구현하지 않는다. 다음 Batch 확대 전에 검토할 최소 관측 항목은 다음과 같다.

- 각 ACCEPT 결과에 `kakao_candidate_count`, `naver_local_candidate_count`, accepted provider set을 runtime report에 남길 것.
- NAVER_LOCAL 0건인 ACCEPT와 NAVER_LOCAL evidence가 있는 ACCEPT를 분리 집계할 것.
- VERIFIED cache skip 사유와 `search_policy_version`을 함께 기록할 것.
- NAVER Local 근거가 없는 VERIFIED를 전부 자동 재처리하지 말고, 명시적 소규모 보강 대상 목록으로 제한할 것.
- Place ID 단계에서 Local evidence 사용 여부, Canonical fallback 여부, UI raw candidate count를 기록할 것.

특히 9599처럼 원본/Canonical 주소가 다른 경우는 Provider search 문제가 아니라 Canonical/source data quality 검토 대상으로 별도 분리해야 한다.

## 13. 다음 Batch 확대 가능 여부

**조건부 가능.**

- 현재 코드·테스트에는 새 결함이 발견되지 않았고 AI Harness는 통과했다.
- 그러나 NAVER Local 근거 없는 VERIFIED 73건과 search policy provenance가 NULL인 512건 때문에, 전체 Batch 전에 NAVER coverage를 관측할 수 있는 report 보강 또는 명시적 소규모 보강 계획이 필요하다.
- 9576·9599의 직접 실패는 NAVER UI 결과 0건으로 보이며, 해결되지 않은 상태에서 매칭 기준을 완화해 확대하면 오매칭 위험이 있다.
- 전체 Batch는 이번 작업에서 실행하지 않았다.

## 14. Git 및 안전 확인

```text
source code 수정: 없음
test 수정: 없음
migration 수정: 없음
외부 요청: 없음
DB write: 없음
git add: 안 함
git commit: 안 함
git push: 안 함
```

이번 작업에서 새로 작성한 파일은 이 보고서뿐이다. 기존 Working Tree와 기존 실행 산출물은 보존했다.

