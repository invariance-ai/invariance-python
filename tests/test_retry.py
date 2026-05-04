import httpx
import pytest

from invariance import Invariance, RateLimitError, RetryPolicy
from invariance.async_client import AsyncInvariance


def _make_inv(handler, *, max_retries: int = 3) -> Invariance:
    inv = Invariance(api_key="inv_test_abc", api_url="http://test.local")
    inv._http._retry = RetryPolicy(max_retries=max_retries, base_seconds=0.0, jitter=0.0)
    inv._http._client = httpx.Client(
        base_url="http://test.local",
        headers={"Authorization": "Bearer inv_test_abc"},
        transport=httpx.MockTransport(handler),
    )
    return inv


def test_retries_on_429_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": {"code": "rate_limited", "message": "nope"}})
        return httpx.Response(200, json={"agent": {"id": "a", "name": "x"}})

    inv = _make_inv(handler)
    inv.agents.me()
    assert calls["n"] == 3


def test_raises_rate_limit_error_after_exhaustion():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": {"code": "rate_limited", "message": "too fast"}})

    inv = _make_inv(handler, max_retries=2)
    with pytest.raises(RateLimitError) as excinfo:
        inv.agents.me()
    assert excinfo.value.status == 429
    assert excinfo.value.code == "rate_limited"


def test_non_retryable_4xx_is_not_retried():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, json={"error": {"code": "bad_request", "message": "x"}})

    inv = _make_inv(handler)
    with pytest.raises(Exception):
        inv.agents.me()
    assert calls["n"] == 1


def test_top_level_client_accepts_retry_policy():
    inv = Invariance(
        api_key="inv_test_abc",
        api_url="http://test.local",
        retry_policy=RetryPolicy(max_retries=7, base_seconds=0.0, jitter=0.0),
    )
    try:
        assert inv._http._retry.max_retries == 7
    finally:
        inv.close()


def test_retries_on_5xx():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 2:
            return httpx.Response(503, json={"error": {"code": "internal_error", "message": "busy"}})
        return httpx.Response(200, json={"agent": {"id": "a"}})

    inv = _make_inv(handler)
    inv.agents.me()
    assert calls["n"] == 2


def test_mutating_retries_reuse_idempotency_key():
    keys: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        keys.append(request.headers.get("Idempotency-Key"))
        if len(keys) == 1:
            return httpx.Response(503, json={"error": {"code": "internal_error", "message": "busy"}})
        return httpx.Response(200, json={"ok": True})

    inv = _make_inv(handler)
    inv._http.post("/v1/signals", json={"title": "x"})

    assert len(keys) == 2
    assert keys[0]
    assert keys[0] == keys[1]


@pytest.mark.asyncio
async def test_async_retries_on_429():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 2:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": {"code": "rate_limited", "message": "x"}})
        return httpx.Response(200, json={"agent": {"id": "a"}})

    inv = AsyncInvariance(api_key="inv_test_abc", api_url="http://test.local")
    inv._http._retry = RetryPolicy(max_retries=3, base_seconds=0.0, jitter=0.0)
    inv._http._client = httpx.AsyncClient(
        base_url="http://test.local",
        headers={"Authorization": "Bearer inv_test_abc"},
        transport=httpx.MockTransport(handler),
    )
    try:
        await inv.agents.me()
    finally:
        await inv.aclose()
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_async_mutating_retries_reuse_idempotency_key():
    keys: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        keys.append(request.headers.get("Idempotency-Key"))
        if len(keys) == 1:
            return httpx.Response(503, json={"error": {"code": "internal_error", "message": "busy"}})
        return httpx.Response(200, json={"ok": True})

    inv = AsyncInvariance(api_key="inv_test_abc", api_url="http://test.local")
    inv._http._retry = RetryPolicy(max_retries=3, base_seconds=0.0, jitter=0.0)
    inv._http._client = httpx.AsyncClient(
        base_url="http://test.local",
        headers={"Authorization": "Bearer inv_test_abc"},
        transport=httpx.MockTransport(handler),
    )
    try:
        await inv._http.post("/v1/signals", json={"title": "x"})
    finally:
        await inv.aclose()

    assert len(keys) == 2
    assert keys[0]
    assert keys[0] == keys[1]


@pytest.mark.asyncio
async def test_async_top_level_client_accepts_retry_policy():
    inv = AsyncInvariance(
        api_key="inv_test_abc",
        api_url="http://test.local",
        retry_policy=RetryPolicy(max_retries=5, base_seconds=0.0, jitter=0.0),
    )
    try:
        assert inv._http._retry.max_retries == 5
    finally:
        await inv.aclose()
