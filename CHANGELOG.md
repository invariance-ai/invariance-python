# Changelog

All notable changes to `invariance-sdk` (Python) are documented here. This project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.2] - 2026-04-24

### Added

- `node_types` resource on both `Invariance` and `AsyncInvariance` clients (parity with TS `inv.nodeTypes`). Wraps `/v1/node-types` `list` and `register`.

### Changed

- Version aligned with `@invariance/sdk` (TypeScript) at `0.1.2` — both SDKs publish in lockstep going forward.

## [0.1.0] - 2026-04-24

Initial MVP release.

### Added

- Sync `Invariance` and async `AsyncInvariance` clients.
- Resources: `runs`, `nodes`, `monitors`, `signals`, `findings`, `reviews`, `agents`, `proofs`, `narratives`.
- Run context manager with auto-finish / auto-fail semantics.
- `Step` context manager for nested node emission.
- Node writes against `/v1/trace/events` with canonical hashing (`hash_node_payload`).
- Ed25519 signing helpers (`generate_keypair`, `sign_ed25519`, `verify_ed25519`).
- `@trace` decorator for function-level instrumentation.
- Handoff token helpers for cross-run lineage.
