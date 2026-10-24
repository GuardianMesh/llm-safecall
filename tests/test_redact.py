import subprocess
import sys

import pytest

from llm_safecall.redact import redact_text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Contact first.last+tag@example.co.uk.", "Contact [REDACTED_EMAIL]."),
        ("a@host.com123@next.net", "[REDACTED_EMAIL][REDACTED_EMAIL]"),
        ("a@host.com-@next.net", "[REDACTED_EMAIL][REDACTED_EMAIL]"),
        ("a@invalid%user@example.com", "a@[REDACTED_EMAIL]"),
        ("a@host.com123 and b@host.net-123", "[REDACTED_EMAIL]123 and [REDACTED_EMAIL]-123"),
        ("a@host..com and b@.com", "[REDACTED_EMAIL] and b@.com"),
        ("a@host.c, b@host.12, plain text", "a@host.c, b@host.12, plain text"),
    ],
)
def test_email_matching(text, expected):
    assert redact_text(text, ["email"]) == expected


def test_redaction_is_optional_and_combines_fields():
    text = "a@example.com +1 234-567-8901"
    assert redact_text(text, []) == text
    assert redact_text(text, ["email", "phone"]) == "[REDACTED_EMAIL] [REDACTED_PHONE]"


def test_long_malformed_email_input_finishes_in_a_bounded_process():
    source = """
from llm_safecall.redact import redact_text
for text in ['%' * 1_000_000, 'a@' + 'x.' * 250_000 + '1']:
    assert redact_text(text, ['email']) == text
"""
    child = subprocess.run(
        [sys.executable, "-c", source], capture_output=True, text=True, timeout=5, check=False
    )
    assert child.returncode == 0, child.stderr
