from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import streamlit as st

from src.settings import DB_PATH
from src.storage.db import init_db
from src.storage.opportunities import opportunities_by_lead as lead_opportunities_by_lead
from src.storage.scores import scores_by_lead as lead_scores_by_lead
from src.storage.seo import audits_by_lead as seo_audits_by_lead
from src.storage.seo import page_audits_for_audit
from src.storage.technologies import detections_by_lead
from src.storage.visual import audits_by_lead as visual_audits_by_lead
from src.storage.visual import page_audits_for_audit as visual_page_audits_for_audit

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover
    load_dotenv = None  # type: ignore


try:  # Optional (nicer table + exports)
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover
    pd = None  # type: ignore

try:  # Optional (requested by todo)
    import plotly.express as px  # type: ignore
except Exception:  # pragma: no cover
    px = None  # type: ignore


try:  # Optional (local semantic search engine, Phase 14)
    from src.search.config import from_settings as search_config_from_settings
    from src.search.query import SearchError, SearchQuery
    from src.search.search_service import SearchResult, SearchService
except Exception:  # pragma: no cover
    search_config_from_settings = None  # type: ignore
    SearchError = ValueError  # type: ignore
    SearchQuery = None  # type: ignore
    SearchResult = None  # type: ignore
    SearchService = None  # type: ignore


try:  # Optional (grounded chat assistant, Phase 15)
    from src.chat.config import from_settings as chat_config_from_settings
    from src.chat.service import ChatService
except Exception:  # pragma: no cover
    chat_config_from_settings = None  # type: ignore
    ChatService = None  # type: ignore


@dataclass(frozen=True)
class LeadRow:
    id: int
    business_name: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    website_url: Optional[str]
    platform: Optional[str]
    complexity: Optional[str]
    load_speed: Optional[str]
    city: Optional[str]
    state: Optional[str]
    category: Optional[str]
    score: Optional[int]
    priority: Optional[str]
    extraction_success: bool
    extracted_at: Optional[str]
    last_error: Optional[str]
    outreach_sent: bool
    outreach_sent_at: Optional[str]
    notes: Optional[str]


def main() -> None:
    if load_dotenv is not None:
        load_dotenv()

    st.set_page_config(page_title="Lead Finder Dashboard", layout="wide")
    st.title("Second Brain Lead Finder — Dashboard (v1)")

    db_path = DB_PATH

    _render_discover_section(db_path)

    if not db_path.exists():
        st.info("Database not initialized. Run a discovery search above to create it.")
        return

    page = st.sidebar.radio("Page", ["Leads", "AI Search", "AI Chat"], key="page_select")
    if page == "AI Search":
        _render_search_page(db_path)
        return
    if page == "AI Chat":
        _render_chat_page(db_path)
        return

    all_rows: list[LeadRow] = []
    total_db_leads = 0
    tech_by_lead: dict[int, list[dict[str, Any]]] = {}
    seo_by_lead: dict[int, dict[str, Any]] = {}
    visual_by_lead: dict[int, dict[str, Any]] = {}
    score_by_lead: dict[int, dict[str, Any]] = {}
    opp_by_lead: dict[int, list[dict[str, Any]]] = {}
    with _connect(db_path) as connection:
        init_db(connection)
        all_rows = _fetch_leads(connection)
        total_db_leads = len(all_rows)
        tech_by_lead = detections_by_lead(connection)
        seo_by_lead = seo_audits_by_lead(connection)
        visual_by_lead = visual_audits_by_lead(connection)
        score_by_lead = lead_scores_by_lead(connection)
        opp_by_lead = lead_opportunities_by_lead(connection)

    if not all_rows:
        st.info("No leads found yet. Use the discovery panel in the sidebar to find new leads.")
        return

    min_score = int(st.sidebar.slider("Min score", 0, 100, 30))
    max_rows = int(st.sidebar.number_input("Max rows", min_value=10, max_value=10_000, value=500, step=10))
    priority_filter = st.sidebar.multiselect(
        "Priority",
        options=["Hot", "Warm", "Cold", "Avoid"],
        default=["Hot", "Warm", "Cold"],
    )
    sort_by = st.sidebar.selectbox(
        "Sort by",
        options=["Final score (high to low)", "Legacy score", "Most recent"],
        index=0,
        key="scoring_sort",
    )

    tech_filter = st.sidebar.multiselect(
        "Has technology (category)",
        options=["cms", "frontend", "backend", "hosting", "analytics", "libraries", "search", "payment", "shopping"],
        format_func=lambda c: {
            "cms": "CMS",
            "frontend": "Frontend / Framework",
            "backend": "Backend",
            "hosting": "Hosting / CDN",
            "analytics": "Analytics",
            "libraries": "Libraries",
            "search": "Search",
            "payment": "Payments",
            "shopping": "Shopping / e-commerce",
        }.get(c, c),
        key="tech_category_filter",
    )

    st.sidebar.subheader("Scoring filters")
    priority_label_filter = st.sidebar.multiselect(
        "Priority label",
        options=["Hot", "Warm", "Cold", "Avoid"],
        default=[],
        key="priority_label_filter",
    )
    min_final_score = int(st.sidebar.slider("Min final score", 0, 100, 0, key="min_final_score"))

    st.sidebar.subheader("SEO filters")
    seo_health_filter = st.sidebar.multiselect(
        "SEO health",
        options=["Excellent", "Good", "Fair", "Poor", "Critical"],
        default=[],
        key="seo_health_filter",
    )
    min_seo_score = int(st.sidebar.slider("Min site SEO score", 0, 100, 0, key="min_seo_score"))

    st.sidebar.subheader("Visual filters")
    visual_health_filter = st.sidebar.multiselect(
        "Visual health",
        options=["Excellent", "Good", "Fair", "Poor", "Critical"],
        default=[],
        key="visual_health_filter",
    )
    min_visual_score = int(st.sidebar.slider("Min visual score", 0, 100, 0, key="min_visual_score"))
    visual_weak_mobile = st.sidebar.checkbox("Weak mobile layout", key="visual_weak_mobile")
    visual_clutter = st.sidebar.checkbox("Cluttered layout", key="visual_clutter")
    visual_weak_cta = st.sidebar.checkbox("Weak call-to-action", key="visual_weak_cta")
    visual_strong_brand = st.sidebar.checkbox("Strong branding", key="visual_strong_brand")

    st.sidebar.subheader("Opportunity filters")
    opp_category_filter = st.sidebar.multiselect(
        "Opportunity category",
        options=[
            "website_redesign",
            "seo_improvement",
            "performance_optimization",
            "accessibility_improvement",
            "analytics_setup",
            "security_improvement",
            "contact_funnel_improvement",
        ],
        format_func=lambda c: {
            "website_redesign": "Website Redesign",
            "seo_improvement": "SEO Improvement",
            "performance_optimization": "Performance Optimization",
            "accessibility_improvement": "Accessibility Improvement",
            "analytics_setup": "Analytics Setup",
            "security_improvement": "Security Improvement",
            "contact_funnel_improvement": "Contact Funnel Improvement",
        }.get(c, c),
        key="opp_category_filter",
    )
    min_opp_score = int(st.sidebar.slider("Min opportunity score", 0, 100, 0, key="min_opp_score"))
    opp_priority_filter = st.sidebar.multiselect(
        "Opportunity priority",
        options=[
            "High Revenue Potential",
            "Medium Revenue Potential",
            "Low Revenue Potential",
            "Minimal Opportunity",
        ],
        default=[],
        key="opp_priority_filter",
    )

    # Per-page toggles applied to the selected lead's page breakdown.
    page_missing_title = st.sidebar.checkbox("Pages missing title", key="page_missing_title")
    page_missing_meta = st.sidebar.checkbox("Pages missing meta description", key="page_missing_meta")
    page_thin = st.sidebar.checkbox("Pages with thin content", key="page_thin")
    page_noindex = st.sidebar.checkbox("Pages with noindex", key="page_noindex")
    page_missing_alt = st.sidebar.checkbox("Pages with images missing alt", key="page_missing_alt")
    page_issue_filters = {
        "missing_title": page_missing_title,
        "missing_meta": page_missing_meta,
        "thin": page_thin,
        "noindex": page_noindex,
        "missing_alt": page_missing_alt,
    }

    # Require at least one detection in a selected category.
    def _has_tech(lead_id: int, categories: list[str]) -> bool:
        if not categories:
            return True
        detections = tech_by_lead.get(lead_id, [])
        detected = {d.get("category") for d in detections}
        return bool(detected & set(categories))

    def _has_seo(lead_id: int) -> bool:
        seo = seo_by_lead.get(lead_id)
        if not seo:
            return not (seo_health_filter or min_seo_score > 0)
        if seo_health_filter and str(seo.get("overall_health")) not in set(seo_health_filter):
            return False
        if int(seo.get("site_score") or 0) < min_seo_score:
            return False
        return True

    visual_signal_flags = {
        "pages_with_weak_mobile_signal": visual_weak_mobile,
        "pages_with_clutter_signal": visual_clutter,
        "pages_with_weak_cta_signal": visual_weak_cta,
        "pages_with_strong_brand_signal": visual_strong_brand,
    }

    def _has_visual(lead_id: int) -> bool:
        visual = visual_by_lead.get(lead_id)
        if not visual:
            return not (
                visual_health_filter
                or min_visual_score > 0
                or any(visual_signal_flags.values())
            )
        if visual_health_filter and str(visual.get("visual_health_label")) not in set(visual_health_filter):
            return False
        if int(visual.get("visual_score") or 0) < min_visual_score:
            return False
        for field, flag in visual_signal_flags.items():
            if flag and int(visual.get(field) or 0) == 0:
                return False
        return True

    def _opportunity_summary(lead_id: int) -> tuple[Optional[str], int, Optional[str]]:
        opportunities = opp_by_lead.get(lead_id) or []
        top = opportunities[0] if opportunities else None
        if top is None:
            return None, 0, None
        return (
            str(top.get("label") or top.get("category") or ""),
            int(top.get("score") or 0),
            str(top.get("priority") or ""),
        )

    def _has_opportunity(lead_id: int) -> bool:
        label, top_score, priority = _opportunity_summary(lead_id)
        if opp_category_filter:
            categories = {str(o.get("category")) for o in opp_by_lead.get(lead_id, [])}
            if not categories & set(opp_category_filter):
                return False
        if min_opp_score > 0 and top_score < min_opp_score:
            return False
        if opp_priority_filter and (not priority or priority not in set(opp_priority_filter)):
            return False
        if not opp_category_filter and not opp_priority_filter and min_opp_score == 0:
            return True
        return True

    def _lead_label_and_score(lead_id: int) -> tuple[str, int]:
        score_row = score_by_lead.get(lead_id)
        if score_row:
            return (
                str(score_row.get("priority_label") or "Unknown"),
                int(score_row.get("final_score") or 0),
            )
        lead_row = next((r for r in all_rows if r.id == lead_id), None)
        return (
            str(lead_row.priority or "Unknown") if lead_row else "Unknown",
            int(lead_row.score or 0) if lead_row else 0,
        )

    filtered = [
        row
        for row in all_rows
        if (row.score is not None and row.score >= min_score)
        and (not priority_filter or (row.priority in set(priority_filter)))
        and _has_tech(row.id, tech_filter)
        and _has_seo(row.id)
        and _has_visual(row.id)
        and _has_opportunity(row.id)
    ]
    if priority_label_filter:
        filtered = [row for row in filtered if _lead_label_and_score(row.id)[0] in set(priority_label_filter)]
    if min_final_score > 0:
        filtered = [row for row in filtered if _lead_label_and_score(row.id)[1] >= min_final_score]

    if sort_by == "Most recent":
        filtered = sorted(filtered, key=lambda r: r.extracted_at or "", reverse=True)
    elif sort_by == "Legacy score":
        filtered = sorted(filtered, key=lambda r: r.score or 0, reverse=True)
    else:
        filtered = sorted(filtered, key=lambda r: _lead_label_and_score(r.id)[1], reverse=True)
    filtered = filtered[:max_rows]

    st.subheader("Metrics")
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("Leads in view", str(len(filtered)))
    col2.metric("Hot in view", str(sum(1 for r in filtered if _lead_label_and_score(r.id)[0] == "Hot")))
    col3.metric("Warm in view", str(sum(1 for r in filtered if _lead_label_and_score(r.id)[0] == "Warm")))
    col4.metric("Cold in view", str(sum(1 for r in filtered if _lead_label_and_score(r.id)[0] == "Cold")))
    avg_final = _avg([_lead_label_and_score(r.id)[1] for r in filtered])
    col5.metric("Avg final score", f"{avg_final:.1f}" if avg_final is not None else "—")
    high_opp = sum(1 for r in filtered if _opportunity_summary(r.id)[1] >= 70)
    col6.metric("High opportunity leads", str(high_opp))

    st.subheader("Score distribution")
    scores = [r.score for r in filtered if r.score is not None]
    if px is not None and scores:
        fig = px.histogram(scores, nbins=20, labels={"value": "Score"}, title="")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.bar_chart(scores)

    st.subheader("Technology overview")
    tech_counts: dict[str, int] = {}
    for detections_ in tech_by_lead.values():
        for d in detections_:
            name = str(d.get("technology_name") or "")
            if name:
                tech_counts[name] = tech_counts.get(name, 0) + 1
    if tech_counts:
        top_tech = sorted(tech_counts.items(), key=lambda kv: kv[1], reverse=True)[:10]
        cols = st.columns(min(5, len(top_tech)))
        for idx, (name, count) in enumerate(top_tech):
            cols[idx % len(cols)].metric(name, str(count))
    else:
        st.caption("No technology detections yet. Run discovery/scraping to populate.")

    st.subheader("Leads table")
    table_rows = [
        {
            "id": r.id,
            "business_name": r.business_name,
            "phone": r.phone,
            "email": r.email,
            "website_url": r.website_url,
            "score": r.score,
            "priority": r.priority,
            "final_score": _lead_label_and_score(r.id)[1],
            "priority_label": _lead_label_and_score(r.id)[0],
            "platform": r.platform,
            "technologies": ", ".join(
                str(d.get("technology_name"))
                for d in sorted(tech_by_lead.get(r.id, []), key=lambda x: -int(x.get("confidence") or 0))[:3]
            ),
            "seo_score": seo_by_lead.get(r.id, {}).get("site_score"),
            "seo_health": seo_by_lead.get(r.id, {}).get("overall_health"),
            "visual_score": visual_by_lead.get(r.id, {}).get("visual_score"),
            "visual_health": visual_by_lead.get(r.id, {}).get("visual_health_label"),
            "top_opportunity": _opportunity_summary(r.id)[0],
            "opportunity_score": _opportunity_summary(r.id)[1],
            "opportunity_priority": _opportunity_summary(r.id)[2],
            "outreach_sent": r.outreach_sent,
            "outreach_sent_at": r.outreach_sent_at,
        }
        for r in filtered
    ]

    selected_from_table: Optional[int] = None
    if pd is not None:
        df = pd.DataFrame(table_rows)
        display_cols = [
            "id",
            "business_name",
            "phone",
            "email",
            "website_url",
            "final_score",
            "priority_label",
            "score",
            "priority",
            "platform",
            "technologies",
            "seo_score",
            "seo_health",
            "visual_score",
            "visual_health",
            "top_opportunity",
            "opportunity_score",
            "opportunity_priority",
        ]
        display_df = df[[c for c in display_cols if c in df.columns]]
        event = st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
        )
        try:
            selected_rows = list(getattr(event, "selection", {}).get("rows", []))
            if selected_rows:
                row_index = int(selected_rows[0])
                selected_from_table = int(display_df.iloc[row_index]["id"])
        except Exception:
            selected_from_table = None
    else:
        st.dataframe(table_rows, use_container_width=True)

    st.subheader("Lead detail + outreach draft")
    lead_ids = [r.id for r in filtered]
    if not lead_ids:
        st.info("No leads match the current filters.")
        return

    if "selected_lead_id" not in st.session_state:
        st.session_state["selected_lead_id"] = lead_ids[0]
    if st.session_state["selected_lead_id"] not in lead_ids:
        st.session_state["selected_lead_id"] = lead_ids[0]
    if selected_from_table is not None and selected_from_table in lead_ids:
        st.session_state["selected_lead_id"] = selected_from_table

    selected_id = st.selectbox(
        "Select lead",
        options=lead_ids,
        index=lead_ids.index(int(st.session_state["selected_lead_id"])),
        format_func=lambda i: _label_for_id(filtered, i),
        key="selected_lead_id_selectbox",
    )
    st.session_state["selected_lead_id"] = selected_id
    selected = next((r for r in filtered if r.id == selected_id), None)
    if selected is None:
        st.warning("Select a lead to see details.")
        return

    left, right = st.columns([1, 1])
    with left:
        st.json(_as_dict(selected))
        if selected.last_error:
            st.warning(f"Last error: {selected.last_error}")

    with right:
        draft = _outreach_email(selected)
        st.text_area("Outreach email draft", value=draft, height=320)

        detections = tech_by_lead.get(selected.id, [])
        if detections:
            st.markdown("### Detected technologies")
            for d in sorted(detections, key=lambda x: -int(x.get("confidence") or 0)):
                percent = int(d.get("confidence") or 0)
                st.markdown(f"- **{d.get('technology_name')}** — {percent}% ({d.get('category')})")
        else:
            st.caption("No technology detections stored for this lead.")

        _render_opportunities_section(opp_by_lead.get(selected.id))

        _render_scoring_section(score_by_lead.get(selected.id))

        _render_seo_section(db_path, selected.id, seo_by_lead, page_issue_filters)

        _render_visual_section(db_path, selected.id, visual_by_lead)

        st.markdown("### Lead actions")
        sent = st.checkbox("Outreach sent", value=bool(selected.outreach_sent), key=f"sent_{selected.id}")
        notes = st.text_area("Notes", value=selected.notes or "", height=120, key=f"notes_{selected.id}")
        if st.button("Save", key=f"save_{selected.id}"):
            with _connect(db_path) as connection:
                _update_lead_actions(connection, selected.id, outreach_sent=sent, notes=notes)
            st.success("Saved.")
            st.rerun()

    st.subheader("Exports")
    exports_dir = Path("exports")
    exports_dir.mkdir(parents=True, exist_ok=True)

    if st.button("Export Current View"):
        path = exports_dir / f"dashboard_view_{_ts()}.csv"
        _write_csv(path, table_rows)
        st.success(f"Wrote {path}")

    if st.button("Export Not Contacted (Current View)"):
        path = exports_dir / f"dashboard_not_contacted_view_{_ts()}.csv"
        not_contacted = [r for r in table_rows if not bool(r.get("outreach_sent"))]
        _write_csv(path, not_contacted)
        st.success(f"Wrote {path}")

    if st.button("Export All Leads"):
        path = exports_dir / f"dashboard_all_{_ts()}.csv"
        _write_csv(path, [_as_dict(r) for r in all_rows])
        st.success(f"Wrote {path}")

    if st.button("Export Not Contacted (All Leads)"):
        path = exports_dir / f"dashboard_not_contacted_all_{_ts()}.csv"
        not_contacted_all = [_as_dict(r) for r in all_rows if not bool(r.outreach_sent)]
        _write_csv(path, not_contacted_all)
        st.success(f"Wrote {path}")


def _fetch_leads(connection: sqlite3.Connection) -> list[LeadRow]:
    rows = connection.execute(
        """
        SELECT
          id, business_name, phone, email, website_url,
          platform, complexity, load_speed,
          city, state, category,
          score, priority, extraction_success,
          extracted_at, last_error,
          outreach_sent, outreach_sent_at, notes
        FROM leads
        ORDER BY extracted_at DESC
        """
    ).fetchall()

    leads: list[LeadRow] = []
    for row in rows:
        leads.append(
            LeadRow(
                id=int(row["id"]),
                business_name=row["business_name"],
                phone=row["phone"],
                email=row["email"],
                website_url=row["website_url"],
                platform=row["platform"],
                complexity=row["complexity"],
                load_speed=row["load_speed"],
                city=row["city"],
                state=row["state"],
                category=row["category"],
                score=row["score"],
                priority=row["priority"],
                extraction_success=bool(row["extraction_success"]),
                extracted_at=row["extracted_at"],
                last_error=row["last_error"],
                outreach_sent=bool(row["outreach_sent"]),
                outreach_sent_at=row["outreach_sent_at"],
                notes=row["notes"],
            )
        )
    return leads


def _label_for_id(rows: list[LeadRow], lead_id: int) -> str:
    row = next((r for r in rows if r.id == lead_id), None)
    if row is None:
        return str(lead_id)
    name = row.business_name or "(no name)"
    score = row.score if row.score is not None else "—"
    return f"{name} — {score} ({row.priority or '—'})"


def _render_opportunities_section(opportunities: Optional[list[dict[str, Any]]]) -> None:
    st.markdown("### Business opportunities (deterministic)")
    if not opportunities:
        st.caption("No business opportunities detected for this lead.")
        return

    top = opportunities[0]
    col_score, col_label, col_impact = st.columns(3)
    col_score.metric("Top opportunity", f"{int(top.get('score') or 0)}/100")
    col_label.metric("Priority", str(top.get("priority") or "—"))
    col_impact.metric("Business impact", str(top.get("business_impact") or "—"))

    for item in opportunities:
        label = str(item.get("label") or item.get("category") or "")
        score = int(item.get("score") or 0)
        severity = str(item.get("severity") or "")
        with st.expander(
            f"{label} — {score}/100 ({severity})", expanded=item is top
        ):
            st.progress(score / 100.0, text=f"Score: {score}/100")
            impact = item.get("business_impact") or "—"
            effort = item.get("implementation_effort") or "—"
            confidence = int(item.get("confidence") or 0)
            st.write(
                f"Impact: **{impact}** · Effort: **{effort}** · "
                f"Confidence: {confidence}%"
            )
            services = item.get("recommended_services") or []
            if services:
                st.markdown("**Recommended services**")
                st.markdown(" · ".join(f"`{s}`" for s in services))
            evidence = item.get("evidence") or []
            if evidence:
                st.markdown("**Evidence**")
                for reason in evidence:
                    st.markdown(f"- {reason}")


def _render_scoring_section(score_row: Optional[dict[str, Any]]) -> None:
    st.markdown("### Lead score (deterministic)")
    if not score_row:
        st.caption("No multi-dimensional score stored for this lead.")
        return

    col_score, col_label = st.columns(2)
    col_score.metric("Final score", f"{int(score_row.get('final_score') or 0)}/100")
    col_label.metric("Priority", str(score_row.get("priority_label") or "—"))

    st.markdown("**Dimension breakdown**")
    dimension_scores: list[tuple[str, str, int]] = [
        ("Contactability", "contactability_score", int(score_row.get("contactability_score") or 0)),
        ("Technical health", "technical_health_score", int(score_row.get("technical_health_score") or 0)),
        ("SEO health", "seo_health_score", int(score_row.get("seo_health_score") or 0)),
        ("Content strength", "content_strength_score", int(score_row.get("content_strength_score") or 0)),
        ("Trust / professionalism", "trust_professionalism_score", int(score_row.get("trust_professionalism_score") or 0)),
        ("Discovery quality", "discovery_quality_score", int(score_row.get("discovery_quality_score") or 0)),
        ("Outreach potential", "outreach_potential_score", int(score_row.get("outreach_potential_score") or 0)),
        ("Visual presentation", "visual_presentation_score", int(score_row.get("visual_presentation_score") or 0)),
    ]
    for label, _, value in dimension_scores:
        st.progress(value / 100.0, text=f"{label}: {value}/100")

    st.markdown("**Why this lead is ranked here**")
    positives = score_row.get("top_positive_reasons") or []
    negatives = score_row.get("top_negative_reasons") or []
    strongest_positive = positives[0] if positives else "no positive signals"
    strongest_negative = negatives[0] if negatives else "no negative signals"
    st.write(
        f"Ranks {score_row.get('priority_label')} at {score_row.get('final_score')}/100. "
        f"Strongest positive: {strongest_positive}. Strongest negative: {strongest_negative}."
    )

    if positives:
        st.markdown("**Top positive reasons**")
        for reason in positives[:5]:
            st.markdown(f"- {reason}")
    if negatives:
        st.markdown("**Top negative reasons**")
        for reason in negatives[:5]:
            st.markdown(f"- {reason}")

    reasons_by_dimension = score_row.get("dimension_reasons") or {}
    if reasons_by_dimension:
        st.markdown("**Per-dimension explanations**")
        for dimension, reasons in reasons_by_dimension.items():
            label = dimension.replace("_", " ").title()
            with st.expander(f"{label}"):
                for reason in reasons:
                    st.markdown(f"- {reason}")

    angle = score_row.get("recommended_outreach_angle")
    if angle:
        st.markdown("**Recommended outreach angle**")
        st.info(str(angle))


def _render_seo_section(
    db_path: Path,
    lead_id: int,
    seo_by_lead: dict[int, dict[str, Any]],
    page_issue_filters: dict[str, bool],
) -> None:
    st.markdown("### SEO audit")
    seo = seo_by_lead.get(lead_id)
    if not seo:
        st.caption("No SEO audit stored for this lead.")
        return

    col_score, col_health, col_pages = st.columns(3)
    col_score.metric("Site SEO score", f"{seo.get('site_score')}/100")
    col_health.metric("Health", str(seo.get("overall_health") or "—"))
    col_pages.metric("Pages audited", str(seo.get("total_pages_audited") or 0))

    summary = seo.get("severity_summary") or []
    if summary:
        st.markdown("**Top site issues**")
        for issue in summary[:5]:
            st.markdown(f"- {issue.get('reason')}")

    connection = _connect(db_path)
    try:
        page_rows = page_audits_for_audit(connection, int(seo["id"]))
    finally:
        connection.close()
    if not page_rows:
        st.caption("No per-page audits stored.")
        return

    filtered_pages = [
        page
        for page in page_rows
        if _passes_page_filters(page, page_issue_filters)
    ]

    with st.expander(f"Page breakdown ({len(filtered_pages)} of {len(page_rows)})", expanded=True):
        display = [
            {
                "url": page.get("url"),
                "page_type": page.get("page_type"),
                "score": page.get("score"),
                "health": page.get("health"),
                "title": "yes" if page.get("title_present") else "no",
                "meta_description": "yes" if page.get("meta_description_present") else "no",
                "h1": page.get("h1_count"),
                "words": page.get("word_count"),
                "noindex": "yes" if page.get("noindex") else "",
                "issues": len(page.get("issues") or []),
            }
            for page in filtered_pages
        ]
        if pd is not None:
            st.dataframe(pd.DataFrame(display), use_container_width=True, hide_index=True)
        else:
            st.dataframe(display, use_container_width=True)

        for page in filtered_pages[:5]:
            issues = page.get("issues") or []
            if not issues:
                continue
            with st.expander(f"{page.get('url')}"):
                for issue in issues[:8]:
                    st.markdown(f"- **{issue.get('severity')}** — {issue.get('reason')}")
                    st.caption(f"Fix: {issue.get('fix')}")


def _render_visual_section(
    db_path: Path,
    lead_id: int,
    visual_by_lead: dict[int, dict[str, Any]],
) -> None:
    st.markdown("### Visual website audit")
    visual = visual_by_lead.get(lead_id)
    if not visual:
        st.caption("No visual audit stored for this lead.")
        return

    col_score, col_health, col_pages = st.columns(3)
    col_score.metric("Visual score", f"{visual.get('visual_score')}/100")
    col_health.metric("Health", str(visual.get("visual_health_label") or "—"))
    col_pages.metric("Pages audited", str(visual.get("total_pages_audited") or 0))

    summary = visual.get("summary")
    if summary:
        st.markdown("**Summary**")
        st.write(str(summary))

    connection = _connect(db_path)
    try:
        page_rows = visual_page_audits_for_audit(connection, int(visual["id"]))
    finally:
        connection.close()
    if not page_rows:
        st.caption("No per-page visual audits stored.")
        return

    issues = [issue for page in page_rows for issue in (page.get("issues") or [])]
    strengths = [strength for page in page_rows for strength in (page.get("strengths") or [])]

    if issues:
        st.markdown("**Top visual issues**")
        for issue in issues[:5]:
            st.markdown(f"- {issue}")
    else:
        st.caption("No visual issues detected.")

    if strengths:
        st.markdown("**Observed strengths**")
        for strength in strengths[:5]:
            st.markdown(f"- {strength}")

    with st.expander(f"Page breakdown ({len(page_rows)})", expanded=True):
        display = [
            {
                "url": page.get("url"),
                "page_type": page.get("page_type"),
                "visual_score": page.get("visual_score"),
                "layout": page.get("layout_quality"),
                "readability": page.get("readability_quality"),
                "branding": page.get("branding_quality"),
                "mobile": page.get("mobile_quality"),
                "conversion": page.get("conversion_quality"),
                "issues": len(page.get("issues") or []),
                "strengths": len(page.get("strengths") or []),
            }
            for page in page_rows
        ]
        if pd is not None:
            st.dataframe(pd.DataFrame(display), use_container_width=True, hide_index=True)
        else:
            st.dataframe(display, use_container_width=True)

        for page in page_rows:
            screenshot = page.get("screenshot_path") or page.get("mobile_screenshot_path")
            if not screenshot or not Path(str(screenshot)).exists():
                continue
            with st.expander(f"Screenshot: {page.get('url')}"):
                st.image(str(screenshot), use_container_width=True, caption=f"Visual score {page.get('visual_score')}/100")


def _passes_page_filters(page: dict[str, Any], filters: dict[str, bool]) -> bool:
    if filters.get("missing_title") and not page.get("title_present"):
        return True
    if filters.get("missing_meta") and not page.get("meta_description_present"):
        return True
    if filters.get("thin"):
        issues = {issue.get("code") for issue in (page.get("issues") or [])}
        if "thin_content" in issues:
            return True
    if filters.get("noindex") and page.get("noindex"):
        return True
    if filters.get("missing_alt") and int(page.get("images_missing_alt_count") or 0) > 0:
        return True
    if not any(filters.values()):
        return True
    return False


def _outreach_email(lead: LeadRow) -> str:
    name = lead.business_name or "there"
    city = ", ".join([p for p in [lead.city, lead.state] if p])
    city_line = f" in {city}" if city else ""

    signals: list[str] = []
    if not lead.email:
        signals.append("I couldn’t find a clear email address on the site")
    if lead.load_speed and str(lead.load_speed).lower() == "slow":
        signals.append("the site felt a bit slow to load")
    if lead.platform and str(lead.platform).lower() in {"wix", "weebly", "squarespace"}:
        signals.append(f"it looks like it may be built on {lead.platform}")
    if lead.complexity and str(lead.complexity).lower() == "basic":
        signals.append("the current site looks fairly minimal")

    signals_text = ""
    if signals:
        signals_text = "I took a quick look at your website and noticed " + ", ".join(signals[:2]) + ".\n\n"

    url_line = f"Website: {lead.website_url}\n\n" if lead.website_url else ""

    return (
        f"Subject: Quick website improvement idea for {lead.business_name or 'your business'}\n\n"
        f"Hi {name},\n\n"
        f"I'm a freelance web developer{city_line}. {signals_text}"
        "If you’d like, I can send a short (no-pressure) list of 2–3 improvements that can help:\n"
        "- get more calls / form submissions\n"
        "- improve speed and mobile experience\n"
        "- make the site look more modern and trustworthy\n\n"
        f"{url_line}"
        "Would you be open to a 10-minute call this week? If you reply with the best number/time, I’ll work around you.\n\n"
        "Thanks,\n"
        "— Your Name\n"
    )


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    if pd is not None:
        pd.DataFrame(rows).to_csv(path, index=False)
        return
    import csv

    fieldnames = sorted({k for row in rows for k in row.keys()})
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _as_dict(row: LeadRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "business_name": row.business_name,
        "phone": row.phone,
        "email": row.email,
        "website_url": row.website_url,
        "platform": row.platform,
        "complexity": row.complexity,
        "load_speed": row.load_speed,
        "city": row.city,
        "state": row.state,
        "category": row.category,
        "score": row.score,
        "priority": row.priority,
        "extraction_success": row.extraction_success,
        "extracted_at": row.extracted_at,
        "last_error": row.last_error,
        "outreach_sent": row.outreach_sent,
        "outreach_sent_at": row.outreach_sent_at,
        "notes": row.notes,
    }


def _avg(values: list[int]) -> Optional[float]:
    if not values:
        return None
    return float(sum(values)) / float(len(values))


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def _update_lead_actions(
    connection: sqlite3.Connection,
    lead_id: int,
    *,
    outreach_sent: bool,
    notes: str,
) -> None:
    connection.execute(
        """
        UPDATE leads
        SET
          outreach_sent = ?,
          outreach_sent_at = CASE
            WHEN ? = 1 THEN COALESCE(outreach_sent_at, datetime('now'))
            ELSE NULL
          END,
          notes = ?
        WHERE id = ?
        """,
        (
            1 if outreach_sent else 0,
            1 if outreach_sent else 0,
            (notes or "").strip() or None,
            int(lead_id),
        ),
    )
    connection.commit()


def _render_discover_section(db_path: Path) -> None:
    st.sidebar.markdown("---")
    st.sidebar.subheader("Discover New Leads")
    st.sidebar.caption("Find businesses via OpenStreetMap (free, no key) and scrape + score them.")

    provider = st.sidebar.selectbox(
        "Discovery source",
        options=["osm", "google"],
        format_func=lambda p: "OpenStreetMap (free)" if p == "osm" else "Google Places (deprecated)",
        key="disc_provider",
    )

    category = st.sidebar.text_input(
        "Business category",
        placeholder="plumber, electrician, salon...",
        key="disc_category",
    )
    location = st.sidebar.text_input(
        "Location",
        placeholder="Austin, TX",
        key="disc_location",
    )
    max_leads = st.sidebar.number_input(
        "Max leads", min_value=5, max_value=200, value=50, step=5, key="disc_max",
    )

    if st.sidebar.button("Run Discovery", type="primary", key="disc_btn"):
        if not category or not location:
            st.sidebar.error("Both category and location are required.")
            return

        if provider == "google" and not _check_google_places_key():
            st.sidebar.error(
                "GOOGLE_MAPS_API_KEY is not set. Add it to your .env file, "
                "or switch to the free OpenStreetMap source."
            )
            return

        status_placeholder = st.sidebar.status(
            f"Discovering {category} in {location}...", state="running"
        )

        try:
            status_placeholder.write(f"Querying {provider.upper()} for businesses...")
            st.session_state["disc_run_started"] = True

            from main import run_discovery_pipeline

            result = run_discovery_pipeline(
                category=category,
                location=location,
                limit=int(max_leads),
                min_score_export=30,
                provider=provider,
            )

            total = result["total"]
            ok = result["ok"]
            seeds = result["seeds"]

            if seeds == 0:
                status_placeholder.update(
                    label=f"No businesses found for '{category}' in '{location}'.",
                    state="error",
                )
                return

            status_placeholder.update(
                label=f"Discovery complete: {seeds} found, {total} processed, {ok} succeeded.",
                state="complete",
            )
            if result.get("export"):
                status_placeholder.write(f"Export saved to {result['export']}")

            st.session_state["disc_last_run"] = result
            st.rerun()
        except Exception as exc:
            status_placeholder.update(
                label=f"Discovery failed: {exc}",
                state="error",
            )

    last_run = st.session_state.get("disc_last_run")
    if last_run:
        st.sidebar.markdown("**Last discovery run**")
        st.sidebar.markdown(
            f"- {last_run['seeds']} businesses found"
            f"\n- {last_run['total']} processed"
            f"\n- {last_run['ok']} succeeded"
            f"\n- {last_run['failed']} failed"
        )


def _check_google_places_key() -> bool:
    from src.settings import GOOGLE_MAPS_API_KEY
    return bool(GOOGLE_MAPS_API_KEY)


# --- AI Search page (Phase 14, local semantic search) ------------------------


def _render_search_page(db_path: Path) -> None:
    """AI Search: natural-language queries over the local semantic index."""
    st.header("AI Search")

    if SearchService is None:
        st.info("The search engine is not available in this environment.")
        return

    try:
        config = search_config_from_settings()
    except Exception as exc:
        st.error(f"Search configuration failed: {exc}")
        return

    if not config.enabled:
        st.info("Search is disabled (SEARCH_ENABLED=0). Enable it in .env to use AI Search.")
        return

    try:
        service = SearchService(db_path, config=config)
    except Exception as exc:
        st.error(f"Could not initialize the search engine: {exc}")
        return

    _render_search_sidebar(service)

    query_text = st.text_input(
        "Search leads in plain language",
        placeholder='e.g. "restaurants with poor SEO", "plumbers using WordPress", "weak branding"',
        key="ai_query",
    )
    mode = st.radio(
        "Search mode",
        options=["hybrid", "semantic", "keyword"],
        index=0,
        horizontal=True,
        key="ai_mode",
        help="Hybrid combines semantic similarity with keyword overlap.",
    )
    search_clicked = st.button("Search", type="primary", key="ai_search_button")

    if search_clicked and query_text.strip():
        try:
            results = service.search(
                SearchQuery(text=query_text, mode=mode, top_k=20, filters=_search_filters())
            )
            st.session_state["ai_results"] = results
            st.session_state["ai_results_for"] = query_text
            st.session_state.pop("ai_similar_for", None)
        except (SearchError, ValueError) as exc:
            st.error(str(exc))
            return

    results = st.session_state.get("ai_results")
    if results is None:
        st.caption(
            "The index currently holds "
            f"**{service.count()}** leads (embedder: {service.embedder.name}). "
            "Type a query above to search."
        )
        return

    st.markdown(f"**{len(results)} results** for “{st.session_state.get('ai_results_for', '')}”")
    for result in results:
        _render_search_result_card(service, result)

    similar_for = st.session_state.get("ai_similar_for")
    if similar_for is not None:
        st.divider()
        st.subheader(f"Similar businesses to lead #{similar_for}")
        try:
            similar = service.similar(int(similar_for), top_k=10)
            if not similar:
                st.caption("No similar leads found.")
            for result in similar:
                _render_search_result_card(service, result)
        except (SearchError, ValueError) as exc:
            st.error(str(exc))


def _render_search_sidebar(service: SearchService) -> None:
    st.sidebar.subheader("AI Search filters")
    db_path = getattr(service, "_db_path", None)
    if db_path is None:
        return
    with _connect(db_path) as connection:
        distinct = {
            "category": _distinct_values(connection, "category"),
            "city": _distinct_values(connection, "city"),
            "state": _distinct_values(connection, "state"),
            "country": _distinct_values(connection, "country"),
            "platform": _distinct_values(connection, "platform"),
        }
        technologies = _distinct_technologies(connection)

    st.sidebar.multiselect("Category", distinct["category"], key="ai_f_category")
    st.sidebar.multiselect("Platform", distinct["platform"], key="ai_f_platform")
    st.sidebar.multiselect("City", distinct["city"], key="ai_f_city")
    st.sidebar.multiselect("State", distinct["state"], key="ai_f_state")
    st.sidebar.multiselect("Country", distinct["country"], key="ai_f_country")
    st.sidebar.selectbox(
        "Priority",
        options=["", "Hot", "Warm", "Cold", "Avoid"],
        format_func=lambda v: v or "Any",
        key="ai_f_priority",
    )
    st.sidebar.checkbox("Only leads with a website", key="ai_f_website")
    st.sidebar.multiselect("Has technology (name)", technologies, key="ai_f_tech")

    st.sidebar.subheader("Score ranges")
    st.sidebar.slider("SEO score", 0, 100, (0, 100), key="ai_f_seo")
    st.sidebar.slider("Lead score", 0, 100, (0, 100), key="ai_f_lead")
    st.sidebar.slider("Visual score", 0, 100, (0, 100), key="ai_f_visual")
    st.sidebar.slider("Opportunity score", 0, 100, (0, 100), key="ai_f_opp")

    st.sidebar.divider()
    st.sidebar.markdown("**Index**")
    stats = service.stats()
    st.sidebar.caption(
        f"{stats['count']} leads indexed · {stats['embedder']} · {stats['vector_store']}"
    )
    if st.sidebar.button("Rebuild index", key="ai_rebuild"):
        stats = service.rebuild_index()
        st.sidebar.success(f"Rebuilt: {stats.indexed} indexed, {stats.skipped} skipped.")
        st.rerun()


def _search_filters() -> dict[str, Any]:
    filters: dict[str, Any] = {}

    def _multi(key: str, target: str) -> None:
        selected = st.session_state.get(key) or []
        if selected:
            filters[target] = list(selected)

    _multi("ai_f_category", "category")
    _multi("ai_f_platform", "platform")
    _multi("ai_f_city", "city")
    _multi("ai_f_state", "state")
    _multi("ai_f_country", "country")

    tech = st.session_state.get("ai_f_tech") or []
    if tech:
        filters["technologies"] = list(tech)

    priority = st.session_state.get("ai_f_priority")
    if priority:
        filters["priority"] = priority

    if st.session_state.get("ai_f_website"):
        filters["website_present"] = True

    for key, target in (
        ("ai_f_seo", "seo_score"),
        ("ai_f_lead", "lead_score"),
        ("ai_f_visual", "visual_score"),
        ("ai_f_opp", "opportunity_score"),
    ):
        low, high = st.session_state.get(key) or (0, 100)
        if int(low) > 0 or int(high) < 100:
            filters[target] = {"min": int(low), "max": int(high)}
    return filters


def _render_search_result_card(service: SearchService, result: Any) -> None:
    with st.container(border=True):
        title = result.business_name or f"Lead #{result.lead_id}"
        location = ", ".join(
            [p for p in (result.city, result.state, result.country) if p]
        )
        st.markdown(f"**{title}**  ·  {result.priority or '—'} · {result.category or ''}")
        if location:
            st.caption(location)

        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Similarity", f"{result.similarity * 100:.0f}%")
        col2.metric("Lead score", _metric_value(result.lead_score))
        col3.metric("Opportunity", _metric_value(result.opportunity_score))
        col4.metric("SEO", _metric_value(result.seo_score))
        col5.metric("Visual", _metric_value(result.visual_score))

        st.caption(f"Platform: {result.platform or 'unknown'} · Rank score: {result.combined_score:.3f}")
        if result.top_reasons:
            st.markdown("**Top reasons**")
            for reason in result.top_reasons[:3]:
                st.markdown(f"- {reason}")
        if result.website_url:
            st.markdown(f"[Open website]({result.website_url})")

        col_a, col_b, col_c = st.columns(3)
        if col_a.button("Find similar businesses", key=f"ai_similar_{result.lead_id}"):
            st.session_state["ai_similar_for"] = result.lead_id
        if col_b.button("AI context", key=f"ai_context_{result.lead_id}"):
            st.session_state["ai_context_for"] = result.lead_id
        if col_c.button("Copy business name", key=f"ai_copy_{result.lead_id}"):
            st.toast(f"Copied {title}", icon="📋")

    if st.session_state.get("ai_context_for") == result.lead_id:
        context = service.context_text_for_lead(result.lead_id)
        with st.expander(f"AI context for {title}", expanded=True):
            if context:
                st.markdown(context)
            else:
                st.caption("No context available.")


def _metric_value(value: Any) -> str:
    return "—" if value is None else str(int(value))


# --- AI Chat page (Phase 15, grounded chat assistant) ------------------------


def _render_chat_page(db_path: Path) -> None:
    """AI Chat: conversational questions answered from the lead database only."""
    st.header("AI Chat")

    if ChatService is None:
        st.info("The chat assistant is not available in this environment.")
        return

    try:
        service = ChatService(db_path, config=chat_config_from_settings())
    except Exception as exc:
        st.error(f"Chat initialization failed: {exc}")
        return

    if not service.config.enabled:
        st.info("The chat assistant is disabled (CHAT_ENABLED=0). Enable it in .env to use AI Chat.")
        return

    _render_chat_sidebar(service)

    st.caption(
        "Every answer is grounded in the leads stored in the database; it never "
        "invents data. Without a local LLM (Ollama or an OpenAI-compatible "
        "endpoint) the assistant answers from retrieval summaries instead of "
        "free text."
    )

    history = st.session_state.setdefault("chat_history", [])

    if "chat_restored" not in st.session_state:
        st.session_state["chat_restored"] = True
        if "chat_session_id" not in st.session_state:
            last = service.last_session()
            if last:
                st.session_state["chat_session_id"] = last
                restored = service.load_history(last)
                if restored:
                    history.extend(restored)

    prompt = st.chat_input(
        'Ask about your leads — e.g. "restaurants with weak SEO" or '
        '"which businesses should I pitch first?"'
    )
    if prompt:
        st.session_state["chat_pending"] = prompt
        st.rerun()

    pending = st.session_state.pop("chat_pending", None)
    if pending:
        session_id = st.session_state.setdefault(
            "chat_session_id", service.new_session()
        )
        response = service.ask(
            pending,
            session_id=session_id,
            filters=_chat_filters(),
        )
        history.append({"role": "user", "content": pending})
        history.append({"role": "assistant", "content": response})
        st.rerun()

    for turn in history:
        if turn["role"] == "user":
            with st.chat_message("user"):
                st.markdown(turn["content"])
        else:
            _render_chat_turn(turn["content"])

    if not history:
        st.info(
            "No questions yet. Try e.g. **“restaurants with weak SEO”**, "
            "**“which businesses should I pitch outreach to?”**, or "
            "**“show me the top 10 most promising leads”**."
        )


def _render_chat_turn(content: Any) -> None:
    with st.chat_message("assistant"):
        mode = getattr(content, "mode", None)
        if mode is None:
            st.markdown(content)
            return
        mode_label = mode.value.replace("_", " ") if mode is not None else "answer"
        backend_name = getattr(content, "backend_name", None)
        badge = mode_label
        if backend_name:
            badge = f"{mode_label} · {backend_name}"
        st.markdown(f"`{badge}`")
        st.markdown(content.answer)

        sources = getattr(content, "sources", None) or []
        if sources:
            with st.expander(f"Sources ({len(sources)})", expanded=False):
                for source in sources:
                    _render_chat_source(source)


def _render_chat_source(source: Any) -> None:
    name = source.get("business_name") or f"Lead #{source.get('lead_id')}"
    location = ", ".join(
        part for part in (source.get("city"), source.get("state"), source.get("country")) if part
    )
    st.markdown(
        f"**[{source.get('rank')}] {name}**" + (f" — {location}" if location else "")
    )
    if source.get("category"):
        st.caption(source["category"])
    if source.get("rationale"):
        st.caption(source["rationale"])


def _render_chat_sidebar(service: Any) -> None:
    db_path = getattr(service, "_db_path", None)
    if db_path is not None:
        with _connect(db_path) as connection:
            distinct = {
                "category": _distinct_values(connection, "category"),
                "city": _distinct_values(connection, "city"),
                "state": _distinct_values(connection, "state"),
                "country": _distinct_values(connection, "country"),
                "platform": _distinct_values(connection, "platform"),
            }
            technologies = _distinct_technologies(connection)

        st.sidebar.subheader("Chat filters")
        st.sidebar.multiselect("Category", distinct["category"], key="chat_f_category")
        st.sidebar.multiselect("Platform", distinct["platform"], key="chat_f_platform")
        st.sidebar.multiselect("City", distinct["city"], key="chat_f_city")
        st.sidebar.multiselect("State", distinct["state"], key="chat_f_state")
        st.sidebar.multiselect("Country", distinct["country"], key="chat_f_country")
        st.sidebar.selectbox(
            "Priority",
            options=["", "Hot", "Warm", "Cold", "Avoid"],
            format_func=lambda v: v or "Any",
            key="chat_f_priority",
        )
        st.sidebar.checkbox("Only leads with a website", key="chat_f_website")
        st.sidebar.multiselect("Has technology (name)", technologies, key="chat_f_tech")

        st.sidebar.subheader("Score ranges")
        st.sidebar.slider("SEO score", 0, 100, (0, 100), key="chat_f_seo")
        st.sidebar.slider("Lead score", 0, 100, (0, 100), key="chat_f_lead")
        st.sidebar.slider("Visual score", 0, 100, (0, 100), key="chat_f_visual")
        st.sidebar.slider("Opportunity score", 0, 100, (0, 100), key="chat_f_opp")

        st.sidebar.divider()
        status = service.backend_status()
        st.sidebar.markdown("**Assistant**")
        st.sidebar.caption(
            f"Backend: {status['name']} · mode: {status['mode'].replace('_', ' ')}"
        )
        if st.sidebar.button("Clear conversation", key="chat_clear"):
            session_id = st.session_state.get("chat_session_id")
            if session_id:
                service.clear_session(session_id)
            st.session_state.pop("chat_history", None)
            st.session_state.pop("chat_session_id", None)
            st.session_state.pop("chat_restored", None)
            st.rerun()


def _chat_filters() -> dict[str, Any]:
    filters: dict[str, Any] = {}

    def _multi(key: str, target: str) -> None:
        selected = st.session_state.get(key) or []
        if selected:
            filters[target] = list(selected)

    _multi("chat_f_category", "category")
    _multi("chat_f_platform", "platform")
    _multi("chat_f_city", "city")
    _multi("chat_f_state", "state")
    _multi("chat_f_country", "country")

    tech = st.session_state.get("chat_f_tech") or []
    if tech:
        filters["technologies"] = list(tech)

    priority = st.session_state.get("chat_f_priority")
    if priority:
        filters["priority"] = priority

    if st.session_state.get("chat_f_website"):
        filters["website_present"] = True

    for key, target in (
        ("chat_f_seo", "seo_score"),
        ("chat_f_lead", "lead_score"),
        ("chat_f_visual", "visual_score"),
        ("chat_f_opp", "opportunity_score"),
    ):
        low, high = st.session_state.get(key) or (0, 100)
        if int(low) > 0 or int(high) < 100:
            filters[target] = {"min": int(low), "max": int(high)}
    return filters


def _distinct_values(connection: sqlite3.Connection, column: str) -> list[str]:
    rows = connection.execute(
        f"SELECT DISTINCT {column} FROM leads "
        f"WHERE {column} IS NOT NULL AND {column} != '' ORDER BY 1"
    ).fetchall()
    return [str(row[0]) for row in rows]


def _distinct_technologies(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        "SELECT DISTINCT technology_name FROM technology_detections "
        "WHERE technology_name IS NOT NULL ORDER BY 1"
    ).fetchall()
    return [str(row[0]) for row in rows]


if __name__ == "__main__":
    main()
