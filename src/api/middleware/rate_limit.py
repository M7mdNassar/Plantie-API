from fastapi import Request, HTTPException
from collections import defaultdict
import time
from src.config import get_settings

settings = get_settings()

class RateLimiter:
    def __init__(self, max_requests: int = 60, period: int = 60):
        self.max_requests = max_requests
        self.period = period
        self.tokens = defaultdict(int)
        self.last_reset = defaultdict(int)

    async def check(self, user_id: str) -> bool:
        if not settings.RATE_LIMIT_ENABLED:
            return True
        now = time.time()
        if now - self.last_reset[user_id] > self.period:
            self.tokens[user_id] = 0
            self.last_reset[user_id] = now
        if self.tokens[user_id] >= self.max_requests:
            return False
        self.tokens[user_id] += 1
        return True

rate_limiter = RateLimiter(
    max_requests=settings.RATE_LIMIT_MAX_REQUESTS,
    period=settings.RATE_LIMIT_PERIOD
)

async def rate_limit_middleware(request: Request, call_next):
    path = request.url.path
    if (path in ["/", "/docs", "/openapi.json", "/redoc"] or
        path.startswith("/docs/") or path.startswith("/redoc/") or
        path.startswith("/api/v1/health") or
        path.startswith("/api/v1/test")):
        return await call_next(request)

    user_id = getattr(request.state, 'user_id', 'anonymous')
    if not await rate_limiter.check(user_id):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please try again later."
        )
    return await call_next(request)