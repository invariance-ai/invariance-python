"""Shared retry policy for sync + async HTTP clients.

Retries on 429 and 5xx with exponential backoff + jitter. Honors the
``Retry-After`` response header when the server sets it (seconds form only;
HTTP-date form is ignored as the SDK never talks to caches that use it).
"""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 3
    base_seconds: float = 0.5
    factor: float = 2.0
    max_seconds: float = 30.0
    jitter: float = 0.25  # ± fraction of the computed delay


def should_retry(status_code: int) -> bool:
    return status_code == 429 or 500 <= status_code < 600


def parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        n = float(value.strip())
    except ValueError:
        return None
    if n < 0:
        return None
    return n


def backoff_delay(policy: RetryPolicy, attempt: int, retry_after: float | None = None) -> float:
    """Delay before attempt `attempt` (1-indexed retry number).

    If the server supplied a Retry-After, honor it (clamped to max_seconds).
    Otherwise use exponential backoff with multiplicative jitter.
    """
    if retry_after is not None:
        return min(retry_after, policy.max_seconds)
    base = min(policy.max_seconds, policy.base_seconds * (policy.factor ** (attempt - 1)))
    jitter_range = base * policy.jitter
    return max(0.0, base + random.uniform(-jitter_range, jitter_range))
