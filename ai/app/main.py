from fastapi import FastAPI
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str


app = FastAPI(
    title="ZeroPay Lunch AI Server",
    version="0.1.0",
)


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    # 현재 FastAPI는 추천 실행 경로가 아니라 Spring이 확인하는 내부 health/계약 경계다.
    return HealthResponse(status="ok", service="ai")
