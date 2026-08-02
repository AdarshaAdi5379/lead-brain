from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Optional, Sequence
from urllib.parse import urlparse

from src.seo.base import SEVERITY_PENALTY, PageSeoAudit, Severity, SeoIssue, SiteSeoAudit, health_for_score
from src.seo.page_audit import audit_page, audit_page_from_text
from src.settings import SEO_PROBE_ROBOTS


@dataclass(frozen=True)
class WellKnownProbe:
    robots_url: str
    sitemap_url: str
    robots_txt_found: bool
    sitemap_found: bool
    sitemap_in_robots: bool


def _issue(severity: Severity, code: str, reason: str, fix: str) -> SeoIssue:
    return SeoIssue(severity=severity, code=code, reason=reason, fix=fix)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


async def probe_well_known(fetcher: Any, home_url: str) -> Optional[WellKnownProbe]:
    """Optional same-origin probe of /robots.txt and /sitemap.xml.

    Only runs when ``SEO_PROBE_ROBOTS`` is enabled; otherwise returns None and
    the audit relies purely on references inside the crawled HTML. Probes are
    strictly same-origin and bounded by the fetcher's existing caps; any
    failure is treated as 'not found' and never raises.
    """
    if not SEO_PROBE_ROBOTS:
        return None

    parsed = urlparse(home_url or "")
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    origin = f"{parsed.scheme}://{parsed.netloc}"
    robots_url = f"{origin}/robots.txt"
    sitemap_url = f"{origin}/sitemap.xml"

    async def _found(url: str) -> bool:
        try:
            result = await fetcher.fetch(url)
            return bool(result.success) and result.status is not None and result.status < 400
        except Exception:
            return False

    robots_txt_found = await _found(robots_url)
    sitemap_found = await _found(sitemap_url)

    sitemap_in_robots = False
    if robots_txt_found:
        try:
            robots_result = await fetcher.fetch(robots_url)
            robots_text = (robots_result.text or robots_result.html or "").lower()
            sitemap_in_robots = "sitemap:" in robots_text
        except Exception:
            sitemap_in_robots = False

    return WellKnownProbe(
        robots_url=robots_url,
        sitemap_url=sitemap_url,
        robots_txt_found=robots_txt_found,
        sitemap_found=sitemap_found,
        sitemap_in_robots=sitemap_in_robots,
    )


def audit_site(
    pages: Sequence[Any],
    home_url: str,
    *,
    probe: Optional[WellKnownProbe] = None,
) -> SiteSeoAudit:
    """Aggregate per-page audits into a single site-level SEO audit.

    ``pages`` may be any sequence of records exposing ``url``, ``html`` and
    ``text`` (e.g. the crawler's PageRecord), so the SEO layer stays decoupled
    from the scraping layer. Pages without retained HTML are audited
    text-only and are excluded from the HTML-derived aggregates so they are
    never falsely counted as 'missing title' etc.
    """
    home_key = (home_url or "").strip().rstrip("/")
    page_audits: list[PageSeoAudit] = []
    home_robots_reference = False
    home_sitemap_reference = False

    for page in pages:
        url = str(getattr(page, "url", "") or "")
        html = str(getattr(page, "html", "") or "")
        text = str(getattr(page, "text", "") or "")
        is_homepage = bool(url) and url.strip().rstrip("/") == home_key
        if html:
            from src.seo.parser import extract_evidence

            evidence = extract_evidence(html, url, is_homepage=is_homepage)
            audit = audit_page(evidence, is_homepage=is_homepage)
            if is_homepage:
                home_robots_reference = evidence.robots_txt_reference
                home_sitemap_reference = evidence.sitemap_reference
        else:
            audit = audit_page_from_text(url, word_count=len(text.split()))
        page_audits.append(audit)

    html_pages = [audit for audit in page_audits if audit.html_available]

    pages_with_title = sum(1 for a in html_pages if a.title_present)
    pages_with_meta_description = sum(1 for a in html_pages if a.meta_description_present)
    pages_with_h1 = sum(1 for a in html_pages if a.h1_count >= 1)
    pages_with_multiple_h1 = sum(1 for a in html_pages if a.h1_count > 1)
    pages_with_noindex = sum(1 for a in html_pages if a.noindex)
    pages_with_canonical = sum(1 for a in html_pages if a.canonical_present)
    pages_with_json_ld = sum(1 for a in html_pages if a.json_ld_present)
    pages_with_images_missing_alt = sum(1 for a in html_pages if a.images_missing_alt_count > 0)
    pages_with_thin_content = sum(1 for a in html_pages if _has_issue(a, "thin_content"))

    pages_with_duplicate_titles = _duplicate_pages(
        html_pages, key=lambda a: a.title if a.title_present else None
    )
    pages_with_duplicate_descriptions = _duplicate_pages(
        html_pages, key=lambda a: a.meta_description if a.meta_description_present else None
    )

    robots_txt_detected = home_robots_reference
    sitemap_detected = home_sitemap_reference

    if probe is not None:
        robots_txt_detected = robots_txt_detected or probe.robots_txt_found
        sitemap_detected = sitemap_detected or probe.sitemap_found or probe.sitemap_in_robots

    if not page_audits:
        return SiteSeoAudit(
            lead_url=home_url,
            site_score=100,
            overall_health=health_for_score(100),
            total_pages_audited=0,
            html_pages=0,
            pages_with_title=0,
            pages_with_meta_description=0,
            pages_with_h1=0,
            pages_with_multiple_h1=0,
            pages_with_noindex=0,
            pages_with_canonical=0,
            pages_with_json_ld=0,
            pages_with_images_missing_alt=0,
            pages_with_duplicate_titles=0,
            pages_with_duplicate_descriptions=0,
            pages_with_thin_content=0,
            robots_txt_detected=robots_txt_detected,
            sitemap_detected=sitemap_detected,
            severity_summary=(),
            pages=(),
        )

    site_issues = _site_issues(
        page_audits,
        pages_with_duplicate_titles=pages_with_duplicate_titles,
        pages_with_duplicate_descriptions=pages_with_duplicate_descriptions,
        robots_txt_detected=robots_txt_detected,
        sitemap_detected=sitemap_detected,
    )

    if page_audits:
        base_score = round(sum(a.score for a in page_audits) / len(page_audits))
    else:
        base_score = 100
    site_score = base_score - sum(SEVERITY_PENALTY[issue.severity] for issue in site_issues)
    site_score = max(0, min(100, site_score))

    ordered_issues = sorted(site_issues, key=lambda issue: -SEVERITY_PENALTY[issue.severity])

    return SiteSeoAudit(
        lead_url=home_url,
        site_score=site_score,
        overall_health=health_for_score(site_score),
        total_pages_audited=len(page_audits),
        html_pages=len(html_pages),
        pages_with_title=pages_with_title,
        pages_with_meta_description=pages_with_meta_description,
        pages_with_h1=pages_with_h1,
        pages_with_multiple_h1=pages_with_multiple_h1,
        pages_with_noindex=pages_with_noindex,
        pages_with_canonical=pages_with_canonical,
        pages_with_json_ld=pages_with_json_ld,
        pages_with_images_missing_alt=pages_with_images_missing_alt,
        pages_with_duplicate_titles=pages_with_duplicate_titles,
        pages_with_duplicate_descriptions=pages_with_duplicate_descriptions,
        pages_with_thin_content=pages_with_thin_content,
        robots_txt_detected=robots_txt_detected,
        sitemap_detected=sitemap_detected,
        severity_summary=tuple(ordered_issues),
        pages=tuple(page_audits),
    )


def _has_issue(audit: PageSeoAudit, code: str) -> bool:
    return any(issue.code == code for issue in audit.issues)


def _duplicate_pages(
    audits: list[PageSeoAudit], key
) -> int:
    groups: dict[str, list[str]] = defaultdict(list)
    for audit in audits:
        value = key(audit)
        if not value:
            continue
        groups[_normalize(value)].append(audit.url)
    duplicate_urls: set[str] = set()
    for urls in groups.values():
        if len(urls) > 1:
            duplicate_urls.update(urls)
    return len(duplicate_urls)


def _site_issues(
    page_audits: list[PageSeoAudit],
    *,
    pages_with_duplicate_titles: int,
    pages_with_duplicate_descriptions: int,
    robots_txt_detected: bool,
    sitemap_detected: bool,
) -> list[SeoIssue]:
    issues: list[SeoIssue] = []

    if pages_with_duplicate_titles > 0:
        issues.append(
            _issue(
                Severity.MAJOR,
                "duplicate_titles",
                f"{pages_with_duplicate_titles} page(s) share duplicate title tags",
                "Give every page a unique, descriptive title.",
            )
        )

    if pages_with_duplicate_descriptions > 0:
        issues.append(
            _issue(
                Severity.MODERATE,
                "duplicate_descriptions",
                f"{pages_with_duplicate_descriptions} page(s) share duplicate meta descriptions",
                "Write a unique meta description for every page.",
            )
        )

    page_types = {audit.page_type for audit in page_audits if audit.page_type}
    if "contact" not in page_types:
        issues.append(
            _issue(
                Severity.MODERATE,
                "no_contact_page",
                "No contact page found in the crawl",
                "Make sure the contact details page is linked from the navigation.",
            )
        )
    if "about" not in page_types:
        issues.append(
            _issue(
                Severity.MINOR,
                "no_about_page",
                "No about page found in the crawl",
                "Add an about page describing the business.",
            )
        )
    if "services" not in page_types:
        issues.append(
            _issue(
                Severity.MINOR,
                "no_services_page",
                "No services page found in the crawl",
                "Add a services page listing what the business offers.",
            )
        )

    if not sitemap_detected:
        issues.append(
            _issue(
                Severity.MINOR,
                "no_sitemap",
                "No XML sitemap detected for this site",
                "Add a sitemap.xml and reference it from robots.txt.",
            )
        )

    if not robots_txt_detected:
        issues.append(
            _issue(
                Severity.MINOR,
                "no_robots_txt",
                "No robots.txt detected for this site",
                "Add a robots.txt controlling crawler access.",
            )
        )

    return issues
