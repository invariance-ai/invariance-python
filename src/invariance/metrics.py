"""Metrics — usage + cost rollups over a trailing window.

``overview`` returns aggregate totals, a success rate, a latency figure and a
time series; ``agents`` returns per-agent usage rows. The window defaults to
24h and is capped server-side at 2160h (90d). Reads accept an agent **or**
operator key.
"""

from __future__ import annotations

from ._query import with_query
from ._types import AgentUsage, OverviewMetrics
from .client import HttpClient


class MetricsResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def overview(self, *, window_hours: int | None = None) -> OverviewMetrics:
        res = self._http.get(
            with_query("/v1/metrics/overview", window_hours=window_hours)
        )
        return res["metrics"]

    def agents(self, *, window_hours: int | None = None) -> list[AgentUsage]:
        res = self._http.get(
            with_query("/v1/metrics/agents", window_hours=window_hours)
        )
        return res["usage"]
