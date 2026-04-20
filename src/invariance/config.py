from __future__ import annotations

import os
from dataclasses import dataclass, field

DEFAULT_API_URL = "https://api.useinvariance.com"


@dataclass(frozen=True)
class Features:
    replay: bool = False
    cost_tracking: bool = True


@dataclass(frozen=True)
class ResolvedConfig:
    api_key: str
    api_url: str
    signing_key: str | None
    features: Features = field(default_factory=Features)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def resolve_config(
    api_key: str | None = None,
    api_url: str | None = None,
    signing_key: str | None = None,
    features: dict[str, bool] | None = None,
) -> ResolvedConfig:
    key = api_key or os.environ.get("INVARIANCE_API_KEY")
    if not key:
        raise ValueError("api_key is required (pass arg or set INVARIANCE_API_KEY)")

    url = api_url or os.environ.get("INVARIANCE_API_URL") or DEFAULT_API_URL
    sig = signing_key or os.environ.get("INVARIANCE_SIGNING_KEY")

    f = features or {}
    replay = f["replay"] if "replay" in f else _env_bool("INVARIANCE_FEATURE_REPLAY", False)
    cost = f["cost_tracking"] if "cost_tracking" in f else _env_bool("INVARIANCE_COST_TRACKING", True)

    return ResolvedConfig(
        api_key=key,
        api_url=url,
        signing_key=sig,
        features=Features(replay=replay, cost_tracking=cost),
    )
