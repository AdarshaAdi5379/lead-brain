from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from src.llm.openai_responses import OpenAIUsage


@dataclass(frozen=True)
class CostEstimate:
    input_tokens: int
    output_tokens: int
    total_tokens: int
    total_cost_usd: float


@dataclass(frozen=True)
class PricingConfig:
    input_cost_per_1k: float
    output_cost_per_1k: float

    @property
    def enabled(self) -> bool:
        return self.input_cost_per_1k > 0.0 or self.output_cost_per_1k > 0.0


def pricing_config() -> PricingConfig:
    """
    Read pricing config from env.

    If unset, returns zeros (disabled).
    """

    return PricingConfig(
        input_cost_per_1k=_as_float_env("OPENAI_INPUT_COST_PER_1K", default=0.0),
        output_cost_per_1k=_as_float_env("OPENAI_OUTPUT_COST_PER_1K", default=0.0),
    )


def estimate_cost(usage: Optional[OpenAIUsage]) -> Optional[CostEstimate]:
    """
    Estimate cost from token usage using configurable per-1K token prices.

    Configure via env vars (floats, USD):
      - OPENAI_INPUT_COST_PER_1K
      - OPENAI_OUTPUT_COST_PER_1K

    Defaults to 0.0 if unset (so cost tracking is safe-by-default, not misleading).
    """

    if usage is None:
        return None

    pricing = pricing_config()

    total_cost = (usage.input_tokens / 1000.0) * pricing.input_cost_per_1k + (
        usage.output_tokens / 1000.0
    ) * pricing.output_cost_per_1k
    return CostEstimate(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
        total_cost_usd=round(float(total_cost), 6),
    )


def _as_float_env(name: str, *, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except Exception:
        return default
