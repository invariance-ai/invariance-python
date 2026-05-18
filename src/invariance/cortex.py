"""Cortex jobs resource: generic evals, counterfactuals, attributions.

Wraps ``POST /v1/cortex/jobs`` and friends. See plan
``give-fiel-apth-for-zesty-forest.md`` for the full request/response shapes.
"""

from __future__ import annotations

from typing import Any, Literal
from urllib.parse import quote

from ._types import (
    CortexJob,
    CortexJobResult,
    CortexJobKind,
    CortexTargetType,
    CreateCortexJobResponse,
)
from .client import HttpClient


class CortexJobsResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def create(
        self,
        *,
        project_id: str,
        job_kind: CortexJobKind,
        target_type: CortexTargetType,
        target_ref: str,
        question: str | None = None,
        criteria: dict[str, Any] | None = None,
        input_refs: dict[str, Any] | None = None,
        input_payload: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> CreateCortexJobResponse:
        """Enqueue a Cortex job. Returns ``{job_id, status}`` immediately."""
        payload: dict[str, Any] = {
            "project_id": project_id,
            "job_kind": job_kind,
            "target_type": target_type,
            "target_ref": target_ref,
        }
        if question is not None:
            payload["question"] = question
        if criteria is not None:
            payload["criteria"] = criteria
        if input_refs is not None:
            payload["input_refs"] = input_refs
        if input_payload is not None:
            payload["input_payload"] = input_payload
        if options is not None:
            payload["options"] = options
        return self._http.post("/v1/cortex/jobs", json=payload)

    def get(self, job_id: str) -> CortexJob:
        """Fetch job lifecycle/status without the result body."""
        res = self._http.get(f"/v1/cortex/jobs/{quote(job_id, safe='')}")
        if isinstance(res, dict) and isinstance(res.get("job"), dict):
            return res["job"]
        return res

    def result(self, job_id: str) -> CortexJobResult:
        """Fetch the structured result.

        ``result`` key is absent while the job is still queued/running —
        callers should branch on ``status``.
        """
        return self._http.get(f"/v1/cortex/jobs/{quote(job_id, safe='')}/result")


class CortexResource:
    """Container exposed as ``client.cortex`` — currently only ``jobs``."""

    def __init__(self, http: HttpClient) -> None:
        self.jobs = CortexJobsResource(http)
