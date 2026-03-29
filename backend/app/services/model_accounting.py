from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import Float, case, cast, func, or_


USAGE_SOURCE_EXACT = "exact"
USAGE_SOURCE_ESTIMATED = "estimated"
USAGE_SOURCE_UNKNOWN = "unknown"

COST_SOURCE_BINDING_PRICING = "binding_pricing"
COST_SOURCE_PROVIDER_REPORTED = "provider_reported"
COST_SOURCE_MANUAL_OVERRIDE = "manual_override"
COST_SOURCE_UNKNOWN = "unknown"

EXACT_USAGE_SOURCES = {USAGE_SOURCE_EXACT}
ESTIMATED_USAGE_SOURCES = {USAGE_SOURCE_ESTIMATED}
UNKNOWN_USAGE_SOURCES = {USAGE_SOURCE_UNKNOWN}

EXACT_COST_SOURCES = {COST_SOURCE_BINDING_PRICING, COST_SOURCE_PROVIDER_REPORTED}
ESTIMATED_COST_SOURCES = {COST_SOURCE_MANUAL_OVERRIDE}
UNKNOWN_COST_SOURCES = {COST_SOURCE_UNKNOWN}


def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _quantize_usd(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


@dataclass
class NormalizedUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_input_tokens: int | None = None
    cached_output_tokens: int | None = None
    reasoning_tokens: int | None = None
    audio_input_tokens: int | None = None
    audio_output_tokens: int | None = None
    image_input_units: int | None = None
    image_output_units: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def finalize(self) -> "NormalizedUsage":
        normalized = NormalizedUsage(
            input_tokens=max(0, self.input_tokens) if self.input_tokens is not None else None,
            output_tokens=max(0, self.output_tokens) if self.output_tokens is not None else None,
            total_tokens=max(0, self.total_tokens) if self.total_tokens is not None else None,
            cached_input_tokens=max(0, self.cached_input_tokens) if self.cached_input_tokens is not None else None,
            cached_output_tokens=max(0, self.cached_output_tokens) if self.cached_output_tokens is not None else None,
            reasoning_tokens=max(0, self.reasoning_tokens) if self.reasoning_tokens is not None else None,
            audio_input_tokens=max(0, self.audio_input_tokens) if self.audio_input_tokens is not None else None,
            audio_output_tokens=max(0, self.audio_output_tokens) if self.audio_output_tokens is not None else None,
            image_input_units=max(0, self.image_input_units) if self.image_input_units is not None else None,
            image_output_units=max(0, self.image_output_units) if self.image_output_units is not None else None,
            extra=dict(self.extra or {}),
        )
        if normalized.total_tokens is None:
            parts = [normalized.input_tokens, normalized.output_tokens]
            if all(part is not None for part in parts):
                normalized.total_tokens = sum(int(part or 0) for part in parts)
        return normalized

    def to_json(self) -> dict[str, Any]:
        payload = asdict(self.finalize())
        return {key: value for key, value in payload.items() if value not in (None, {}, [])}


@dataclass
class NormalizedCost:
    currency: str = "USD"
    total_cost: Decimal | None = None
    line_items: list[dict[str, Any]] = field(default_factory=list)
    source: str = COST_SOURCE_UNKNOWN

    def to_json(self) -> dict[str, Any]:
        total_cost = _quantize_usd(self.total_cost)
        payload = {
            "currency": self.currency,
            "total_cost": float(total_cost) if total_cost is not None else None,
            "line_items": self.line_items,
            "source": self.source,
        }
        return {key: value for key, value in payload.items() if value not in (None, [], {})}


def usage_total_expr(run_model: Any) -> Any:
    return func.coalesce(run_model.total_tokens, run_model.usage_tokens, 0)


def usage_exact_expr(run_model: Any) -> Any:
    return case(
        (run_model.usage_source.in_(tuple(EXACT_USAGE_SOURCES)), usage_total_expr(run_model)),
        else_=0,
    )


def usage_estimated_expr(run_model: Any) -> Any:
    return case(
        (run_model.usage_source.in_(tuple(ESTIMATED_USAGE_SOURCES)), usage_total_expr(run_model)),
        else_=0,
    )


def usage_unknown_count_expr(run_model: Any) -> Any:
    return case(
        (
            or_(
                run_model.usage_source.is_(None),
                run_model.usage_source.in_(tuple(UNKNOWN_USAGE_SOURCES)),
            ),
            1,
        ),
        else_=0,
    )


def cost_exact_expr(run_model: Any) -> Any:
    return case(
        (
            run_model.cost_source.in_(tuple(EXACT_COST_SOURCES)),
            func.coalesce(run_model.cost_usd, 0.0),
        ),
        else_=0.0,
    )


def cost_estimated_expr(run_model: Any) -> Any:
    return case(
        (
            run_model.cost_source.in_(tuple(ESTIMATED_COST_SOURCES)),
            func.coalesce(run_model.cost_usd, 0.0),
        ),
        else_=0.0,
    )


def cost_unknown_count_expr(run_model: Any) -> Any:
    return case(
        (
            or_(
                run_model.cost_source.is_(None),
                run_model.cost_source.in_(tuple(UNKNOWN_COST_SOURCES)),
                run_model.cost_usd.is_(None),
            ),
            1,
        ),
        else_=0,
    )


def cost_total_expr(run_model: Any) -> Any:
    return cast(func.coalesce(run_model.cost_usd, 0.0), Float)


def billable_total_tokens(run: Any) -> int:
    return max(0, int(getattr(run, "total_tokens", None) or getattr(run, "usage_tokens", 0) or 0))


def build_usage_from_total(total_tokens: int | None) -> NormalizedUsage:
    usage = NormalizedUsage(total_tokens=_to_int(total_tokens))
    return usage.finalize()


def resolved_usage_source(run: Any) -> str:
    raw_source = str(getattr(run, "usage_source", "") or "").strip()
    if raw_source in EXACT_USAGE_SOURCES | ESTIMATED_USAGE_SOURCES | UNKNOWN_USAGE_SOURCES:
        return raw_source
    total_tokens = getattr(run, "total_tokens", None)
    usage_tokens = getattr(run, "usage_tokens", None)
    if total_tokens is not None or usage_tokens:
        return USAGE_SOURCE_ESTIMATED
    return USAGE_SOURCE_UNKNOWN


def usage_payload_from_run(run: Any) -> dict[str, Any] | None:
    if run is None:
        return None

    source = resolved_usage_source(run)
    total_tokens = getattr(run, "total_tokens", None)
    usage_tokens = getattr(run, "usage_tokens", None)
    normalized = NormalizedUsage(
        input_tokens=_to_int(getattr(run, "input_tokens", None)),
        output_tokens=_to_int(getattr(run, "output_tokens", None)),
        total_tokens=_to_int(total_tokens if total_tokens is not None else usage_tokens),
        cached_input_tokens=_to_int(getattr(run, "cached_input_tokens", None)),
        cached_output_tokens=_to_int(getattr(run, "cached_output_tokens", None)),
        reasoning_tokens=_to_int(getattr(run, "reasoning_tokens", None)),
    ).finalize()
    return {
        "source": source,
        "input_tokens": normalized.input_tokens,
        "output_tokens": normalized.output_tokens,
        "total_tokens": normalized.total_tokens if normalized.total_tokens is not None else 0,
        "cached_input_tokens": normalized.cached_input_tokens,
        "cached_output_tokens": normalized.cached_output_tokens,
        "reasoning_tokens": normalized.reasoning_tokens,
    }


def binding_pricing_snapshot(binding: Any) -> dict[str, Any]:
    pricing_config = dict(getattr(binding, "pricing_config", None) or {})
    return pricing_config


def compute_cost_from_snapshot(
    *,
    usage: NormalizedUsage,
    pricing_snapshot: dict[str, Any] | None,
    provider_reported_cost: Any = None,
) -> NormalizedCost:
    usage = usage.finalize()
    provider_cost = _to_decimal(provider_reported_cost)
    if provider_cost is not None:
        return NormalizedCost(
            currency="USD",
            total_cost=_quantize_usd(provider_cost),
            line_items=[{"dimension": "provider_reported_total", "amount": float(_quantize_usd(provider_cost) or 0)}],
            source=COST_SOURCE_PROVIDER_REPORTED,
        )

    snapshot = dict(pricing_snapshot or {})
    currency = str(snapshot.get("currency") or "USD").upper()
    billing_mode = str(snapshot.get("billing_mode") or "unknown").strip().lower()
    rates = snapshot.get("rates") if isinstance(snapshot.get("rates"), dict) else {}

    if billing_mode == "manual":
        amount = _to_decimal(snapshot.get("manual_total_cost"))
        return NormalizedCost(
            currency=currency,
            total_cost=_quantize_usd(amount),
            line_items=[{"dimension": "manual_total_cost", "amount": float(_quantize_usd(amount) or 0)}] if amount is not None else [],
            source=COST_SOURCE_MANUAL_OVERRIDE if amount is not None else COST_SOURCE_UNKNOWN,
        )

    if billing_mode == "flat_per_request":
        flat_amount = _to_decimal(snapshot.get("flat_amount"))
        return NormalizedCost(
            currency=currency,
            total_cost=_quantize_usd(flat_amount),
            line_items=[{"dimension": "flat_per_request", "amount": float(_quantize_usd(flat_amount) or 0)}] if flat_amount is not None else [],
            source=COST_SOURCE_BINDING_PRICING if flat_amount is not None else COST_SOURCE_UNKNOWN,
        )

    divisor = Decimal("1000") if billing_mode == "per_1k_tokens" else Decimal("1")
    supported_dimensions = {
        "input": usage.input_tokens,
        "output": usage.output_tokens,
        "cached_input": usage.cached_input_tokens,
        "cached_output": usage.cached_output_tokens,
        "reasoning": usage.reasoning_tokens,
        "audio_input": usage.audio_input_tokens,
        "audio_output": usage.audio_output_tokens,
        "image_input": usage.image_input_units,
        "image_output": usage.image_output_units,
    }
    line_items: list[dict[str, Any]] = []
    total = Decimal("0")
    has_priced_dimension = False
    for dimension, quantity in supported_dimensions.items():
        rate = _to_decimal(rates.get(dimension))
        if quantity is None or rate is None:
            continue
        has_priced_dimension = True
        amount = (Decimal(str(quantity)) / divisor) * rate
        amount = _quantize_usd(amount) or Decimal("0")
        total += amount
        line_items.append(
            {
                "dimension": dimension,
                "quantity": int(quantity),
                "rate": float(rate),
                "amount": float(amount),
                "billing_mode": billing_mode,
            }
        )

    if not has_priced_dimension and usage.total_tokens is not None:
        input_rate = _to_decimal(rates.get("input"))
        if input_rate is not None:
            amount = (Decimal(str(usage.total_tokens)) / divisor) * input_rate
            amount = _quantize_usd(amount) or Decimal("0")
            total += amount
            line_items.append(
                {
                    "dimension": "total_tokens_fallback",
                    "quantity": int(usage.total_tokens),
                    "rate": float(input_rate),
                    "amount": float(amount),
                    "billing_mode": billing_mode,
                }
            )
            has_priced_dimension = True

    minimum_charge = _to_decimal(snapshot.get("minimum_charge"))
    if minimum_charge is not None and total < minimum_charge:
        total = minimum_charge
        line_items.append({"dimension": "minimum_charge", "amount": float(_quantize_usd(minimum_charge) or 0)})

    if has_priced_dimension:
        return NormalizedCost(
            currency=currency,
            total_cost=_quantize_usd(total),
            line_items=line_items,
            source=COST_SOURCE_BINDING_PRICING,
        )

    return NormalizedCost(currency=currency, total_cost=None, line_items=[], source=COST_SOURCE_UNKNOWN)
