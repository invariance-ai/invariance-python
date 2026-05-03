"""Deterministic replay / fork support.

Gated behind the ``replay`` feature flag (``INVARIANCE_FEATURE_REPLAY=true``)
so users who don't care about reproducibility pay no overhead.

Usage::

    inv = Invariance()  # features.replay picked up from env

    @reproducible(seed="run-42")
    def agent(run):
        ...

    with inv.runs.start(name="demo", replay_seed="run-42") as run:
        agent(run)

To re-run deterministically from a checkpoint, fork the run from any node::

    forked = inv.runs.fork(run.run_id, from_node_id=some_node_id)

The fork inherits ``replay_seed``; wrap the replay function with
``@reproducible(seed=forked.replay_seed)`` to restore PRNG state before
re-execution.
"""

from __future__ import annotations

import functools
import hashlib
import os
import random
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def _seed_prngs(seed: str) -> None:
    # Derive a 64-bit int from the string seed so all PRNGs line up.
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    int_seed = int.from_bytes(digest[:8], "big", signed=False)

    random.seed(int_seed)
    os.environ.setdefault("PYTHONHASHSEED", str(int_seed % (2**32)))

    try:
        import numpy as np

        np.random.seed(int_seed % (2**32))
    except ImportError:
        pass


def reproducible(*, seed: str | None = None) -> Callable[[F], F]:
    """Decorator that seeds PRNGs before the wrapped function runs.

    No-op when ``INVARIANCE_FEATURE_REPLAY`` is not set — users opt in at the
    deployment level rather than per-call.
    """

    def decorator(fn: F) -> F:
        enabled = os.environ.get("INVARIANCE_FEATURE_REPLAY", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )

        if not enabled:
            return fn

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            s = seed or kwargs.pop("_replay_seed", None)
            if s is None:
                raise ValueError("reproducible() requires a seed")
            _seed_prngs(s)
            return fn(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
