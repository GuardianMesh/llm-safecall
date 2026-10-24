import math
import time
from contextlib import contextmanager
from dataclasses import dataclass
from types import SimpleNamespace


@dataclass
class CallReport:
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    model: str | None = None
    cost_estimate: float | None = None

    def __post_init__(self):
        for name in ("latency_ms", "input_tokens", "output_tokens"):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ValueError(f"{name} must be a non-negative integer")
        if self.model is not None and not isinstance(self.model, str):
            raise ValueError("model must be a string")
        if self.cost_estimate is not None and (
            isinstance(self.cost_estimate, bool)
            or not isinstance(self.cost_estimate, (int, float))
            or not math.isfinite(self.cost_estimate)
            or self.cost_estimate < 0
        ):
            raise ValueError("cost_estimate must be finite and non-negative")

    def model_dump(self) -> dict:
        return {
            "latency_ms": self.latency_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "model": self.model,
            "cost_estimate": self.cost_estimate,
        }


@contextmanager
def time_it():
    start = time.perf_counter()
    elapsed = SimpleNamespace(elapsed_ms=0)
    try:
        yield elapsed
    finally:
        elapsed.elapsed_ms = max(0, int((time.perf_counter() - start) * 1000))
