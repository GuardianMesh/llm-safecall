import os
from pathlib import Path

from .budget import Budget
from .policy import PolicyConfig, PolicyEngine
from .providers.anthropic_provider import AnthropicProvider
from .providers.openai_provider import OpenAIProvider
from .rate_limit import TokenBucket
from .safe_call import SafeCall


def from_env(output=None):
    provider = (os.getenv("LLM_PROVIDER") or "openai").lower()
    if provider not in {"openai", "anthropic", "mock"}:
        raise ValueError("LLM_PROVIDER must be openai, anthropic, or mock")
    model = os.getenv("LLM_MODEL") or (
        "claude-sonnet-4-6" if provider == "anthropic" else "gpt-4o-mini"
    )

    allow_shell = (os.getenv("LLM_ALLOW_SHELL") or "false").lower() == "true"
    allow_urls = [u.strip() for u in (os.getenv("LLM_URL_ALLOWLIST") or "").split(",") if u.strip()]

    policy = PolicyEngine(
        PolicyConfig(
            allow_shell_output=allow_shell,
            outbound_url_allowlist=allow_urls,
        )
    )

    budget = None
    if os.getenv("LLM_BUDGET_DAILY"):
        daily = float(os.getenv("LLM_BUDGET_DAILY"))
        path = os.getenv("LLM_BUDGET_PATH", ".llm_safecall_budget.json")
        budget = Budget(path=Path(path), daily_limit=daily)

    rate = os.getenv("LLM_RATE_PER_SEC")
    rate_limit = TokenBucket(float(rate)) if rate else None

    if provider == "openai":
        llm = OpenAIProvider(model=model)
    elif provider == "anthropic":
        llm = AnthropicProvider(model=model)
    else:
        from .providers.mock_provider import MockProvider

        llm = MockProvider()

    return SafeCall(
        llm=llm,
        output=output,
        policy=policy,
        budget=budget,
        rate_limit=rate_limit,
    )
