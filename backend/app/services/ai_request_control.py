from collections import Counter, defaultdict, deque
from dataclasses import dataclass
import hashlib
import math
import re
import time
import uuid
from typing import Any, Protocol

from redis import Redis
from redis.exceptions import RedisError


IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]+$")
SUPPORTED_REQUEST_CONTROL_BACKENDS = {"memory", "redis"}


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int = 0


class RateLimitBackend(Protocol):
    def check(self, *, key: str, limit: int, now: float | None = None) -> RateLimitDecision: ...

    def clear(self) -> None: ...


class InFlightBackend(Protocol):
    def begin(self, key: str) -> None: ...

    def finish(self, key: str | None) -> None: ...

    def clear(self) -> None: ...


class RequestControlBackendError(RuntimeError):
    """Raised when a shared request-control backend cannot be used."""


class RateLimiter:
    """In-memory fixed-window limiter for local/dev and single-process deployments."""

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


class RedisRateLimiter:
    """Redis-backed sliding-window limiter shared by multiple API replicas."""

    def __init__(self, redis_client: Redis, *, prefix: str, window_seconds: int = 60) -> None:
        self.redis = redis_client
        self.prefix = prefix.rstrip(":")
        self.window_seconds = window_seconds

    def _key(self, key: str) -> str:
        # Hash untrusted client/path input so Redis keys stay compact and do not leak request paths into key listings.
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return f"{self.prefix}:rate:{digest}"

    def check(self, *, key: str, limit: int, now: float | None = None) -> RateLimitDecision:
        if limit <= 0:
            return RateLimitDecision(allowed=True)

        current_time = now if now is not None else time.time()
        redis_key = self._key(key)
        cutoff = current_time - self.window_seconds
        member = f"{current_time:.6f}:{uuid.uuid4().hex}"
        try:
            # Keep the window mutation grouped so concurrent workers see a consistent enough shared count.
            pipe = self.redis.pipeline(transaction=True)
            pipe.zremrangebyscore(redis_key, 0, cutoff)
            pipe.zcard(redis_key)
            _, count = pipe.execute()
            if int(count) >= limit:
                oldest = self.redis.zrange(redis_key, 0, 0, withscores=True)
                if oldest:
                    retry_after = max(1, math.ceil(self.window_seconds - (current_time - float(oldest[0][1]))))
                else:
                    retry_after = self.window_seconds
                return RateLimitDecision(allowed=False, retry_after_seconds=retry_after)

            pipe = self.redis.pipeline(transaction=True)
            pipe.zadd(redis_key, {member: current_time})
            pipe.expire(redis_key, self.window_seconds * 2)
            pipe.execute()
            return RateLimitDecision(allowed=True)
        except RedisError as exc:
            raise RequestControlBackendError("Redis AI request-control rate limiter failed") from exc

    def clear(self) -> None:
        pattern = f"{self.prefix}:rate:*"
        try:
            keys = list(self.redis.scan_iter(match=pattern, count=100))
            if keys:
                self.redis.delete(*keys)
        except RedisError as exc:
            raise RequestControlBackendError("Redis AI request-control rate limiter cleanup failed") from exc


class DuplicateRequestError(ValueError):
    """Raised when the same in-flight generation payload is already running."""


class InFlightRequestRegistry:
    """Tracks in-flight request fingerprints for a single API process."""

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


class RedisInFlightRequestRegistry:
    """Redis-backed duplicate-submit registry shared by API replicas."""

    def __init__(self, redis_client: Redis, *, prefix: str, ttl_seconds: int) -> None:
        self.redis = redis_client
        self.prefix = prefix.rstrip(":")
        self.ttl_seconds = max(1, ttl_seconds)

    def _key(self, key: str) -> str:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return f"{self.prefix}:inflight:{digest}"

    def begin(self, key: str) -> None:
        redis_key = self._key(key)
        try:
            # SET NX EX gives cross-process duplicate protection and self-heals if a worker dies before finish().
            if not self.redis.set(redis_key, str(time.time()), nx=True, ex=self.ttl_seconds):
                raise DuplicateRequestError(key)
        except RedisError as exc:
            raise RequestControlBackendError("Redis AI request-control in-flight registry failed") from exc

    def finish(self, key: str | None) -> None:
        if not key:
            return
        try:
            self.redis.delete(self._key(key))
        except RedisError as exc:
            raise RequestControlBackendError("Redis AI request-control in-flight cleanup failed") from exc

    def clear(self) -> None:
        pattern = f"{self.prefix}:inflight:*"
        try:
            keys = list(self.redis.scan_iter(match=pattern, count=100))
            if keys:
                self.redis.delete(*keys)
        except RedisError as exc:
            raise RequestControlBackendError("Redis AI request-control in-flight cleanup failed") from exc


class InvalidIdempotencyKeyError(ValueError):
    """Raised when a client-provided idempotency key is unsafe or too long."""


class AIRequestControlService:
    """Coordinates rate-limit, duplicate-submit and idempotency-key concerns."""

    def __init__(
        self,
        *,
        backend: str = "memory",
        redis_url: str | None = None,
        redis_prefix: str = "latexed:ai_request_control",
        in_flight_ttl_seconds: int = 300,
        redis_client: Redis | None = None,
    ) -> None:
        normalized_backend = backend.strip().lower()
        if normalized_backend not in SUPPORTED_REQUEST_CONTROL_BACKENDS:
            raise ValueError(
                "Unsupported AI request-control backend "
                f"{backend!r}. Use one of: {', '.join(sorted(SUPPORTED_REQUEST_CONTROL_BACKENDS))}."
            )

        self.backend = normalized_backend
        # Counters are process-local by design; shared Redis state controls behavior, while these expose per-replica activity.
        self.rate_limit_decisions: Counter[str] = Counter()
        self.in_flight_decisions: Counter[str] = Counter()
        self.redis: Redis | None = None
        if self.backend == "redis":
            if redis_client is None and not redis_url:
                raise ValueError("AI_REQUEST_CONTROL_REDIS_URL is required when AI_REQUEST_CONTROL_BACKEND=redis.")
            self.redis = redis_client or Redis.from_url(str(redis_url), decode_responses=True)
            self.rate_limiter: RateLimitBackend = RedisRateLimiter(self.redis, prefix=redis_prefix)
            self.in_flight: InFlightBackend = RedisInFlightRequestRegistry(
                self.redis,
                prefix=redis_prefix,
                ttl_seconds=in_flight_ttl_seconds,
            )
        else:
            self.rate_limiter = RateLimiter()
            self.in_flight = InFlightRequestRegistry()

    def check_rate_limit(self, *, key: str, limit: int) -> RateLimitDecision:
        try:
            decision = self.rate_limiter.check(key=key, limit=limit)
        except RequestControlBackendError:
            self.rate_limit_decisions["error"] += 1
            raise
        self.rate_limit_decisions["allowed" if decision.allowed else "limited"] += 1
        return decision

    def begin_in_flight(self, key: str) -> None:
        try:
            self.in_flight.begin(key)
        except DuplicateRequestError:
            self.in_flight_decisions["duplicate"] += 1
            raise
        except RequestControlBackendError:
            self.in_flight_decisions["error"] += 1
            raise
        self.in_flight_decisions["accepted"] += 1

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

    def metrics_snapshot(self) -> dict[str, Any]:
        snapshot: dict[str, Any] = {"backend": self.backend, "shared": self.backend == "redis"}
        try:
            snapshot.update(self.health_check())
            snapshot["healthy"] = True
        except RequestControlBackendError as exc:
            snapshot["healthy"] = False
            snapshot["error"] = str(exc)
        snapshot["rate_limit_decisions"] = dict(self.rate_limit_decisions)
        snapshot["in_flight_decisions"] = dict(self.in_flight_decisions)
        return snapshot

    def health_check(self) -> dict[str, Any]:
        details: dict[str, Any] = {"backend": self.backend}
        if self.backend != "redis":
            details["shared"] = False
            return details
        if self.redis is None:
            raise RequestControlBackendError("Redis AI request-control client is not configured")
        try:
            self.redis.ping()
        except RedisError as exc:
            raise RequestControlBackendError("Redis AI request-control backend is unavailable") from exc
        details["shared"] = True
        return details


def build_ai_request_control_service() -> AIRequestControlService:
    from app.config import settings

    return AIRequestControlService(
        backend=settings.AI_REQUEST_CONTROL_BACKEND,
        redis_url=settings.AI_REQUEST_CONTROL_REDIS_URL,
        redis_prefix=settings.AI_REQUEST_CONTROL_REDIS_PREFIX,
        in_flight_ttl_seconds=settings.AI_IN_FLIGHT_TTL_SECONDS,
    )
