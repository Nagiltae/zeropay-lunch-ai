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

`conversationId`는 현재 React가 새 대화를 시작할 때 UUID로 생성합니다. 대화와 메시지는 아직 영속화하지 않으므로 페이지를 새로 고치면 복구되지 않습니다.

프런트엔드에는 강남구 주요 지역을 선택하는 UI가 있지만 현재 채팅 요청에는 위치가 포함되지 않습니다. 위치 식별자나 좌표를 임의로 계약에 추가하지 않고, 강남구 위치 검증 방식과 추천 요청 계약을 설계한 뒤 서버 전송을 연결합니다.

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

현재 Spring Boot 응답은 React와 SSE 연결을 검증하기 위한 안내형 문구입니다. 자연어 해석, 음식점 검색, 추천 결과, FastAPI 연동은 아직 구현되지 않았습니다.

## 계획: 추천

추천 엔드포인트와 DTO는 3단계에서 설계합니다. 외부 계약은 Spring Boot가 소유합니다. Spring Boot와 FastAPI 사이의 계약은 내부 API로 문서화하고, 양쪽에서 요청과 응답을 검증합니다.
