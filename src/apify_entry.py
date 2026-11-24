from __future__ import annotations

import asyncio
from typing import Any, Optional

from apify import Actor

from src import settings as settings_module
from src.contact import ContactSignals, extract_contact_signals_from_crawl
from src.contact.extractor import extract_contact_signals_from_fetch
from src.contact.helpers import google_maps_url as build_google_maps_url
from src.discovery.discovery import discover_to_seeds
from src.discovery.models import DiscoveryQuery
from src.fingerprinting.base import PLATFORM_FROM_TECHNOLOGY, Detection
from src.fingerprinting.detector import (
    FingerprintResult,
    TechnologyDetector,
    build_site_evidence,
)
from src.opportunities import OpportunityReport, detect_opportunities
from src.scoring import LeadScore, ScoringInputs, score_site_lead
from src.scraping.browser_fetch import PlaywrightFetcher
from src.scraping.focused_crawler import CrawlResult, FocusedCrawler
from src.seo.base import SiteSeoAudit
from src.seo.report import top_issues
from src.seo.site_audit import audit_site
from src.settings import (
    FINGERPRINT_MIN_CONFIDENCE,
    FINGERPRINT_MIN_OVERRIDE_CONFIDENCE,
)
from src.url_loader import SeedRow
from src.visual import run_visual_audit
from src.visual.base import VisualAuditReport
from src.visual.config import from_settings as visual_config_from_settings


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}

        max_results = _int(actor_input.get("maxResults"), 20, 1, 100)
        max_pages = _int(actor_input.get("maxPagesPerSite"), 3, 1, 5)
        min_score = _int(actor_input.get("minScore"), 0, 0, 100)
        include_no_website = bool(actor_input.get("includeNoWebsite", True))
        require_contact = bool(actor_input.get("requireContact", True))

        urls = [u.strip() for u in (actor_input.get("urls") or []) if u and str(u).strip()]
        category = (actor_input.get("category") or "").strip()
        location = (actor_input.get("location") or "").strip()

        seeds = _build_seeds(
            urls,
            category,
            location,
            max_results,
            include_no_website=include_no_website,
            require_contact=require_contact,
        )
        if not seeds:
            Actor.log.warning(
                "No seeds: provide either a 'urls' list or a 'category' + 'location'."
            )
            await Actor.set_value(
                "SUMMARY",
                {"scanned": 0, "qualified": 0, "error": "no seeds provided"},
            )
            return

        Actor.log.info(
            "Processing %d seed(s) (max_pages=%d, min_score=%d, include_no_website=%s, require_contact=%s)",
            len(seeds),
            max_pages,
            min_score,
            include_no_website,
            require_contact,
        )

        crawler = FocusedCrawler(max_pages=max_pages)
        pushed = 0
        by_priority: dict[str, int] = {}
        score_total = 0

        async with PlaywrightFetcher() as fetcher:
            for index, seed in enumerate(seeds, start=1):
                try:
                    item = await _process_seed(
                        fetcher, crawler, seed, include_no_website=include_no_website
                    )
                except Exception as exc:  # one bad site never stops the run
                    Actor.log.warning("Seed %s failed: %s", seed.url or seed.business_name, exc)
                    continue

                if item is None:
                    continue

                if require_contact and not _has_contact(item):
                    Actor.log.info(
                        "Skipping %s: no contact channels found and requireContact is enabled",
                        item.get("business_name") or item.get("website_url"),
                    )
                    continue

                score_total += int(item["lead_score"])
                by_priority[item["priority"]] = by_priority.get(item["priority"], 0) + 1

                if int(item["lead_score"]) >= min_score:
                    await Actor.push_data(item)
                    pushed += 1

                if index % 5 == 0:
                    Actor.log.info("Progress: %d/%d scanned, %d pushed", index, len(seeds), pushed)

        summary = {
            "scanned": len(seeds),
            "qualified": pushed,
            "avg_score": round(score_total / pushed, 1) if pushed else 0,
            "by_priority": by_priority,
            "input_mode": "urls" if urls else "discovery",
            "require_contact": require_contact,
        }
        await Actor.set_value("SUMMARY", summary)
        Actor.log.info("Done. %s", summary)


def _build_seeds(
    urls: list[str],
    category: str,
    location: str,
    max_results: int,
    *,
    include_no_website: bool = True,
    require_contact: bool = True,
) -> list[SeedRow]:
    if urls:
        city = location.split(",")[0].strip() if location else ""
        state = location.split(",")[1].strip() if "," in location else ""
        return [
            SeedRow(
                business_name="",
                category=category,
                url=url,
                city=city,
                state=state,
            )
            for url in urls[:max_results]
        ]
    if category and location:
        # If the user disabled website-less leads or requires contact details, discover
        # a wider pool to find enough qualified candidates to fulfill max_results.
        query_limit = (
            max(max_results * 5, 50)
            if (not include_no_website or require_contact)
            else max(max_results * 2, 20)
        )
        raw_seeds = discover_to_seeds(
            [DiscoveryQuery(category=category, location=location)],
            provider="osm",
            limit=query_limit,
        )
        filtered = raw_seeds
        if require_contact:
            # Website-less leads will not be crawled, so they MUST have phone or email from discovery.
            # Leads with website URLs will be crawled for contact info.
            filtered = [s for s in filtered if bool(s.url or s.phone or s.email)]
        if not include_no_website:
            filtered = [s for s in filtered if s.url]
        return filtered[:max_results]
    return []


async def _process_seed(
    fetcher: PlaywrightFetcher,
    crawler: FocusedCrawler,
    seed: SeedRow,
    *,
    include_no_website: bool,
) -> Optional[dict[str, Any]]:
    fetch = None
    crawl: Optional[CrawlResult] = None
    fingerprint: Optional[FingerprintResult] = None
    seo_audit: Optional[SiteSeoAudit] = None
    visual_audit: Optional[VisualAuditReport] = None
    visual_config = visual_config_from_settings(settings_module)

    if seed.url and not getattr(seed, "url_error", None):
        fetch = await fetcher.fetch(seed.url)
        if fetch.success:
            try:
                fingerprint = _fingerprint(fetch)
            except Exception as exc:
                Actor.log.debug("Fingerprint failed for %s: %s", seed.url, exc)
            try:
                crawl = await crawler.crawl(fetcher, seed.url, home_fetch=fetch)
            except Exception as exc:
                Actor.log.debug("Crawl failed for %s: %s", seed.url, exc)
            try:
                seo_audit = _audit(seed, fetch, crawl)
            except Exception as exc:
                Actor.log.debug("SEO audit failed for %s: %s", seed.url, exc)
            try:
                if visual_config.enabled:
                    visual_audit = await run_visual_audit(
                        fetcher,
                        seed.url,
                        _crawl_summary(crawl),
                        (
                            [d.to_dict() for d in fingerprint.detections]
                            if fingerprint and fingerprint.detections
                            else []
                        ),
                        visual_config,
                        page_context=_visual_page_context(seed, crawl, seo_audit),
                    )
            except Exception as exc:
                Actor.log.debug("Visual audit failed for %s: %s", seed.url, exc)
        else:
            Actor.log.info(
                "Website fetch failed for %s (%s); evaluating for broken-site recovery",
                seed.url,
                fetch.error,
            )
    elif not include_no_website:
        return None

    contact = _contact(seed, fetch, crawl)
    platform = _platform(fingerprint)

    extracted = {
        "business_name": seed.business_name or None,
        "phone": contact.phone or seed.phone,
        "email": contact.email or seed.email,
        "platform": platform or "unknown",
        "complexity": "unknown",
        "load_speed": "unknown",
        "extraction_success": bool(fetch and fetch.success),
        "last_error": getattr(fetch, "error", None) if fetch and not fetch.success else None,
    }

    signals = ScoringInputs(
        extracted=extracted,
        business_name=seed.business_name or None,
        category=seed.category or None,
        city=seed.city or None,
        state=seed.state or None,
        address=(contact.address or seed.address) or None,
        source=seed.source or None,
        osm_id=seed.osm_id or None,
        website_url=seed.url or None,
        fetch_ok=bool(fetch and fetch.success),
        last_error=getattr(fetch, "error", None) if fetch and not fetch.success else None,
        detections=(
            [d.to_dict() for d in fingerprint.detections]
            if fingerprint and fingerprint.detections
            else None
        ),
        crawl=_crawl_summary(crawl),
        seo_audit=seo_audit.to_dict() if seo_audit is not None else None,
        visual_audit=visual_audit.to_dict() if visual_audit is not None else None,
    )

    lead_score = score_site_lead(signals)

    opportunity_report: Optional[OpportunityReport] = None
    try:
        opportunity_report = detect_opportunities(signals, lead_score=lead_score)
    except Exception as exc:
        Actor.log.debug("Opportunity detection failed for %s: %s", seed.url, exc)

    return _build_item(
        seed=seed,
        lead_score=lead_score,
        opportunity_report=opportunity_report,
        seo_audit=seo_audit,
        visual_audit=visual_audit,
        contact=contact,
        fingerprint=fingerprint,
        platform=platform,
        fetch=fetch,
    )


def _build_item(
    *,
    seed: SeedRow,
    lead_score: LeadScore,
    opportunity_report: Optional[OpportunityReport],
    seo_audit: Optional[SiteSeoAudit],
    visual_audit: Optional[VisualAuditReport],
    contact: ContactSignals,
    fingerprint: Optional[FingerprintResult],
    platform: Optional[str],
    fetch: Any = None,
) -> dict[str, Any]:
    technologies = []
    if fingerprint is not None:
        for detection in sorted(fingerprint.detections, key=lambda d: -d.confidence):
            technologies.append(
                {
                    "name": detection.name,
                    "category": detection.category,
                    "confidence": detection.confidence,
                }
            )

    services: list[str] = []
    opportunities: list[dict[str, Any]] = []
    if opportunity_report is not None:
        top_opps = sorted(opportunity_report.opportunities, key=lambda o: -o.score)[:5]
        for opportunity in top_opps:
            opportunities.append(opportunity.to_dict())
            services.extend(opportunity.recommended_services)
    services = sorted(set(services))[:8]

    top_opp = (
        opportunity_report.top_opportunity
        if opportunity_report is not None and opportunity_report.top_opportunity
        else ""
    )
    opp_count = (
        opportunity_report.opportunity_count if opportunity_report is not None else 0
    )

    # If lead has no website, surface the primary "New Website Build" opportunity
    # instead of empty blanks so user has clear, actionable audit recommendations.
    if not seed.url:
        if not top_opp:
            top_opp = "New Website Build"
        if not opportunities:
            opp_count = 1
            opportunities = [
                {
                    "category": "new_website_build",
                    "label": "New Website Build",
                    "score": 85,
                    "severity": "High",
                    "confidence": 90,
                    "evidence": [
                        "No website found for this business",
                        f"Active business in '{seed.category or 'local'}' with no online presence",
                    ],
                    "business_impact": "Very High",
                    "implementation_effort": "Medium",
                    "recommended_services": [
                        "Custom Starter Website",
                        "Mobile-Responsive Design",
                        "Domain & Hosting Setup",
                        "Google Business Profile Setup",
                        "Local SEO Setup",
                    ],
                }
            ]
        if not services:
            services = [
                "Custom Starter Website",
                "Domain & Hosting Setup",
                "Google Business Profile Setup",
                "Local SEO Setup",
                "Mobile-Responsive Design",
            ]
    elif fetch is not None and not getattr(fetch, "success", False):
        err_msg = str(getattr(fetch, "error", "") or "Unreachable")
        recovery_opp = {
            "category": "website_recovery",
            "label": "Website Recovery & Redesign",
            "score": 95,
            "severity": "Critical",
            "confidence": 95,
            "evidence": [
                f"Website is currently unreachable or broken: {err_msg}",
                "Active business with a broken website link losing visitor traffic",
            ],
            "business_impact": "Very High",
            "implementation_effort": "Medium",
            "recommended_services": [
                "Website Troubleshooting & Recovery",
                "Modern Website Rebuild",
                "Hosting Migration & SSL Setup",
            ],
        }
        # Prepend recovery opportunity so it takes top priority
        opportunities = [recovery_opp] + [o for o in opportunities if o.get("category") != "website_recovery"]
        top_opp = "Website Recovery & Redesign"
        opp_count = len(opportunities)
        services = sorted(set(services + recovery_opp["recommended_services"]))[:8]

    maps_url = contact.google_maps_url or build_google_maps_url(
        seed.latitude, seed.longitude
    )

    visual_issues = []
    if visual_audit is not None:
        for signal_name, count in [
            ("weak_mobile", visual_audit.pages_with_weak_mobile_signal),
            ("clutter", visual_audit.pages_with_clutter_signal),
            ("weak_cta", visual_audit.pages_with_weak_cta_signal),
            ("weak_hierarchy", visual_audit.pages_with_weak_hierarchy_signal),
        ]:
            if count > 0:
                visual_issues.append(signal_name)

    phone_val = contact.phone or seed.phone or None
    phone_source_val = contact.phone_source or (
        "osm" if seed.phone and seed.osm_id else ("seed" if seed.phone else None)
    )
    email_val = contact.email or seed.email or None
    email_source_val = contact.email_source or (
        "osm" if seed.email and seed.osm_id else ("seed" if seed.email else None)
    )

    socials = {
        "facebook": contact.facebook_url,
        "instagram": contact.instagram_url,
        "linkedin": contact.linkedin_url,
        "twitter": contact.twitter_url,
        "youtube": contact.youtube_url,
        "whatsapp": contact.whatsapp_url,
    }

    contact_methods: list[str] = []
    if phone_val:
        contact_methods.append("phone")
    if email_val:
        contact_methods.append("email")
    for net, net_url in socials.items():
        if net_url:
            contact_methods.append(net)
    if contact.contact_form_url:
        contact_methods.append("contact_form")
    elif contact.contact_page_url:
        contact_methods.append("contact_page")

    has_contact = len(contact_methods) > 0

    return {
        "business_name": seed.business_name or None,
        "category": seed.category or None,
        "city": seed.city or None,
        "state": seed.state or None,
        "country": contact.country or seed.country or None,
        "address": contact.address or seed.address or None,
        "postal_code": contact.postal_code or seed.postal_code or None,
        "website_url": seed.url or None,
        "has_website": bool(seed.url),
        "phone": phone_val,
        "phone_source": phone_source_val,
        "email": email_val,
        "email_source": email_source_val,
        "socials": socials,
        "contact_page_url": contact.contact_page_url or None,
        "contact_form_url": contact.contact_form_url or None,
        "has_contact": has_contact,
        "contact_methods": contact_methods,
        "opening_hours": contact.opening_hours or seed.opening_hours or None,
        "service_areas": list(contact.service_areas),
        "google_maps_url": maps_url,
        "platform": platform or "unknown",
        "technologies": technologies,
        "seo_score": seo_audit.site_score if seo_audit is not None else None,
        "seo_health": seo_audit.overall_health if seo_audit is not None else None,
        "top_seo_issues": (
            [
                {"code": issue.code, "severity": issue.severity.value, "reason": issue.reason}
                for issue in top_issues(seo_audit, n=5)
            ]
            if seo_audit is not None
            else []
        ),
        "visual_score": visual_audit.visual_score if visual_audit is not None else None,
        "visual_health": visual_audit.visual_health_label if visual_audit is not None else None,
        "visual_summary": visual_audit.summary if visual_audit is not None else None,
        "visual_issues": visual_issues,
        "lead_score": lead_score.final_score,
        "priority": lead_score.priority_label,
        "dimension_scores": lead_score.dimension_scores,
        "top_opportunity": top_opp or None,
        "opportunity_count": opp_count,
        "opportunities": opportunities,
        "recommended_services": services,
        "pitch_angle": lead_score.recommended_outreach_angle,
        "top_positive_reasons": lead_score.top_positive_reasons,
        "top_negative_reasons": lead_score.top_negative_reasons,
        "source": seed.source or ("osm" if seed.osm_id else "manual"),
        "osm_id": seed.osm_id,
    }


def _contact(
    seed: SeedRow, fetch: Any, crawl: Optional[CrawlResult]
) -> ContactSignals:
    try:
        if crawl is not None and crawl.ok:
            return extract_contact_signals_from_crawl(crawl, website_url=seed.url)
        if fetch is not None and getattr(fetch, "success", False):
            return extract_contact_signals_from_fetch(fetch)
    except Exception as exc:
        Actor.log.debug("Contact extraction failed for %s: %s", seed.url, exc)
    return ContactSignals()


def _fingerprint(fetch: Any) -> FingerprintResult:
    evidence = build_site_evidence(
        html=fetch.html,
        headers=fetch.headers or None,
        cookies=fetch.cookies or None,
    )
    return TechnologyDetector(min_confidence=FINGERPRINT_MIN_CONFIDENCE).detect(
        evidence, site_url=fetch.final_url or fetch.url
    )


def _platform(fingerprint: Optional[FingerprintResult]) -> Optional[str]:
    if fingerprint is None:
        return None
    best: Optional[str] = None
    best_conf = 0
    for detection in fingerprint.detections:
        mapped = PLATFORM_FROM_TECHNOLOGY.get(detection.name)
        if mapped and detection.confidence > best_conf:
            best, best_conf = mapped, detection.confidence
    if best_conf >= FINGERPRINT_MIN_OVERRIDE_CONFIDENCE:
        return best
    return None


def _audit(seed: SeedRow, fetch: Any, crawl: Optional[CrawlResult]) -> Optional[SiteSeoAudit]:
    if crawl is not None and crawl.ok and crawl.pages:
        return audit_site(crawl.pages, crawl.url)
    if fetch.success and (fetch.html or "").strip():
        from types import SimpleNamespace

        home = SimpleNamespace(
            url=fetch.final_url or fetch.url,
            label="HOME",
            title="",
            text=fetch.text or "",
            html=fetch.html or "",
        )
        return audit_site([home], home.url)
    return None


def _visual_page_context(
    seed: SeedRow,
    crawl: Optional[CrawlResult],
    seo_audit: Optional[SiteSeoAudit],
) -> dict[str, dict]:
    context: dict[str, dict] = {}
    if seo_audit is not None and getattr(seo_audit, "pages", None):
        for page in seo_audit.pages:
            context[page.url] = {
                "word_count": int(getattr(page, "word_count", 0) or 0),
                "image_count": int(getattr(page, "image_count", 0) or 0),
            }
    return context


def _crawl_summary(crawl: Optional[CrawlResult]) -> Optional[dict[str, Any]]:
    if crawl is None:
        return None
    return {
        "ok": bool(crawl.ok),
        "error": crawl.error,
        "merged_text": crawl.merged_text,
        "contact_clues": list(crawl.contact_clues),
        "social_urls": list(crawl.contact_signals.social_urls),
        "pages": [
            {"url": page.url, "label": page.label, "title": page.title, "text": page.text}
            for page in crawl.pages
        ],
    }


def _get_contact_methods(item: dict[str, Any]) -> list[str]:
    methods: list[str] = []
    if item.get("phone"):
        methods.append("phone")
    if item.get("email"):
        methods.append("email")
    socials = item.get("socials") or {}
    for network, url in socials.items():
        if url:
            methods.append(network)
    if item.get("contact_form_url"):
        methods.append("contact_form")
    elif item.get("contact_page_url"):
        methods.append("contact_page")
    return methods


def _has_contact(item: dict[str, Any]) -> bool:
    if item.get("has_contact") is not None:
        return bool(item.get("has_contact"))
    return len(_get_contact_methods(item)) > 0


def _int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


if __name__ == "__main__":
    asyncio.run(main())
