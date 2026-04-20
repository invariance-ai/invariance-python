"""Narrative reports — LLM-authored per-run summaries fetched from the backend.

Generation and provider selection stay server-side (the backend owns the LLM
API keys). This resource is a thin fetcher over ``GET /v1/runs/{id}/narrative``.
"""

from __future__ import annotations

from ._types import Narrative
from .client import HttpClient


class NarrativesResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def get(self, run_id: str, *, refresh: bool = False) -> Narrative:
        """Fetch the narrative for a run. Lazy-generates on the first call.

        Pass ``refresh=True`` to force the backend to re-synthesize, overwriting
        the cached version.

        Raises :class:`InvarianceApiError` with status 503 when no LLM provider
        is configured on the backend.
        """
        path = f"/v1/runs/{run_id}/narrative"
        if refresh:
            path += "?refresh=true"
        res = self._http.get(path)
        return res["narrative"]
