from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag


@dataclass(frozen=True)
class PageEvidence:
    """Deterministic evidence extracted from a rendered HTML document."""

    raw_html: str
    generator: str | None
    metas: tuple[tuple[str, str], ...]      # (name_or_property, content)
    script_srcs: tuple[str, ...]            # <script src="...">
    style_hrefs: tuple[str, ...]            # <link rel="stylesheet" href="...">
    css_urls: tuple[str, ...]               # url(...) tokens inside <style>
    classes: tuple[str, ...]                # class-member tokens
    ids: tuple[str, ...]                    # id attribute values
    inline_js: str                          # concatenated inline <script> text

    # -- matchers --------------------------------------------------------------

    def match_html(self, pattern: str) -> str | None:
        rx = re.compile(pattern, re.IGNORECASE)
        if rx.search(self.raw_html):
            return self._clip(rx.search(self.raw_html).group(0))
        return None

    def match_generator(self, pattern: str) -> str | None:
        if not self.generator:
            return None
        rx = re.compile(pattern, re.IGNORECASE)
        if rx.search(self.generator):
            return self._clip(self.generator)
        return None

    def match_meta(self, name_pattern: str, content_pattern: str) -> str | None:
        name_rx = re.compile(name_pattern, re.IGNORECASE)
        content_rx = re.compile(content_pattern, re.IGNORECASE)
        for name, content in self.metas:
            if name_rx.search(name) and content_rx.search(content):
                return self._clip(content)
        return None

    def match_script(self, pattern: str) -> str | None:
        rx = re.compile(pattern, re.IGNORECASE)
        for src in self.script_srcs:
            if rx.search(src):
                return self._clip(src)
        return None

    def match_style(self, pattern: str) -> str | None:
        rx = re.compile(pattern, re.IGNORECASE)
        for href in self.style_hrefs:
            if rx.search(href):
                return self._clip(href)
        return None

    def match_class(self, pattern: str) -> str | None:
        rx = re.compile(pattern, re.IGNORECASE)
        for token in self.classes:
            if rx.search(token):
                return self._clip(token)
        return None

    def match_id(self, pattern: str) -> str | None:
        rx = re.compile(pattern, re.IGNORECASE)
        for value in self.ids:
            if rx.search(value):
                return self._clip(value)
        return None

    def match_global(self, pattern: str) -> str | None:
        rx = re.compile(pattern, re.IGNORECASE)
        if rx.search(self.inline_js):
            return self._clip(rx.search(self.inline_js).group(0))
        return None

    def match_canonical(self, pattern: str, base_url: str | None = None) -> str | None:
        rx = re.compile(pattern, re.IGNORECASE)
        for tag_name, value in self.metas:
            if tag_name in {"twitter:url", "og:url"} and rx.search(value):
                return self._clip(value)
        return None

    @staticmethod
    def _clip(text: str, limit: int = 90) -> str:
        text = " ".join((text or "").split())
        return text if len(text) <= limit else text[: limit - 1] + "…"


def _clean(value: str | None) -> str:
    return " ".join((value or "").split())


def _is_stylesheet(tag: Tag) -> bool:
    rel = tag.get("rel")
    rels = rel if isinstance(rel, list) else [rel]
    return any(str(r).strip().lower() == "stylesheet" for r in rels if r)


def build_page_evidence(html: str | None) -> PageEvidence:
    """Parse a rendered page's HTML into PageEvidence (deterministic, offline)."""
    html = html or ""
    soup = BeautifulSoup(html, "html.parser")

    generator: str | None = None
    metas: list[tuple[str, str]] = []
    for meta in soup.find_all("meta"):
        if not isinstance(meta, Tag):
            continue
        content = str(meta.get("content") or "").strip()
        if not content:
            continue
        name = _clean(meta.get("name"))
        prop = _clean(meta.get("property"))
        key = name or prop
        if key:
            metas.append((key, content))
            if key == "generator":
                generator = content

    script_srcs = [
        str(tag.get("src")).strip()
        for tag in soup.find_all("script", src=True)
        if isinstance(tag, Tag) and str(tag.get("src") or "").strip()
    ]

    style_hrefs = [
        str(tag.get("href")).strip()
        for tag in soup.find_all("link")
        if isinstance(tag, Tag) and _is_stylesheet(tag) and str(tag.get("href") or "").strip()
    ]

    css_urls: list[str] = []
    for style in soup.find_all("style"):
        if not isinstance(style, Tag):
            continue
        if style.string:
            found = re.findall(r"url\(\s*[\"']?([^\"')]+)[\"']?\s*\)", style.string)
            css_urls.extend(found)

    classes: list[str] = []
    for tag in soup.find_all(class_=True):
        if not isinstance(tag, Tag):
            continue
        raw = tag.get("class")
        tokens = raw if isinstance(raw, list) else [raw]
        classes.extend(str(t) for t in tokens if isinstance(t, str) and t)

    ids = [
        str(tag.get("id")).strip()
        for tag in soup.find_all(id=True)
        if isinstance(tag, Tag) and str(tag.get("id") or "").strip()
    ]

    inline_js = "\n".join(
        str(tag.string)
        for tag in soup.find_all("script")
        if isinstance(tag, Tag) and tag.string and not tag.get("src")
    )

    return PageEvidence(
        raw_html=html,
        generator=generator,
        metas=tuple(metas),
        script_srcs=tuple(script_srcs),
        style_hrefs=tuple(style_hrefs),
        css_urls=tuple(css_urls),
        classes=tuple(classes),
        ids=tuple(ids),
        inline_js=inline_js,
    )