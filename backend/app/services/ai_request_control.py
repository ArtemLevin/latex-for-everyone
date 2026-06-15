from collections import defaultdict, deque
from dataclasses import dataclass
import math
import re
import time


IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]+$")


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int = 0


class RateLimiter:
    """In-memory fixed-window limiter behind a service boundary.

    The implementation remains process-local for local/dev simplicity, but all
    router code now depends on this boundary so PRs can swap in Redis or another
    shared store without changing endpoint control flow.
    """

    def __init__(self, *, window_seconds: int = 60) -> None:
        self.window_seconds = window_seconds
        self.buckets: dict[str, deque[float]] = defaultdict(deque)

    def check(self, *, key: str, limit: int, now: float | None = None) -> RateLimitDecision:
        if limit <= 0:
            return RateLimitDecision(allowed=True)

        current_time = now if now is not None else time.monotonic()
        bucket = self.buckets[key]
        while bucket and current_time - bucket[0] >= self.window_seconds:
            bucket.popleft()
        if len(bucket) >= limit:
            retry_after = max(1, math.ceil(self.window_seconds - (current_time - bucket[0])))
            return RateLimitDecision(allowed=False, retry_after_seconds=retry_after)
        bucket.append(current_time)
        return RateLimitDecision(allowed=True)

    def clear(self) -> None:
        self.buckets.clear()


class DuplicateRequestError(ValueError):
    """Raised when the same in-flight generation payload is already running."""


class InFlightRequestRegistry:
    """Tracks in-flight request fingerprints behind a replaceable boundary."""

    def __init__(self) -> None:
        self.active_requests: dict[str, float] = {}

    def begin(self, key: str) -> None:
        if key in self.active_requests:
            raise DuplicateRequestError(key)
        self.active_requests[key] = time.monotonic()

    def finish(self, key: str | None) -> None:
        if key:
            self.active_requests.pop(key, None)

    def clear(self) -> None:
        self.active_requests.clear()


class InvalidIdempotencyKeyError(ValueError):
    """Raised when a client-provided idempotency key is unsafe or too long."""


class AIRequestControlService:
    """Coordinates rate-limit, duplicate-submit and idempotency-key concerns."""

    def __init__(self) -> None:
        self.rate_limiter = RateLimiter()
        self.in_flight = InFlightRequestRegistry()

    def check_rate_limit(self, *, key: str, limit: int) -> RateLimitDecision:
        return self.rate_limiter.check(key=key, limit=limit)

    def begin_in_flight(self, key: str) -> None:
        self.in_flight.begin(key)

    def finish_in_flight(self, key: str | None) -> None:
        self.in_flight.finish(key)

    def normalize_idempotency_key(self, value: str | None, *, max_chars: int) -> str | None:
        if value is None:
            return None
        key = value.strip()
        if not key:
            return None
        if len(key) > max_chars or not IDEMPOTENCY_KEY_PATTERN.fullmatch(key):
            raise InvalidIdempotencyKeyError(
                "Invalid idempotency key. Use up to "
                f"{max_chars} ASCII letters, digits, dots, underscores, colons, or hyphens."
            )
        return key
