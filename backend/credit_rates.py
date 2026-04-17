"""Credit rates per model — credits per 1,000 tokens.

Formula: rate = (provider_cost_per_MTok × 1.4)
Where 1.4 = 40% platform margin, 1 credit = $0.001.
"""

from __future__ import annotations

from math import ceil

CREDIT_RATES: dict[str, dict[str, dict]] = {
    "openai": {
        "gpt-5.2":       {"input": 1.2,   "output": 9.8,    "tier": "standard"},
        "gpt-5.2-pro":   {"input": 14.7,  "output": 117.6,  "tier": "ultra"},
        "gpt-5":         {"input": 0.9,   "output": 7.0,    "tier": "standard"},
        "gpt-5-mini":    {"input": 0.2,   "output": 1.4,    "tier": "budget"},
        "gpt-5-nano":    {"input": 0.04,  "output": 0.3,    "tier": "budget"},
        "gpt-4.1":       {"input": 1.4,   "output": 5.6,    "tier": "standard"},
        "gpt-4.1-mini":  {"input": 0.6,   "output": 2.2,    "tier": "mid"},
        "gpt-4.1-nano":  {"input": 0.1,   "output": 0.6,    "tier": "budget"},
        "o4-mini":       {"input": 0.4,   "output": 2.8,    "tier": "mid"},
        "o3":            {"input": 3.5,   "output": 21.0,   "tier": "premium"},
    },
    "anthropic": {
        "claude-opus-4-6":            {"input": 7.0,  "output": 35.0, "tier": "premium"},
        "claude-sonnet-4-6":          {"input": 4.2,  "output": 21.0, "tier": "premium"},
        "claude-haiku-4-5":           {"input": 1.4,  "output": 7.0,  "tier": "standard"},
        "claude-sonnet-4-20250514":   {"input": 4.2,  "output": 21.0, "tier": "premium"},
        "claude-3.5-sonnet-20241022": {"input": 4.2,  "output": 21.0, "tier": "premium"},
    },
    "google": {
        "gemini-3.1-pro-preview":        {"input": 2.8,  "output": 16.8, "tier": "premium"},
        "gemini-3.1-flash-lite-preview": {"input": 0.4,  "output": 2.1,  "tier": "mid"},
        "gemini-3-flash-preview":        {"input": 0.7,  "output": 4.2,  "tier": "mid"},
        "gemini-2.5-pro":                {"input": 1.8,  "output": 14.0, "tier": "premium"},
        "gemini-2.5-flash":              {"input": 0.4,  "output": 3.5,  "tier": "mid"},
    },
    "xai": {
        "grok-4-20250720":              {"input": 4.2,  "output": 21.0, "tier": "premium"},
        "grok-4.20-beta":               {"input": 2.8,  "output": 8.4,  "tier": "standard"},
        "grok-4.20-multi-agent-beta":   {"input": 2.8,  "output": 8.4,  "tier": "standard"},
        "grok-3":                       {"input": 2.1,  "output": 7.0,  "tier": "standard"},
        "grok-3-mini":                  {"input": 0.4,  "output": 2.1,  "tier": "mid"},
        "grok-3-mini-fast":             {"input": 0.3,  "output": 1.4,  "tier": "mid"},
        "grok-2-vision-1212":           {"input": 1.4,  "output": 5.6,  "tier": "standard"},
    },
    "openrouter": {
        "openai/gpt-5.4-pro":                           {"input": 42.0, "output": 252.0, "tier": "ultra"},
        "openai/gpt-5.4":                               {"input": 3.5,  "output": 21.0,  "tier": "premium"},
        "openai/gpt-5.4-mini":                          {"input": 1.1,  "output": 6.3,   "tier": "standard"},
        "openai/gpt-5.4-nano":                          {"input": 0.3,  "output": 1.8,   "tier": "mid"},
        "openai/gpt-5.3-codex":                         {"input": 2.5,  "output": 19.6,  "tier": "premium"},
        "anthropic/claude-opus-4.6":                    {"input": 7.0,  "output": 35.0,  "tier": "premium"},
        "x-ai/grok-4.20-beta":                          {"input": 2.8,  "output": 8.4,   "tier": "standard"},
        "qwen/qwen3-max-thinking":                      {"input": 1.1,  "output": 5.5,   "tier": "standard"},
        "qwen/qwen3-next-80b-a3b-instruct:free":        {"input": 0.0,  "output": 0.0,   "tier": "budget"},
        "qwen/qwen3-coder:free":                        {"input": 0.0,  "output": 0.0,   "tier": "budget"},
        "google/gemma-4-26b-a4b-it:free":               {"input": 0.0,  "output": 0.0,   "tier": "budget"},
        "google/gemma-4-31b-it:free":                   {"input": 0.0,  "output": 0.0,   "tier": "budget"},
        "nvidia/nemotron-nano-9b-v2:free":              {"input": 0.0,  "output": 0.0,   "tier": "budget"},
        "minimax/minimax-m2.5:free":                    {"input": 0.0,  "output": 0.0,   "tier": "budget"},
        "z-ai/glm-4.5-air:free":                        {"input": 0.0,  "output": 0.0,   "tier": "budget"},
        "qwen/qwen3-coder-next":                        {"input": 0.2,  "output": 1.1,   "tier": "budget"},
        "qwen/qwen3.5-9b":                              {"input": 0.1,  "output": 0.2,   "tier": "budget"},
        "qwen/qwen3.5-122b-a10b":                       {"input": 0.4,  "output": 2.9,   "tier": "mid"},
        "mistralai/mistral-small-4":                    {"input": 0.2,  "output": 0.8,   "tier": "budget"},
        "google/gemini-3.1-pro-preview-custom-tools":   {"input": 2.8,  "output": 16.8,  "tier": "premium"},
        "minimax/minimax-m2.7":                         {"input": 0.6,  "output": 2.8,   "tier": "mid"},
        "minimax/minimax-m2.5":                         {"input": 0.3,  "output": 1.7,   "tier": "budget"},
        "nvidia/nemotron-3-super-120b-a12b":             {"input": 0.2,  "output": 0.7,   "tier": "budget"},
        "nvidia/nemotron-3-super-120b-a12b:free":       {"input": 0.0,  "output": 0.0,   "tier": "budget"},
        "z-ai/glm-5-turbo":                             {"input": 1.3,  "output": 4.5,   "tier": "mid"},
        "z-ai/glm-5":                                   {"input": 1.0,  "output": 3.2,   "tier": "mid"},
        "bytedance-seed/seed-2.0-lite":                 {"input": 0.4,  "output": 1.7,   "tier": "budget"},
        "xiaomi/mimo-v2-omni":                          {"input": 0.6,  "output": 2.8,   "tier": "mid"},
        "xiaomi/mimo-v2-pro":                           {"input": 1.4,  "output": 4.2,   "tier": "standard"},
    },
}

PLAN_ALLOWANCES: dict[str, int] = {
    "free": 1_000,
    "pro": 50_000,
    "team": 200_000,
}

OVERAGE_RATES: dict[str, float] = {
    "pro": 0.001,    # $0.001 per credit overage ($1/1K)
    "team": 0.0008,  # $0.0008 per credit overage ($0.80/1K)
}


def get_rate(provider: str, model: str) -> dict:
    """Get credit rate for a provider/model combo.  Falls back to mid-tier defaults."""
    if provider == "chronos":
        provider = "openrouter"  # chronos uses openrouter rates
    provider_rates = CREDIT_RATES.get(provider, {})
    rate = provider_rates.get(model)
    if rate:
        return rate
    return {"input": 1.0, "output": 5.0, "tier": "standard"}


def calculate_credits(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> tuple[float, int, float]:
    """Calculate credit usage for an interaction.

    Returns ``(exact_credits, charged_credits, raw_cost_usd)``.
    """
    rate = get_rate(provider, model)
    exact = (input_tokens / 1000 * rate["input"]) + (output_tokens / 1000 * rate["output"])
    charged = max(1, ceil(exact))  # minimum 1 credit per interaction
    # Back-calculate raw cost (remove the 1.4× margin)
    raw_cost = exact / 1.4 * 0.001
    return exact, charged, raw_cost


def get_tier(provider: str, model: str) -> str:
    """Get the cost tier for a model: budget, mid, standard, premium, ultra."""
    rate = get_rate(provider, model)
    return rate.get("tier", "standard")
