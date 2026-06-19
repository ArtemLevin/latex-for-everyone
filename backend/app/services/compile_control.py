from functools import partial
from typing import Callable, TypeVar

import anyio
from anyio import to_thread

from app.config import settings
from app.services.ai_request_control import RateLimitDecision, RateLimiter

T = TypeVar("T")


class CompileRateLimitError(RuntimeError):
    """Raised when a compile request exceeds the configured rate limit."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("Compile rate limit exceeded")
        self.retry_after_seconds = retry_after_seconds


class CompileQueueFullError(RuntimeError):
    """Raised when no compile concurrency slot becomes available in time."""


class CompileControlService:
    """Request-control boundary for expensive pdflatex execution."""

    def __init__(self) -> None:
        self.rate_limiter = RateLimiter(window_seconds=60 * 60)
        self._semaphore: anyio.Semaphore | None = None
        self._semaphore_limit: int | None = None

    def _compile_limit(self) -> int:
        return max(1, settings.COMPILE_CONCURRENCY_LIMIT)

    def _get_semaphore(self) -> anyio.Semaphore:
        limit = self._compile_limit()
        if self._semaphore is None or self._semaphore_limit != limit:
            self._semaphore = anyio.Semaphore(limit)
            self._semaphore_limit = limit
        return self._semaphore

    def check_rate_limit(self, *, key: str) -> RateLimitDecision:
        decision = self.rate_limiter.check(key=key, limit=settings.COMPILE_RATE_LIMIT_PER_HOUR)
        if not decision.allowed:
            raise CompileRateLimitError(decision.retry_after_seconds)
        return decision

    async def run_in_thread(self, func: Callable[..., T], /, *args, **kwargs) -> T:
        semaphore = self._get_semaphore()
        timeout = max(0.001, settings.COMPILE_QUEUE_TIMEOUT_SECONDS)
        acquired = False
        with anyio.move_on_after(timeout) as cancel_scope:
            await semaphore.acquire()
            acquired = True
        if cancel_scope.cancel_called or not acquired:
            raise CompileQueueFullError("Compile queue is full. Try again later.")

        try:
            return await to_thread.run_sync(partial(func, *args, **kwargs))
        finally:
            semaphore.release()

    def clear_rate_limits(self) -> None:
        self.rate_limiter.clear()
