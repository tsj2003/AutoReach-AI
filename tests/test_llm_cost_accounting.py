"""COGS honesty: cost is derived from REAL token usage when the API reports it,
and clearly labelled as an estimate only when it doesn't."""

from __future__ import annotations

from engine.llm.gemini import (
    GeminiResult,
    GeminiUsage,
    cost_breakdown_for_result,
    estimate_cost_cents,
)


def _result(usage):
    return GeminiResult(
        data={"subject": "hi", "body": "there"},
        raw_text='{"subject":"hi","body":"there"}',
        model="gemini-2.0-flash",
        usage=usage,
    )


def test_cost_uses_real_tokens_when_usage_present():
    r = _result(GeminiUsage(prompt_tokens=1000, output_tokens=500, total_tokens=1500))
    cb = cost_breakdown_for_result(r, prompt="x" * 4000)
    assert cb.basis == "actual_tokens"
    assert cb.prompt_tokens == 1000
    assert cb.output_tokens == 500
    # 1000*0.10/1e6 + 500*0.40/1e6 = 0.0001 + 0.0002 = 0.0003 USD = 300 micro-USD
    assert cb.micro_usd == 300
    # coarse ledger cents rounds up any non-zero cost to >=1
    assert cb.cents == 1


def test_cost_falls_back_to_char_estimate_without_usage():
    r = _result(None)  # API reported no usageMetadata
    cb = cost_breakdown_for_result(r, prompt="x" * 4000)
    assert cb.basis == "estimated_chars"
    assert cb.prompt_tokens == 0
    assert cb.micro_usd > 0


def test_token_cost_scales_with_tokens():
    small = cost_breakdown_for_result(
        _result(GeminiUsage(1000, 500, 1500)), prompt="p"
    )
    big = cost_breakdown_for_result(
        _result(GeminiUsage(1_000_000, 500_000, 1_500_000)), prompt="p"
    )
    assert big.micro_usd > small.micro_usd
    # 1M in @ $0.10 + 0.5M out @ $0.40 = $0.10 + $0.20 = $0.30 => 30 cents
    assert big.cents == 30


def test_estimate_cost_cents_backward_compatible():
    # Existing char-based helper still returns a conservative >=1 cent.
    assert estimate_cost_cents(prompt_chars=10, output_chars=10) >= 1


def test_zero_usage_falls_back_to_chars():
    # A usageMetadata with all-zero counts must not be treated as a real $0 cost.
    r = _result(GeminiUsage(0, 0, 0))
    cb = cost_breakdown_for_result(r, prompt="x" * 1000)
    assert cb.basis == "estimated_chars"
