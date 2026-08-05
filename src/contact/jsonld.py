from __future__ import annotations

import json
from typing import Any, Iterable, Optional

from bs4 import BeautifulSoup

from src.contact.helpers import clean_text

# Schema.org types we treat as business/organization entities. Anything
# containing these tokens (including LocalBusiness subtypes) is considered.
_ORG_TYPE_TOKENS = (
    "organization",
    "business",
    "corporation",
    "store",
    "shop",
    "restaurant",
    "cafe",
    "bar",
    "salon",
    "clinic",
    "practice",
    "agency",
    "studio",
    "hotel",
    "hospital",
    "gym",
    "school",
    "church",
    "bank",
    "company",
    "person",
)

_OWNER_ROLES = ("founder", "owner", "employee", "employees", "cofounder", "ceo", "president")

_DAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)

# Schema.org types that are page/document chrome rather than a business
# entity; used only when the @type token heuristic does not match.
_NON_ENTITY_TYPES = {
    "webpage",
    "article",
    "blogposting",
    "newsarticle",
    "report",
    "faqpage",
    "question",
    "answer",
    "product",
    "review",
    "offer",
    "itemlist",
    "listitem",
    "breadcrumblist",
    "website",
    "webapp",
    "videoobject",
    "imageobject",
    "musicrecording",
    "event",
    "jobposting",
    "howto",
    "howtosection",
    "recipe",
}

# Fields that mark a node as carrying contact facts (fallback heuristic).
_ENTITY_HINT_FIELDS = (
    "address",
    "telephone",
    "email",
    "sameas",
    "openinghours",
    "areaserved",
    "contactpoint",
    "founder",
    "owner",
)


def _loads(raw: Optional[str]) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def _iter_objects(value: Any) -> Iterable[dict[str, Any]]:
    """Depth-first walk over JSON-LD graphs/arrays yielding dict nodes."""
    if isinstance(value, dict):
        yield value
        graph = value.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                yield from _iter_objects(item)
        for key, item in value.items():
            if key not in ("@graph", "@context"):
                yield from _iter_objects(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_objects(item)


def _is_org_type(value: Any) -> bool:
    types = value if isinstance(value, list) else [value]
    for raw_type in types:
        name = clean_text(raw_type)
        if not name:
            continue
        lowered = name.lower()
        if any(token in lowered for token in _ORG_TYPE_TOKENS):
            return True
    return False


def _looks_like_entity(item: dict[str, Any]) -> bool:
    """Whether a JSON-LD node plausibly describes a business/organization.

    The @type token heuristic covers Organization/LocalBusiness families;
    as a fallback, nodes carrying contact-ish fields are accepted unless they
    are clearly page/document chrome (WebPage, Article, Product, ...).
    """
    if _is_org_type(item.get("@type")):
        return True
    types = item.get("@type") or []
    for raw_type in (types if isinstance(types, list) else [types]):
        if clean_text(raw_type) and str(raw_type).lower() in _NON_ENTITY_TYPES:
            return False
    lowered = {str(key).lower() for key in item}
    return bool(lowered & set(_ENTITY_HINT_FIELDS))


def _day_name(value: Any) -> Optional[str]:
    text = clean_text(value)
    if not text:
        return None
    for day in _DAYS:
        if day.lower() in text.lower():
            return day
    return None


def _compose_opening_hours(item: dict[str, Any]) -> Optional[str]:
    plain = item.get("openingHours")
    if clean_text(plain):
        return clean_text(plain)

    specs = item.get("openingHoursSpecification")
    if not specs:
        return None
    if isinstance(specs, dict):
        specs = [specs]
    if not isinstance(specs, list):
        return None

    lines: list[str] = []
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        day = _day_name(spec.get("dayOfWeek"))
        opens = clean_text(spec.get("opens"))
        closes = clean_text(spec.get("closes"))
        if opens and closes:
            lines.append(f"{day or 'Unknown'} {opens}-{closes}")
        elif day:
            lines.append(day)
    return "; ".join(lines) if lines else None


def _extract_address(item: dict[str, Any]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    address = item.get("address")
    if not isinstance(address, dict):
        return None, None, None
    parts = [
        part
        for part in (
            clean_text(address.get("streetAddress")),
            clean_text(address.get("addressLocality")),
            clean_text(address.get("addressRegion")),
            clean_text(address.get("postalCode")),
            clean_text(address.get("addressCountry")),
        )
        if part
    ]
    composed = ", ".join(parts) if parts else None
    return composed, clean_text(address.get("postalCode")), clean_text(address.get("addressCountry"))


def _collect_names(value: Any) -> list[str]:
    """Extract names from a string, dict (name field) or list of either."""
    names: list[str] = []
    items = value if isinstance(value, list) else [value]
    for item in items:
        if isinstance(item, dict):
            name = clean_text(item.get("name"))
        else:
            name = clean_text(item)
        if name and name not in names:
            names.append(name)
    return names


def extract_jsonld(html: str) -> dict[str, Any]:
    """Deterministic extraction of contact facts from JSON-LD blocks.

    Returns a plain dict (never raises); fields absent from the markup stay
    missing. Phone/email are returned raw and sanitized by the caller through
    the pipeline's existing normalizers.
    """
    result: dict[str, Any] = {}
    if not html:
        return result

    soup = BeautifulSoup(html or "", "html.parser")
    for script in soup.find_all("script", type=True):
        script_type = (script.get("type") or "").lower()
        if "ld+json" not in script_type:
            continue
        data = _loads(script.string or script.get_text())
        for item in _iter_objects(data):
            if not isinstance(item, dict) or not _looks_like_entity(item):
                continue
            _collect_item(item, result)
    return result


def _collect_item(item: dict[str, Any], result: dict[str, Any]) -> None:
    types = item.get("@type") or []
    type_names = types if isinstance(types, list) else [types]

    # Owner: a Person entity itself, or an explicit founder/owner/employee role.
    owner_name = None
    if any(clean_text(t).lower() == "person" for t in type_names):
        owner_name = clean_text(item.get("name"))
    for role in _OWNER_ROLES:
        nested = item.get(role)
        if isinstance(nested, dict):
            owner_name = owner_name or clean_text(nested.get("name"))
        elif isinstance(nested, list):
            for sub in nested:
                if isinstance(sub, dict):
                    owner_name = owner_name or clean_text(sub.get("name"))
    if owner_name and not result.get("owner_name"):
        result["owner_name"] = owner_name

    composed, postal_code, country = _extract_address(item)
    if composed and not result.get("address"):
        result["address"] = composed
    if postal_code and not result.get("postal_code"):
        result["postal_code"] = postal_code
    if country and not result.get("country"):
        result["country"] = country

    hours = _compose_opening_hours(item)
    if hours and not result.get("opening_hours"):
        result["opening_hours"] = hours

    areas = item.get("areaServed") or item.get("serviceArea") or item.get("servesArea")
    if areas:
        names = _collect_names(areas)
        existing = set(result.get("service_areas") or [])
        for name in names:
            if name not in existing:
                result.setdefault("service_areas", []).append(name)
                existing.add(name)

    same_as = item.get("sameAs")
    if same_as:
        urls = [clean_text(u) for u in (same_as if isinstance(same_as, list) else [same_as])]
        existing = set(result.get("same_as") or [])
        for url in urls:
            if url and url not in existing:
                result.setdefault("same_as", []).append(url)
                existing.add(url)

    contact_point = item.get("contactPoint")
    points = contact_point if isinstance(contact_point, list) else [contact_point]
    for point in points:
        if not isinstance(point, dict):
            continue
        if not result.get("telephone"):
            result["telephone"] = point.get("telephone")
        if not result.get("email"):
            result["email"] = point.get("email")

    if not result.get("telephone"):
        result["telephone"] = item.get("telephone")
    if not result.get("email"):
        result["email"] = item.get("email")
