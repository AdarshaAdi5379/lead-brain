from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import streamlit as st

from src.settings import DB_PATH
from src.storage.db import init_db

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

    all_rows: list[LeadRow] = []
    total_db_leads = 0
    with _connect(db_path) as connection:
        init_db(connection)
        all_rows = _fetch_leads(connection)
        total_db_leads = len(all_rows)

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

    filtered = [
        row
        for row in all_rows
        if (row.score is not None and row.score >= min_score)
        and (not priority_filter or (row.priority in set(priority_filter)))
    ]
    filtered = filtered[:max_rows]

    st.subheader("Metrics")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Leads in view", str(len(filtered)))
    col2.metric("Hot in view", str(sum(1 for r in filtered if r.priority == "Hot")))
    avg_score = _avg([r.score for r in filtered if r.score is not None])
    col3.metric("Avg score (view)", f"{avg_score:.1f}" if avg_score is not None else "—")
    col4.metric("Total leads (DB)", str(total_db_leads))

    st.subheader("Score distribution")
    scores = [r.score for r in filtered if r.score is not None]
    if px is not None and scores:
        fig = px.histogram(scores, nbins=20, labels={"value": "Score"}, title="")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.bar_chart(scores)

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
            "platform": r.platform,
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
            "score",
            "priority",
            "platform",
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


if __name__ == "__main__":
    main()
