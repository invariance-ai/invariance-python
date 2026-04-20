"""Best-effort $/token pricing.

Prices are baked in for major models; users can override via
``INVARIANCE_PRICING_OVERRIDE`` (path to JSON) or :func:`register_pricing`.
Unknown models price to 0.0 — callers are responsible for noticing.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PricingEntry:
    """USD per 1K tokens. Cache-read/write optional (Anthropic-style)."""

    input_per_1k: float
    output_per_1k: float
    cache_read_per_1k: float = 0.0
    cache_write_per_1k: float = 0.0


# Representative prices circa 2026; users should override for exact billing.
_BUILTIN: dict[str, PricingEntry] = {
    # OpenAI
    "gpt-4o":              PricingEntry(0.0025, 0.010),
    "gpt-4o-mini":         PricingEntry(0.00015, 0.0006),
    "gpt-4-turbo":         PricingEntry(0.010, 0.030),
    "gpt-3.5-turbo":       PricingEntry(0.0005, 0.0015),
    "o1":                  PricingEntry(0.015, 0.060),
    "o1-mini":             PricingEntry(0.003, 0.012),
    # Anthropic
    "claude-opus-4-7":     PricingEntry(0.015, 0.075, 0.0015, 0.01875),
    "claude-sonnet-4-6":   PricingEntry(0.003, 0.015, 0.0003, 0.00375),
    "claude-haiku-4-5":    PricingEntry(0.0008, 0.004, 0.00008, 0.001),
    "claude-3-5-sonnet":   PricingEntry(0.003, 0.015),
    "claude-3-5-haiku":    PricingEntry(0.0008, 0.004),
    # Google
    "gemini-2.0-flash":    PricingEntry(0.000075, 0.0003),
    "gemini-1.5-pro":      PricingEntry(0.00125, 0.005),
}

_OVERRIDES: dict[str, PricingEntry] = {}


def _load_overrides() -> None:
    path = os.environ.get("INVARIANCE_PRICING_OVERRIDE")
    if not path or not os.path.exists(path):
        return
    try:
        with open(path) as f:
            raw = json.load(f)
        for model, entry in raw.items():
            _OVERRIDES[model] = PricingEntry(
                input_per_1k=float(entry.get("input_per_1k", 0.0)),
                output_per_1k=float(entry.get("output_per_1k", 0.0)),
                cache_read_per_1k=float(entry.get("cache_read_per_1k", 0.0)),
                cache_write_per_1k=float(entry.get("cache_write_per_1k", 0.0)),
            )
    except (OSError, ValueError, KeyError):
        # Silently ignore malformed override file — pricing is non-critical.
        pass


_load_overrides()


def register_pricing(model: str, entry: PricingEntry) -> None:
    _OVERRIDES[model] = entry


def _lookup(model: str) -> PricingEntry | None:
    if model in _OVERRIDES:
        return _OVERRIDES[model]
    if model in _BUILTIN:
        return _BUILTIN[model]
    # Prefix match for versioned aliases like "gpt-4o-2024-08-06".
    for prefix, entry in _BUILTIN.items():
        if model.startswith(prefix + "-") or model.startswith(prefix + ":"):
            return entry
    return None


def price_call(
    model: str,
    input_tokens: int,
    output_tokens: int,
    *,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    entry = _lookup(model)
    if entry is None:
        return 0.0
    return round(
        (input_tokens * entry.input_per_1k / 1000.0)
        + (output_tokens * entry.output_per_1k / 1000.0)
        + (cache_read_tokens * entry.cache_read_per_1k / 1000.0)
        + (cache_write_tokens * entry.cache_write_per_1k / 1000.0),
        6,
    )
