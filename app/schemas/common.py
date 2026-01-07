from pydantic import BaseModel


class ErrorResponse(BaseModel):
    error: str
    message: str
    details: dict | None = None


class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str = "1.0.0"
    timestamp: str
    circuit_breaker: dict | None = None
