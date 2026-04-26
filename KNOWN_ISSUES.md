# Known Issues — invariance-python

Seeded from the 2026-04-25 cross-repo audit.

| ID | Severity | Title | Test | Status |
|----|----------|-------|------|--------|
| PY-001 | low | 4 `# type: ignore` for decorator inference + optional numpy | n/a | accepted |
| PY-002 | medium | Live integration test is env-gated and not wired into CI | `tests/test_integration.py` | in_progress |

## Item details

### PY-001 — `# type: ignore` comments
Four occurrences:
- `src/invariance/trace.py:62` (decorator return type)
- `src/invariance/replay.py:46` (numpy optional import)
- `src/invariance/replay.py:79` (decorator)
- `src/invariance/async_client.py:833` (decorator return type)

**Accepted.** Decorator inference and optional-dependency imports are well-known mypy limitations. Replacing them would require Protocol overloads that obscure the public API for marginal type-checker benefit. Revisit when Python 3.13 + mypy improve decorator inference, or when numpy becomes a hard dependency.

### PY-002 — Live integration coverage is not in CI
`tests/test_integration.py` now contains an executable MVP dry run gated behind `INVARIANCE_E2E=1` and `INVARIANCE_API_KEY`. Normal unit runs still skip it.

Fix: wire CI to run the test against a local or staging platform service. Done when CI runs the env-gated suite green against a service in another job.
