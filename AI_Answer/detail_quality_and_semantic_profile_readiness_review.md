# ZeroPay Lunch AI — Detail 데이터 품질 감사 및 Semantic Profile 준비 보고서

## 1. Executive Summary

현재 활성·`ELIGIBLE`·Numeric NAVER MATCHED 대상은 360건이다. 단순 row 존재 기준으로는 325건이 메뉴·영업시간·Review Summary를 모두 갖지만, Section Lifecycle이 없는 legacy 데이터가 대부분이므로 이 수치를 곧바로 Profile 생성 가능 건수로 취급하지 않았다.

분석용 분류 기준을 적용한 결과:

| 그룹 | 건수 | 의미 |
|---|---:|---|
| PROFILE_READY | 1 | 세 section SUCCESS, 가격 메뉴 존재, 구조화 영업시간 존재 |
| PARTIAL_DATA | 5 | lifecycle은 있으나 메뉴 부재 또는 반복 시간 미확보 |
| REFRESH_REQUIRED | 0 | 확인 가능한 section이 TTL 초과하지 않음 |
| LEGACY_UNVERIFIED | 354 | lifecycle 없음. row가 있어도 수집 성공을 확정하지 않음 |
| COLLECTION_FAILED | 0 | 현재 lifecycle FAILED 없음 |
| IDENTITY_CONFLICT | 0 | 현재 대상의 MATCHED mapping 충돌 없음 |

제한적 재수집은 5건 dry-run, 3건 실제 저장으로 수행했다.

* 9654, 9731, 9750: DOM 수집 성공, 메뉴 부재를 `ABSENT_CONFIRMED`로 저장
* 9667: 메뉴·리뷰 완결성 부족으로 dry-run 실패, DB 저장 없음
* 9758: DOM 수집 성공했으나 실제 저장 대상에서 제외
* 3건 저장 후 메뉴·시간·리뷰 section lifecycle과 Snapshot을 확인
* 3건 재실행은 `preexisting_skipped=3`, target/navigation 0으로 종료했다

현재 보수적 기준의 Semantic Profile 생성 가능 음식점은 1건이다. Profile 생성, Qwen 호출, embedding, Qdrant 적재는 실행하지 않았다.

## 2. 감사 범위와 판정 기준

감사 모집단:

```text
restaurants.active = 1
recommendation_eligibility = ELIGIBLE
restaurant_external_places.provider = NAVER
match_status = MATCHED
external_place_id = numeric
```

현재 개발 DB 집계:

| 항목 | 건수 |
|---|---:|
| 활성 Restaurant | 517 |
| Numeric NAVER MATCHED + ELIGIBLE | 360 |
| 메뉴 row 보유 대상 | 325 |
| 영업시간 row 보유 대상 | 360 |
| Review Summary row 보유 대상 | 360 |
| 메뉴·시간·Review Summary 모두 row 보유 | 325 |
| Section Lifecycle 보유 Restaurant | 6 |
| Venue | 0 |
| Restaurant-Venue Association | 0 |

`restaurant_menus`·`restaurant_business_hours`·`restaurant_review_summaries`의 row 존재는 성공이나 최신성을 뜻하지 않는다. Lifecycle이 없으면 `LEGACY_UNVERIFIED`로 분리했다. 시간 row가 존재해도 `open_time`·`close_time`이 NULL인 상태 문구 row는 반복 영업시간으로 인정하지 않았다.

## 3. 품질 그룹 세부 의미

### PROFILE_READY

다음 조건을 모두 만족해야 한다.

* Numeric Place ID 소유권 충돌 없음
* menu section `SUCCESS`
* 가격이 숫자 또는 비어 있지 않은 가격 텍스트로 하나 이상 확인됨
* business hours에 반복 요일과 시작·종료 시간이 구조화됨
* review section `SUCCESS`
* 세 section checked_at이 freshness TTL 안에 있음

현재 9617 `마성떡볶이 논현역점`이 이 기준에 해당한다. 이는 Profile 생성 승인 대상이라는 분석 결과이지, 실제 Profile을 생성했다는 뜻은 아니다.

### PARTIAL_DATA

현재 lifecycle이 확인되지만 Profile 입력에 필요한 정보가 일부 부족한 경우다.

* 9559, 9560: 세 section은 SUCCESS지만 active business-hour row가 상태 문구이며 반복 시간이 NULL
* 9654: 메뉴 ABSENT_CONFIRMED, 영업시간은 상태 문구 기반 SUCCESS
* 9731, 9750: 메뉴 ABSENT_CONFIRMED, 영업시간은 일부 구조화됨

ABSENT_CONFIRMED 메뉴는 수집 실패가 아니라 정상적으로 메뉴가 노출되지 않았다는 snapshot 근거가 있는 상태지만, Profile에는 `menuAvailability=ABSENT_CONFIRMED`로 남기고 메뉴 취향 정보를 생성하지 않는다.

### LEGACY_UNVERIFIED

354건은 section lifecycle이 없다. 이 중 일부는 메뉴·시간·리뷰 row가 모두 있지만, parser 성공·정상 snapshot·checked_at의 section 의미가 보존되지 않았으므로 PROFILE_READY로 승격하지 않는다.

### REFRESH_REQUIRED / COLLECTION_FAILED / IDENTITY_CONFLICT

이번 읽기 전용 감사에서 현재 확인 가능한 stale section은 없었다. `FAILED` lifecycle도 없었다. Numeric MATCHED row 자체의 소유권 충돌도 확인하지 않았다. 과거 충돌 이력 대상은 별도 제외 정책을 유지하며 이 감사 모집단에 자동 재편입하지 않았다.

## 4. 제한적 Detail 재수집

### 선정 대상

기존 충돌·동일성 검토 대상 9582, 9619, 9661, 9695, 9610은 제외했다. 비음식업종 가능성이 높은 `엠케이카써비스`, 디자인 업체 등도 대상에서 제외했다.

선정한 5건:

| ID | 이름 | Numeric Place ID | 가설 |
|---:|---|---:|---|
| 9654 | 지리산황토골토종흑돼지 | 1696442585 | 메뉴 부재가 실제 NAVER 부재인지 확인 |
| 9667 | 희(HEE) | 31055061 | 메뉴·리뷰 부재와 parser 실패 구분 |
| 9731 | 카메스시 | 1271618346 | 메뉴 부재와 구조화 시간 확인 |
| 9750 | 종로떡집 | 13511111 | 메뉴 부재와 구조화 시간 확인 |
| 9758 | 예삐네집 | 37414426 | 메뉴 부재와 리뷰/시간 snapshot 확인 |

모두 기존 Numeric mapping의 `NAVER/MATCHED` 소유권을 READ-ONLY로 확인했다. Provider/Qwen은 재실행하지 않았다.

### Dry-run

report:

`ai/build/reports/naver-place-pipeline/e2e/detail-quality-audit-20260924-01-detail.json`

실측:

| 항목 | 결과 |
|---|---:|
| 대상 | 5 |
| DOM 수집 success | 4 |
| incomplete failure | 1 (9667) |
| retry / blocked / HTTP 429 | 0 / 0 / 0 |
| menu navigation | 5 |
| review navigation | 5 |
| hours 수집 | 5 |
| 평균 처리시간 | 약 12.9초/건 |
| DB write | 없음 |

9654·9731·9750·9758은 DOM이 정상적으로 응답했지만 메뉴가 0건이었다. 9667은 메뉴 0건이고 review 결과도 완결되지 않아 `_collected_sections_complete`가 false가 되었고 저장하지 않았다.

### 실제 저장

실행 전 snapshot:

`AI_Answer/detail_quality_snapshot_before_9654_9731_9750.json`

실행 report:

`ai/build/reports/naver-place-pipeline/e2e/detail-quality-audit-20260924-02-detail.json`

정확히 3건을 저장했다.

| ID | 저장 결과 | MENU | HOURS | REVIEW |
|---:|---|---|---|---|
| 9654 | SUCCESS | ABSENT_CONFIRMED | SUCCESS | SUCCESS |
| 9731 | SUCCESS | ABSENT_CONFIRMED | SUCCESS | SUCCESS |
| 9750 | SUCCESS | ABSENT_CONFIRMED | SUCCESS | SUCCESS |

실제 DOM에서 9654는 영업 상태 문구만 있고 open/close가 NULL이었다. 따라서 반복 영업시간을 추론하지 않았다. 9731·9750은 active 구조화 요일 row가 확인됐고, 기존 상태 문구 row는 inactive로 남았다.

실행 후 snapshot:

`AI_Answer/detail_quality_snapshot_after_9654_9731_9750.json`

저장 결과의 핵심:

* Numeric Place ID·mapping 소유권 변경 없음
* 메뉴 row를 임의 생성하지 않음
* 정상 Review Summary/keywords/representative review 보존
* 정상 snapshot에 대해서만 reconciliation 수행
* 실패한 9667은 persistence하지 않음
* 대상 외 음식점의 의도하지 않은 변경 없음

## 5. Section Lifecycle 및 보존 평가

현재 lifecycle은 section별로 다음을 표현한다.

```text
SUCCESS
ABSENT_CONFIRMED
FAILED
```

이번 저장에서 메뉴 0건은 DOM 메뉴 페이지가 정상 응답했기 때문에 `ABSENT_CONFIRMED`가 됐다. parser/navigation 자체가 실패한 경우에는 FAILED로 저장되어 기존 row를 보호해야 한다.

9654의 `business_hours`는 lifecycle상 SUCCESS지만 실제 row는 상태 문구와 NULL 시간이다. 따라서 lifecycle SUCCESS를 “구조화된 반복 영업시간 존재”로 해석하지 않고, Profile 품질 판정에서 PARTIAL_DATA로 낮췄다. 이는 현재 DB 상태를 변경한 것이 아니라 분석 기준을 보수적으로 적용한 것이다.

## 6. Semantic Profile 입력 계약

Profile 입력은 Restaurant 또는 명시적으로 검증된 Venue를 기준으로 하나만 생성한다. 현재 Venue association이 없으면 `venueId: null`이고 `restaurantId`를 identity key로 사용한다. CONFIRMED + ACTIVE Venue가 생긴 경우에만 `(venueId, providerPlaceId)`를 dedup key 후보로 사용하며, 원본 Restaurant의 Eligibility를 합치지 않는다.

### 권장 JSON 입력 예시

```json
{
  "schemaVersion": "semantic-profile-input-v1",
  "restaurantId": 9617,
  "venueId": null,
  "identity": {
    "canonicalName": "마성떡볶이 논현역점",
    "canonicalAddress": "서울 강남구 학동로 지하 102",
    "provider": "NAVER",
    "providerPlaceId": "1987855627",
    "ownership": "MATCHED",
    "sourceCheckedAt": "2026-09-23T20:00:00+09:00"
  },
  "sections": {
    "menu": {
      "state": "SUCCESS",
      "fresh": true,
      "items": [
        {
          "name": "떡볶이",
          "priceValue": 4000,
          "priceText": null,
          "source": "NAVER_DOM",
          "collectedAt": "2026-09-23T20:00:00+09:00"
        }
      ]
    },
    "businessHours": {
      "state": "SUCCESS",
      "fresh": true,
      "structured": true,
      "days": [
        {"dayOfWeek": "매일", "openTime": "07:00", "closeTime": "20:30", "breakHours": null}
      ],
      "statusText": null,
      "source": "NAVER_DOM",
      "collectedAt": "2026-09-23T20:00:00+09:00"
    },
    "review": {
      "state": "SUCCESS",
      "fresh": true,
      "summary": {"visitorTotal": 10, "visitorScore": 4.2},
      "keywords": ["매콤함"],
      "representativeReviews": [],
      "source": "NAVER_DOM",
      "collectedAt": "2026-09-23T20:00:00+09:00"
    }
  },
  "quality": {
    "profileEligible": true,
    "missingFields": [],
    "warnings": []
  }
}
```

위 값은 계약 예시이며, 존재하지 않는 음식점 데이터나 임의의 취향을 뜻하지 않는다.

### Structured Output Schema 초안

```json
{
  "type": "object",
  "required": ["restaurantId", "profileStatus", "claims", "evidence"],
  "properties": {
    "restaurantId": {"type": "integer"},
    "venueId": {"type": ["integer", "null"]},
    "profileStatus": {"enum": ["READY", "PARTIAL", "INSUFFICIENT", "IDENTITY_REVIEW"]},
    "claims": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["kind", "value", "confidence", "sourceFields"],
        "properties": {
          "kind": {"type": "string"},
          "value": {},
          "confidence": {"enum": ["HIGH", "MEDIUM", "LOW", "UNKNOWN"]},
          "sourceFields": {"type": "array", "items": {"type": "string"}}
        }
      }
    },
    "evidence": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["section", "state", "collectedAt"],
        "properties": {
          "section": {"enum": ["MENU", "BUSINESS_HOURS", "REVIEW"]},
          "state": {"enum": ["SUCCESS", "ABSENT_CONFIRMED", "FAILED", "LEGACY_UNVERIFIED"]},
          "collectedAt": {"type": ["string", "null"]},
          "source": {"type": ["string", "null"]}
        }
      }
    }
  }
}
```

Qwen은 제공된 evidence에서 의미를 요약할 수 있지만, 없는 메뉴·가격·영업시간·재료·취향을 생성하거나 상태 문구에서 반복 시간을 추론해서는 안 된다. `FAILED`, `LEGACY_UNVERIFIED`, `ABSENT_CONFIRMED`는 각각 구분하여 profile eligibility를 낮춘다.

## 7. 결측 및 출처 원칙

* 메뉴 0건 + 정상 메뉴 페이지: `ABSENT_CONFIRMED`; 메뉴 취향 claim 생성 금지
* selector/DOM/parser/navigation 오류: `FAILED`; 기존 정상 row 보존
* lifecycle 없음: `LEGACY_UNVERIFIED`; Profile 자동 생성 금지
* open/close NULL인 상태 문구: `structured=false`; 주간 반복 시간 추론 금지
* 가격 NULL: 가격 claim 생성 금지; 기존 가격을 NULL로 덮어쓰지 않음
* 리뷰 요약 없음: 리뷰 취향 claim 생성 금지
* source, externalPlaceId, checked/crawled time을 모든 section evidence에 포함
* ID 충돌 또는 Venue 동일성 검토 중: `IDENTITY_REVIEW`; Profile 생성 금지

## 8. 테스트 및 실행 결과

| 검증 | 결과 |
|---|---|
| Detail dry-run 5건 | 4 success, 1 incomplete failure |
| Detail 실제 persistence | 3 success, 0 failure |
| AI Harness | 166 passed, 1 warning |
| Backend Harness | PASS |
| Integration Harness | PASS |
| 관련 Detail/section 회귀 테스트 | AI Harness에 포함, PASS |
| 외부 Provider/Qwen | 미실행 |
| 전체 Batch | 미실행 |
| `git diff --check` | PASS |

이번 단계는 Python/Backend source를 변경하지 않고 기존 수집 계약과 persistence를 사용했다. 따라서 신규 코드 회귀 테스트를 추가하지 않았다.

보존된 runtime report:

* `ai/build/reports/naver-place-pipeline/e2e/detail-quality-audit-20260924-01-detail.json`
* `ai/build/reports/naver-place-pipeline/e2e/detail-quality-audit-20260924-02-detail.json`
* `ai/build/reports/naver-place-pipeline/e2e/detail-quality-audit-20260924-03-detail.json`

## 9. 다음 단계 진행 조건

1. LEGACY_UNVERIFIED 354건을 기존 row 존재만으로 Profile에 포함하지 않는다.
2. 메뉴 부재와 parser 실패를 lifecycle로 계속 분리한다.
3. 9654처럼 상태 문구만 있는 영업시간은 Profile READY로 승격하지 않는다.
4. PROFILE_READY 1건으로 소규모 Qwen Profile shadow evaluation을 먼저 수행한다.
5. Profile 출력의 각 claim에 source field와 confidence를 보존한다.
6. CONFIRMED Venue가 실제로 생기기 전에는 Restaurant 단위 identity를 사용한다.
7. Embedding/Qdrant 적재는 Profile 품질 검토와 샘플링 이후에 시작한다.

## 10. Git 및 데이터 보호

* 기존 Flyway migration 수정: 없음
* 기존 Place ID 변경: 없음
* Venue association 자동 생성: 없음
* Provider/Qwen 재실행: 없음
* 대상 외 Detail 의도적 변경: 없음
* 전체 Batch: 실행하지 않음
* Git add/commit/push: 하지 않음
* 기존 working tree 및 report/snapshot 보존: 유지
