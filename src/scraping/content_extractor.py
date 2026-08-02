from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

# Element selectors stripped before visible text is extracted. They are
# navigation/boilerplate (Step 6) and add little business value.
BOILERPLATE_SELECTORS = [
    "header",
    "footer",
    "nav",
    "script",
    "style",
    "noscript",
    "template",
    "iframe",
    "svg",
    "form",
    "button",
    "input",
    "select",
    "textarea",
    ".cookie",
    "#cookie",
    ".cookie-banner",
    ".cookie-consent",
    ".cookie-notice",
    ".consent",
    "#consent",
    ".gdpr",
    "#gdpr",
    ".popup",
    ".modal",
    ".newsletter",
    ".subscribe",
    ".social",
    ".social-icons",
    ".breadcrumb",
    ".menu",
    ".navigation",
    ".ads",
    ".advertisement",
    "ins",
    ".skip-link",
    "[role=banner]",
    "[role=navigation]",
    "[role=complementary]",
    "[aria-hidden=true]",
]

# Text containers / elements whose text we keep as line blocks.
_TEXT_TAGS = {
    "p",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "li",
    "dd",
    "dt",
    "td",
    "th",
    "caption",
    "blockquote",
    "figcaption",
    "address",
    "pre",
}

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


@dataclass(frozen=True)
class Heading:
    level: int
    text: str


@dataclass(frozen=True)
class PageContent:
    url: str
    title: str
    meta_description: str
    canonical_url: Optional[str]
    headings: tuple[Heading, ...]
    text: str  # cleaned, boilerplate-free visible text
    word_count: int


def _clean_text(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def _first_meta_description(soup: BeautifulSoup) -> str:
    tag = soup.find("meta", attrs={"name": re.compile("^description$", re.IGNORECASE)})
    if not isinstance(tag, Tag):
        return ""
    return _clean_text(tag.get("content"))


def _canonical_url(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    tag = soup.find("link", attrs={"rel": re.compile(r"\bcanonical\b", re.IGNORECASE)})
    if not isinstance(tag, Tag):
        return None
    href = _clean_text(tag.get("href"))
    return urljoin(base_url, href) if href else None


def _collect_text_blocks(body: Tag) -> list[str]:
    """Walk the (cleaned) DOM and emit non-empty text blocks in document order.

    Menus/headers/footers were already removed, and duplicate repeated lines
    (copyright, social handles, menu fragments) are collapsed."""
    blocks: list[str] = []
    seen: set[str] = set()

    def visit(node) -> None:
        for child in node.children:
            if not isinstance(child, Tag):
                continue
            child_name = child.name or ""
            text = ""
            if child_name in _TEXT_TAGS:
                text = _clean_text(child.get_text(" "))
                if text:
                    # Collapse lines that already appeared earlier (boilerplate).
                    key = text.lower()
                    if key not in seen:
                        seen.add(key)
                        blocks.append(text)
                visit(child)
            else:
                visit(child)

    visit(body)
    return blocks


def parse_page(html: str, url: str) -> PageContent:
    """Extract the structured content of a rendered page from its HTML."""
    soup = BeautifulSoup(html or "", "html.parser")

    for selector in BOILERPLATE_SELECTORS:
        for element in soup.select(selector):
            element.decompose()

    title = _clean_text(soup.title.get_text(" ") if soup.title is not None else "")
    description = _first_meta_description(soup)
    canonical = _canonical_url(soup, url)

    headings = tuple(
        Heading(level=int(h.name[1]), text=_clean_text(h.get_text(" ")))
        for h in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
        if _clean_text(h.get_text(" "))
    )

    text_blocks = _collect_text_blocks(soup)
    text = "\n\n".join(text_blocks)

    return PageContent(
        url=url,
        title=title,
        meta_description=description,
        canonical_url=canonical,
        headings=headings,
        text=text,
        word_count=len(text.split()) if text else 0,
    )


def extract_contact_clues(html_text: str, url: str) -> list[str]:
    """Deterministic hint extraction for phone/email that live in mailto/tel
    links or footers, which the boilerplate removal intentionally strips.

    Returns short, deduplicated lines like 'email: bob@example.com'."""
    soup = BeautifulSoup(html_text or "", "html.parser")
    clues: list[str] = []

    # mailto: and tel: hrefs are the most reliable signal.
    for tag in soup.find_all("a", href=True):
        href = (tag.get("href") or "").strip()
        lowered = href.lower()
        if lowered.startswith("mailto:"):
            clues.append(f"email: {href[7:]}")
        elif lowered.startswith("tel:"):
            clues.append(f"phone: {href[4:]}")

    # Common footer/address text can hold bare emails.
    for match in _EMAIL_RE.finditer(html_text):
        clues.append(f"email: {match.group(0)}")

    # Strip obvious list noise and keep first-seen order.
    cleaned: list[str] = []
    seen: set[str] = set()
    for line in clues:
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(line)
    return cleaned