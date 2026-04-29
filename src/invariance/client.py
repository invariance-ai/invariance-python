from __future__ import annotations

import time
from typing import Any

import httpx

from ._retry import RetryPolicy, backoff_delay, parse_retry_after, should_retry


class InvarianceApiError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        details: Any | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.details = details
        self.request_id = request_id


class RateLimitError(InvarianceApiError):
    """Raised when the server returned 429 and retries are exhausted."""


class HttpClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )
        self._retry = retry_policy or RetryPolicy()

    def request(self, method: str, path: str, *, json: Any | None = None) -> Any:
        last_status = 0
        for attempt in range(self._retry.max_retries + 1):
            res = self._client.request(method, path, json=json)
            if res.status_code < 400 or not should_retry(res.status_code):
                break
            last_status = res.status_code
            if attempt >= self._retry.max_retries:
                break
            retry_after = parse_retry_after(res.headers.get("Retry-After"))
            time.sleep(backoff_delay(self._retry, attempt + 1, retry_after))
        if res.status_code >= 400:
            body: dict[str, Any] = {}
            try:
                body = res.json()
            except Exception:
                pass
            err = body.get("error", {})
            cls = RateLimitError if last_status == 429 else InvarianceApiError
            raise cls(
                status=res.status_code,
                code=err.get("code", "unknown"),
                message=err.get("message", f"HTTP {res.status_code}"),
                details=err.get("details"),
                request_id=err.get("request_id"),
            )
        if res.status_code == 204 or not res.content:
            return None
        return res.json()

    def get(self, path: str) -> Any:
        return self.request("GET", path)

    def post(self, path: str, json: Any | None = None) -> Any:
        return self.request("POST", path, json=json)

    def patch(self, path: str, json: Any | None = None) -> Any:
        return self.request("PATCH", path, json=json)

    def delete(self, path: str) -> Any:
        return self.request("DELETE", path)

    def close(self) -> None:
        self._client.close()
