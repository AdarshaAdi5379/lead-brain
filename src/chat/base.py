from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

# Core data contracts for the grounded chat assistant. Pure dataclasses with no
# I/O — the service layer builds them and the dashboard renders them.


class Intent(enum.Enum):
    """What the user is asking for, detected by lightweight rules (router.py)."""

    SEARCH = "search"
    RANK = "rank"
    SUMMARIZE = "summarize"
    COMPARE = "compare"
    SIMILAR = "similar"
    OUTREACH = "outreach"
    EXPLAIN = "explain"
    DETAIL = "detail"


class ChatMode(enum.Enum):
    """How the answer was produced (shown in the dashboard)."""

    RETRIEVAL_SUMMARY = "retrieval_summary"
    RAG = "rag"
    LEAD_DETAIL = "lead_detail"
    NO_DATA = "no_data"


class RetrievalStrategy(enum.Enum):
    """Which retrieval path produced the context for the answer."""

    SEMANTIC_SEARCH = "semantic_search"
    SQL_FILTERS = "sql_filters"
    SIMILARITY = "similarity"
    LEAD_DETAIL = "lead_detail"
    COMPARE = "compare"
    NONE = "none"


@dataclass(frozen=True)
class IntentRoute:
    """Parsed user question: the detected intent plus extracted parameters.

    ``params`` keys reuse the semantic-search filter vocabulary where possible
    (category, city, state, platform, priority, website_present, *_score), plus
    chat-specific keys: ``top_n`` (int) and ``business_name`` (str).
    """

    intent: Intent
    params: dict[str, Any] = field(default_factory=dict)
    raw_query: str = ""

    @property
    def top_n(self) -> int:
        raw = self.params.get("top_n")
        return int(raw) if isinstance(raw, int) and raw > 0 else 0

    def with_params(self, **overrides: Any) -> "IntentRoute":
        params = dict(self.params)
        params.update(overrides)
        return IntentRoute(
            intent=self.intent, params=params, raw_query=self.raw_query
        )


@dataclass(frozen=True)
class RetrievedLead:
    """One lead pulled from the database for a question."""

    lead_id: int
    intel: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""
    similarity: Optional[float] = None

    @property
    def lead(self) -> dict[str, Any]:
        return self.intel.get("lead") or {}


@dataclass(frozen=True)
class RetrievedContext:
    """Everything retrieved for one question, before answer generation."""

    query: str
    intent: Intent = Intent.SEARCH
    strategy: RetrievalStrategy = RetrievalStrategy.NONE
    filters_used: dict[str, Any] = field(default_factory=dict)
    retrieved_leads: list[RetrievedLead] = field(default_factory=list)
    index_count: int = 0

    @property
    def is_empty(self) -> bool:
        return not self.retrieved_leads


@dataclass(frozen=True)
class ChatResponse:
    """The final assistant answer plus everything the UI needs to show."""

    answer: str
    mode: ChatMode = ChatMode.NO_DATA
    intent: Intent = Intent.SEARCH
    strategy: RetrievalStrategy = RetrievalStrategy.NONE
    grounded: bool = False
    sources: list[dict[str, Any]] = field(default_factory=list)
    retrieved_lead_ids: list[int] = field(default_factory=list)
    backend_name: str = "none"
    filters_used: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "mode": self.mode.value,
            "intent": self.intent.value,
            "strategy": self.strategy.value,
            "grounded": self.grounded,
            "sources": self.sources,
            "retrieved_lead_ids": list(self.retrieved_lead_ids),
            "backend_name": self.backend_name,
            "filters_used": dict(self.filters_used),
            "created_at": self.created_at,
        }


def source_for_lead(lead: RetrievedLead, rank: int = 0) -> dict[str, Any]:
    """Flatten one retrieved lead into the sources-panel record shape."""
    intel_lead = lead.lead
    score = lead.intel.get("score") or {}
    seo = lead.intel.get("seo") or {}
    visual = lead.intel.get("visual") or {}
    opportunities = lead.intel.get("opportunities") or []
    return {
        "rank": rank,
        "lead_id": lead.lead_id,
        "business_name": intel_lead.get("business_name"),
        "website_url": intel_lead.get("website_url"),
        "category": intel_lead.get("category"),
        "city": intel_lead.get("city"),
        "state": intel_lead.get("state"),
        "lead_score": score.get("final_score") if score else intel_lead.get("score"),
        "seo_score": seo.get("site_score"),
        "visual_score": visual.get("visual_score"),
        "opportunity_score": max(
            (int(item.get("score") or 0) for item in opportunities), default=0
        )
        or None,
        "priority": intel_lead.get("priority"),
        "similarity": lead.similarity,
        "rationale": lead.rationale,
    }
