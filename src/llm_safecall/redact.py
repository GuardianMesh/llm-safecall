import re
from collections.abc import Iterable

EMAIL_LOCAL_RE = re.compile(r"[A-Za-z0-9._%+-]+")
PHONE_RE = re.compile(r"(?:\+?\d[\s-]?){7,}")


def _ascii_letter(value: str) -> bool:
    return "A" <= value <= "Z" or "a" <= value <= "z"


def _email_end(text: str, domain_start: int) -> int:
    end = -1
    letters_after_dot = -1
    for index in range(domain_start, len(text)):
        char = text[index]
        letter = _ascii_letter(char)
        if not letter and not "0" <= char <= "9" and char not in ".-":
            break
        if char == ".":
            letters_after_dot = 0 if index > domain_start else -1
        elif letter and letters_after_dot >= 0:
            letters_after_dot += 1
            if letters_after_dot >= 2:
                end = index + 1
        else:
            letters_after_dot = -1
    return end


def _redact_emails(text: str) -> str:
    parts = []
    cursor = 0
    # Each local-part token and following domain is scanned once, including failed matches.
    for match in EMAIL_LOCAL_RE.finditer(text):
        start = max(match.start(), cursor)
        local_end = match.end()
        if start >= local_end or local_end == len(text) or text[local_end] != "@":
            continue
        end = _email_end(text, local_end + 1)
        if end < 0:
            continue
        parts.extend((text[cursor:start], "[REDACTED_EMAIL]"))
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts)


def redact_text(text: str, fields: Iterable[str]) -> str:
    out = text
    if "email" in fields:
        out = _redact_emails(out)
    if "phone" in fields:
        out = PHONE_RE.sub("[REDACTED_PHONE]", out)
    return out
