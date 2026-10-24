import pytest

from llm_safecall.pricing import PRICING, estimate_cost


@pytest.fixture(autouse=True)
def rates(monkeypatch):
    monkeypatch.setitem(PRICING, "test:model", {"input": 0.2, "output": 0.5})


def test_estimate_uses_explicit_rates_and_complete_usage():
    assert estimate_cost("test:model", 2000, 1000) == 0.9
    assert estimate_cost("test:model", 0, 0) == 0
    assert estimate_cost("unknown", 1000, 1000) is None
    assert estimate_cost("test:model", None, 1000) is None
    assert estimate_cost("test:model", 1000, None) is None


@pytest.mark.parametrize("count", [-1, 0.5, True, float("inf"), float("nan")])
def test_invalid_token_counts_are_rejected(count):
    with pytest.raises(ValueError, match="Token counts"):
        estimate_cost("test:model", count, 1000)


@pytest.mark.parametrize("rate", [-1, True, float("inf"), float("nan"), "0.2"])
def test_invalid_rates_are_rejected(monkeypatch, rate):
    monkeypatch.setitem(PRICING, "test:model", {"input": rate, "output": 0.5})
    with pytest.raises(ValueError, match="Token rates"):
        estimate_cost("test:model", 1000, 1000)


def test_overflow_is_rejected(monkeypatch):
    monkeypatch.setitem(PRICING, "test:model", {"input": 1e308, "output": 1e308})
    with pytest.raises(ValueError, match="numeric range"):
        estimate_cost("test:model", 2000, 2000)
    with pytest.raises(ValueError, match="numeric range"):
        estimate_cost("test:model", 10**1000, 0)
