from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlsplit

from pydantic import BaseModel, SecretBytes, SecretStr

from .errors import PolicyViolationError
from .sanitize import (
    remove_urls_not_in_allowlist,
    strip_disallowed_codeblocks,
    strip_disallowed_commands,
)
from .secrets import redact_findings
from .secrets import scan as scan_secrets

INJECTION_SIGNS = [
    "ignore previous instructions",
    "disregard prior instructions",
    "reveal the system prompt",
    "show hidden prompt",
    "exfiltrate",
    "send to http",
    "upload to",
    "base64 encode the following secrets",
]


@dataclass
class PolicyConfig:
    block_secrets: bool = True
    redact_secrets: bool = True
    allow_shell_output: bool = False
    outbound_url_allowlist: list[str] = field(default_factory=list)
    json_only_when_schema: bool = True
    max_output_chars: int = 10000
    max_input_chars: int = 20000
    forbid_injection_phrases: list[str] = field(default_factory=lambda: list(INJECTION_SIGNS))

    def __post_init__(self):
        for name in (
            "block_secrets",
            "redact_secrets",
            "allow_shell_output",
            "json_only_when_schema",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be a boolean")
        for name in ("max_input_chars", "max_output_chars"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        for name in ("outbound_url_allowlist", "forbid_injection_phrases"):
            value = getattr(self, name)
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise ValueError(f"{name} must be a list of strings")
            setattr(self, name, list(value))
        self.forbid_injection_phrases = [phrase.lower() for phrase in self.forbid_injection_phrases]
        for value in self.outbound_url_allowlist:
            try:
                url = urlsplit(value)
                if (
                    url.scheme not in {"http", "https"}
                    or not url.hostname
                    or url.username
                    or url.password
                    or "\\" in value
                    or any(character.isspace() for character in value)
                ):
                    raise ValueError
                url.port
            except ValueError as error:
                raise ValueError("URL allowlist entries must be absolute HTTP(S) URLs") from error


class PolicyEngine:
    def __init__(self, cfg: PolicyConfig | None = None):
        self.cfg = cfg or PolicyConfig()

    def pre_call(self, prompt: str) -> str:
        if not isinstance(prompt, str):
            raise TypeError("Prompt must be a string")
        if len(prompt) > self.cfg.max_input_chars:
            raise PolicyViolationError("Prompt too long", {"max": self.cfg.max_input_chars})
        lowered = prompt.lower()
        for phrase in self.cfg.forbid_injection_phrases:
            if phrase in lowered:
                raise PolicyViolationError("Prompt contains injection markers", {"phrase": phrase})
        findings = scan_secrets(prompt)
        if findings and self.cfg.block_secrets:
            if self.cfg.redact_secrets:
                prompt = redact_findings(prompt, findings)
            else:
                raise PolicyViolationError(
                    "Secrets detected in prompt", {"findings": [f.name for f in findings]}
                )
        if len(prompt) > self.cfg.max_input_chars:
            raise PolicyViolationError("Prompt too long", {"max": self.cfg.max_input_chars})
        return prompt

    def post_call(self, text: str, schema_expected: bool) -> str:
        if not isinstance(text, str):
            raise TypeError("Provider output must be a string")
        if len(text) > self.cfg.max_output_chars:
            raise PolicyViolationError("Output too long", {"max": self.cfg.max_output_chars})
        findings = scan_secrets(text)
        if findings and self.cfg.block_secrets:
            if self.cfg.redact_secrets:
                text = redact_findings(text, findings)
            else:
                raise PolicyViolationError(
                    "Secrets detected in output", {"findings": [f.name for f in findings]}
                )
        text = strip_disallowed_codeblocks(text, self.cfg.allow_shell_output)
        text = strip_disallowed_commands(text, self.cfg.allow_shell_output)
        text = remove_urls_not_in_allowlist(text, self.cfg.outbound_url_allowlist)
        if len(text) > self.cfg.max_output_chars:
            raise PolicyViolationError("Output too long", {"max": self.cfg.max_output_chars})
        if schema_expected and self.cfg.json_only_when_schema:
            # This checks the prefix only; SafeCall parses and validates the JSON.
            stripped = text.strip()
            if not (stripped.startswith("{") or stripped.startswith("[")):
                raise PolicyViolationError("Non-JSON output when JSON schema expected")
        return text

    def check_value(self, value, *, output: bool, moderation=None):
        """Check strings in dictionaries and sequences before schema validation."""
        remaining = self.cfg.max_output_chars if output else self.cfg.max_input_chars
        filtered_remaining = remaining
        nodes = 1000

        def visit(item, depth=0):
            nonlocal remaining, filtered_remaining, nodes
            nodes -= 1
            if depth > 32 or nodes < 0:
                raise PolicyViolationError("Structured value is too deeply nested or too large")
            if isinstance(item, str):
                remaining -= len(item)
                if remaining < 0:
                    raise PolicyViolationError("Structured value exceeds the character limit")
                if moderation:
                    moderation(item)
                filtered = (
                    self.post_call(item, schema_expected=False) if output else self.pre_call(item)
                )
                filtered_remaining -= len(filtered)
                if filtered_remaining < 0:
                    raise PolicyViolationError("Structured value exceeds the character limit")
                return filtered
            if isinstance(item, BaseModel):
                # Serializers can hide decoded or excluded fields; inspect the stored values too.
                raw = {
                    name: item.__dict__[name]
                    for name in type(item).model_fields
                    if name in item.__dict__
                }
                raw.update(item.__pydantic_extra__ or {})
                if visit(raw, depth + 1) != raw:
                    raise PolicyViolationError(
                        "Validated model contains values that violate policy"
                    )
                return item
            if isinstance(item, (SecretStr, SecretBytes)):
                raw = item.get_secret_value()
                if visit(raw, depth + 1) != raw:
                    raise PolicyViolationError("Secret field contains data that violates policy")
                return item
            if isinstance(item, (bytes, bytearray)):
                if len(item) > remaining:
                    raise PolicyViolationError("Structured value exceeds the character limit")
                decoded = item.decode("latin-1")
                if visit(decoded, depth + 1) != decoded:
                    raise PolicyViolationError("Binary value contains data that violates policy")
                return item
            if isinstance(item, dict):
                checked = {}
                for key, child in item.items():
                    if visit(key, depth + 1) != key:
                        raise PolicyViolationError("Policy filtering would change a field name")
                    checked[key] = visit(child, depth + 1)
                return checked
            if isinstance(item, (list, tuple, set, frozenset)):
                checked = [visit(child, depth + 1) for child in item]
                if isinstance(item, tuple):
                    return tuple(checked)
                if isinstance(item, (set, frozenset)):
                    return type(item)(checked)
                return checked
            return item

        return visit(value)
