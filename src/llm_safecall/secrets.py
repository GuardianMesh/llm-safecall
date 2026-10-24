import re
from collections.abc import Iterable
from dataclasses import dataclass

# Recognized credential formats; broad patterns can also match ordinary text.
PATTERNS = {
    "aws_access_key_id": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "aws_secret_access_key": re.compile(r"\b(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9/+=]{40}\b"),
    "gcp_api_key": re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b"),
    "slack_webhook": re.compile(r"https://hooks.slack.com/services/[A-Za-z0-9_/]+"),
    "github_pat": re.compile(r"\bghp_[A-Za-z0-9]{36}\b"),
    "private_key_block": re.compile(
        r"-----BEGIN (RSA|EC|DSA|OPENSSH|PGP) PRIVATE KEY-----[\s\S]+?-----END \1 PRIVATE KEY-----",
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
    out = text
    for f in sorted(findings, key=lambda x: x.start, reverse=True):
        out = out[: f.start] + f"[REDACTED_{f.name.upper()}]" + out[f.end :]
    return out
