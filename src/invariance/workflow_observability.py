"""Workflow observability — read-only rollups + per-execution health.

Mirrors platform routes ``GET /v1/workflow-observability`` (rollups across
every workflow_key), ``GET /v1/workflow-observability/:workflow_key`` (single
rollup) and ``.../:workflow_key/executions`` (per-case health). Reads accept an
agent **or** operator key.
"""

from __future__ import annotations

from ._types import (
    WorkflowExecutionHealthList,
    WorkflowObservabilityRollup,
    WorkflowObservabilityRollupList,
)
from .client import HttpClient


class WorkflowObservabilityResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def list(self) -> WorkflowObservabilityRollupList:
        """Rollups across every workflow_key (``next_cursor`` is always null)."""
        return self._http.get("/v1/workflow-observability")

    def get(self, workflow_key: str) -> WorkflowObservabilityRollup:
        """The rollup for a single workflow_key."""
        res = self._http.get(f"/v1/workflow-observability/{workflow_key}")
        return res["rollup"]

    def executions(self, workflow_key: str) -> WorkflowExecutionHealthList:
        """Per-execution (case) health for a workflow_key."""
        return self._http.get(
            f"/v1/workflow-observability/{workflow_key}/executions"
        )
