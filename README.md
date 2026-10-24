# llm-safecall

Validate model responses with Pydantic, retry failed requests, and keep a call
report. Supports OpenAI, Anthropic, and custom providers on Python 3.10+.

Use it when several call sites need the same validation and error handling.
If your application already handles those in a provider SDK or framework,
you probably don't need another wrapper.

The text filters match known patterns. They can miss attacks and reject harmless
text. Tool permissions, approvals, and process isolation belong in the
application; this package does not enforce them.

## Install

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install 'llm-safecall[openai]'
```

Use the `anthropic` extra for Anthropic, or install `llm-safecall` without extras
to use your own provider. On Windows, activate with
`.venv\Scripts\Activate.ps1`.

For changes in **0.2.3**, see the
[changelog](https://github.com/GuardianMesh/llm-safecall/blob/main/CHANGELOG.md)
and [migration notes](https://github.com/GuardianMesh/llm-safecall/blob/main/docs/migration.md).

## Validate a response

Set `OPENAI_API_KEY` and `LLM_MODEL` to a model available to your account.

```python
import os

from pydantic import BaseModel
from llm_safecall import OpenAIProvider, SafeCall


class Summary(BaseModel):
    title: str
    summary: str


safe = SafeCall(
    OpenAIProvider(model=os.environ["LLM_MODEL"]),
    output=Summary,
    timeout_s=15,
    retries=2,
)
result = safe.generate('Return a title and summary about unit tests.')
print(result.model_dump())
print(result._report.model_dump())
```

The schema is included in the prompt. Invalid JSON or a schema mismatch gets
one repair call; a policy rejection raises immediately. Requests can incur
charges, including retries and repairs.

Without `output=`, the result is a string with the same `_report` attribute.
To check installation without credentials:

```sh
LLM_PROVIDER=mock llm-safecall --prompt "Hello"
```

## Handle errors

Calls raise by default. Catch errors where your application can decide whether
to retry later, show a message, or abandon the operation. Set `retries=0` if
another layer already retries requests.

For a display-only fallback, opt in explicitly:

```python
safe = SafeCall(
    OpenAIProvider(model=os.environ["LLM_MODEL"]),
    output=Summary,
    fail_safe=True,
    fail_safe_return="Summary unavailable",
)
result = safe.generate("Summarize the release notes.")
if isinstance(result, str):
    print(result)
else:
    print(result.title)
```

A fallback is always a string, even with a schema. It is not a validated result.

## Configure checks

Pass `policy=load_policy("policy.yml")` to load a
[policy file](https://github.com/GuardianMesh/llm-safecall/blob/main/policy.yml.example).
Use `redact=["email", "phone"]` for input redaction. Settings from the process
environment are available through `from_env()`; it does not load `.env` files.

Streaming checks individual chunks. A secret or other pattern split across
chunks can pass through. Use `generate()` when the complete response must pass
validation before anything is displayed or executed.

The [behavior reference](https://github.com/GuardianMesh/llm-safecall/blob/main/docs/behavior.md)
covers defaults, retries, streaming, tools, reports, budgets, caches, and the CLI.
Read the [migration notes](https://github.com/GuardianMesh/llm-safecall/blob/main/docs/migration.md)
before reusing an old cache or the pricing helper.

## Development

```sh
python -m pip install -e '.[dev]'
ruff check .
ruff format --check .
pytest --cov=llm_safecall --cov-fail-under=85
python -m build
python -m twine check dist/*
python scripts/check_package.py dist/*.whl
```

[Contributing](https://github.com/GuardianMesh/llm-safecall/blob/main/CONTRIBUTING.md)
· [Security reports](https://github.com/GuardianMesh/llm-safecall/blob/main/SECURITY.md)
· [MIT license](LICENSE)
