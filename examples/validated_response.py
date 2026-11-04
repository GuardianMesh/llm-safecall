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
