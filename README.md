# llm-safecall for Python

`llm-safecall` wraps model calls with input checks, output filtering, Pydantic
validation, retries, and structured logs. It includes adapters for OpenAI and
Anthropic, plus a local mock provider for tests.

The checks use fixed patterns and can miss prompt injections, secrets, and unsafe
output. Keep tool permissions and network access under application control, and
validate model output before executing it.

## Install

Requires Python 3.10 or later. Start in a virtual environment:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install llm-safecall
```

In Windows PowerShell, create the environment with `py -m venv .venv` and activate
with `.venv\Scripts\Activate.ps1` instead.
The base install includes the mock provider. For a live provider, install either
`python -m pip install 'llm-safecall[openai]'` or
`python -m pip install 'llm-safecall[anthropic]'`.

## Try it without an API key

Save this as `example.py` and run `python example.py`:

```python
from llm_safecall import MockProvider, SafeCall

safe = SafeCall(MockProvider())
result = safe.generate("Hello")
print(result)
print(result._report.model_dump())
```

Without an output schema, `generate()` returns a string with an attached
`_report`. With a Pydantic schema, it returns an instance of that schema:

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
    redact=["email", "phone"],
)
result = safe.generate('Return JSON with "title" and "summary" about unit tests.')
print(result.model_dump())
```

Set `OPENAI_API_KEY` and choose a model available to your account before running
that example. Provider calls and repair attempts may incur charges.

Choose a model explicitly in production. The OpenAI compatibility default,
`gpt-4o-mini`, is [scheduled for removal on January 14, 2027](https://developers.openai.com/api/docs/deprecations).
The Anthropic adapter defaults to `claude-sonnet-4-6` and rejects `temperature`,
`top_p`, and `top_k`, which are no longer supported by the current Messages API.

## Policies

Load a policy with `load_policy("policy.yml")`, then pass it as `policy=` to
`SafeCall`. The YAML keys match `PolicyConfig`:

```yaml
block_secrets: true
redact_secrets: true
allow_shell_output: false
outbound_url_allowlist:
  - "https://docs.example.com/"
json_only_when_schema: true
max_input_chars: 20000
max_output_chars: 10000
```

See [policy.yml.example](policy.yml.example) for the complete example. Omitted
injection phrases use the built-in list; an explicit empty list disables that
particular check. Shell filtering removes a small set of recognizable commands
and code blocks. URL filtering examines output text, not network requests. An
empty URL allowlist leaves URLs unchanged.
Allowed paths match a complete path or a directory beneath it. Paths containing
dot segments or encoded separators are rejected to avoid differing URL interpretations.
Input and output limits reject oversized values. Output is never truncated into
a prefix that could hide a secret delimiter. Structured checks cover decoded
JSON, nested strings and byte values, and actual Pydantic fields before and
after validation. Custom object attributes are outside these checks.

## Errors and fallback values

`generate()` raises errors by default. Set `fail_safe=True` to return
`fail_safe_return` (an empty string by default) when generation fails. This
fallback is a string even when a schema was requested, so check its type before
using it as a structured result.

```python
safe = SafeCall(MockProvider(), fail_safe=True, fail_safe_return="Unavailable")
```

Each provider call can retry up to `retries` times (0–10, default 2). Permanent
HTTP errors, programming errors, and local policy, budget, or rate-limit
rejections are not retried. Built-in SDK retries are disabled. Every retry and
repair consumes a rate-limit token and checks the remaining recorded budget.

When a schema is supplied, the provider receives its JSON Schema. Invalid JSON
or schema mismatches allow one repair call, which passes the same input checks.
Policy and moderation rejections are returned directly.

The circuit counts consecutive failed generation operations, including failed
repairs and rejected output. Failed streams also increment it. A completed
generation or stream resets the count; local budget and rate denials do not
count. After five failures it stays open without a timed cooldown. Investigate
the failures before calling `reset_circuit()` to allow another request.

## Streaming and tools

`safe.stream_generate(prompt)` yields filtered text chunks. It does not validate
a final structured result, and patterns split across chunks can escape the
filters. Buffer and validate the full response if you need every check to pass
before displaying or acting on it.

`ToolRunner` checks strings and bytes in nested dictionaries and sequences, then
validates registered arguments and results when schemas are supplied. It also
checks values introduced by validation. Traversal stops at 32 levels or 1,000
values. It executes functions in the current process and does not provide
isolation, authorization, or a network firewall. Tool exceptions propagate.

## Environment and CLI

`from_env()` reads provider, model, API keys, policy, budget, and rate-limit settings
from the process environment. See [.env.example](.env.example); the library does
not load that file automatically. The example selects the mock provider, which
needs no credentials.

```sh
LLM_PROVIDER=mock llm-safecall --prompt "Hello"
llm-safecall --help
```

For a local `.env` file, copy the example and load it explicitly with the optional
`python-dotenv` CLI:

```sh
python -m pip install 'python-dotenv[cli]'
dotenv -f .env run -- llm-safecall --prompt "Hello"
```

To use a live provider, set `LLM_PROVIDER` to `openai` or `anthropic`, set
`LLM_MODEL` to an available model, and supply the matching API key. Keep the
`.env` file out of version control; use your deployment's secret store in production.

The CLI also accepts `--policy`, `--schema title:str,count:int`, and `--fail-safe`.
Schema types are `str`, `int`, `float`, and `bool`. Results go to stdout and JSON
logs to stderr. Missing arguments exit with status 2; configuration and generation
errors exit with status 1. A configured generation fallback exits successfully.

## Reports and accounting

Reports include total generation latency, model, and token usage and cost when
all successful provider responses supply them. Initial and repair responses are
combined; failed requests may incur unreported charges. Cache hits retain the
original report and do not add another budget entry.

`Budget` records supplied amounts by UTC day. `SafeCall` adds a provider's reported
cost after each successful response and checks the recorded limit before each
new provider attempt. A response can exceed the limit: its actual cost is still
saved, an error is raised, and further provider work is blocked. Unknown costs,
streaming charges, and simultaneous in-flight requests prevent this from being
a strict spending cap. Configure provider-side limits when you need one.

## Custom providers

Implement `complete(prompt, **params)` returning
`llm_safecall.providers.base.ProviderResponse`, and `stream(prompt, **params)`
yielding strings. Honor `timeout_s`. Response token counts must be non-negative
integers, and reported costs must be finite non-negative numbers. Omit unknown
usage or cost instead of reporting zero.

## Current limits

- Secret and moderation checks use fixed patterns, not a trained security model.
- Timeout handling depends on the provider adapter and SDK. Custom providers
  must honor `timeout_s`; retries are not a single overall deadline.
- Cache storage is in memory by default. Passing a path to `Cache` enables JSON
  persistence. Entries belong to one `SafeCall` instance and are checked against
  its current output policy and schema on every hit. New instances do not reuse
  earlier entries, including after a process restart. File-backed cache and
  budget storage are not designed for concurrent writers.
- Streaming does not apply whole-response schema checks or automatic retries.

### Migrating an existing cache

Pickle cache files are no longer supported. Point `Cache` at a new `.json` file
and let responses populate it. The library rejects old files without loading,
converting, or deleting them. Do not unpickle an old cache to migrate it.
Direct `Cache.set()` calls must store JSON-compatible values. Both memory and
file caches keep serialized snapshots, so changing a returned value does not
change the stored entry.

Caches hold at most 256 entries and 1 MiB of serialized keys and values by
default. The oldest written entries are evicted when either limit is reached;
oversized or non-serializable values are skipped. Override these limits with
`Cache(max_entries=512, max_bytes=2 * 1024 * 1024)`. Existing files over the
configured limits are rejected and left untouched; use a new path or raise the
limit if you need to read one.

## Development

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
ruff check .
ruff format --check .
pytest
python -m build
python -m twine check dist/*
python scripts/check_package.py dist/*.whl
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md). The package
uses the [MIT license](LICENSE). Source and issue tracking are on
[GitHub](https://github.com/GuardianMesh/llm-safecall).
