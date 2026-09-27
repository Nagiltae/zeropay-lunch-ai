# Serving Model v2 — Business Hours Multi-Interval Fix

## 결과

`restaurant_business_hours`는 이전에 `(provider, external_place_id, day_of_week)` unique key를 사용했고 Python detail persistence가 동일 키에 `ON DUPLICATE KEY UPDATE`를 실행했다. DOM parser는 반복된 요일과 시간 range를 각각 `BusinessHour`로 만들 수 있었지만, 같은 요일의 두 번째 row가 첫 번째 row를 덮어썼다. 기존 deactivation도 day만 비교해 구간 단위 생명주기를 표현하지 못했다.

신규 Flyway `V22__support_multiple_naver_hours_intervals.sql`은 `interval_index INT NOT NULL DEFAULT 0`을 추가하고 unique key를 `(provider, external_place_id, day_of_week, interval_index)`로 바꾼다. 기존 데이터는 삭제·재작성하지 않으며 모두 기본 index `0`을 유지한다. Python persistence는 요일별 원본 순서 index로 upsert하고, 성공 snapshot에서 누락된 요일/index 조합만 inactive 처리한다. Spring 조회는 여러 source row를 이미 목록으로 전달하므로 조회 계약 변경은 없다.

## 검증

- Python parser/persistence targeted: 36 passed; same weekday `11:00–15:00`, `17:00–22:00` 파싱과 SQL의 index 0/1 저장을 확인.
- Spring `VerifiedHoursPolicyTests` 및 `VerifiedNaverServingCandidateServiceTests`: 통과.
- 전체 `./scripts/check-backend.sh`: PASS (compile/test/build).
- 회귀 사례: 단일 당일 구간, 동일 요일 복수 interval, overnight `18:00–02:00`, `00:00–24:00`, 반복 휴무, 현재 날짜 휴무, break interval, 불명확 휴무/break의 `UNKNOWN`.
- H2 Flyway test에서 V22 migration을 실행했다. MySQL Docker 통합 harness는 공유 개발 DB fixture 및 사용자 데이터를 변경할 수 있어 이번 실행에서는 NOT_RUN이다. 따라서 MySQL 실엔진 migration 적용은 아직 검증하지 않았다.

## 저장된 과거 원문 복구 가능성

READ-ONLY 현재 개발 DB 조회는 활성 NAVER 영업시간 412행/412 place-day key였고, 저장된 `description` 안에 같은 요일이 서로 다른 두 시간 구간과 함께 반복되는 signature는 0행이었다. 확인 가능한 저장된 source evidence에서 정확히 재파싱해 복구 가능한 split interval은 0건이다. 이미 덮어써진 구간을 추측해 복원하지 않았다. 그 외 잠재적 유실 건의 전체 수는 저장 evidence만으로 확인할 수 없어 UNKNOWN이며, 발견될 경우 개별 bounded recrawl이 필요하다. 이번 작업은 NAVER 재수집을 하지 않았다.

## 제한

이번 변경은 신규/재수집 snapshot이 동일 요일 다중 구간을 보존하게 한다. 모든 기존 Restaurant를 자동 재수집하거나 serving state를 바꾸지 않았고, 402곳 broad crawl도 실행하지 않았다. 기존 `VerifiedHoursPolicy`는 여러 row를 union 방식으로 평가하며, 어느 interval에도 속하지 않는 시간은 CLOSED, source가 애매한 상황은 UNKNOWN을 유지한다.
