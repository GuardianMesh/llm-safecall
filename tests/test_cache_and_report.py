from llm_safecall import MockProvider, SafeCall


def test_cache_roundtrip(tmp_path):
    from llm_safecall.cache import Cache

    cache = Cache(tmp_path / "cache.json")
    safe = SafeCall(MockProvider(), cache=cache)
    a = safe.generate("hello as JSON")
    b = safe.generate("hello as JSON")  # should hit cache
    assert type(a) is type(b)
    assert getattr(a, "_report", None) is not None
