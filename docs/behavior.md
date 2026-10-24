# Behavior reference

## Defaults

`SafeCall` accepts a provider with `complete()` and `stream()` methods.

| Option | Default | Meaning |
| --- | --- | --- |
| `output` | `None` | Pydantic model class; otherwise return text |
| `timeout_s` | `20` | Timeout passed to each provider attempt |
| `retries` | `2` | Additional attempts per provider call, from 0 to 10 |
| `moderation` | `True` | Reject the substrings `bomb`, `dox`, and `credit card number` |
| `redact` | `[]` | Optional input email and phone redaction |
| `fail_safe` | `False` | Return a string fallback on error |
| `fail_safe_return` | `""` | Fallback text |
| `cache` | New in-memory cache | Reuse checked responses within this instance |
| `budget`, `rate_limit` | `None` | Optional accounting and request admission |

The moderation check is a case-insensitive substring list, including matches
inside other words. It does not understand context. Set `moderation=False` if
your application supplies its own moderation.

## Policy

`load_policy("policy.yml")` returns a `PolicyEngine`. Unknown YAML keys and
invalid types are rejected. The defaults are:

```yaml
block_secrets: true
redact_secrets: true
allow_shell_output: false
outbound_url_allowlist: []
json_only_when_schema: true
max_input_chars: 20000
max_output_chars: 10000
```

When `block_secrets` is enabled, recognized secrets are redacted if
`redact_secrets` is true and rejected otherwise. These patterns are incomplete.

Omitting `forbid_injection_phrases` uses the built-in phrase list; `[]` disables
that check. Phrase matches reject input, including repair prompts.
Shell filtering removes a small set of recognizable commands and code blocks.

An empty URL allowlist leaves output URLs unchanged. An allowed URL matches
scheme, authority, and either the exact path or a directory beneath it. Paths
with dot segments or encoded separators are rejected. This filters text; it
does not restrict network requests.

Oversized input and output are rejected. Structured checks inspect decoded JSON,
nested strings, bytes, built-in containers, and stored Pydantic fields before
and after validation, including excluded fields. Custom object attributes are
outside these checks. Traversal stops at 32 levels or 1,000 values.

## Generation and errors

Without a schema, `generate()` returns `LLMText`, a string subclass with
`_report`. With a schema it returns a Pydantic model with `_report`.

The provider receives the JSON Schema in the prompt. This does not enable
provider-native constrained decoding. Invalid JSON or a schema mismatch allows
one repair call. Policy and moderation rejections are not repaired. Repair
prompts go through input checks.

Each initial or repair call can make `retries + 1` attempts. Permanent HTTP
errors, programming errors, and local policy, budget, and rate-limit rejections
are not retried. Built-in SDK retries are disabled. Every attempt consumes a
rate-limit token and checks the recorded budget. The timeout applies per attempt;
there is no single deadline for the operation. Custom providers must honor it.

Five consecutive failed generation operations open the circuit. Rejected
output, failed repairs, and failed streams count. A completed operation resets
the count; local budget and rate denials do not count. There is no timed
cooldown. Call `reset_circuit()` after investigating the failures.

`fail_safe=True` catches generation errors and returns `fail_safe_return` as
an `LLMText` with a report containing zero latency and no usage. This includes
policy errors and an open circuit. The fallback is not checked against a schema
or output policy; use trusted display text.

## Streaming and tools

`stream_generate(prompt)` yields filtered strings. It bounds received and emitted text by
`max_output_chars`, checks chunks independently, and does not validate a final
structured result or retry a failed stream. Patterns split across chunks can
escape checks. Already yielded text cannot be recalled. In fallback mode a
failure yields the fallback after any earlier chunks.

`ToolRunner` checks nested arguments, validates registered argument schemas,
calls the function, then checks and validates its result. Values introduced by
schema validation are checked too. Tool exceptions propagate. Functions run in
the caller's process with its permissions; the runner provides no authorization
or isolation.

## Reports, budgets, and rates

Reports contain total generation latency, model, and token usage and cost when
all successful provider responses supply them. Initial and repair responses
are combined. Failed requests can incur unreported charges. Built-in adapters
report token usage but do not calculate monetary cost.

`Budget` records supplied amounts by UTC day and checks the recorded limit
before each attempt. A response can exceed the limit: the known charge is saved,
an error is raised, and later provider work is blocked. Unknown costs, streaming,
and simultaneous requests prevent this from enforcing a strict spending cap.
File-backed budgets do not support concurrent writers.

`TokenBucket(rate_per_sec=0.5)` admits one initial request and refills one token
every two seconds. Default capacity is at least one token. Admission rejects
immediately when there are not enough tokens; it does not queue work.

The optional `pricing` module starts with an empty `PRICING` registry. Supply
your own rates per 1,000 tokens before calling `estimate_cost()`. Missing rates
or either missing token count return `None`. Rates and counts must be
non-negative and finite; counts must be integers. The helper is not called
automatically by provider adapters.

## Cache

Cache storage is in memory unless you pass a JSON file path to `Cache`.
Entries belong to one `SafeCall` instance. A new instance, including after a
restart, does not reuse old entries. Every hit is checked against the current
policy and schema. Hits retain the original report and add no budget entry.

Values are serialized snapshots. Direct `Cache.set()` calls accept
JSON-compatible values. Defaults are 256 entries and 1 MiB of serialized keys
and values, with oldest-written entries evicted first. Oversized or
non-serializable entries are skipped.

Override limits with `Cache(max_entries=512, max_bytes=2 * 1024 * 1024)`.
Existing files over these limits are rejected and left untouched. File-backed
storage does not support concurrent writers. See [migration](migration.md) for
old pickle files.

## Providers and CLI

Choose the model explicitly. The OpenAI adapter sends Chat Completions requests;
the Anthropic adapter sends Messages requests and rejects `temperature`,
`top_p`, and `top_k`. Check the provider's documentation for model support.

Custom `complete(prompt, **params)` methods return
`llm_safecall.providers.base.ProviderResponse`; `stream(prompt, **params)`
yields strings. Honor `timeout_s`. Omit unknown usage or cost instead of
reporting zero. Token counts must be non-negative integers and costs finite
non-negative numbers.

`from_env()` reads provider, model, API keys, policy, budget, and rate settings
from the process environment. See [the example](../.env.example). It does not
load files. To load a local `.env` explicitly:

```sh
python -m pip install 'python-dotenv[cli]'
dotenv -f .env run -- llm-safecall --prompt "Hello"
```

The CLI accepts `--policy`, `--schema title:str,count:int`, and `--fail-safe`.
Schema types are `str`, `int`, `float`, and `bool`. Results go to stdout and
JSON logs to stderr. Missing arguments exit with status 2; configuration and
generation errors exit with status 1. Schema and policy errors include fixed
guidance; provider errors report only the exception class. An explicit generation
fallback exits successfully.
