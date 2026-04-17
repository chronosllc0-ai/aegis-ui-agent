"""Regression tests for credit-rate charging behavior."""

from backend.credit_rates import calculate_credits


def test_calculate_credits_free_model_charges_zero() -> None:
    """Free-tier models should not incur the minimum 1-credit floor."""
    exact, charged, raw_cost = calculate_credits(
        "chronos",
        "qwen/qwen3-coder:free",
        input_tokens=1200,
        output_tokens=800,
    )
    assert exact == 0.0
    assert charged == 0
    assert raw_cost == 0.0


def test_calculate_credits_paid_model_keeps_minimum_floor() -> None:
    """Paid models should retain minimum 1-credit charging behavior."""
    exact, charged, raw_cost = calculate_credits(
        "openrouter",
        "minimax/minimax-m2.5",
        input_tokens=1,
        output_tokens=1,
    )
    assert exact > 0.0
    assert charged == 1
    assert raw_cost > 0.0
