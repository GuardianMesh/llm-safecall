PRICING = {
    # Example rates in USD per 1,000 tokens; replace with your provider's rates.
    "openai:gpt-4o-mini": {"input": 0.0003, "output": 0.0012},  # $/1k tokens
    "anthropic:claude-3-5-sonnet-20240620": {"input": 0.003, "output": 0.015},
}


def estimate_cost(vendor_model: str, in_tokens: int | None, out_tokens: int | None) -> float | None:
    if in_tokens is None and out_tokens is None:
        return None
    p = PRICING.get(vendor_model)
    if not p:
        return None
    total = 0.0
    if in_tokens:
        total += (in_tokens / 1000.0) * p["input"]
    if out_tokens:
        total += (out_tokens / 1000.0) * p["output"]
    return round(total, 6)
