from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import yaml

from .policy import PolicyConfig, PolicyEngine


def load_policy(path: str | Path) -> PolicyEngine:
    data = yaml.safe_load(Path(path).read_text())
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("Policy must be a YAML mapping")
    unknown = set(data) - {field.name for field in fields(PolicyConfig)}
    if unknown:
        raise ValueError(f"Unknown policy fields: {', '.join(sorted(map(str, unknown)))}")
    for key, value in data.items():
        if key in {"outbound_url_allowlist", "forbid_injection_phrases"}:
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise ValueError(f"{key} must be a list of strings")
        elif key in {"max_input_chars", "max_output_chars"}:
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{key} must be a positive integer")
        elif not isinstance(value, bool):
            raise ValueError(f"{key} must be a boolean")
    return PolicyEngine(PolicyConfig(**data))
