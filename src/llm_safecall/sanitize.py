import re
from urllib.parse import urlsplit

URL_RE = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)
AMBIGUOUS_PATH_RE = re.compile(r"%(?:2e|2f|5c|25)", re.IGNORECASE)

BASH_CODEBLOCK_RE = re.compile(r"```(?:bash|sh|zsh|powershell|cmd)[\s\S]*?```", re.IGNORECASE)
SHELL_COMMAND_RE = re.compile(
    r"\b(rm\s+-rf|curl\s+|wget\s+|Invoke-WebRequest|powershell\s+-)\b", re.IGNORECASE
)


def strip_disallowed_codeblocks(text: str, allow_shell: bool) -> str:
    if allow_shell:
        return text
    return BASH_CODEBLOCK_RE.sub("[REDACTED_SHELL_BLOCK]", text)


def strip_disallowed_commands(text: str, allow_shell: bool) -> str:
    if allow_shell:
        return text
    return SHELL_COMMAND_RE.sub("[REDACTED_SHELL_CMD]", text)


def extract_urls(text: str) -> list[str]:
    return URL_RE.findall(text)


def _safe_path(path: str) -> bool:
    return (
        "\\" not in path
        and not AMBIGUOUS_PATH_RE.search(path)
        and all(segment not in {".", ".."} for segment in path.split("/"))
    )


def _path_matches(path: str, base: str) -> bool:
    return path == base or path.startswith(base.rstrip("/") + "/")


def remove_urls_not_in_allowlist(text: str, allowlist: list[str]) -> str:
    if not allowlist:
        return text

    def allowed(url: str) -> bool:
        try:
            target = urlsplit(url)
            if target.username or target.password or "\\" in url or not _safe_path(target.path):
                return False
            for prefix in allowlist:
                base = urlsplit(prefix)
                if (
                    target.scheme == base.scheme
                    and target.hostname == base.hostname
                    and target.port == base.port
                    and not base.username
                    and not base.password
                    and _safe_path(base.path)
                    and _path_matches(target.path, base.path)
                    and (not base.query or target.query == base.query)
                ):
                    return True
        except ValueError:
            return False
        return False

    return URL_RE.sub(lambda match: match[0] if allowed(match[0]) else "[BLOCKED_URL]", text)
