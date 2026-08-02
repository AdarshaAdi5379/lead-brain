from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse

from src.seo.base import SEVERITY_PENALTY, PageEvidence, Severity, SeoIssue

# Title length bands (characters).
TITLE_MIN_LENGTH = 30
TITLE_MAX_LENGTH = 60
# Meta description length bands (characters).
DESCRIPTION_MIN_LENGTH = 120
DESCRIPTION_MAX_LENGTH = 160
# A page with fewer words is treated as thin content.
THIN_CONTENT_WORDS = 300
# The homepage gets a stricter bar because it is the primary landing page.
HOMEPAGE_THIN_CONTENT_WORDS = 150
# Penalty once this share of images is missing alt text (and at the worse band).
ALT_MISSING_WARN_RATIO = 0.2
ALT_MISSING_BAD_RATIO = 0.5
# Fewer internal links than this on a page is worth flagging.
MIN_INTERNAL_LINKS = 3


def _issue(severity: Severity, code: str, reason: str, fix: str) -> SeoIssue:
    return SeoIssue(severity=severity, code=code, reason=reason, fix=fix)


def _canonical_mismatch(evidence: PageEvidence) -> Optional[SeoIssue]:
    if not evidence.canonical_url:
        return None
    page_host = urlparse(evidence.url).hostname or ""
    canonical_host = urlparse(evidence.canonical_url).hostname or ""
    if page_host and canonical_host and page_host.lower() != canonical_host.lower():
        return _issue(
            Severity.MAJOR,
            "canonical_cross_domain",
            "Canonical URL points to another domain",
            "Point the canonical tag at the current page URL on the same domain.",
        )
    return None


def page_issues(
    evidence: PageEvidence, *, is_homepage: Optional[bool] = None
) -> tuple[list[SeoIssue], int]:
    """Run every per-page rule against the evidence; return (issues, score).

    Scoring: start at 100 and subtract a fixed penalty per issue (by
    severity), clamping to [0, 100]. Length/ratio checks only apply when the
    signal exists, so a missing signal is never double-penalised.
    """
    if is_homepage is None:
        is_homepage = evidence.page_type == "home"
    issues: list[SeoIssue] = []

    if not evidence.title:
        issues.append(
            _issue(
                Severity.CRITICAL,
                "missing_title",
                "No <title> tag on this page",
                "Add a descriptive <title> tag (30-60 characters) with the business name.",
            )
        )
    else:
        title_length = len(evidence.title)
        if title_length < TITLE_MIN_LENGTH:
            issues.append(
                _issue(
                    Severity.MINOR,
                    "title_too_short",
                    f"Title is only {title_length} characters (recommended 30-60)",
                    "Extend the title to 30-60 characters.",
                )
            )
        elif title_length > TITLE_MAX_LENGTH:
            issues.append(
                _issue(
                    Severity.MINOR,
                    "title_too_long",
                    f"Title is {title_length} characters (recommended 30-60)",
                    "Shorten the title to 60 characters or fewer.",
                )
            )

    if not evidence.meta_description:
        issues.append(
            _issue(
                Severity.MAJOR,
                "missing_meta_description",
                "No meta description on this page",
                "Add a meta description of 120-160 characters summarising the page.",
            )
        )
    else:
        description_length = len(evidence.meta_description)
        if description_length < DESCRIPTION_MIN_LENGTH:
            issues.append(
                _issue(
                    Severity.MINOR,
                    "meta_description_too_short",
                    f"Meta description is only {description_length} characters (recommended 120-160)",
                    "Extend the meta description to 120-160 characters.",
                )
            )
        elif description_length > DESCRIPTION_MAX_LENGTH:
            issues.append(
                _issue(
                    Severity.MINOR,
                    "meta_description_too_long",
                    f"Meta description is {description_length} characters (recommended 120-160)",
                    "Trim the meta description to 160 characters or fewer.",
                )
            )

    if evidence.h1_count == 0:
        issues.append(
            _issue(
                Severity.CRITICAL,
                "missing_h1",
                "No H1 heading on this page",
                "Add exactly one H1 heading summarising the page topic.",
            )
        )
    elif evidence.h1_count > 1:
        issues.append(
            _issue(
                Severity.MAJOR,
                "multiple_h1",
                f"{evidence.h1_count} H1 headings found (only one is recommended)",
                "Keep exactly one H1; demote the others to H2/H3.",
            )
        )
    elif evidence.h1_count == 1 and evidence.h2_count == 0 and evidence.h3_count == 0:
        issues.append(
            _issue(
                Severity.MINOR,
                "weak_heading_structure",
                "H1 present but no sub-headings below it",
                "Add H2/H3 headings to structure the content.",
            )
        )

    if not evidence.canonical_url:
        issues.append(
            _issue(
                Severity.MODERATE,
                "missing_canonical",
                "No canonical URL tag on this page",
                "Add a self-referencing canonical tag to prevent duplicate-content confusion.",
            )
        )

    canonical_mismatch = _canonical_mismatch(evidence)
    if canonical_mismatch is not None:
        issues.append(canonical_mismatch)

    robots_lower = evidence.robots_meta.lower()
    if "noindex" in robots_lower:
        issues.append(
            _issue(
                Severity.CRITICAL,
                "noindex",
                "Page is blocked from search engines (noindex)",
                "Remove noindex unless this page must stay out of search results.",
            )
        )
    if "nofollow" in robots_lower:
        issues.append(
            _issue(
                Severity.MAJOR,
                "nofollow",
                "Page links are blocked from search engines (nofollow)",
                "Remove nofollow unless links on this page must not be followed.",
            )
        )

    if not evidence.viewport_present:
        issues.append(
            _issue(
                Severity.MAJOR,
                "missing_viewport",
                "No viewport meta tag (mobile layout may be broken)",
                "Add <meta name='viewport' content='width=device-width, initial-scale=1'>.",
            )
        )

    if not evidence.is_https:
        issues.append(
            _issue(
                Severity.MAJOR,
                "not_https",
                "Page is served over HTTP instead of HTTPS",
                "Enable HTTPS and redirect all HTTP requests to HTTPS.",
            )
        )

    if evidence.mixed_content_count > 0:
        issues.append(
            _issue(
                Severity.MODERATE,
                "mixed_content",
                f"{evidence.mixed_content_count} mixed-content reference(s) on an HTTPS page",
                "Load all scripts/styles/images over HTTPS.",
            )
        )

    thin_word_count = HOMEPAGE_THIN_CONTENT_WORDS if is_homepage else THIN_CONTENT_WORDS
    if evidence.word_count > 0 and evidence.word_count < thin_word_count:
        issues.append(
            _issue(
                Severity.MAJOR,
                "thin_content",
                f"Page has only {evidence.word_count} words of content",
                "Expand the page with more original, useful content.",
            )
        )

    if evidence.image_count > 0:
        ratio = evidence.images_missing_alt_count / evidence.image_count
        if ratio >= ALT_MISSING_BAD_RATIO:
            issues.append(
                _issue(
                    Severity.MAJOR,
                    "images_missing_alt",
                    f"{evidence.images_missing_alt_count} of {evidence.image_count} images lack alt text",
                    "Add descriptive alt text to every image.",
                )
            )
        elif ratio >= ALT_MISSING_WARN_RATIO:
            issues.append(
                _issue(
                    Severity.MODERATE,
                    "images_missing_alt",
                    f"{evidence.images_missing_alt_count} of {evidence.image_count} images lack alt text",
                    "Add descriptive alt text to every image.",
                )
            )
        elif evidence.images_missing_alt_count > 0:
            issues.append(
                _issue(
                    Severity.MINOR,
                    "images_missing_alt",
                    f"{evidence.images_missing_alt_count} image(s) lack alt text",
                    "Add descriptive alt text to every image.",
                )
            )

    if evidence.images_broken_count > 0:
        issues.append(
            _issue(
                Severity.MINOR,
                "broken_images",
                f"{evidence.images_broken_count} image(s) have empty or invalid src",
                "Fix the image source URLs.",
            )
        )

    if not evidence.json_ld_present:
        issues.append(
            _issue(
                Severity.MINOR,
                "missing_json_ld",
                "No JSON-LD structured data on this page",
                "Add JSON-LD structured data (e.g. LocalBusiness) for richer results.",
            )
        )

    if not evidence.schema_present:
        issues.append(
            _issue(
                Severity.MINOR,
                "missing_schema",
                "No schema.org markup found on this page",
                "Add schema.org microdata or JSON-LD describing the business.",
            )
        )

    if not evidence.og_title_present or not evidence.og_description_present:
        issues.append(
            _issue(
                Severity.MODERATE,
                "missing_open_graph",
                "Open Graph title/description missing",
                "Add og:title and og:description so links preview well when shared.",
            )
        )

    if not evidence.twitter_card_present:
        issues.append(
            _issue(
                Severity.MINOR,
                "missing_twitter_card",
                "No twitter:card meta tag",
                "Add a twitter:card tag so tweets preview nicely.",
            )
        )

    if not evidence.favicon_present:
        issues.append(
            _issue(
                Severity.INFO,
                "missing_favicon",
                "No favicon link detected",
                "Add a favicon for a more polished browser tab.",
            )
        )

    if evidence.internal_link_count < MIN_INTERNAL_LINKS:
        issues.append(
            _issue(
                Severity.MINOR,
                "few_internal_links",
                f"Only {evidence.internal_link_count} internal links on this page",
                "Link to related pages (services, about, contact) from the content.",
            )
        )

    score = 100 - sum(SEVERITY_PENALTY[issue.severity] for issue in issues)
    return issues, max(0, min(100, score))
