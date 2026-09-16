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

## 계획: 추천

추천 엔드포인트와 DTO는 3단계에서 설계합니다. 외부 계약은 Spring Boot가 소유합니다. Spring Boot와 FastAPI 사이의 계약은 내부 API로 문서화하고, 양쪽에서 요청과 응답을 검증합니다.
