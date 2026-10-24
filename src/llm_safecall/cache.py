import hashlib
import json
import os
from pathlib import Path
from threading import RLock
from typing import Any


class Cache:
    def __init__(
        self,
        path: str | os.PathLike | None = None,
        *,
        max_entries: int = 256,
        max_bytes: int = 1024 * 1024,
    ):
        for name, value, minimum in (("max_entries", max_entries, 1), ("max_bytes", max_bytes, 2)):
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ValueError(f"{name} must be an integer of at least {minimum}")
        self.path = Path(path) if path is not None else None
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self._data: dict[str, str] = {}
        self._lock = RLock()
        if self.path is not None and not self.path.exists():
            self.path.touch(mode=0o600, exist_ok=False)
            self.path.write_text("{}", encoding="utf-8")

    def key(self, prompt: str, params: dict, output_type: Any) -> str:
        spec = {
            "prompt": prompt,
            "params": params,
            "schema": (
                output_type.model_json_schema()
                if hasattr(output_type, "model_json_schema")
                else str(output_type)
            ),
        }
        return hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()

    def get(self, key: str):
        with self._lock:
            encoded = self._read().get(key)
            return json.loads(encoded) if encoded is not None else None

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._set(key, value)

    def _set(self, key: str, value: Any) -> None:
        try:
            data = self._read()
            encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            data.pop(key, None)
            if self._size({key: encoded}) <= self.max_bytes:
                data[key] = encoded
            while data and (len(data) > self.max_entries or self._size(data) > self.max_bytes):
                del data[next(iter(data))]
            if self.path is not None:
                content = "{" + ",".join(json.dumps(k) + ":" + v for k, v in data.items()) + "}"
                self.path.write_text(content, encoding="utf-8")
        except (OSError, TypeError, ValueError, RecursionError):
            # A cache write must not discard a completed model response.
            return

    @staticmethod
    def _size(data: dict[str, str]) -> int:
        return 2 + sum(
            len(json.dumps(key).encode("utf-8")) + len(value.encode("utf-8")) + 2
            for key, value in data.items()
        )

    def _read(self) -> dict[str, str]:
        if self.path is None:
            return self._data
        with self.path.open("rb") as stream:
            content = stream.read(self.max_bytes + 1)
        if len(content) > self.max_bytes:
            raise ValueError(
                "Cache file exceeds max_bytes; use a new cache file or raise the limit"
            )
        try:
            data = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Cache must be JSON; discard legacy pickle cache files") from error
        if not isinstance(data, dict):
            raise ValueError("Cache must contain a JSON object")
        if len(data) > self.max_entries:
            raise ValueError(
                "Cache file exceeds max_entries; use a new cache file or raise the limit"
            )
        return {
            key: json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            for key, value in data.items()
        }
