import math

# Caller-supplied rates per 1,000 tokens, in a consistent currency.
PRICING: dict[str, dict[str, float]] = {}


def estimate_cost(vendor_model: str, in_tokens: int | None, out_tokens: int | None) -> float | None:
    for count in (in_tokens, out_tokens):
        if count is not None and (
            isinstance(count, bool) or not isinstance(count, int) or count < 0
        ):
            raise ValueError("Token counts must be non-negative integers")
    p = PRICING.get(vendor_model)
    if p is None or in_tokens is None or out_tokens is None:
        return None
    for field in ("input", "output"):
        rate = p.get(field)
        if (
            isinstance(rate, bool)
            or not isinstance(rate, (float, int))
            or not math.isfinite(rate)
            or rate < 0
        ):
            raise ValueError("Token rates must be finite non-negative numbers")
    try:
        total = (in_tokens / 1000) * p["input"] + (out_tokens / 1000) * p["output"]
    except OverflowError as error:
        raise ValueError("Estimated cost exceeds the numeric range") from error
    if not math.isfinite(total):
        raise ValueError("Estimated cost exceeds the numeric range")
    return round(total, 6)
