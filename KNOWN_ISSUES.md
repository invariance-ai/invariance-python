# Known Issues — invariance-python

Seeded from the 2026-04-25 cross-repo audit.

| ID | Severity | Title | Test | Status |
|----|----------|-------|------|--------|
| PY-001 | low | 4 `# type: ignore` for decorator inference + optional numpy | n/a | accepted |
| PY-002 | medium | No integration tests (only unit tests with respx mocks) | `tests/test_integration.py` | open |

## Item details

### PY-001 — `# type: ignore` comments
Four occurrences:
- `src/invariance/trace.py:62` (decorator return type)
- `src/invariance/replay.py:46` (numpy optional import)
- `src/invariance/replay.py:79` (decorator)
- `src/invariance/async_client.py:833` (decorator return type)

**Accepted.** Decorator inference and optional-dependency imports are well-known mypy limitations. Replacing them would require Protocol overloads that obscure the public API for marginal type-checker benefit. Revisit when Python 3.13 + mypy improve decorator inference, or when numpy becomes a hard dependency.

### PY-002 — No integration tests
The 81-test suite is entirely unit-tested with `respx` mocking HTTP. No test hits a real platform.

Fix: add `tests/test_integration.py` (gated behind `INVARIANCE_E2E` env var) that drives the full Run/Step/Monitor/Review loop against a locally booted platform. Done when CI can run the suite green against a service running in another job.
