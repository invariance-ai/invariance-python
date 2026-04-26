"""Integration tests against a real platform (PY-002).

Skipped unless INVARIANCE_E2E=1 and INVARIANCE_API_KEY is set. Drives the
Run/Step/Monitor/Review loop end-to-end against a live API.
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("INVARIANCE_E2E") != "1",
    reason="set INVARIANCE_E2E=1 to run integration tests",
)


@pytest.mark.skip(reason="todo: implement once boot harness exists")
def test_run_lifecycle_against_live_platform() -> None:
    """Start a run, write 5 nodes, finish, fetch back, verify proof."""


@pytest.mark.skip(reason="todo")
def test_monitor_evaluate_creates_signal_and_finding() -> None:
    """Create keyword monitor, evaluate against the run, expect signal+finding+review."""


@pytest.mark.skip(reason="todo")
def test_canonical_hash_matches_typescript_sdk() -> None:
    """Drive a fixture run, assert the canonical hash matches the TS SDK output (XR-002)."""
