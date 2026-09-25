# ZeroPay Lunch AI — Venue 식별 및 E2E 영속성 통합 검증 보고서

## 1. Executive Summary

이번 검증의 결론은 다음과 같다.

1. 현재 자료만으로 KOMSCO 가맹점과 물리적 Venue의 다대일 관계를 확정할 수는 없었다. 9582/9619와 9661/9695는 동일 장소 가능성이 매우 높지만, 주소·좌표·상호만으로 자동 병합하거나 제로페이 자격을 공유해서는 안 된다.
2. 현 단계에서는 신규 Venue 테이블을 도입하지 않고, 기존 `restaurant_id`와 Provider Place ID의 분리 및 충돌 차단을 유지하는 것이 안전하다.
3. 실제 Python 애플리케이션 저장 함수로 격리 MySQL DB에서 신규 저장, 동일 재실행, 교차 소유권 충돌, ID 교체, 동시 저장을 검증했다.
4. 통합 테스트 중 `_existing_restaurant_place_id()`의 실제 MySQL JSON 행 파싱 결함을 발견해 최소 수정하고 회귀 테스트를 추가했다.
5. 신규 E2E 후보 `9673`은 Place ID dry-run에서 후보를 확보하지 못해 `UNRESOLVED`로 종료했다. 따라서 운영 Place ID/Detail 저장은 실행하지 않았다.

## 2. 장소 식별 관계 분석

현재 흐름은 다음과 같다.

```text
KOMSCO restaurants
  → verification / canonical_restaurants
  → restaurant_external_places
  → numeric NAVER Place ID
  → detail tables 및 section lifecycle
```

`restaurants.id`는 KOMSCO 원본 가맹점 식별자이고, Numeric NAVER Place ID는 외부 Provider의 물리 장소 식별자다. 현재 모델은 이 둘을 하나의 키로 합치지 않고 mapping 테이블로 연결한다. `recommendation_eligibility`와 NAVER verification도 별도 의미를 가진다.

현재 `restaurant_external_places`의 핵심 제약은 다음과 같다.

* `(restaurant_id, provider)` UNIQUE
* `(provider, external_place_id)` UNIQUE
* `restaurant_id` foreign key
* `external_place_id` nullable

따라서 같은 Provider Place ID의 다중 소유는 DB에서 금지되지만, “서로 다른 KOMSCO 가맹점이 동일 Venue를 합법적으로 참조한다”는 관계를 명시적으로 표현하지는 못한다.

## 3. 중복 의심 가맹점 조사

현재 개발 DB 읽기 전용 집계:

| 항목 | 수치 |
|---|---:|
| 활성 restaurants | 517 |
| 동일 주소 중복 그룹 | 32 |
| 동일 주소 중복 그룹에 속한 restaurant | 74 |
| 동일 좌표 중복 그룹 | 79 |
| Numeric NAVER mapping 보유 restaurant | 360 |
| 현재 중복 Provider/Place ID row | 0 |

현재 중복 row가 0인 것은 UNIQUE 제약이 작동하고 있다는 의미이지, 과거 충돌 시도나 동일 Venue 가능성이 없다는 뜻은 아니다.

### 9582 우정 양곱창 / 9619 우정양곱창

두 원본은 다음 자료가 일치한다.

* 상호 표기가 사실상 동일
* 도산대로30길 23 주소 계열
* 동일 좌표 `37.5184384, 127.0301249`
* 동일 Canonical 도로명 주소 계열
* Place ID `1921750340`은 현재 9582가 소유

동일 물리 장소일 가능성은 높다. 하지만 KOMSCO 가맹점의 사업자·제로페이 자격이 동일하다는 근거는 별도로 확인하지 않았으므로 자동 병합하지 않는다. 9619에 9582의 Place ID, Eligibility, Detail을 상속하지 않는다.

### 9661 현대순대국 / 9695 현대순대국

두 원본은 다음 자료가 일치한다.

* 상호 동일
* 강남대로124길 20 주소
* 동일 좌표 `37.5090540, 127.0242365`
* Canonical 주소 동일 계열
* Place ID `19882368`은 현재 9661이 소유

동일 장소 가능성은 높지만, 역시 업무적 동일 Venue로 확정할 근거가 부족하다. 9695에 ID를 복사하거나 Detail을 공유하지 않는다.

## 4. Venue 모델 결정

### 결정

이번 작업에서는 Venue 테이블을 도입하지 않는다.

### 근거

현재 확인된 것은 “동일 장소일 가능성이 높은 원본 쌍”이지, 여러 KOMSCO 가맹점이 하나의 물리 장소를 공유해야 한다는 업무 계약이 아니다. 자동 병합은 KOMSCO의 원본 자격, 추천 eligibility, verification provenance를 오염시킬 수 있다.

현재 모델은 다음 안전한 보수적 동작을 제공한다.

* KOMSCO 가맹점 row는 각각 보존
* 외부 Place ID는 한 `restaurant_id`에만 소유
* 다른 소유자의 ID를 덮어쓰지 않음
* 충돌 시 Detail 진입 차단
* 동일 Venue 여부는 수동/업무 검토로 보류

### 향후 Venue 모델이 필요해지는 조건

업무적으로 다대일 관계가 확정되면 다음 구조를 별도 설계해야 한다.

```text
restaurants
  → restaurant_venue_associations
  → venues
  → venue_provider_places
  → venue_detail_sections
```

이때도 `restaurants`의 제로페이 자격과 원본 상태는 각 row에 남겨야 한다. 기존 mapping/detail을 자동 이전하거나 병합하지 않고, 별도 association의 근거와 수동 승인 상태를 두어 단계적으로 전환해야 한다. Spring 추천은 association을 통해 동일 Venue 중복 노출을 제거하되, 기존 eligibility 조건과 충돌하지 않는 계약을 먼저 확정해야 한다. 이번 작업에서는 이 설계를 실행하거나 Migration을 추가하지 않았다.

## 5. 실제 애플리케이션 저장 코드 검증

### 격리 환경

운영 DB와 분리된 `zeropay_place_it_1790188426887` 테스트 DB를 생성하고 운영 테이블과 동일한 핵심 제약을 가진 `restaurant_external_places` 테이블을 복제했다. 운영 `zeropay_lunch` 데이터에는 테스트 row를 쓰지 않았다.

실제 호출 함수:

* `app.naver.place_resolver_cli._write_place_mapping`
* `app.naver.place_id_linker_cli._numeric_mapping_insert_sql`
* `app.naver.place_id_linker_cli._execute_sql_write`

검증 결과:

| 시나리오 | 결과 |
|---|---|
| 신규 mapping INSERT | PASS |
| 동일 restaurant·동일 ID 재실행 | PASS, no-op |
| 다른 restaurant의 동일 ID | PASS, RuntimeError/DB duplicate로 거부 |
| 동일 restaurant의 다른 ID 교체 | PASS, RuntimeError로 거부 |
| 두 worker의 동일 ID 동시 저장 | PASS, 한 건만 저장되고 다른 건 duplicate 실패 |
| 실패 후 기존 row의 ID/status/query/timestamp | PASS, 변경 없음 |

동시 저장 결과는 restaurant 10004만 test Place ID `70003`을 저장했고, restaurant 10003은 duplicate 오류로 실패했다. 정상 row의 timestamp/query/status는 변하지 않았다.

### 발견 및 수정한 실제 결함

`_mysql_rows()`는 JSON object 결과를 dict로 변환하는 방식인데, `_existing_restaurant_place_id()`가 일반 scalar SELECT를 사용하면서 int/string을 dict처럼 접근했다. 실제 통합 테스트에서 동일 mapping 재실행 시 `AttributeError`로 재현됐다.

수정:

* `ai/app/naver/place_resolver_cli.py`
* 조회를 `JSON_OBJECT('external_place_id', external_place_id)`로 변경
* 실제 DB 이름을 격리 테스트에 주입할 수 있도록 MySQL subprocess에 `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE` 전달

Place ID linker에도 동일한 DB 설정 전달을 적용했다. 기본값은 기존 `zeropay_lunch`와 기존 credential 정책을 유지한다.

## 6. 충돌 상태와 Detail 차단

현재 상태 의미는 다음과 같다.

| 상황 | 상태/동작 |
|---|---|
| 검색 후보 없음 | UNRESOLVED |
| 후보가 여러 개 | AMBIGUOUS |
| 다른 restaurant가 Place ID 소유 | `AMBIGUOUS` + `PLACE_ID_EXTERNAL_ID_CONFLICT` |
| 동일 mapping 재실행 | REUSED/no-op |
| 신규 mapping 성공 | SAVED |
| 저장 자체 오류 | FAILED/예외 전파 |

검색 후보 중복 AMBIGUOUS와 소유권 충돌은 runtime reason으로 구분해야 한다. 충돌 대상은 numeric mapping이 확정되지 않으므로 Detail 저장 대상이 되지 않는다.

## 7. 신규 음식점 1건 검증

### 선정 대상

`9673 이모왕곱창`을 선정했다.

* 활성 KOMSCO restaurant
* VERIFIED/ELIGIBLE
* Numeric NAVER mapping 없음
* 제외 목록(9582, 9619, 9661, 9695, 9610) 아님
* 기존 DB에서 동일 Numeric ID 소유 기록 없음

### 실행

DB write가 차단된 기존 Place ID linker dry-run 1회를 실행했다.

* 검색어: `논현동 이모왕곱창 본점`
* 결과: raw/numeric matching candidate 0
* 최종: `UNRESOLVED`
* Runtime report: `ai/build/reports/naver-place-pipeline/e2e/venue-e2e-20260924-9673-place_id.json`

동일 지점 Numeric ID를 확보하지 못했으므로 다음 단계는 실행하지 않았다.

* Place ID persistence: NOT RUN
* Detail dry-run: NOT RUN
* Detail persistence: NOT RUN
* Freshness 재실행: NOT RUN

따라서 이번 작업에서 신규 운영 음식점의 Place ID → Detail E2E 성공을 주장하지 않는다.

## 8. 테스트

* Place ID/Resolver/Batch targeted tests: **68 passed**
* AI Harness: **165 passed, 1 warning**
* 실제 Python 저장 함수 + 격리 MySQL 신규/재실행/충돌/교체/동시성 검증: **PASS**
* `git diff --check`: **PASS**
* Backend: Python 코드와 테스트만 변경되어 실행하지 않음
* Integration: Schema/Migration 및 Spring 계약 변경이 없어 실행하지 않음
* 외부 Provider/Qwen: 실행하지 않음
* NAVER Maps UI: Place ID dry-run 1회
* 전체 Batch: 실행하지 않음

## 9. 변경 파일과 안전성

이번 작업에서 변경한 source/test 핵심 파일:

* `ai/app/naver/place_resolver_cli.py`
* `ai/app/naver/place_id_linker_cli.py`
* `ai/tests/naver/test_place_resolver.py`

기존의 Place ID 충돌 보호 및 persistence metric 변경은 보존했다. 기존 Flyway Migration, 운영 데이터, 9582/9619, 9661/9695 mapping은 자동 병합·삭제·재지정하지 않았다.

격리 테스트 DB는 실제 운영 DB와 분리되어 있으며 테스트 결과 보존을 위해 삭제하지 않았다.

## 10. 전체 Batch 진행 판단

현재 저장 충돌 방어와 실제 애플리케이션 코드의 MySQL transaction/UNIQUE 동작은 검증되었다. 그러나 9673은 Provider/Maps 후보를 확보하지 못했고, Venue 다대일 업무 계약도 확정되지 않았다.

따라서 저장 계층 자체는 후속 제한 검증에 사용할 수 있지만, 전체 Batch를 즉시 실행하기 전에는 다음을 별도로 결정해야 한다.

1. 9582/9619 및 9661/9695의 사업자·Venue 관계 수동 확인
2. 소유권 충돌 대상의 재시도/검토 workflow
3. 충돌 없는 실제 Place ID 후보 1건의 제한적 Detail persistence 검증
4. 다대일 Venue가 업무 요구사항인지 여부

## 11. Git 및 실행 안전 확인

* 기존 운영 데이터 변경: 없음
* 기존 가맹점 자동 병합: 없음
* 기존 Flyway 수정: 없음
* 전체 Batch: 실행하지 않음
* Git add/commit/push: 하지 않음
* 기존 working tree 및 실행 산출물: 보존

현재 working tree에는 이번 작업 이전의 미커밋 변경과 산출물이 함께 존재하며, 이를 되돌리거나 정리하지 않았다.
