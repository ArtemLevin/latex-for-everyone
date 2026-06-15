import pytest
from redis.exceptions import ConnectionError

from app.services.ai_request_control import (
    AIRequestControlService,
    DuplicateRequestError,
    InvalidIdempotencyKeyError,
    RequestControlBackendError,
)
from app.services.readiness import check_ai_request_control_ready


class _FakePipeline:
    def __init__(self, redis):
        self.redis = redis
        self.operations = []

    def zremrangebyscore(self, key, minimum, maximum):
        self.operations.append(("zremrangebyscore", key, minimum, maximum))
        return self

    def zcard(self, key):
        self.operations.append(("zcard", key))
        return self

    def zadd(self, key, mapping):
        self.operations.append(("zadd", key, mapping))
        return self

    def expire(self, key, seconds):
        self.operations.append(("expire", key, seconds))
        return self

    def execute(self):
        results = []
        for operation in self.operations:
            name = operation[0]
            if name == "zremrangebyscore":
                _, key, minimum, maximum = operation
                values = self.redis.sorted_sets.get(key, {})
                removed = [member for member, score in values.items() if minimum <= score <= maximum]
                for member in removed:
                    values.pop(member, None)
                results.append(len(removed))
            elif name == "zcard":
                _, key = operation
                results.append(len(self.redis.sorted_sets.get(key, {})))
            elif name == "zadd":
                _, key, mapping = operation
                self.redis.sorted_sets.setdefault(key, {}).update(mapping)
                results.append(len(mapping))
            elif name == "expire":
                results.append(True)
        return results


class _FakeRedis:
    def __init__(self):
        self.sorted_sets = {}
        self.values = {}
        self.fail_ping = False

    def pipeline(self, transaction=True):  # noqa: ARG002 - mirrors redis-py signature
        return _FakePipeline(self)

    def zrange(self, key, start, end, withscores=False):
        items = sorted(self.sorted_sets.get(key, {}).items(), key=lambda item: item[1])
        sliced = items[start : end + 1]
        return sliced if withscores else [member for member, _score in sliced]

    def set(self, key, value, nx=False, ex=None):  # noqa: ARG002 - TTL is not needed in the fake clock
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    def delete(self, *keys):
        deleted = 0
        for key in keys:
            deleted += int(self.values.pop(key, None) is not None)
            deleted += int(self.sorted_sets.pop(key, None) is not None)
        return deleted

    def scan_iter(self, match=None, count=None):  # noqa: ARG002 - count is accepted for compatibility
        prefix = (match or "").rstrip("*")
        for key in list(self.values) + list(self.sorted_sets):
            if not prefix or key.startswith(prefix):
                yield key

    def ping(self):
        if self.fail_ping:
            raise ConnectionError("redis unavailable")
        return True


def test_memory_request_control_keeps_existing_idempotency_contract():
    service = AIRequestControlService()

    assert service.health_check() == {"backend": "memory", "shared": False}
    assert service.normalize_idempotency_key(" job-1 ", max_chars=10) == "job-1"
    with pytest.raises(InvalidIdempotencyKeyError):
        service.normalize_idempotency_key("bad key", max_chars=10)


def test_redis_request_control_shares_rate_limit_and_duplicate_state():
    fake_redis = _FakeRedis()
    first = AIRequestControlService(
        backend="redis",
        redis_client=fake_redis,
        redis_prefix="test:ai",
        in_flight_ttl_seconds=30,
    )
    second = AIRequestControlService(
        backend="redis",
        redis_client=fake_redis,
        redis_prefix="test:ai",
        in_flight_ttl_seconds=30,
    )

    assert first.health_check() == {"backend": "redis", "shared": True}
    assert first.check_rate_limit(key="client:/api/generation/jobs", limit=1).allowed is True
    denied = second.check_rate_limit(key="client:/api/generation/jobs", limit=1)
    assert denied.allowed is False
    assert denied.retry_after_seconds > 0

    first.begin_in_flight("same-payload")
    with pytest.raises(DuplicateRequestError):
        second.begin_in_flight("same-payload")
    first.finish_in_flight("same-payload")
    second.begin_in_flight("same-payload")


def test_ai_request_control_readiness_reports_invalid_backend(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "AI_REQUEST_CONTROL_BACKEND", "invalid")

    response = check_ai_request_control_ready()

    assert response.status == "error"
    assert "Unsupported AI request-control backend" in response.details["error"]


def test_redis_request_control_health_check_reports_backend_failure():
    fake_redis = _FakeRedis()
    fake_redis.fail_ping = True
    service = AIRequestControlService(backend="redis", redis_client=fake_redis, redis_prefix="test:ai")

    with pytest.raises(RequestControlBackendError):
        service.health_check()
