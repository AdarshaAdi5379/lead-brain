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


def pricing_config(*, model: Optional[str] = None) -> PricingConfig:
    """
    Read pricing config from env.

    Priority:
    1) If OPENAI_INPUT_COST_PER_1K / OPENAI_OUTPUT_COST_PER_1K are set, use them.
    2) Else, if OPENAI_PRICING_PRESET is not "off", try a built-in per-model preset.
    3) Else, return zeros (disabled).
    """

    input_cost = _as_float_env("OPENAI_INPUT_COST_PER_1K", default=0.0)
    output_cost = _as_float_env("OPENAI_OUTPUT_COST_PER_1K", default=0.0)
    if input_cost > 0.0 or output_cost > 0.0:
        return PricingConfig(input_cost_per_1k=input_cost, output_cost_per_1k=output_cost)

    preset_mode = os.environ.get("OPENAI_PRICING_PRESET", "").strip().lower()
    if preset_mode == "off":
        return PricingConfig(input_cost_per_1k=0.0, output_cost_per_1k=0.0)

    resolved_model = (
        (model or "").strip()
        or os.environ.get("OPENAI_MODEL_PRIMARY", "").strip()
        or "gpt-4.1-nano"
    )
    preset = _pricing_preset_for_model(resolved_model)
    if preset is not None:
        return preset

    return PricingConfig(input_cost_per_1k=0.0, output_cost_per_1k=0.0)


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


def _pricing_preset_for_model(model: str) -> Optional[PricingConfig]:
    """
    Returns a best-effort PricingConfig for a known model name.

    Notes:
    - Values are per-1K tokens, USD.
    - Matches common snapshot suffixes (e.g. "gpt-4o-mini-2024-07-18").
    """

    key = (model or "").strip().lower()
    if not key:
        return None

    # Normalize common snapshot suffix patterns.
    if ":" in key:
        key = key.split(":", 1)[0].strip()

    presets: dict[str, PricingConfig] = {
        # Prices are based on OpenAI's published per-1M token rates, converted to per-1K.
        "gpt-4.1": PricingConfig(input_cost_per_1k=0.002, output_cost_per_1k=0.008),
        "gpt-4.1-mini": PricingConfig(input_cost_per_1k=0.0004, output_cost_per_1k=0.0016),
        "gpt-4.1-nano": PricingConfig(input_cost_per_1k=0.0001, output_cost_per_1k=0.0004),
        "gpt-4o-mini": PricingConfig(input_cost_per_1k=0.00015, output_cost_per_1k=0.0006),
    }

    if key in presets:
        return presets[key]
    for prefix, cfg in presets.items():
        if key.startswith(prefix + "-"):
            return cfg

    return None
