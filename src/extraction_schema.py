from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal, Optional


Complexity = Literal["basic", "medium", "complex", "unknown"]
LoadSpeed = Literal["fast", "medium", "slow", "unknown"]
Platform = Literal[
    "wordpress",
    "wix",
    "squarespace",
    "weebly",
    "shopify",
    "custom_html",
    "custom_react",
    "unknown",
]


@dataclass(frozen=True)
class ExtractedLead:
    # Input identity
    url: Optional[str]

    # Extracted fields
    business_name: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    platform: Platform
    complexity: Complexity
    load_speed: LoadSpeed

    # Meta
    extraction_success: bool
    last_error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean_optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _clean_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y"}


def _as_enum(value: Any, allowed: set[str], default: str = "unknown") -> str:
    text = str(value).strip().lower() if value is not None else ""
    return text if text in allowed else default


def validate_extracted_lead(payload: dict[str, Any]) -> ExtractedLead:
    """
    Validate and normalize an extracted lead payload into the v1 contract.

    Rules:
    - `url` is required (can be null, but key must exist).
    - Missing/blank strings become null.
    - Enums are normalized to lowercase and default to 'unknown'.
    """

    if "url" not in payload:
        raise ValueError("Missing required key: url")

    platform = _as_enum(
        payload.get("platform"),
        {
            "wordpress",
            "wix",
            "squarespace",
            "weebly",
            "shopify",
            "custom_html",
            "custom_react",
            "unknown",
        },
    )
    complexity = _as_enum(payload.get("complexity"), {"basic", "medium", "complex", "unknown"})
    load_speed = _as_enum(payload.get("load_speed"), {"fast", "medium", "slow", "unknown"})

    return ExtractedLead(
        url=_clean_optional_str(payload.get("url")),
        business_name=_clean_optional_str(payload.get("business_name")),
        phone=_clean_optional_str(payload.get("phone")),
        email=_clean_optional_str(payload.get("email")),
        platform=platform,  # type: ignore[arg-type]
        complexity=complexity,  # type: ignore[arg-type]
        load_speed=load_speed,  # type: ignore[arg-type]
        extraction_success=_clean_bool(payload.get("extraction_success")),
        last_error=_clean_optional_str(payload.get("last_error")),
    )

