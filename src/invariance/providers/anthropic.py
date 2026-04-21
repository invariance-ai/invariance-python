"""Anthropic client instrumentation. Wraps ``messages.create``."""

from __future__ import annotations

import time
from typing import Any

from .pricing import price_call


class _MessagesProxy:
    def __init__(self, inner: Any, run: Any) -> None:
        self._inner = inner
        self._run = run

    def create(self, *args: Any, **kwargs: Any) -> Any:
        model = kwargs.get("model", "unknown")
        start = time.time()
        error: Any = None
        result: Any = None
        try:
            result = self._inner.create(*args, **kwargs)
            return result
        except Exception as e:
            error = {"type": type(e).__name__, "message": str(e)}
            raise
        finally:
            latency_ms = int((time.time() - start) * 1000)
            usage = _extract_usage(result)
            cost = price_call(
                model,
                usage["input_tokens"],
                usage["output_tokens"],
                cache_read_tokens=usage["cache_read_tokens"],
                cache_write_tokens=usage["cache_write_tokens"],
            )
            with self._run.step(
                "llm_call",
                type="llm_call",
                metadata={
                    "llm": {
                        "provider": "anthropic",
                        "model": model,
                        **usage,
                        "cost_usd": cost,
                        "latency_ms": latency_ms,
                        "status": "error" if error else "success",
                    }
                },
            ) as s:
                if error:
                    s.error = error


class _AnthropicProxy:
    def __init__(self, client: Any, run: Any) -> None:
        self._client = client
        self.messages = _MessagesProxy(client.messages, run)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


def _extract_usage(result: Any) -> dict[str, int]:
    usage = getattr(result, "usage", None)
    if usage is None and isinstance(result, dict):
        usage = result.get("usage")
    if usage is None:
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
        }

    def g(obj: Any, name: str) -> int:
        v = getattr(obj, name, None)
        if v is None and isinstance(obj, dict):
            v = obj.get(name)
        return int(v or 0)

    return {
        "input_tokens": g(usage, "input_tokens"),
        "output_tokens": g(usage, "output_tokens"),
        "cache_read_tokens": g(usage, "cache_read_input_tokens"),
        "cache_write_tokens": g(usage, "cache_creation_input_tokens"),
    }


def instrument_anthropic(client: Any, run: Any) -> Any:
    return _AnthropicProxy(client, run)
