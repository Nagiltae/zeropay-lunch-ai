# AI 서버

이 서비스는 자연어 의도 분석, 의미 기반 검색, 워크플로 조정, LLM 호출, 추천 설명 생성과 같은 AI 전용 기능을 담당합니다.

애플리케이션 아키텍처에서 이 서비스는 Spring Boot만 호출할 수 있습니다. 프런트엔드에서 직접 호출해서는 안 됩니다.

현재 1단계 범위는 상태 확인 엔드포인트로 제한됩니다. LangGraph, LangChain, 모델 SDK, 벡터 저장소, 관측성 관련 의존성은 해당 기능을 구현할 때만 추가합니다.

```bash
poetry install
poetry run uvicorn app.main:app --reload --port 8001
poetry run ruff check .
poetry run pytest
```
