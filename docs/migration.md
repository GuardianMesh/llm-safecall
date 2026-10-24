# Migration to 0.2.3

These changes apply to version 0.2.3. Update the package before using the new
behavior described below.

## Pickle caches

Pickle cache files are no longer supported. Point `Cache` at a new `.json`
file and let responses populate it. Old files are rejected without loading,
converting, or deleting them. Do not unpickle an old cache to migrate it.

Caches now default to memory. Entries are scoped to one `SafeCall` instance
and do not carry across a restart, even with file storage. Direct `Cache.set()`
values must be JSON-compatible.

## Pricing

The example model prices have been removed. Register rates that match your
provider contract. For example, if your own rate is 0.2 currency units per
1,000 input tokens and 0.5 per 1,000 output tokens:

```python
from llm_safecall.pricing import PRICING, estimate_cost

PRICING["my-provider:my-model"] = {"input": 0.2, "output": 0.5}
assert estimate_cost("my-provider:my-model", 2000, 1000) == 0.9
```

Missing rates or incomplete usage now return `None`. Invalid rates and counts
raise `ValueError`. Built-in adapters do not use this helper automatically.

## Checks and providers

Invalid policy keys, provider names, retry counts, and timeouts now raise during
configuration. Oversized output is rejected instead of truncated. Failed
repairs and streams count toward the circuit; `reset_circuit()` reopens it.

The Anthropic adapter uses `claude-sonnet-4-6` as its default and rejects
`temperature`, `top_p`, and `top_k`. Set models explicitly and test adapter
compatibility before deployment.
