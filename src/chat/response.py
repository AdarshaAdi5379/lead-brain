from __future__ import annotations

import logging
from typing import Any, Optional

from src.chat import prompts
from src.chat.base import (
    ChatMode,
    ChatResponse,
    Intent,
    IntentRoute,
    RetrievalStrategy,
    RetrievedContext,
    RetrievedLead,
    source_for_lead,
)
from src.chat.config import ChatConfig
from src.chat.context_builder import build_context_block, build_lead_block
from src.chat.llm import LLMBackend, NoLLMBackend
from src.chat.memory import ConversationMemory
from src.chat.safety import fenced_data, sanitize_text, validate_grounded_answer

logger = logging.getLogger("lead.chat.response")

# Answer generation. Two modes:
#   * retrieval summary — deterministic templates over the retrieved records
#     (always works, never hallucinates by construction);
#   * RAG synthesis — a local LLM writes a natural-language answer over the
#     fenced retrieved data, with a grounding check and automatic fallback to
#     the deterministic mode on any failure.


class ResponseGenerator:
    """Turn a RetrievedContext into a grounded ChatResponse."""

    def __init__(self, backend: LLMBackend, config: ChatConfig) -> None:
        self.backend = backend
        self.config = config

    def generate(
        self,
        route: IntentRoute,
        context: RetrievedContext,
        memory: Optional[ConversationMemory] = None,
    ) -> ChatResponse:
        if context.strategy is RetrievalStrategy.LEAD_DETAIL:
            return self._detail_response(route, context)
        if context.is_empty:
            return self._no_data_response(route, context)
        if route.intent is Intent.COMPARE:
            return self._compare_response(route, context)
        if self.backend.available():
            answer = self._try_rag(route, context, memory)
            if answer is not None:
                return self._response(
                    route, context, mode=ChatMode.RAG, answer=answer, grounded=True
                )
        return self._summary_response(route, context)

    # -- deterministic modes -------------------------------------------------

    def _summary_response(
        self, route: IntentRoute, context: RetrievedContext
    ) -> ChatResponse:
        lines: list[str] = []
        if context.strategy is RetrievalStrategy.SIMILARITY:
            lines.append("Here are the most similar businesses in the database:")
        else:
            lines.append(
                f"Here are the {len(context.retrieved_leads)} most relevant leads "
                f"for your question ({context.strategy.value.replace('_', ' ')}):"
            )
        lines.append("")
        for index, lead in enumerate(context.retrieved_leads, start=1):
            lines.append(_lead_bullet(lead, index))
        answer = "\n".join(lines)
        return self._response(
            route, context, mode=ChatMode.RETRIEVAL_SUMMARY, answer=answer, grounded=True
        )

    def _compare_response(
        self, route: IntentRoute, context: RetrievedContext
    ) -> ChatResponse:
        header = "| # | Business | Category | Location | Lead | SEO | Visual | Top opportunity |"
        divider = "|---|---------|----------|----------|------|-----|--------|-----------------|"
        rows = [header, divider]
        for index, lead in enumerate(context.retrieved_leads, start=1):
            intel_lead = lead.lead
            score = lead.intel.get("score") or {}
            seo = lead.intel.get("seo") or {}
            visual = lead.intel.get("visual") or {}
            opportunities = lead.intel.get("opportunities") or []
            top = opportunities[0] if opportunities else {}
            rows.append(
                "| {i} | {name} | {cat} | {loc} | {lead} | {seo} | {vis} | {opp} |".format(
                    i=index,
                    name=sanitize_text(intel_lead.get("business_name")) or f"Lead #{lead.lead_id}",
                    cat=sanitize_text(intel_lead.get("category")) or "—",
                    loc=_location(intel_lead) or "—",
                    lead=_score(score.get("final_score")),
                    seo=_score(seo.get("site_score")),
                    vis=_score(visual.get("visual_score")),
                    opp=_score(top.get("score")),
                )
            )
        rows.append("")
        rows.append(
            "Compare columns show the stored scores; \"—\" means the value is "
            "not present in the database."
        )
        return self._response(
            route, context, mode=ChatMode.RETRIEVAL_SUMMARY, answer="\n".join(rows), grounded=True
        )

    def _detail_response(
        self, route: IntentRoute, context: RetrievedContext
    ) -> ChatResponse:
        lead = context.retrieved_leads[0]
        block = build_lead_block(lead.intel, rationale=lead.rationale)
        if block is None:
            return self._no_data_response(route, context)
        answer = "Detailed profile from the database:\n\n" + block
        return self._response(
            route, context, mode=ChatMode.LEAD_DETAIL, answer=answer, grounded=True
        )

    def _no_data_response(
        self, route: IntentRoute, context: RetrievedContext
    ) -> ChatResponse:
        hint = ""
        if route.intent is Intent.SIMILAR or route.intent is Intent.DETAIL:
            hint = (
                " I could not find that business in the database."
                if route.params.get("business_name")
                else ""
            )
        answer = (
            "I do not have enough data for this question." + hint
            + " Try a different wording, or check that the search index has been "
            "built (the dashboard AI Search page shows the index state)."
        )
        return self._response(route, context, mode=ChatMode.NO_DATA, answer=answer, grounded=True)

    # -- RAG mode ------------------------------------------------------------

    def _try_rag(
        self,
        route: IntentRoute,
        context: RetrievedContext,
        memory: Optional[ConversationMemory],
    ) -> Optional[str]:
        try:
            body = build_context_block(
                context,
                max_leads=self.config.max_context_leads,
                max_chars=self.config.max_context_chars,
            )
            user_prompt = prompts.build_user_prompt(
                route.raw_query,
                fenced_data([body]) if body else "",
                history_text=memory.history_text(max_turns=4) if memory else "",
            )
            answer = self.backend.synthesize(prompts.SYSTEM_PROMPT, user_prompt)
            if not answer or not answer.strip():
                return None
            names = [
                str(lead.lead.get("business_name") or f"Lead #{lead.lead_id}")
                for lead in context.retrieved_leads
            ]
            ok, unknown = validate_grounded_answer(answer, names)
            if not ok:
                logger.debug("RAG answer rejected (unknown references %s); falling back", unknown)
                return None
            return answer.strip()
        except Exception as exc:
            logger.debug("RAG synthesis failed: %s", exc)
            return None

    # -- shared --------------------------------------------------------------

    def _response(
        self,
        route: IntentRoute,
        context: RetrievedContext,
        *,
        mode: ChatMode,
        answer: str,
        grounded: bool,
    ) -> ChatResponse:
        return ChatResponse(
            answer=answer,
            mode=mode,
            intent=route.intent,
            strategy=context.strategy,
            grounded=grounded,
            sources=[source_for_lead(lead, rank) for rank, lead in enumerate(context.retrieved_leads, start=1)],
            retrieved_lead_ids=[lead.lead_id for lead in context.retrieved_leads],
            backend_name=self.backend.name,
            filters_used=dict(context.filters_used),
        )


def _lead_bullet(lead: RetrievedLead, index: int) -> str:
    intel_lead = lead.lead
    score = lead.intel.get("score") or {}
    seo = lead.intel.get("seo") or {}
    visual = lead.intel.get("visual") or {}
    opportunities = lead.intel.get("opportunities") or []
    top = opportunities[0] if opportunities else {}

    name = sanitize_text(intel_lead.get("business_name")) or f"Lead #{lead.lead_id}"
    parts = [f"[{index}] **{name}**"]
    meta = [p for p in (intel_lead.get("category"), _location(intel_lead)) if p]
    if meta:
        parts.append(" · ".join(meta))
    metrics = []
    if score.get("final_score") is not None:
        metrics.append(f"lead {score['final_score']}/100")
    if seo.get("site_score") is not None:
        metrics.append(f"seo {seo['site_score']}/100")
    if visual.get("visual_score") is not None:
        metrics.append(f"visual {visual['visual_score']}/100")
    if top.get("label"):
        metrics.append(f"top opportunity: {sanitize_text(top['label'])} {top.get('score', '')}/100")
    if metrics:
        parts.append(" — " + ", ".join(metrics))
    if lead.similarity is not None:
        parts.append(f" (similarity {lead.similarity:.2f})")
    line = "".join(parts)
    if lead.rationale:
        line += f"\n    Why: {sanitize_text(lead.rationale)}"
    return line


def _location(lead: dict[str, Any]) -> str:
    return ", ".join(part for part in (lead.get("city"), lead.get("state"), lead.get("country")) if part)


def _score(value: Any) -> str:
    return "—" if value is None else str(int(value))


def make_backend(config: ChatConfig) -> LLMBackend:
    from src.chat.llm import get_backend

    try:
        return get_backend(config)
    except Exception as exc:
        logger.debug("Backend resolution failed: %s", exc)
        return NoLLMBackend()