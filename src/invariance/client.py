from __future__ import annotations

from typing import Any

import httpx


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


class HttpClient:
    def __init__(self, base_url: str, api_key: str) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )

    def request(self, method: str, path: str, *, json: Any | None = None) -> Any:
        res = self._client.request(method, path, json=json)
        if res.status_code >= 400:
            body: dict[str, Any] = {}
            try:
                body = res.json()
            except Exception:
                pass
            err = body.get("error", {})
            raise InvarianceApiError(
                status=res.status_code,
                code=err.get("code", "unknown"),
                message=err.get("message", f"HTTP {res.status_code}"),
                details=err.get("details"),
                request_id=err.get("request_id"),
            )
        return res.json()

    def get(self, path: str) -> Any:
        return self.request("GET", path)

    def post(self, path: str, json: Any | None = None) -> Any:
        return self.request("POST", path, json=json)

    def patch(self, path: str, json: Any | None = None) -> Any:
        return self.request("PATCH", path, json=json)

    def close(self) -> None:
        self._client.close()
