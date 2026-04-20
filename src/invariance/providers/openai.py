"""OpenAI client instrumentation.

Wraps ``chat.completions.create`` (sync + async). Extracts ``usage.*_tokens``,
prices the call, and emits an ``llm_call`` node on the provided run.
"""

from __future__ import annotations

import time
from typing import Any

from .pricing import price_call


class _CompletionsProxy:
    def __init__(self, inner: Any, run: Any, provider: str = "openai") -> None:
        self._inner = inner
        self._run = run
        self._provider = provider

    def create(self, *args: Any, **kwargs: Any) -> Any:
        model = kwargs.get("model") or (args[0] if args else "unknown")
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
                        "provider": self._provider,
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


class _ChatProxy:
    def __init__(self, inner: Any, run: Any, provider: str) -> None:
        self.completions = _CompletionsProxy(inner.completions, run, provider)


class _OpenAIProxy:
    def __init__(self, client: Any, run: Any, provider: str) -> None:
        self._client = client
        self.chat = _ChatProxy(client.chat, run, provider)

    def __getattr__(self, name: str) -> Any:
        # Passthrough for untouched surface (embeddings, files, etc.).
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

    def g(obj: Any, *names: str) -> int:
        for n in names:
            v = getattr(obj, n, None)
            if v is None and isinstance(obj, dict):
                v = obj.get(n)
            if v is not None:
                return int(v)
        return 0

    cached = 0
    details = getattr(usage, "prompt_tokens_details", None)
    if details is None and isinstance(usage, dict):
        details = usage.get("prompt_tokens_details")
    if details is not None:
        cached = g(details, "cached_tokens")

    return {
        "input_tokens": g(usage, "prompt_tokens", "input_tokens"),
        "output_tokens": g(usage, "completion_tokens", "output_tokens"),
        "cache_read_tokens": cached,
        "cache_write_tokens": 0,
    }


def instrument_openai(client: Any, run: Any, *, provider: str = "openai") -> Any:
    """Return a proxy around ``client`` that emits an llm_call node per completion.

    The ``provider`` kwarg lets callers label calls to OpenAI-compatible APIs
    (vLLM, Together, Groq, Azure OpenAI) distinctly in the dashboard.
    """
    return _OpenAIProxy(client, run, provider)
