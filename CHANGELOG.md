# Changelog

## 0.2.3 — 2026-10-24

- Merge overlapping secret matches before redaction and recognize generic and encrypted PEM keys.
- Match the literal Slack webhook hostname so unrelated hosts are not redacted.
- Check sets, mapping keys, and Pydantic secret fields; enforce limits after redaction expands text.
- Close provider iterators when streaming stops early and reset the circuit on a valid cache hit.
- Allow fractional request rates with a default bucket capacity of at least one request.
- Bound secret-pattern lookaheads so long harmless input does not cause quadratic scanning.
- Remove example prices; cost estimates require configured rates and complete token usage.
- Explain CLI schema and policy errors without printing input, file contents, or provider messages.
- Shorten the quick start and move exact behavior and migration details into reference docs.
- Scan email redaction candidates in linear time so long malformed prompts cannot stall the caller.
- Send requested schemas to providers and validate every repair prompt before dispatch.
- Check decoded structured values and actual Pydantic fields, including excluded and encoded fields.
- Apply output moderation and reject oversized output before returning a prefix.
- Validate direct options, isolate default policies, and check nested tool arguments and results.
- Measure complete generation latency and combine reported usage from initial and repair responses.
- Record known costs even when they exceed a budget, then block further provider work.
- Count failed repairs and streams in the circuit breaker; add an explicit reset method.
- Close provider clients and streams and disable overlapping SDK retries.
- Use the supported Anthropic default and reject removed sampling options.
- Keep CLI output separate from logs and reject malformed schemas.
- Test supported Python versions and install the built wheel in a clean consumer environment.
- Keep default caches in memory and replace pickle persistence with JSON; old cache files must be replaced explicitly.
- Isolate cache entries by `SafeCall` instance and recheck cached output before returning it.
- Bound cache storage by entry count and serialized size, with FIFO eviction.
- Reject URL path traversal, encoded separators, and directory-prefix lookalikes.
- Reject unknown provider names instead of silently choosing a fallback provider.
- Pin CI actions and require a reviewed release environment after building and checking packages.
- Correct the installation, policy, and error-handling examples.
- Start the environment example with the mock provider and document explicit `.env` loading.
- Fix fallback and streaming methods on `SafeCall` and honor the retry count.
- Validate YAML policy keys and types, preserving default injection checks.
- Match URL scheme and authority before applying output path prefixes.
- Require patched AnyIO, certifi, and idna versions with optional provider adapters.
- Remove generated files from source control and fix package metadata.

## 0.2.0

- Add secret-pattern checks, output URL allowlists, and output filtering.
- Add budget accounting, rate limiting, and structured logs.
- Load settings from environment variables and policy files from YAML.
- Filter streamed output one chunk at a time.
- Add `ToolRunner` for argument and result validation.
- Add an optional fallback value for failed calls.
- Add a CLI and development container.
