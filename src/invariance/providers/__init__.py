"""Optional LLM provider instrumentation helpers.

These wrap the vendor SDK client call surface (rather than monkey-patching)
so users opt in explicitly and parallel invocations don't get hijacked.

Usage::

    from openai import OpenAI
    from invariance.providers import instrument_openai

    oa = instrument_openai(OpenAI(), run)
    resp = oa.chat.completions.create(model="gpt-4o-mini", messages=[...])
    # resp is returned as-is; a node with metadata.llm = {tokens, cost, ...}
    # is emitted as a side effect.
"""

from .openai import instrument_openai
from .anthropic import instrument_anthropic
from .pricing import price_call, register_pricing, PricingEntry

__all__ = [
    "instrument_openai",
    "instrument_anthropic",
    "price_call",
    "register_pricing",
    "PricingEntry",
]
