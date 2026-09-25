# ZeroPay Lunch AI — Place Identity 및 영속성 개선 검토 보고서

## 1. Executive Summary

이번 감사에서 확인된 직접 원인은 Numeric NAVER Place ID 저장 경로의 포괄적인 `ON DUPLICATE KEY UPDATE`였다. 이미 다른 `restaurant_id`가 소유한 `(provider, external_place_id)`에 대해 삽입을 시도하면, 충돌한 기존 행의 timestamp/query/status가 갱신될 수 있었다.

확인된 충돌은 다음과 같다.

| 대상 | 시도된 Place ID | 현재 소유자 | 결론 |
|---|---:|---:|---|
| 9619 우정양곱창 | 1921750340 | 9582 | 소유권 충돌. 저장/상세 진입 차단 |
| 9695 현대순대국 | 19882368 | 9661 | 소유권 충돌. 저장/상세 진입 차단 |

9582/9619와 9661/9695는 각각 이름·주소·좌표가 동일하거나 거의 동일해 동일 물리 장소를 참조할 가능성이 높지만, KOMSCO 가맹점 원본을 자동 병합하지 않았다. 현재 모델은 `restaurant_external_places`의 유일 제약으로 한 Place ID의 단일 소유자만 표현하며, 여러 가맹점이 하나의 물리 장소를 참조하는 관계를 명시적으로 표현하지는 못한다.

이번 구현에서는 신규 Migration 없이 저장 경로를 안전한 plain `INSERT`로 바꾸고, 동일 매핑 재실행만 no-op으로 허용했다. 다른 음식점 소유 ID의 덮어쓰기, 같은 음식점의 다른 ID 교체, 충돌 후 Detail 진입은 차단한다.

## 2. 현재 데이터 모델과 관계

현재 흐름은 다음과 같다.

```text
restaurants (KOMSCO 원본)
  → restaurant_naver_verifications / canonical_restaurants
  → restaurant_external_places (provider별 외부 mapping)
  → restaurant_detail_section_states 및 detail tables
```

`restaurant_id`는 KOMSCO 원본 가맹점의 식별자다. Canonical과 verification은 원본과 Provider 후보의 검증 결과를 저장한다. Numeric NAVER Place ID는 `restaurant_external_places`의 NAVER mapping에 저장되고, Detail은 해당 외부 mapping을 전제로 한다. 따라서 KOMSCO 가맹점 식별자와 외부 물리 장소 식별자는 같은 개념으로 취급하면 안 된다.

현재 `restaurant_external_places`에서 확인된 핵심 제약은 다음과 같다.

* `(restaurant_id, provider)` UNIQUE
* `(provider, external_place_id)` UNIQUE
* `restaurant_id` foreign key
* Numeric external ID는 nullable

이 제약은 동일 Provider의 동일 Place ID가 둘 이상의 가맹점에 저장되는 것을 막지만, 충돌 원인을 자동으로 “동일 장소의 중복 가맹점”으로 해석하지는 않는다.

## 3. 전체 DB 읽기 전용 감사

현재 개발 DB에서 활성 `restaurants`는 517건이다. 동일 또는 유사 주소를 공유하는 여러 restaurant_id 그룹이 존재하며, 이는 동일 장소 중복 또는 같은 건물/주소를 사용하는 별도 사업장을 모두 포함할 수 있다. 따라서 주소 중복만으로 자동 병합할 수 없다.

현재 DB에는 UNIQUE 제약 때문에 동일 `(provider, external_place_id)`가 여러 행으로 저장된 사례는 확인되지 않았다. 그러나 과거 report/ledger에는 충돌 시도와 동일 후보의 반복 기록이 남아 있어, 현재 중복이 없다는 사실만으로 과거 충돌 위험이 없었다고 판단할 수 없다.

과거 기록에서 9619는 1921750340 후보와 반복적으로 연결되었고, 9695는 19882368 후보와 연결되었다. 두 ID는 각각 현재 다른 restaurant_id가 소유한다.

## 4. 9582·9619 및 9661·9695 비교

### 9582·9619

* 원본명: `우정 양곱창` / `우정양곱창`
* 주소: 도산대로30길 23 계열
* 좌표: 9582와 9619가 동일한 좌표로 저장됨
* Canonical 주소: 서울특별시 강남구 도산대로30길 23 1층 우정양곱창
* Numeric Place ID: 1921750340은 9582 소유

동일 물리 장소일 가능성을 강하게 시사하지만, KOMSCO 가맹점 원본의 사업자 관계를 이 자료만으로 확정하지 않았다. 자동 병합이나 9619에 기존 9582의 자격/상태를 상속하지 않았다.

### 9661·9695

* 원본명: `현대순대국`
* 주소: 강남대로124길 20
* 좌표가 동일하게 저장됨
* Canonical 주소도 동일 계열
* Numeric Place ID 19882368은 9661 소유

마찬가지로 동일 장소 가능성은 있으나, 9695에 ID를 복사하거나 자동 병합하지 않았다.

## 5. 발견된 설계 문제와 적용한 개선

| 영역 | 기존 위험 | 현재 변경 |
|---|---|---|
| Numeric Place ID 저장 | 모든 duplicate key를 기존 행 update로 처리할 수 있음 | 충돌 가능한 Numeric mapping은 plain `INSERT` 사용 |
| 다른 restaurant 소유 ID | 기존 소유자의 timestamp/query/status 변경 가능 | duplicate 충돌을 CONFLICT로 기록하고 중단 |
| 같은 restaurant 재실행 | 동일 mapping 재삽입 시 실패 가능 | 기존 동일 mapping은 REUSED/no-op |
| 같은 restaurant의 다른 ID | 기존 ID를 조용히 교체할 위험 | 교체를 거부하고 명시적 오류 처리 |
| Place ID → Detail | 충돌 ID로 후속 수집할 위험 | 소유권 충돌 대상은 Detail 진입 차단 |
| 관측성 | MATCHED와 실제 저장 성공 구분 부족 | SAVED/REUSED/CONFLICT/FAILED 카운터 추가 |

수정 파일은 `ai/app/naver/place_id_linker_cli.py`, `ai/app/naver/place_resolver_cli.py`, `ai/app/batch/batch_progress.py` 및 관련 테스트다. 기존 Flyway migration은 수정하지 않았고 새 schema도 추가하지 않았다.

기존 unresolved/ambiguous 경로의 target-row upsert는 유지했다. 이는 Numeric Place ID 소유권을 다른 행으로 이전하는 경로와 분리되어 있으며, 이번 변경에서 검색·Qwen·Detail 정책을 바꾸지 않았다.

## 6. 충돌 상태와 후속 처리

현재 의미는 다음처럼 구분된다.

| 상황 | 처리 |
|---|---|
| 검색 결과 없음 | UNRESOLVED |
| 유효 후보가 여러 개 | AMBIGUOUS |
| Place ID가 다른 restaurant에 소유됨 | AMBIGUOUS + `PLACE_ID_EXTERNAL_ID_CONFLICT` |
| 같은 restaurant의 동일 mapping 재실행 | REUSED |
| 신규 mapping INSERT 성공 | SAVED |
| 기타 DB 오류 | FAILED 및 오류 전파 |

소유권 충돌은 단순한 검색 실패와 구별되며, 독립 검토 전에는 Detail 저장으로 진행하지 않는다. 동일 물리 장소를 여러 KOMSCO 가맹점이 참조해야 한다는 업무 규칙이 확정되면, 원본 가맹점과 물리 장소를 분리하는 별도 Venue 모델이 필요할 수 있다. 이번 작업에서는 그 의미를 추측해 기존 데이터를 병합하지 않았다.

## 7. 원자성 및 동시성 보호

애플리케이션의 선행 SELECT는 진단용일 뿐 최종 방어가 아니다. 최종 저장은 MySQL UNIQUE 제약을 가진 plain `INSERT`와 transaction에 맡긴다. SELECT와 INSERT 사이에 다른 worker가 먼저 저장해도 duplicate key가 발생하고 해당 작업만 실패/충돌 처리된다.

예전의 포괄적 `ON DUPLICATE KEY UPDATE` 경로를 Numeric mapping 성공 저장에 사용하지 않으므로, `(provider, external_place_id)` 충돌 때문에 기존 소유자의 timestamp/query/status를 변경하지 않는다.

## 8. 실제 MySQL 통합 검증

운영 테이블을 건드리지 않기 위해 동일한 UNIQUE 구조의 temporary table을 사용했다.

1. 9582/NAVER/1921750340을 정상 INSERT 후 COMMIT
2. 9619가 같은 ID를 INSERT 시도 → MySQL 1062, ROLLBACK
3. 9582가 다른 ID를 INSERT 시도 → `(restaurant_id, provider)` 충돌, 1062, ROLLBACK
4. 최종 행은 원래 9582 mapping 하나만 유지

결과: `A COMMIT / B ROLLBACK / C(실패 후 원상 유지)` PASS. 실제 운영 데이터, 9582/9619, 9661/9695의 영속 행은 변경하지 않았다.

9695의 제한적 정상 저장 검증은 수행하지 않았다. 후보 ID 19882368이 이미 9661에 소유되어 있어 안전한 신규 mapping이 아니기 때문이다. 따라서 9695의 Place ID 저장/Detail 성공을 보고하지 않는다.

## 9. Runtime Metric

Batch progress에 다음 Place ID persistence metric을 추가했다.

* `place_id_persisted`
* `place_id_reused`
* `place_id_conflicts`
* `place_id_persist_failures`

기존 candidate 확보·numeric candidate·rejected candidate·Local evidence·Canonical fallback metric과 함께 사용해야 한다. `MATCHED` 후보 확보와 실제 DB 저장 성공을 같은 수치로 세지 않도록 분리했다.

## 10. 테스트 결과

* Place ID/Resolver/Batch 관련 targeted tests: **78 passed**
* 전체 AI Harness: **165 passed, 1 warning**
* 실제 MySQL temporary-table transaction/unique 충돌 검증: **PASS**
* `git diff --check`: **PASS**
* Backend: 이번 변경에 schema/migration 변경이 없어 실행하지 않음
* Integration: 이번 변경에 schema/migration 변경이 없어 실행하지 않음
* 외부 Provider/Qwen/NAVER/Detail/전체 Batch: 실행하지 않음

## 11. 남아 있는 위험과 추가 Schema 검토

### 확인된 위험

과거 Numeric mapping 저장 경로의 broad upsert는 충돌 시 기존 소유자의 일부 필드를 갱신할 수 있었다. 이번 저장 경로는 이를 차단하지만, 과거에 이미 변경된 timestamp/query의 정확한 원래 값은 보존 자료가 없어 복원하지 않았다.

### 설계 검토 대상

현재 schema는 “한 Provider Place ID = 한 restaurant_id”를 강제한다. 실제 업무 규칙이 여러 KOMSCO 가맹점과 하나의 물리 장소를 공유하는 것을 허용한다면, `venue`와 restaurant-to-venue 연결을 별도 migration으로 설계해야 한다. 그 전에는 동일 장소로 보이는 두 원본을 자동 병합하거나 외부 mapping을 공유하지 않는 것이 안전하다.

Canonical/provider mapping의 의미와 Numeric NAVER mapping의 의미가 서로 다르므로, 향후 모든 저장 경로에 동일한 소유권 계약과 충돌 reason을 적용할지 별도 점검이 필요하다. 이번 작업에서는 범위를 넓혀 다른 알고리즘이나 schema를 변경하지 않았다.

## 12. 전체 Batch 진행 판단

코드상 충돌 overwrite 방어와 transaction/UNIQUE 보호는 검증되었다. 그러나 9582·9619, 9661·9695의 업무적 동일 장소 여부는 수동 검토가 남아 있다. 따라서 전체 513건 Batch는 다음을 확인한 뒤 진행하는 것이 안전하다.

1. 충돌 reason이 runtime report와 후속 selection에서 유지되는지 확인
2. 충돌 대상을 Detail에서 차단하는지 stage report로 확인
3. Venue 다대일 정책이 필요한지 사업 규칙 확정
4. 충돌 없는 신규 Place ID 1건을 별도 제한 범위에서 저장 검증

## 13. 안전 및 Git

* 기존 운영 데이터 자동 병합/삭제: 없음
* 기존 Flyway migration 수정: 없음
* 전체 Batch: 실행하지 않음
* 외부 Provider/Qwen/NAVER: 실행하지 않음
* Git add/commit/push: 하지 않음
* 기존 working tree 변경: 보존

현재 working tree에는 이번 변경 외의 기존 수정과 산출물도 함께 존재한다. 이를 정리하거나 되돌리지 않았다.
