# API 계약

> **Harness Role:** React↔Spring Boot 공개 API와 계획된 Spring Boot↔FastAPI 내부 계약의 기준입니다. Agent는 Controller, API client, DTO 또는 SSE event를 바꾸기 전에 읽고 같은 변경에서 갱신합니다. 이 문서가 없으면 호출 양쪽이 서로 다른 필드나 이벤트 순서를 구현할 수 있습니다. `architecture.md`의 서비스 경계를 구체화하고 API 테스트와 `check-integration.sh`의 기대 동작으로 이어집니다.

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

모든 `/api/conversations/**` API는 로그인이 필요합니다. Spring Boot는 요청한 사용자가 해당 대화의 `user_id`와 일치할 때만 생성 이후 조회, 메시지 전송과 비활성화를 허용합니다. 미인증 요청은 `401 Unauthorized`, 다른 사용자의 대화 ID를 사용한 요청은 대화 존재 여부를 노출하지 않도록 `404 Not Found`를 반환합니다.

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

현재 Spring Boot는 `만원 이하`, `국물`, `샐러드`, `가볍게`, `한식`처럼 제한된 키워드만 임시로 해석합니다. 제로페이 가능 여부는 사용자 선택과 무관한 필수 조건입니다. 영업시간 조회, 취향·최근 식사 필터와 최종 순위는 Spring Boot와 MySQL이 처리합니다. FastAPI 자연어 분석은 아직 구현되지 않았습니다.

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
생성된 대화는 현재 세션의 사용자와 연결됩니다.

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

## 구현됨: CSRF 토큰 조회

```http
GET /api/auth/csrf
```

브라우저 쿠키(CSRF 토큰) 갱신 용도의 더미 엔드포인트입니다. Spring Security가 요청을 가로채 CSRF 쿠키를 갱신합니다.

## 구현됨: 회원가입

```http
POST /api/auth/signup
Content-Type: application/json
```

요청:
```json
{
  "email": "user@example.com",
  "password": "password123",
  "displayName": "사용자이름"
}
```

입력 제약:

- `email`: 유효한 이메일 형식, 최대 255자
- `password`: 8~72자이며 BCrypt 제한을 위해 UTF-8 기준 최대 72바이트
- `displayName`: 공백이 아닌 문자열, 최대 100자

응답 `200 OK`:
```json
{
  "userId": "uuid-...",
  "email": "user@example.com",
  "displayName": "사용자이름"
}
```

이미 사용 중인 이메일이면 `409 Conflict`와 `EMAIL_ALREADY_IN_USE` 오류를 반환합니다.

## 구현됨: 로그인

```http
POST /api/auth/login
Content-Type: application/json
```

요청:
```json
{
  "email": "user@example.com",
  "password": "password123"
}
```

응답 `200 OK`:
```json
{
  "userId": "uuid-...",
  "email": "user@example.com",
  "displayName": "사용자이름"
}
```

응답 `401 Unauthorized`:
```json
{
  "code": "INVALID_CREDENTIALS",
  "message": "이메일 또는 비밀번호가 올바르지 않습니다."
}
```

## 구현됨: 현재 사용자 조회

```http
GET /api/auth/me
```

응답 `200 OK` (로그인 상태일 때):
```json
{
  "userId": "uuid-...",
  "email": "user@example.com",
  "displayName": "사용자이름"
}
```

응답 `401 Unauthorized` (미인증 시)

## 구현됨: 로그아웃

```http
POST /api/auth/logout
```

응답 `204 No Content`. 세션과 관련 쿠키가 삭제됩니다.

로그인 성공 시 기존 HTTP 세션 ID는 교체되며 인증 컨텍스트는 Spring Session JDBC에 저장됩니다.

## 구현됨: 사용자 취향 조회·저장

```http
GET /api/preferences/me
PUT /api/preferences/me
Content-Type: application/json
```

`PUT` 요청:

```json
{
  "defaultBudget": 12000,
  "spiceLevel": "MEDIUM",
  "preferredCategories": ["KOREAN", "KOREAN_SOUP"],
  "dislikedCategories": ["SALAD"],
  "allergies": ["땅콩"]
}
```

응답:

```json
{
  "defaultBudget": 12000,
  "spiceLevel": "MEDIUM",
  "preferredCategories": ["KOREAN", "KOREAN_SOUP"],
  "dislikedCategories": ["SALAD"],
  "allergies": ["땅콩"],
  "zeroPayRequired": true
}
```

- `defaultBudget`: 미설정은 `null`, 설정 시 1,000~100,000원
- `spiceLevel`: `ANY`, `MILD`, `MEDIUM`, `HOT`
- 카테고리: 현재 `KOREAN`, `KOREAN_SOUP`, `SALAD`
- 같은 카테고리를 선호와 비선호에 동시에 저장할 수 없음
- `zeroPayRequired`는 항상 `true`이며 수정 가능한 요청 필드가 아님
- 알레르기와 매운맛은 AI 컨텍스트에 포함되지만 실제 재료·매운맛 음식점 데이터가 생기기 전에는 결정론적 필터로 사용하지 않음

## 구현됨: 최근 식사 기록

식사 기록은 추천을 받았다는 이유만으로 생성되지 않습니다. 사용자가 추천 카드의 `먹었어요` 버튼을 누를 때만 다음 API를 호출합니다.

```http
POST /api/meals
Content-Type: application/json
```

```json
{
  "restaurantId": 1001,
  "sourceMessageId": "46448535-1bcf-4568-91ff-3186de828bb5"
}
```

Spring Boot는 `sourceMessageId`가 현재 사용자 대화의 assistant 추천 메시지이고 해당 음식점이 실제 추천 결과에 포함됐는지 검증합니다. 같은 사용자·메시지·음식점 요청은 기존 기록을 반환해 중복 생성하지 않습니다.

```http
GET /api/meals/recent
```

현재 시각 기준 최근 72시간의 기록만 최신순으로 반환합니다.

```json
[
  {
    "mealId": "23a34e5b-cdf8-4f79-97b7-e46bb735488a",
    "restaurantId": 1001,
    "restaurantName": "강남 샘플 한식당",
    "category": "KOREAN",
    "sourceMessageId": "46448535-1bcf-4568-91ff-3186de828bb5",
    "eatenAt": "2026-09-17T03:00:00Z"
  }
]
```

## 계약 확정: Spring Boot → FastAPI 의도 분석

FastAPI 구현 시 사용할 내부 경로는 `POST /internal/v1/intent-analysis`로 정의합니다. 현재는 HTTP 호출 없이 같은 필드의 Java 계약과 임시 결정론적 분석기를 사용합니다.

요청:

```json
{
  "message": "만원 이하 국물 음식 추천해줘",
  "locationId": "gangnam",
  "defaultBudget": 12000,
  "spiceLevel": "MEDIUM",
  "preferredCategories": ["KOREAN_SOUP"],
  "dislikedCategories": ["SALAD"],
  "allergies": ["땅콩"],
  "recentMeals": [
    {
      "restaurantId": 1002,
      "category": "KOREAN_SOUP",
      "eatenAt": "2026-09-16T03:00:00Z"
    }
  ]
}
```

응답:

```json
{
  "intent": "RECOMMEND_RESTAURANT",
  "maximumPrice": 10000,
  "category": "KOREAN_SOUP",
  "keywords": ["국물"],
  "clarificationRequired": false,
  "clarificationQuestion": null
}
```

FastAPI 응답은 Spring Boot에서 enum과 타입을 다시 검증합니다. FastAPI는 후보 음식점을 만들거나 제로페이·강남구·영업시간·최근 식사 조건과 최종 순위를 변경하지 않습니다.

## 계획: AI 추천 구현

FastAPI는 위 내부 계약의 자연어 의도 분석부터 구현합니다. 이후 LLM 설명 생성과 Qdrant 의미 검색은 별도 계약으로 추가하며 영업시간 필터와 최종 순위는 계속 Spring Boot가 소유합니다.
