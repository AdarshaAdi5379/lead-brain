from __future__ import annotations

from typing import Any

from src.seo.base import SeoIssue, SiteSeoAudit

CSV_FIELDS = [
    "site_seo_score",
    "seo_health",
    "seo_issue_summary",
    "pages_with_missing_title",
    "pages_with_missing_meta_description",
    "pages_with_thin_content",
    "pages_with_duplicate_titles",
    "pages_with_images_missing_alt",
]


def to_llm_text(audit: SiteSeoAudit) -> str:
    """Concise markdown banner consumed by the LLM as neutral context.

    The LLM is never asked to detect SEO issues — it simply sees the summary
    alongside the site content and uses its own judgement.
    """
    if audit.total_pages_audited == 0:
        return "Site SEO audit: not available (no pages to audit).\n"

    lines = [
        "Site SEO audit (deterministic local checks; treat as neutral context):",
        f"- Site score: {audit.site_score}/100 ({audit.overall_health}), "
        f"{audit.total_pages_audited} page(s) audited",
        f"- Titles: {audit.pages_with_title} present, "
        f"{audit.total_pages_audited - audit.pages_with_title} missing",
        f"- Meta descriptions: {audit.pages_with_meta_description} present",
        f"- Pages with thin content: {audit.pages_with_thin_content}",
        f"- Pages with duplicate titles: {audit.pages_with_duplicate_titles}",
        f"- Images missing alt text (pages): {audit.pages_with_images_missing_alt}",
        f"- Sitemap detected: {'yes' if audit.sitemap_detected else 'no'}",
        f"- robots.txt detected: {'yes' if audit.robots_txt_detected else 'no'}",
    ]

    top = top_issues(audit, n=5)
    if top:
        lines.append("- Top issues:")
        for issue in top:
            lines.append(f"    - {issue.reason}")
    else:
        lines.append("- No significant SEO issues detected.")

    return "\n".join(lines) + "\n"


def top_issues(audit: SiteSeoAudit, n: int = 5) -> list[SeoIssue]:
    """Site-level issues first, then the worst per-page issues."""
    ranked_site = sorted(audit.severity_summary, key=lambda issue: _severity_rank(issue))
    ranked_pages = sorted(
        (issue for page in audit.pages for issue in page.issues),
        key=lambda issue: _severity_rank(issue),
    )
    merged: list[SeoIssue] = []
    seen: set[str] = set()
    for issue in ranked_site + ranked_pages:
        if issue.code in seen:
            continue
        seen.add(issue.code)
        merged.append(issue)
        if len(merged) >= n:
            break
    return merged


def summary_dict(audit: SiteSeoAudit) -> dict[str, Any]:
    """Flat site-level dict for storage/dashboard (page list kept compact)."""
    data = audit.to_dict()
    data["pages"] = [
        {
            "url": page.url,
            "page_type": page.page_type,
            "score": page.score,
            "health": page.health,
            "issue_count": len(page.issues),
            "top_issue": page.issues[0].reason if page.issues else None,
        }
        for page in audit.pages
    ]
    return data


def csv_fields(audit: SiteSeoAudit) -> dict[str, Any]:
    """Flat CSV-friendly summary for the pipeline export."""
    html_pages = max(1, audit.html_pages)
    return {
        "site_seo_score": audit.site_score,
        "seo_health": audit.overall_health,
        "seo_issue_summary": "; ".join(issue.reason for issue in top_issues(audit, n=3)),
        "pages_with_missing_title": html_pages - audit.pages_with_title,
        "pages_with_missing_meta_description": html_pages - audit.pages_with_meta_description,
        "pages_with_thin_content": audit.pages_with_thin_content,
        "pages_with_duplicate_titles": audit.pages_with_duplicate_titles,
        "pages_with_images_missing_alt": audit.pages_with_images_missing_alt,
    }


def csv_fields_from_row(row: dict[str, Any]) -> dict[str, Any]:
    """CSV summary derived from a stored seo_audits row (export-time path).

    Mirrors :func:`csv_fields` but works on the persisted row so the pipeline
    export never needs to re-run the audit.
    """
    html_pages = max(1, int(row.get("html_pages") or 0))
    summary = row.get("severity_summary") or []
    top_reasons = [
        str(issue.get("reason")) for issue in summary if isinstance(issue, dict)
    ][:3]
    return {
        "site_seo_score": int(row.get("site_score") or 0),
        "seo_health": str(row.get("overall_health") or ""),
        "seo_issue_summary": "; ".join(top_reasons),
        "pages_with_missing_title": html_pages - int(row.get("pages_with_title") or 0),
        "pages_with_missing_meta_description": html_pages
        - int(row.get("pages_with_meta_description") or 0),
        "pages_with_thin_content": int(row.get("pages_with_thin_content") or 0),
        "pages_with_duplicate_titles": int(row.get("pages_with_duplicate_titles") or 0),
        "pages_with_images_missing_alt": int(row.get("pages_with_images_missing_alt") or 0),
    }


def _severity_rank(issue: SeoIssue) -> int:
    order = {"critical": 0, "major": 1, "moderate": 2, "minor": 3, "info": 4}
    return order.get(issue.severity.value, 5)
