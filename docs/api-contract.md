# API 계약

이 문서는 구현된 엔드포인트와 계획 중인 계약을 구분합니다. 계획으로 표시된 경로와 페이로드는 아직 사용할 수 없습니다.

## 구현됨: AI 상태 확인

Spring Boot 또는 운영 상태 점검에서 호출하는 내부 엔드포인트입니다.

```http
GET /health
```

응답 `200 OK`:

```json
{
  "status": "ok",
  "service": "ai"
}
```

## 구현됨: 백엔드 운영 상태 확인

Spring Boot Actuator가 제공하는 운영 상태 확인 엔드포인트입니다. 애플리케이션용 공개 API와 구분합니다.

```http
GET /actuator/health
```

정상 응답 `200 OK`의 기본 형식:

```json
{
  "groups": ["liveness", "readiness"],
  "status": "UP"
}
```

## 구현됨: 채팅 메시지 스트리밍

React가 사용자 메시지를 Spring Boot로 보내고 답변을 Server-Sent Events로 받는 공개 API입니다. 브라우저는 `EventSource` 대신 POST 응답의 `ReadableStream`을 읽습니다. React는 FastAPI를 직접 호출하지 않습니다.

```http
POST /api/conversations/{conversationId}/messages
Accept: text/event-stream
Content-Type: application/json
```

`conversationId`는 Spring Boot가 대화 생성 시 발급합니다. 대화, 메시지와 추천 결과는 MySQL에 저장되며 React는 브라우저에 활성 대화 ID를 보관해 새로고침 후 기록을 복구합니다.

기준 위치는 대화 생성 요청에 포함하며 대화 도중에는 바뀌지 않습니다. 위치 변경 시 기존 대화를 비활성화한 뒤 새 대화를 생성합니다.

요청:

```json
{
  "message": "만원 이하로 든든한 점심 추천해줘"
}
```

제약 조건:

- `message`: 공백이 아닌 문자열, 최대 2000자

정상 응답은 `200 OK`, `Content-Type: text/event-stream`이며 다음 이벤트를 순서대로 전송합니다.

### `accepted`

```json
{
  "conversationId": "a9b53de8-3de6-4a90-a2ae-014322947d92",
  "userMessageId": "31a18d0d-d5d7-4c9f-8684-bc9ae57b7288",
  "assistantMessageId": "46448535-1bcf-4568-91ff-3186de828bb5"
}
```

### `progress`

```json
{
  "stage": "ANALYZING",
  "message": "요청을 확인하고 있어요."
}
```

현재 단계 값은 `ANALYZING`, `PREPARING`입니다. 내부 추론 과정은 전송하지 않고 사용자에게 보여줄 진행 상태만 전송합니다.

### `assistant_delta`

```json
{
  "text": "말씀하신 요청을 받았어요."
}
```

React는 진행 중인 assistant 말풍선에 `text`를 순서대로 이어 붙입니다. `assistantMessageId`는 이후 대화 영속화와 복구 기능에서 서버 메시지를 식별하는 데 사용합니다.

### `recommendations`

현재 영업 중이고 임시 결정론적 조건을 만족하는 음식점 목록입니다. 이 이벤트는 `assistant_delta`보다 먼저 전송됩니다.

```json
{
  "items": [
    {
      "restaurantId": 1001,
      "name": "강남 샘플 한식당",
      "category": "한식",
      "representativeMenu": "제육볶음",
      "averagePrice": 9000,
      "address": "서울특별시 강남구 강남대로 샘플 101",
      "locationId": "gangnam",
      "locationLabel": "강남역",
      "zeroPayAvailable": true,
      "sampleData": true,
      "reason": "선택한 강남역 기준 위치와 일치해요."
    }
  ]
}
```

### `completed`

```json
{
  "assistantMessageId": "46448535-1bcf-4568-91ff-3186de828bb5"
}
```

### `error`

스트림이 시작된 후 발생한 오류는 HTTP 오류 상태 대신 다음 이벤트로 전달합니다.

```json
{
  "code": "STREAM_FAILED",
  "message": "답변을 생성하지 못했습니다."
}
```

현재 Spring Boot는 `만원 이하`, `국물`, `샐러드`, `가볍게`, `한식`, `제로페이`처럼 제한된 키워드만 임시로 해석합니다. 영업시간 조회, 필터와 최종 순위는 Spring Boot와 MySQL이 처리합니다. FastAPI 자연어 분석은 아직 구현되지 않았습니다.

## 구현됨: 대화 생성

```http
POST /api/conversations
Content-Type: application/json
```

요청:

```json
{
  "locationId": "gangnam"
}
```

지원하는 값은 `gangnam`, `yeoksam`, `seolleung`, `samseong`, `sinsa`, `apgujeong`, `cheongdam`, `suseo`입니다.

응답 `201 Created`:

```json
{
  "conversationId": "a9b53de8-3de6-4a90-a2ae-014322947d92",
  "locationId": "gangnam",
  "active": true,
  "createdAt": "2026-09-16T14:00:00Z"
}
```

## 구현됨: 대화 기록 조회

```http
GET /api/conversations/{conversationId}
```

대화 정보와 시간순 메시지 목록을 반환합니다. 각 assistant 메시지에는 저장된 추천 음식점 배열이 포함됩니다. 비활성 대화도 조회할 수 있습니다.

## 구현됨: 대화 비활성화

```http
POST /api/conversations/{conversationId}/deactivate
```

응답은 `204 No Content`입니다. 대화와 메시지를 삭제하지 않고 `active=false`와 비활성 시각을 기록합니다. 같은 요청을 다시 보내도 삭제는 발생하지 않습니다.

## 계획: AI 추천

FastAPI 연동 시 외부 계약은 계속 Spring Boot가 소유합니다. Spring Boot와 FastAPI 사이의 구조화된 의도 분석 계약은 별도의 내부 API로 문서화하고 양쪽에서 검증합니다. FastAPI는 현재의 임시 키워드 분석만 대체하며 영업시간 필터와 최종 순위를 소유하지 않습니다.
