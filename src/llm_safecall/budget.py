from __future__ import annotations

import json
import math
import os
import tempfile
import time
from pathlib import Path
from threading import Lock

from .errors import BudgetExceededError


def _amount(value, name, *, allow_infinity=False):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or value < 0
        or math.isnan(value)
        or (not allow_infinity and not math.isfinite(value))
    ):
        raise ValueError(f"{name} must be a non-negative number")
    return value


class Budget:
    """Track daily totals in a local JSON file.

    Amounts are summed across models. Use the same unit for every entry and limit.
    Separate Budget instances must not write the same file concurrently.
    """

    def __init__(
        self, path: str | Path = ".llm_safecall_budget.json", daily_limit: float = float("inf")
    ):
        self.path = Path(path)
        self.daily_limit = _amount(daily_limit, "daily_limit", allow_infinity=True)
        self._lock = Lock()
        if not self.path.exists():
            self.path.touch(mode=0o600, exist_ok=False)
            self.path.write_text("{}", encoding="utf-8")

    def _today_key(self) -> str:
        return time.strftime("%Y-%m-%d", time.gmtime())

    def _read(self):
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Budget file must contain a JSON object")
        day = self._today_key()
        return data, day, _amount(data.get(day, 0.0), "stored total")

    def assert_available(self):
        """Reject new work once the recorded UTC daily total reaches the limit."""
        with self._lock:
            _, _, total = self._read()
            if total >= self.daily_limit:
                raise BudgetExceededError(f"Daily budget exhausted: {total} >= {self.daily_limit}")

    def add(self, model: str | None, amount: float):
        amount = _amount(amount, "amount")
        with self._lock:
            data, day, day_tot = self._read()
            total = _amount(day_tot + amount, "daily total")
            data[day] = total
            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", dir=self.path.parent, delete=False
                ) as temp:
                    temp_path = Path(temp.name)
                    json.dump(data, temp, allow_nan=False)
                os.replace(temp_path, self.path)
            finally:
                if temp_path is not None:
                    temp_path.unlink(missing_ok=True)
            if total > self.daily_limit:
                raise BudgetExceededError(f"Daily budget exceeded: {total} > {self.daily_limit}")
