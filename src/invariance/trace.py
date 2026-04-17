"""`@trace` decorator that auto-emits a Step when a decorated function runs.

The decorator must be used inside an active Run context — that is, a
call site that ran within ``with inv.runs.start(...) as run:`` on the
same thread. The decorator finds the currently-active Run via the
``_current_run`` contextvar set by :class:`Run.__enter__` equivalent.

Since Run does not itself install a contextvar (users can have multiple
Runs open concurrently), the trace decorator takes the Run explicitly or
is created via ``inv.trace(...)`` when there is exactly one expected.
"""

from __future__ import annotations

import functools
import inspect
from typing import Any, Callable, TypeVar

from .runs import Run, Step

F = TypeVar("F", bound=Callable[..., Any])


def trace(
    run: Run,
    action_type: str | None = None,
    *,
    capture_args: bool = True,
    capture_return: bool = True,
) -> Callable[[F], F]:
    """Decorate a function so each call emits a Step in ``run``.

    Args:
      run: the active Run. Nested calls within the wrapped function
        auto-link via ``parent_id`` thanks to :class:`Step`.
      action_type: label stored on the emitted node. Defaults to the
        wrapped function's ``__qualname__``.
      capture_args: if True, pass bound args as the Step's ``input``.
      capture_return: if True, pass the return value as ``output``.
    """

    def decorator(fn: F) -> F:
        label = action_type or fn.__qualname__
        sig = inspect.signature(fn)

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            input_payload: Any = None
            if capture_args:
                try:
                    bound = sig.bind(*args, **kwargs)
                    bound.apply_defaults()
                    input_payload = dict(bound.arguments)
                except TypeError:
                    input_payload = {"args": args, "kwargs": kwargs}
            with run.step(label, input=input_payload) as s:
                result = fn(*args, **kwargs)
                if capture_return:
                    s.output = result
                return result

        return wrapper  # type: ignore[return-value]

    return decorator
