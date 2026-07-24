from fastapi import Request
import time
import uuid
from src.utils.logging import get_logger

logger = get_logger()

async def logging_middleware(request: Request, call_next):
    path = request.url.path
    if (path in ["/", "/docs", "/openapi.json", "/redoc"] or
        path.startswith("/docs/") or path.startswith("/redoc/") or
        path.startswith("/api/v1/health")):
        return await call_next(request)

    request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    start_time = time.time()
    logger.info(
        f"Request started",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": path,
            "user_id": getattr(request.state, 'user_id', None)
        }
    )

    response = await call_next(request)

    duration = time.time() - start_time
    logger.info(
        f"Request completed",
        extra={
            "request_id": request_id,
            "status_code": response.status_code,
            "duration_ms": round(duration * 1000, 2),
            "user_id": getattr(request.state, 'user_id', None)
        }
    )

    return response