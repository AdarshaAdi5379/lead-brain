from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from src.scraping.link_extractor import Link

# URL path / anchor keywords that make a page worth auditing. Weight = bonus.
PRIORITY_KEYWORDS: dict[str, int] = {
    "about": 5,
    "about-us": 5,
    "who-we-are": 5,
    "team": 3,
    "company": 3,
    "why-us": 5,
    "services": 5,
    "service": 4,
    "what-we-do": 5,
    "solutions": 5,
    "capabilities": 4,
    "offerings": 4,
    "products": 5,
    "product": 4,
    "portfolio": 5,
    "projects": 4,
    "work": 4,
    "case-studies": 5,
    "case-study": 4,
    "cases": 4,
    "clients": 4,
    "customers": 4,
    "testimonials": 3,
    "reviews": 3,
    "pricing": 5,
    "price": 4,
    "faq": 2,
    "contact": 5,
    "contact-us": 5,
    "get-in-touch": 5,
    "support": 3,
    "careers": 2,
}

# Keywords that mark a page as boilerplate we should skip (Step 3).
IGNORE_KEYWORDS: tuple[str, ...] = (
    "privacy",
    "privacy-policy",
    "terms",
    "terms-of-service",
    "terms-and-conditions",
    "cookies",
    "cookie-policy",
    "consent",
    "gdpr",
    "login",
    "log-in",
    "sign-in",
    "signup",
    "sign-up",
    "register",
    "registration",
    "checkout",
    "cart",
    "basket",
    "search",
    "results",
    "blog",
    "archive",
    "feed",
    "rss",
    "sitemap",
    "account",
    "my-account",
    "admin",
    "dashboard",
    "password",
    "forgot-password",
    "reset-password",
    "print",
    "subscribe",
    "subscription",
    "newsletter",
    "unsubscribe",
    "legal",
    "disclaimer",
    "refund",
    "returns",
    "shipping",
    "terms-conditions",
)

# Anchor-text tokens that confirm relevance (e.g. navigation labels).
ANCHOR_HINT_WORDS: tuple[str, ...] = (
    "about",
    "services",
    "service",
    "products",
    "product",
    "portfolio",
    "pricing",
    "contact",
    "team",
    "work",
    "solutions",
    "clients",
    "customers",
    "case studies",
    "case-study",
)


@dataclass(frozen=True)
class PageSelection:
    selected: list[Link]
    skipped: list[Link]

    def labels(self) -> list[str]:
        return [label_for_link(link) for link in self.selected]


def _slugify(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")


def _token_score(tokens: list[str]) -> int:
    score = 0
    for token in tokens:
        if token in IGNORE_KEYWORDS:
            score -= 25
        elif token in PRIORITY_KEYWORDS:
            score += PRIORITY_KEYWORDS[token]

    joined = "-".join(tokens)
    for ignored in IGNORE_KEYWORDS:
        if f"-{ignored}-" in f"-{joined}-":
            score -= 25
    for keyword, weight in PRIORITY_KEYWORDS.items():
        if keyword != joined and f"-{keyword}-" in f"-{joined}-":
            score += weight
    return score


def score_link(link: Link) -> int:
    """Deterministic, rule-based score for a single candidate page."""
    if not link.url:
        return 0
    path = urlparse(link.url).path
    tokens = [t for t in _slugify(path).split("-") if t]
    score = _token_score(tokens)

    anchor = (link.text or "").strip().lower()
    for hint in ANCHOR_HINT_WORDS:
        if hint in anchor:
            score += 1
    return score


def rank_pages(links: list[Link]) -> list[Link]:
    """Sort candidate links by relevance, highest first.

    Deterministic: primary key is the rule-based score, then shorter paths
    first (a 'services' page beats a deep '/mega-parent/services'), then the
    original first-seen order as a final is_tie tie-break."""
    scored = [(link, score_link(link), len(link.url)) for link in links]
    scored.sort(key=lambda item: (-item[1], item[2]))
    return [link for link, _, _ in scored]


_CONTACT_TOKENS = {"contact", "contacts", "contact-us", "contactus", "get-in-touch"}


def find_contact_links(links: list[Link]) -> list[Link]:
    """Links that clearly point at a contact page, in original order.

    Matches on the fully-slugified path, its tokens, or the anchor text so
    variants like /contact, /contact-us, Contact Us or Get in Touch are all
    recognised. The crawler uses this to guarantee a contact page is always
    visited first, ahead of the relevance-ranked budget.
    """
    matches: list[Link] = []
    for link in links:
        if not link.url:
            continue
        path_tokens = [t for t in _slugify(urlparse(link.url).path).split("-") if t]
        anchor_slug = _slugify((link.text or "").strip().lower())
        is_contact = (
            _slugify(urlparse(link.url).path) in _CONTACT_TOKENS
            or anchor_slug in _CONTACT_TOKENS
            or bool({"contact", "contacts"} & set(path_tokens))
        )
        if is_contact:
            matches.append(link)
    return matches


def select_pages(links: list[Link], *, max_pages: int) -> PageSelection:
    """Partition internal links into chosen + ignored boilerplate pages.

    Only ``max_pages`` are visited (homepage counts elsewhere), so a site with
    many plausible pages never explodes the crawl budget (Step 3/4)."""
    if max_pages <= 0:
        return PageSelection(selected=[], skipped=list(links))

    skipped: list[Link] = []
    candidates: list[Link] = []
    for link in links:
        if score_link(link) < 0:
            skipped.append(link)
        else:
            candidates.append(link)

    ordered = rank_pages(candidates)
    return PageSelection(selected=ordered[:max_pages], skipped=skipped)


def label_for_link(link: Link) -> str:
    """Human-readable page name for logging + merged-document headers.

    Uses anchor text when available, else the last meaningful path segment."""
    if link.text and link.text.strip():
        return link.text.strip()[:60]
    path = urlparse(link.url).path.strip("/")
    if not path:
        return "Home"
    segments = [seg.replace("-", " ").replace("_", " ") for seg in path.split("/")]
    return " ".join(segments).strip().title() or "Home"