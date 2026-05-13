"""Run-level operational context.

Bag of metadata plus the memory trace and authoritative system records that
grounded an agent's decisions.
"""

from __future__ import annotations

from ._types import OperationalContext


def empty_operational_context() -> OperationalContext:
    """Default the memory + record arrays so callers can spread partial input."""
    return {
        "memory_reads": [],
        "memory_writes": [],
        "authoritative_records": [],
    }


__all__ = ["OperationalContext", "empty_operational_context"]
