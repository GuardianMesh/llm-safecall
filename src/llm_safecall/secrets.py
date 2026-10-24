import re
from collections.abc import Iterable
from dataclasses import dataclass

# Recognized credential formats; broad patterns can also match ordinary text.
PATTERNS = {
    "aws_access_key_id": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "aws_secret_access_key": re.compile(
        r"\b(?=[A-Za-z0-9/+=]{0,39}[A-Za-z])(?=[A-Za-z0-9/+=]{0,39}\d)[A-Za-z0-9/+=]{40}\b"
    ),
    "gcp_api_key": re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b"),
    "slack_webhook": re.compile(r"https://hooks\.slack\.com/services/[A-Za-z0-9_/]+"),
    "github_pat": re.compile(r"\bghp_[A-Za-z0-9]{36}\b"),
    "private_key_block": re.compile(
        r"-----BEGIN ((?:(?:RSA|EC|DSA|OPENSSH|ENCRYPTED) )?PRIVATE KEY|"
        r"PGP PRIVATE KEY(?: BLOCK)?)-----[\s\S]+?-----END \1-----",
        re.MULTILINE,
    ),
    "generic_bearer": re.compile(r"\bBearer\s+[A-Za-z0-9\-_=\.\/]+\b"),
}


@dataclass
class Finding:
    name: str
    match: str
    start: int
    end: int
    severity: str = "high"


def scan(text: str) -> list[Finding]:
    findings: list[Finding] = []
    for name, pat in PATTERNS.items():
        for m in pat.finditer(text):
            findings.append(Finding(name=name, match=m.group(0), start=m.start(), end=m.end()))
    return findings


def redact_findings(text: str, findings: Iterable[Finding]) -> str:
    spans: list[tuple[int, int, str]] = []
    for finding in sorted(findings, key=lambda item: (item.start, -item.end)):
        if spans and finding.start < spans[-1][1]:
            start, end, name = spans[-1]
            spans[-1] = (start, max(end, finding.end), name)
        else:
            spans.append((finding.start, finding.end, finding.name))

    # Build from the original text so overlapping matches cannot shift later offsets.
    parts = []
    position = 0
    for start, end, name in spans:
        parts.extend((text[position:start], f"[REDACTED_{name.upper()}]"))
        position = end
    parts.append(text[position:])
    return "".join(parts)
