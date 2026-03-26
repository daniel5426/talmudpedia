from decimal import Decimal

from app.services.model_accounting import (
    COST_SOURCE_BINDING_PRICING,
    COST_SOURCE_MANUAL_OVERRIDE,
    COST_SOURCE_UNKNOWN,
    NormalizedUsage,
    binding_pricing_snapshot,
    compute_cost_from_snapshot,
)


class _BindingStub:
    def __init__(self, *, input_rate=None, output_rate=None, pricing_config=None):
        self.cost_per_1k_input_tokens = input_rate
        self.cost_per_1k_output_tokens = output_rate
        self.pricing_config = pricing_config or {}


def test_binding_pricing_snapshot_uses_only_pricing_config():
    binding = _BindingStub(
        input_rate=0.001,
        output_rate=0.004,
        pricing_config={"currency": "USD", "billing_mode": "per_1k_tokens", "rates": {"input": 0.002}},
    )

    snapshot = binding_pricing_snapshot(binding)

    assert snapshot["billing_mode"] == "per_1k_tokens"
    assert snapshot["rates"]["input"] == 0.002
    assert "output" not in snapshot["rates"]


def test_compute_cost_from_snapshot_supports_exact_and_manual_pricing():
    usage = NormalizedUsage(input_tokens=1000, output_tokens=500).finalize()

    exact_cost = compute_cost_from_snapshot(
        usage=usage,
        pricing_snapshot={
            "currency": "USD",
            "billing_mode": "per_1k_tokens",
            "rates": {"input": 0.001, "output": 0.004},
        },
    )
    assert exact_cost.source == COST_SOURCE_BINDING_PRICING
    assert exact_cost.total_cost == Decimal("0.003000")

    manual_cost = compute_cost_from_snapshot(
        usage=usage,
        pricing_snapshot={
            "currency": "USD",
            "billing_mode": "manual",
            "manual_total_cost": 1.25,
        },
    )
    assert manual_cost.source == COST_SOURCE_MANUAL_OVERRIDE
    assert manual_cost.total_cost == Decimal("1.250000")


def test_compute_cost_from_snapshot_returns_unknown_without_seeded_pricing():
    usage = NormalizedUsage(input_tokens=1000, output_tokens=500).finalize()

    cost = compute_cost_from_snapshot(
        usage=usage,
        pricing_snapshot={},
    )

    assert cost.source == COST_SOURCE_UNKNOWN
    assert cost.total_cost is None


def test_compute_cost_from_snapshot_supports_seeded_and_tenant_managed_token_pricing():
    usage = NormalizedUsage(input_tokens=1000, output_tokens=500, reasoning_tokens=200).finalize()

    seeded_cost = compute_cost_from_snapshot(
        usage=usage,
        pricing_snapshot={
            "currency": "USD",
            "billing_mode": "per_1k_tokens",
            "rates": {"input": 0.00125, "output": 0.01},
        },
    )
    assert seeded_cost.source == COST_SOURCE_BINDING_PRICING
    assert seeded_cost.total_cost == Decimal("0.006250")

    local_cost = compute_cost_from_snapshot(
        usage=usage,
        pricing_snapshot={
            "currency": "USD",
            "billing_mode": "per_1k_tokens",
            "rates": {"input": 0.001, "output": 0.004, "reasoning": 0.002},
        },
    )
    assert local_cost.source == COST_SOURCE_BINDING_PRICING
    assert local_cost.total_cost == Decimal("0.003400")
