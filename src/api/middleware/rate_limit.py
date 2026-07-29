"""In-memory, per-key rate limiter.

Checked once per request, inside the auth dependency (see
src/api/dependencies/auth.py) right after the user is resolved — not as a
separate global middleware, so a request is never rate-limited before we
even know who it's for.

Note: this state lives in process memory. If you run more than one worker
or pod, each one enforces its own limit independently (so the *effective*
limit is roughly max_requests * worker_count). Fine for a single instance;
move to a shared store (e.g. Redis) if you scale horizontally.
"""

import time
from collections import defaultdict

from src.config import get_settings

settings = get_settings()


class RateLimiter:
    def __init__(self, max_requests: int, period: int):
        self.max_requests = max_requests
        self.period = period
        self._tokens: dict[str, int] = defaultdict(int)
        self._reset_at: dict[str, float] = defaultdict(float)

    def check(self, key: str) -> bool:
        if not settings.RATE_LIMIT_ENABLED:
            return True
        now = time.time()
        if now > self._reset_at[key]:
            self._tokens[key] = 0
            self._reset_at[key] = now + self.period
        if self._tokens[key] >= self.max_requests:
            return False
        self._tokens[key] += 1
        return True


rate_limiter = RateLimiter(
    max_requests=settings.RATE_LIMIT_MAX_REQUESTS,
    period=settings.RATE_LIMIT_PERIOD,
)