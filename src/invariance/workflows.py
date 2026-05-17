"""Workflow definitions — typed fields, steps, outcomes, and custom metrics."""

from __future__ import annotations

from ._types import (
    WorkflowDefinition,
    WorkflowDefinitionField,
    WorkflowDefinitionOutcome,
    WorkflowDefinitionStep,
    WorkflowMetricWidget,
)
from .client import HttpClient


class WorkflowDefinitionsResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def create(
        self,
        *,
        key: str,
        display_name: str,
        description: str | None = None,
        expected_fields: list[WorkflowDefinitionField] | None = None,
        expected_steps: list[WorkflowDefinitionStep] | None = None,
        allowed_outcomes: list[WorkflowDefinitionOutcome] | None = None,
        custom_metrics: list[WorkflowMetricWidget] | None = None,
    ) -> WorkflowDefinition:
        body = self._body(
            display_name=display_name,
            description=description,
            expected_fields=expected_fields,
            expected_steps=expected_steps,
            allowed_outcomes=allowed_outcomes,
            custom_metrics=custom_metrics,
        )
        body["key"] = key
        res = self._http.post("/v1/workflow-definitions", json=body)
        return res["definition"]

    def get(self, key: str) -> WorkflowDefinition:
        res = self._http.get(f"/v1/workflow-definitions/{key}")
        return res["definition"]

    def list(self) -> dict[str, list[WorkflowDefinition]]:
        return self._http.get("/v1/workflow-definitions")

    def update(
        self,
        key: str,
        *,
        display_name: str | None = None,
        description: str | None = None,
        expected_fields: list[WorkflowDefinitionField] | None = None,
        expected_steps: list[WorkflowDefinitionStep] | None = None,
        allowed_outcomes: list[WorkflowDefinitionOutcome] | None = None,
        custom_metrics: list[WorkflowMetricWidget] | None = None,
    ) -> WorkflowDefinition:
        body = self._body(
            display_name=display_name,
            description=description,
            expected_fields=expected_fields,
            expected_steps=expected_steps,
            allowed_outcomes=allowed_outcomes,
            custom_metrics=custom_metrics,
        )
        res = self._http.patch(f"/v1/workflow-definitions/{key}", json=body)
        return res["definition"]

    def delete(self, key: str) -> dict[str, bool]:
        return self._http.delete(f"/v1/workflow-definitions/{key}")

    @staticmethod
    def _body(
        *,
        display_name: str | None = None,
        description: str | None = None,
        expected_fields: list[WorkflowDefinitionField] | None = None,
        expected_steps: list[WorkflowDefinitionStep] | None = None,
        allowed_outcomes: list[WorkflowDefinitionOutcome] | None = None,
        custom_metrics: list[WorkflowMetricWidget] | None = None,
    ) -> dict[str, object]:
        body: dict[str, object] = {}
        if display_name is not None:
            body["display_name"] = display_name
        if description is not None:
            body["description"] = description
        if expected_fields is not None:
            body["expected_fields"] = expected_fields
        if expected_steps is not None:
            body["expected_steps"] = expected_steps
        if allowed_outcomes is not None:
            body["allowed_outcomes"] = allowed_outcomes
        if custom_metrics is not None:
            body["custom_metrics"] = custom_metrics
        return body
