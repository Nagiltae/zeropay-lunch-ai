# Gemini Menu Budget Classifier v2 — Pilot Review

## 판정

**GEMINI MENU BUDGET PILOT = NO_GO**

5개 Restaurant 모두의 분류 완료 조건을 충족하지 못했다. 부분 성공을 전체 품질 통과로 간주하지 않는다. Spring importer, classification table/migration, import dry-run은 만들지 않았다. Gemini 결과는 artifact에만 있으며 runtime budget filter는 읽지 않는다.

## Provider / Secret / Request 계약

- provider interface: `MenuBudgetClassifier`; 현재 구현 `GeminiMenuBudgetClassifier`.
- SDK: `google-genai 2.25.0` (Poetry lock). Python 공식 structured-output 예시의 `google.genai` SDK/Pydantic schema 사용.
- 요구 model: `gemini-3.8-flash`; `GEMINI_MODEL` 설정으로 관리하며 pilot에서 다른 이름은 거부한다. Google 공식 모델 목록은 이 model ID를 Gemini API 모델로 열거한다: [Gemini models](https://ai.google.dev/gemini-api/docs/models).
- schema: `menuId`, `budgetEligibility` (`ELIGIBLE|INELIGIBLE|UNKNOWN`), `flags[]` (`SIDE|DRINK|ALCOHOL|MULTI_PERSON|COURSE|WEIGHT_BASED`). 응답 rationale는 요청하지 않는다. Python Pydantic validator는 여전히 extra field를 거부한다. Google GenAI Python SDK의 structured JSON/Pydantic 사용 패턴은 [Structured outputs](https://ai.google.dev/gemini-api/docs/generate-content/structured-output) 문서를 따른다.
- input: frozen source row의 menu ID/name/description/실제 `priceValue`만 전송했다. Restaurant ID/user budget은 보내지 않았고 모델이 ID/name/price를 생성·수정하지 않는다.
- chunk: 최대 12 menus/request. 원래 예상 17 requests (188 menus).
- timeout: SDK `HttpOptions.timeout=45,000ms`; SDK 내부 retry 1 attempt. 코드에서는 transient network/5xx만 추가 1회 허용.
- project safety: 실제 429 발견 즉시 batch를 종료했고 retry하지 않았다. (프로젝트 AGENTS의 429 즉시 중단 규칙 적용.)
- 환경 preflight: `GEMINI_API_KEY_PRESENT=true`, `GOOGLE_API_KEY_PRESENT=false`. API client에 `GEMINI_API_KEY`를 명시적으로 전달한다. compose 환경 전달은 FastAPI `ai` service에만 설정했고 Spring/React에는 전달하지 않았다. `.env.example`에는 이름과 빈 값만 기록했다.

첫 시도에서 Google API가 schema 내 `additionalProperties`를 허용하지 않아 `400 INVALID_ARGUMENT`를 반환했다. raw API message에는 인증/요청 세부정보를 포함할 수 있어 저장하지 않았다. wire schema에서 해당 키를 제거한 후 SDK structured call은 1개 chunk에서 성공했다. client-side Pydantic extra-forbid validation은 그대로 유지했다.

## Frozen cohort 및 결과

기존 pilot과 같은 ID를 사용했다: `9617, 9571, 9568, 10042, 9559`. 입력 원본은 `serving_model_v2_pilot_plan.json`의 고정 메뉴 snapshot(188행)이며 source SHA-256은 결과 JSON에 기록했다. fixture는 모델 호출 전에 작성·고정했고 fixture/source fingerprint도 저장했다.

- 실제 API 요청 시도: 16회 합계. 여기에는 classification 요청, schema 수정 진단 4회, SDK의 bounded transient retry가 포함된다.
- 성공 API 응답: 1 chunk (12개 menu row); 실패 API attempt: 15.
- 분류 작업 chunk 실패: 8, retry: 3, timeout: 0, 5xx 관측: 2, 429 관측: 1.
- 429가 발생한 시점에 중지. 각 실패한 식당/요청을 더 재호출하지 않았다.
- completed Restaurant: 0/5. 일부 classification 존재 Restaurant: 1/5. 모델 결과 메뉴: 12/188.
- 성공한 chunk 내 관찰: `8731`(1.5인 set)은 `INELIGIBLE + MULTI_PERSON`; fixture의 명백한 critical negative 1건은 맞았다. `8738`(부산어묵 1인분 2꼬치)은 `INELIGIBLE + SIDE`로 분류되어 fixture의 ambiguous `UNKNOWN` 기준에는 맞지 않았다. 이는 전체 품질 추정치가 아니며 평가 표본이 너무 작다.
- clear positive fixture 관찰 수 0. 기타 fixture는 output 미존재로 `missing input/output`; 이를 정답/오답으로 꾸미지 않았다.
- token usage metadata: prompt 679, candidate 431, total 3,549 (성공 응답 metadata만).
- 전체 wall-clock latency는 첫 실패 batch와 진단 호출 일부를 개별 측정하지 않아 UNKNOWN. 성공 runner segment는 12.652초로 기록됐으나 전체 elapsed로 오인하지 않는다.

## Qwen v1 비교

| 지표 | Qwen 3.5 9B historical | Gemini 3.8 Flash v2 |
|---|---:|---:|
| Restaurant 대상 | 5 | 5 |
| 호출 | 5 | 16 API attempts (4 diagnostics 포함) |
| Restaurant 전체 완료 | 2/5 structured success; 기존 평가에서 0 approved | 0/5 |
| Timeout | 3 | 0 |
| 기타 주요 실패 | 중량 메뉴 오분류, 없는 budget rationale, 음료/주류 일관성 | 400 schema 호환 문제, 429 중단 |
| Critical false positive | 기존 평가에서 확인 | 전체 fixture 판정 불가; 관찰된 1건은 0 false positive |
| Import review | NO | NO_GO |

Gemini가 우수하다고 결론내리지 않는다. 완료율과 품질 gate를 만족하지 못했다.

## 안전·다음 작업

- MySQL writes 0, Qdrant writes 0, menu classification DB persistence 0.
- Spring importer: 미구현. classification Flyway migration: 0.
- Runtime은 raw Gemini output을 사용하지 않으며 기존 explicit-budget fail-closed 정책을 유지한다.
- Gemini API key가 tracked 변경물 및 이번 결과 artifact에 포함되지 않도록 secret scan을 수행한다.
- 26 Restaurant 확대 금지 상태 유지. 다음에는 quota/429 상태와 request throttling 정책을 먼저 확인한 뒤 별도 승인된 bounded pilot이 필요하다. 이번 작업에서 추가 호출하지 않았다.
