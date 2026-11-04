# Validate LLM responses with Pydantic and retries in Python

Use the published `llm-safecall==0.2.3` package to validate a model response,
retry a transient failure and inspect a call report. A deterministic local
provider makes the example runnable without credentials, provider SDKs or
network requests during execution.

## Install

Use Python 3.10 or newer. These commands use a POSIX shell; the example was
verified with Python 3.12 in a new virtual environment.

```sh
mkdir safecall-python-demo
cd safecall-python-demo
python3 -m venv .venv
. .venv/bin/activate
python -m pip install 'llm-safecall==0.2.3'
```

## Run the example

Save this as `validated_response.py`:

```python
"""Exercise the published SafeCall API using a local provider and fictional data."""

import json

from pydantic import BaseModel, ValidationError

from llm_safecall import SafeCall
from llm_safecall.providers.base import ProviderResponse


class Summary(BaseModel):
    title: str
    count: int


class FixtureProvider:
    model = "local-fixture"

    def __init__(self, responses):
        self.responses = responses
        self.calls = 0

    def complete(self, prompt, **params):
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        if isinstance(response, Exception):
            raise response
        return ProviderResponse(
            text=json.dumps(response),
            input_tokens=10,
            output_tokens=5,
            model=self.model,
            cost=0.0,
        )

    def stream(self, prompt, **params):
        yield self.complete(prompt, **params).text


valid = {"title": "Quarterly report", "count": 2}
invalid = {"title": [], "count": "two"}
accepted = SafeCall(FixtureProvider([valid]), output=Summary, retries=0)
result = accepted.generate("Return the fixture report.")
assert result.model_dump() == valid
assert result._report.model == "local-fixture"
print(f"VALIDATED {json.dumps(result.model_dump())}; call report attached")

retry_provider = FixtureProvider([RuntimeError("Synthetic transient failure"), valid])
retried = SafeCall(retry_provider, output=Summary, retries=1).generate(
    "Return the fixture report after a transient failure."
)
assert retried.model_dump() == valid
assert retry_provider.calls == 2
print(f"RETRIED transient failure; provider calls: {retry_provider.calls}")

invalid_provider = FixtureProvider([invalid])
try:
    SafeCall(invalid_provider, output=Summary, retries=0).generate("Return the invalid fixture.")
except ValidationError:
    assert invalid_provider.calls == 2  # Initial response and one schema-repair attempt.
    print(f"REJECTED invalid schema after one repair; provider calls: {invalid_provider.calls}")
else:
    raise AssertionError("Invalid schema unexpectedly accepted")

fallback = SafeCall(
    FixtureProvider([invalid]),
    output=Summary,
    retries=0,
    fail_safe=True,
    fail_safe_return="Summary unavailable",
).generate("Return the display-only fallback fixture.")
assert isinstance(fallback, str) and fallback == "Summary unavailable"
print("FALLBACK Summary unavailable; string, not validated schema output")
print("All assertions passed. Local fixtures; no network or model requests.")
```

```sh
python validated_response.py
```

Expected standard output:

```text
VALIDATED {"title": "Quarterly report", "count": 2}; call report attached
RETRIED transient failure; provider calls: 2
REJECTED invalid schema after one repair; provider calls: 2
FALLBACK Summary unavailable; string, not validated schema output
All assertions passed. Local fixtures; no network or model requests.
```

## Use validation and fallback deliberately

The default logger also writes call events to standard error; timestamps and
call IDs vary.

Calls raise by default. Invalid JSON or schema output can make one additional
repair call. `retries=0` disables transient retries while preserving that repair
step. Live providers can charge for initial requests, retries and repairs.

Pydantic validates the typed result; this example uses its default validation
rules. Configure strict fields when your domain needs strict types. The
explicit `fail_safe` fallback is a string, not a Pydantic result, and is suitable
for display rather than driving typed application behavior.

SafeCall validates model calls; it does not authorize tools. The
[package selection guide](https://github.com/ShieldaAI/agent-guard/blob/main/docs/package-guide.md)
explains the separate tool-authorization and advisory-monitoring components.
For Zod and Node.js, use the
[Node example](https://github.com/GuardianMesh/llm-safecall-node/blob/main/docs/validated-responses.md).

See [behavior](behavior.md), [migration](migration.md), and the
[standalone Python example](../examples/validated_response.py). Python and npm
versions and API names are independent.

