import math
import time
from threading import Lock

from .errors import RateLimitExceededError


def _positive(value: float, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"{name} must be a finite positive number")
    return float(value)


class TokenBucket:
    def __init__(self, rate_per_sec: float, capacity: float | None = None):
        self.rate = _positive(rate_per_sec, "rate_per_sec")
        self.capacity = _positive(rate_per_sec if capacity is None else capacity, "capacity")
        self.tokens = self.capacity
        self.last = time.monotonic()
        self._lock = Lock()

    def take(self, cost: float = 1.0):
        cost = _positive(cost, "cost")
        with self._lock:
            now = time.monotonic()
            self.tokens = min(self.capacity, self.tokens + max(0, now - self.last) * self.rate)
            self.last = now
            if self.tokens < cost:
                raise RateLimitExceededError("Rate limit exceeded")
            self.tokens -= cost
