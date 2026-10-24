import json
import pickle

import pytest
from pydantic import BaseModel

from llm_safecall import MockProvider, SafeCall
from llm_safecall.cache import Cache
from llm_safecall.env import from_env
from llm_safecall.policy import PolicyConfig, PolicyEngine
from llm_safecall.providers.base import ProviderResponse
from llm_safecall.sanitize import remove_urls_not_in_allowlist


class FixedProvider(MockProvider):
    def __init__(self, text):
        super().__init__()
        self.text = text
        self.calls = 0

    def complete(self, prompt, **params):
        self.calls += 1
        return ProviderResponse(text=self.text, model=self.model)


def test_pickle_cache_is_rejected_without_execution_or_modification(tmp_path):
    marker = tmp_path / "executed"

    class Payload:
        def __reduce__(self):
            return eval, (f"__import__('pathlib').Path({str(marker)!r}).write_text('executed')",)

    payload = pickle.dumps({"entry": Payload()})
    path = tmp_path / "legacy.pkl"
    path.write_bytes(payload)
    cache = Cache(path)
    with pytest.raises(ValueError, match="Cache must be JSON"):
        cache.get("entry")
    assert not marker.exists()
    assert path.read_bytes() == payload


def test_shared_cache_does_not_cross_provider_boundaries(tmp_path):
    cache = Cache(tmp_path / "cache.json")
    first = SafeCall(FixedProvider("private result"), cache=cache)
    second = SafeCall(FixedProvider("public result"), cache=cache)
    assert first.generate("Hello") == "private result"
    assert second.generate("Hello") == "public result"


def test_cached_output_is_checked_against_current_policy(tmp_path):
    path = tmp_path / "cache.json"
    provider = FixedProvider("clean result")
    safe = SafeCall(
        provider,
        cache=Cache(path),
        policy=PolicyEngine(PolicyConfig(redact_secrets=False)),
    )
    assert safe.generate("Hello") == "clean result"
    data = json.loads(path.read_text())
    data[next(iter(data))]["text"] = "Bearer secret-token"
    path.write_text(json.dumps(data))
    assert safe.generate("Hello") == "clean result"
    assert provider.calls == 2


def test_mutating_a_returned_model_does_not_mutate_cached_output():
    class Summary(BaseModel):
        title: str

    provider = FixedProvider('{"title":"original"}')
    safe = SafeCall(provider, output=Summary)
    first = safe.generate("Hello")
    first.title = "changed"
    assert safe.generate("Hello").title == "original"
    assert provider.calls == 1


def test_cached_json_is_revalidated_against_schema(tmp_path):
    class Summary(BaseModel):
        title: str

    path = tmp_path / "cache.json"
    provider = FixedProvider('{"title":"original"}')
    safe = SafeCall(provider, output=Summary, cache=Cache(path))
    assert safe.generate("Hello").title == "original"
    data = json.loads(path.read_text())
    data[next(iter(data))]["text"] = '{"title":42}'
    path.write_text(json.dumps(data))
    assert safe.generate("Hello").title == "original"
    assert provider.calls == 2


@pytest.mark.parametrize(
    "path",
    [
        "/guide/../private",
        "/guide/%2e%2e/private",
        "/guide/%2e%2e%2fprivate",
        "/guide/%252e%252e%252fprivate",
        "/guide/%5c../private",
        "/guidebook",
    ],
)
def test_url_paths_cannot_escape_the_allowed_directory(path):
    assert (
        remove_urls_not_in_allowlist(
            "https://docs.example.com" + path, ["https://docs.example.com/guide"]
        )
        == "[BLOCKED_URL]"
    )


def test_replacing_one_url_does_not_leave_another_url_partly_checked():
    text = "https://evil.test/ https://evil.test/https://docs.example.com/guide"
    assert remove_urls_not_in_allowlist(text, ["https://docs.example.com/guide"]) == (
        "[BLOCKED_URL] [BLOCKED_URL]"
    )


def test_unknown_provider_fails_before_any_request(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "opneai")
    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        from_env()


def test_cache_evicts_oldest_entries_at_capacity():
    cache = Cache(max_entries=2)
    cache.set("first", "one")
    cache.set("second", "two")
    cache.set("third", "three")
    assert cache.get("first") is None
    assert cache.get("second") == "two"
    assert cache.get("third") == "three"


def test_default_cache_capacity_is_bounded():
    cache = Cache()
    for index in range(257):
        cache.set(str(index), "value")
    assert cache.get("0") is None
    assert cache.get("256") == "value"


def test_cache_caps_total_bytes_and_skips_oversized_values():
    cache = Cache(max_bytes=100)
    for key in ("a", "b", "c"):
        cache.set(key, "x" * 40)
    assert cache.get("a") is None
    assert cache.get("b") == "x" * 40
    assert cache.get("c") == "x" * 40
    cache.set("oversized", "\U0001f44b" * 30)
    assert cache.get("oversized") is None
    assert cache.get("c") == "x" * 40


def test_cache_snapshots_prevent_mutation_from_growing_stored_values():
    cache = Cache(max_bytes=100)
    value = {"text": "short"}
    cache.set("key", value)
    value["text"] = "x" * 1000
    cached = cache.get("key")
    cached["text"] = "x" * 1000
    assert cache.get("key") == {"text": "short"}


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_entries": 0},
        {"max_entries": True},
        {"max_entries": 1.5},
        {"max_bytes": 1},
        {"max_bytes": float("inf")},
    ],
)
def test_invalid_cache_limits_are_rejected(kwargs):
    with pytest.raises(ValueError):
        Cache(**kwargs)


def test_oversized_cache_write_does_not_discard_model_result():
    safe = SafeCall(FixedProvider("valid response"), cache=Cache(max_bytes=2))
    assert safe.generate("Hello") == "valid response"


def test_oversized_cache_files_are_rejected_without_modification(tmp_path):
    path = tmp_path / "large.json"
    content = json.dumps({"large": "x" * 1000})
    path.write_text(content)
    cache = Cache(path, max_bytes=100)
    with pytest.raises(ValueError, match="exceeds max_bytes"):
        cache.get("large")
    cache.set("small", "value")
    assert path.read_text() == content
