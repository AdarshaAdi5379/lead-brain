from __future__ import annotations

from typing import Optional

from bs4 import BeautifulSoup

from src.contact.helpers import is_contact_page, normalize_absolute_url

# Signals that a form is a contact/lead form rather than site chrome.
_CONTACT_HINTS = ("email", "name", "phone", "message", "subject", "contact", "send", "submit")
_NON_CONTACT_HINTS = (
    "search",
    "login",
    "signin",
    "sign-in",
    "register",
    "newsletter",
    "subscribe",
    "password",
    "comment",
    "checkout",
    "donate",
)


def detect_contact_form(
    html: str,
    page_url: Optional[str],
    *,
    page_label: Optional[str] = None,
) -> Optional[str]:
    """Detect a contact form on a page and return its submission URL.

    Returns the form ``action`` resolved to an absolute URL, or the page URL
    itself when the form has no action. None when no contact-like form exists.
    On a page labelled as a contact page any non-boilerplate form counts.
    """
    if not html:
        return None
    soup = BeautifulSoup(html or "", "html.parser")
    forms = soup.find_all("form")
    if not forms:
        return None

    contact_page = is_contact_page(page_label, page_url)
    for form in forms:
        action = (form.get("action") or "").strip()
        text = form.get_text(" ", strip=True).lower()
        input_names = " ".join(
            f"{field.get('name') or ''} {field.get('type') or ''}"
            for field in form.find_all(["input", "textarea", "select"])
        ).lower()
        haystack = f"{action.lower()} {input_names} {text}"

        if any(hint in haystack for hint in _NON_CONTACT_HINTS):
            continue
        if contact_page or any(hint in haystack for hint in _CONTACT_HINTS):
            if action:
                resolved = normalize_absolute_url(action, page_url)
                if resolved:
                    return resolved
            return page_url or None
    return None
