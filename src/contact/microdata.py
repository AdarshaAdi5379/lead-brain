from __future__ import annotations

from typing import Optional

from bs4 import BeautifulSoup


def extract_microdata(soup: BeautifulSoup) -> dict[str, list[str]]:
    """Collect Schema.org microdata email/telephone itemprop values.

    Handles ``<meta content>``, link ``href`` (mailto:/tel: prefixed) and
    element text forms. Emails and phones are returned raw; callers validate
    and normalize them.
    """
    emails: list[str] = []
    phones: list[str] = []
    for tag in soup.find_all(attrs={"itemprop": "email"}):
        value = _itemprop_value(tag)
        if value:
            if value.lower().startswith("mailto:"):
                value = value[len("mailto:"):]
            if value and value not in emails:
                emails.append(value)
    for tag in soup.find_all(attrs={"itemprop": "telephone"}):
        value = _itemprop_value(tag)
        if value:
            if value.lower().startswith("tel:"):
                value = value[len("tel:"):]
            if value and value not in phones:
                phones.append(value)
    return {"email": emails, "telephone": phones}


def _itemprop_value(tag) -> Optional[str]:
    for attr in ("content", "href", "value"):
        value = tag.get(attr)
        if value:
            return str(value).strip()
    text = tag.get_text(" ", strip=True)
    return text.strip() or None