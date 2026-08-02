from __future__ import annotations

from src.seo.base import PageEvidence, PageSeoAudit, Severity, SeoIssue, health_for_score
from src.seo.rules import page_issues


def audit_page(
    evidence: PageEvidence,
    *,
    is_homepage: bool = False,
) -> PageSeoAudit:
    """Run the deterministic per-page audit over extracted evidence."""
    issues, score = page_issues(evidence, is_homepage=is_homepage)
    robots_lower = evidence.robots_meta.lower()

    return PageSeoAudit(
        url=evidence.url,
        page_type=evidence.page_type,
        html_available=True,
        title=evidence.title,
        meta_description=evidence.meta_description,
        title_present=bool(evidence.title),
        title_length=len(evidence.title),
        meta_description_present=bool(evidence.meta_description),
        meta_description_length=len(evidence.meta_description),
        h1_count=evidence.h1_count,
        h2_count=evidence.h2_count,
        canonical_present=bool(evidence.canonical_url),
        robots_meta=bool(evidence.robots_meta),
        viewport_present=evidence.viewport_present,
        noindex="noindex" in robots_lower,
        nofollow="nofollow" in robots_lower,
        word_count=evidence.word_count,
        image_count=evidence.image_count,
        images_missing_alt_count=evidence.images_missing_alt_count,
        json_ld_present=evidence.json_ld_present,
        schema_present=evidence.schema_present,
        og_title_present=evidence.og_title_present,
        og_description_present=evidence.og_description_present,
        twitter_card_present=evidence.twitter_card_present,
        internal_link_count=evidence.internal_link_count,
        issues=tuple(issues),
        score=score,
        health=health_for_score(score),
    )


def audit_page_from_text(url: str, word_count: int) -> PageSeoAudit:
    """Minimal audit for pages whose HTML was not retained (legacy cache).

    HTML-derived signals are reported as unknown (False/0) but are excluded
    from the site-level aggregates, so a missing title is never falsely
    counted for a page we simply have no HTML for.
    """
    issue = SeoIssue(
        severity=Severity.INFO,
        code="html_not_retained",
        reason="Page HTML was not retained (served from cache); only text signals audited",
        fix="Re-crawl the page with the HTML cache enabled for a full audit.",
    )
    return PageSeoAudit(
        url=url,
        page_type=None,
        html_available=False,
        title="",
        meta_description="",
        title_present=False,
        title_length=0,
        meta_description_present=False,
        meta_description_length=0,
        h1_count=0,
        h2_count=0,
        canonical_present=False,
        robots_meta=False,
        viewport_present=False,
        noindex=False,
        nofollow=False,
        word_count=max(0, int(word_count)),
        image_count=0,
        images_missing_alt_count=0,
        json_ld_present=False,
        schema_present=False,
        og_title_present=False,
        og_description_present=False,
        twitter_card_present=False,
        internal_link_count=0,
        issues=(issue,),
        score=100,
        health=health_for_score(100),
    )
