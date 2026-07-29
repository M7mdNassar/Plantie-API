import time
import uuid

from fastapi import Request

from src.utils.logging import get_logger

logger = get_logger()

_SKIP_PATHS = ("/", "/docs", "/openapi.json", "/redoc")
_SKIP_PREFIXES = ("/docs/", "/redoc/", "/api/v1/health")


async def logging_middleware(request: Request, call_next):
    path = request.url.path
    if path in _SKIP_PATHS or path.startswith(_SKIP_PREFIXES):
        return await call_next(request)

    request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    start_time = time.time()
    logger.info(f"Request started [{request_id}] {request.method} {path}")

    response = await call_next(request)

    duration_ms = round((time.time() - start_time) * 1000, 2)
    logger.info(
        f"Request completed [{request_id}] status={response.status_code} "
        f"duration_ms={duration_ms}"
    )

    return response