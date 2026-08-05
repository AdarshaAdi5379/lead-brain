"""Synthetic fixtures for the local semantic search tests (no network, no LLM).

Provides a small, fast ``SearchConfig`` (hash embedder, 128 dims) and a
temp-DB helper that inserts rich leads (SEO + visual + scoring + opportunities
+ technology detections) the way the pipeline's storage layer would.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Optional

from src.search.config import SearchConfig
from src.search.embedding import HashingEmbedder
from src.storage.db import connect, init_db
from src.storage.leads import LeadUpsert, upsert_lead
from src.storage.normalization import normalize_url_for_dedupe
from src.storage.runs import start_run
from src.storage.technologies import get_lead_id_by_url


def test_config(**overrides: Any) -> SearchConfig:
    """Small, fast config: deterministic hash embedder, 128 dims."""
    base: dict[str, Any] = {
        "enabled": True,
        "embedder": "hash",
        "hash_dimensions": 512,
        "batch_size": 8,
        "hybrid_weight": 0.5,
        "default_top_k": 20,
        "rank_weight_similarity": 0.5,
        "rank_weight_lead": 0.25,
        "rank_weight_opportunity": 0.15,
        "rank_weight_recency": 0.10,
    }
    base.update(overrides)
    return SearchConfig(**base)


def test_embedder() -> HashingEmbedder:
    return HashingEmbedder(dimensions=512)


class SearchTestDb:
    """A temp SQLite DB with the full schema and rich-lead helpers."""

    def __init__(self) -> None:
        self.path = Path(tempfile.mktemp(suffix=".sqlite"))
        self.connection = connect(self.path)
        init_db(self.connection)
        self.run_id = start_run(self.connection)

    def close(self) -> None:
        self.connection.close()
        if self.path.exists():
            self.path.unlink()

    def add_lead(
        self,
        *,
        name: str,
        website: Optional[str] = None,
        category: str = "Restaurant",
        city: str = "Austin",
        state: str = "TX",
        country: str = "US",
        platform: Optional[str] = None,
        priority: Optional[str] = None,
        score: Optional[int] = None,
        extraction_success: bool = True,
        extracted_at: Optional[str] = None,
        run_id: Optional[int] = None,
    ) -> int:
        """Insert a lead row via the normal upsert path; returns its id."""
        upsert_lead(
            self.connection,
            LeadUpsert(
                website_url=website,
                business_name=name,
                platform=platform,
                city=city,
                state=state,
                category=category,
                country=country,
                score=score,
                priority=priority,
                extraction_success=extraction_success,
                run_id=run_id if run_id is not None else self.run_id,
                source="test",
            ),
        )
        if website:
            lead_id = get_lead_id_by_url(
                self.connection, normalize_url_for_dedupe(website)
            )
        else:
            row = self.connection.execute(
                "SELECT id FROM leads WHERE business_name = ? ORDER BY id DESC LIMIT 1",
                (name,),
            ).fetchone()
            lead_id = int(row["id"]) if row else None
        assert lead_id is not None
        if extracted_at:
            self.connection.execute(
                "UPDATE leads SET extracted_at = ? WHERE id = ?", (extracted_at, lead_id)
            )
            self.connection.commit()
        return lead_id

    def add_detection(self, lead_id: int, technology: str, category: str = "cms") -> None:
        self.connection.execute(
            "INSERT INTO technology_detections (lead_id, technology_name, category, confidence, evidence)"
            " VALUES (?, ?, ?, 90, '[]')",
            (lead_id, technology, category),
        )
        self.connection.commit()

    def add_seo(
        self,
        lead_id: int,
        site_score: int = 40,
        overall_health: str = "poor",
        severity: Optional[list[str]] = None,
    ) -> None:
        self.connection.execute(
            "INSERT INTO seo_audits (lead_id, site_score, overall_health, severity_summary)"
            " VALUES (?, ?, ?, ?)",
            (lead_id, site_score, overall_health, json.dumps(
                [{"code": "thin_content", "reason": reason} for reason in (severity or [])]
            )),
        )
        self.connection.commit()

    def add_visual(
        self,
        lead_id: int,
        visual_score: int = 45,
        label: str = "needs_work",
        summary: str = "Cluttered layout and weak mobile design.",
    ) -> None:
        self.connection.execute(
            "INSERT INTO visual_audits (lead_id, visual_score, visual_health_label, summary)"
            " VALUES (?, ?, ?, ?)",
            (lead_id, visual_score, label, summary),
        )
        self.connection.commit()

    def add_score(
        self,
        lead_id: int,
        final_score: int = 62,
        priority_label: str = "Warm",
        positive: Optional[list[str]] = None,
        negative: Optional[list[str]] = None,
        angle: str = "Offer a modern website redesign.",
    ) -> None:
        self.connection.execute(
            "INSERT INTO lead_scores (lead_id, final_score, priority_label,"
            " top_positive_reasons_json, top_negative_reasons_json, recommended_outreach_angle)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                lead_id, final_score, priority_label,
                json.dumps(positive or ["Responsive website detected"]),
                json.dumps(negative or ["Outdated WordPress site"]),
                angle,
            ),
        )
        self.connection.commit()

    def add_opportunity(
        self,
        lead_id: int,
        label: str = "Website redesign",
        score: int = 80,
        evidence: Optional[list[str]] = None,
    ) -> None:
        self.connection.execute(
            "INSERT INTO business_opportunities (lead_id, category, label, score, severity, evidence_json)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (lead_id, "website", label, score, "medium", json.dumps(evidence or ["Outdated design"])),
        )
        self.connection.commit()

    def add_contact(
        self,
        lead_id: int,
        *,
        owner_name: Optional[str] = None,
        address: Optional[str] = None,
        postal_code: Optional[str] = None,
        country: Optional[str] = None,
        opening_hours: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        facebook_url: Optional[str] = None,
        instagram_url: Optional[str] = None,
        linkedin_url: Optional[str] = None,
        twitter_url: Optional[str] = None,
        youtube_url: Optional[str] = None,
        whatsapp_url: Optional[str] = None,
        contact_page_url: Optional[str] = None,
        contact_form_url: Optional[str] = None,
        google_maps_url: Optional[str] = None,
        service_areas: Optional[list[str]] = None,
    ) -> None:
        """Stamp the contact-intelligence columns on a lead row."""
        values = {
            "owner_name": owner_name,
            "address": address,
            "postal_code": postal_code,
            "country": country,
            "opening_hours": opening_hours,
            "phone": phone,
            "email": email,
            "facebook_url": facebook_url,
            "instagram_url": instagram_url,
            "linkedin_url": linkedin_url,
            "twitter_url": twitter_url,
            "youtube_url": youtube_url,
            "whatsapp_url": whatsapp_url,
            "contact_page_url": contact_page_url,
            "contact_form_url": contact_form_url,
            "google_maps_url": google_maps_url,
            "service_areas_json": (
                json.dumps(service_areas) if service_areas is not None else None
            ),
        }
        sets = ", ".join(f"{name} = ?" for name in values)
        self.connection.execute(
            f"UPDATE leads SET {sets} WHERE id = ?", (*values.values(), lead_id)
        )
        self.connection.commit()
