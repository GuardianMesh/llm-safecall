import subprocess
import sys

import pytest

from llm_safecall.errors import PolicyViolationError
from llm_safecall.policy import PolicyConfig, PolicyEngine
from llm_safecall.secrets import Finding, redact_findings, scan


def test_overlapping_credentials_are_removed_using_original_offsets():
    key = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        + "Bearer x\n" * 8
        + "secret-material\n-----END RSA PRIVATE KEY-----"
    )
    text = f"before\n{key}\nafter"
    assert redact_findings(text, scan(text)) == "before\n[REDACTED_PRIVATE_KEY_BLOCK]\nafter"
    assert PolicyEngine().pre_call(text) == "before\n[REDACTED_PRIVATE_KEY_BLOCK]\nafter"
    assert PolicyEngine().post_call(text, False) == "before\n[REDACTED_PRIVATE_KEY_BLOCK]\nafter"


def test_intersecting_spans_do_not_leave_a_credential_suffix():
    text = "prefix ABCDEFGH suffix"
    findings = [Finding("first", "ABCDE", 7, 12), Finding("second", "DEFGH", 10, 15)]
    assert redact_findings(text, findings) == "prefix [REDACTED_FIRST] suffix"


def test_adjacent_credentials_remain_separate_and_preserve_surrounding_text():
    text = "before Bearer x; Bearer y after"
    assert redact_findings(text, scan(text)) == (
        "before [REDACTED_GENERIC_BEARER]; [REDACTED_GENERIC_BEARER] after"
    )


@pytest.mark.parametrize(
    "label",
    [
        "PRIVATE KEY",
        "ENCRYPTED PRIVATE KEY",
        "RSA PRIVATE KEY",
        "EC PRIVATE KEY",
        "DSA PRIVATE KEY",
        "OPENSSH PRIVATE KEY",
        "PGP PRIVATE KEY BLOCK",
    ],
)
def test_private_key_formats(label):
    text = f"-----BEGIN {label}-----\nsynthetic-key-material\n-----END {label}-----"
    assert PolicyEngine().pre_call(text) == "[REDACTED_PRIVATE_KEY_BLOCK]"
    assert PolicyEngine().post_call(text, False) == "[REDACTED_PRIVATE_KEY_BLOCK]"


def test_public_key_is_not_redacted():
    text = "-----BEGIN PUBLIC KEY-----\npublic-material\n-----END PUBLIC KEY-----"
    assert PolicyEngine().pre_call(text) == text


def test_aws_secret_requires_letters_and_digits_within_the_credential():
    assert scan("a" * 40 + " followed by 1") == []
    assert scan("1" * 40 + " followed by a") == []
    assert [finding.name for finding in scan("a1" * 20)] == ["aws_secret_access_key"]


def test_secret_scanning_repeated_words_finishes_in_a_bounded_process():
    source = """
from llm_safecall.secrets import scan
assert scan('a ' * 100_000) == []
"""
    child = subprocess.run(
        [sys.executable, "-c", source], capture_output=True, text=True, timeout=5, check=False
    )
    assert child.returncode == 0, child.stderr


def test_character_limits_apply_after_redaction_expands_text():
    policy = PolicyEngine(PolicyConfig(max_input_chars=10, max_output_chars=10))
    with pytest.raises(PolicyViolationError, match="Prompt too long"):
        policy.pre_call("Bearer ab")
    with pytest.raises(PolicyViolationError, match="Output too long"):
        policy.post_call("Bearer ab", False)
