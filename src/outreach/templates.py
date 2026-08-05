from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence, Tuple

# Modular outreach copy. Each section (greeting, observation, insight,
# opportunity, offer, cta, closing) is an independent function so tests can
# exercise any single section in isolation. Styles only change the wording --
# every style consumes the exact same context object. Values pulled from the
# database are sanitized by the renderer; templates themselves never see
# ``None`` (context lookups use safe fallbacks).

STYLES: Tuple[str, ...] = (
    "professional",
    "friendly",
    "consultative",
    "short_intro",
    "follow_up",
    "linkedin_message",
)

LENGTHS: Tuple[str, ...] = ("short", "medium", "long")

# How long a message is: which sections are composed, in order. "short" drops
# the opportunity/offer sections; "long" adds a neutral business-context line.
_SECTION_ORDER: Mapping[str, Tuple[str, ...]] = {
    "short": ("greeting", "observation", "insight", "cta", "closing"),
    "medium": (
        "greeting",
        "observation",
        "insight",
        "opportunity",
        "offer",
        "cta",
        "closing",
    ),
    "long": (
        "greeting",
        "observation",
        "business_context",
        "insight",
        "opportunity",
        "offer",
        "cta",
        "closing",
    ),
}

# How many detected facts each length packs into the "insight" phrasing.
_FACTS_PER_LENGTH: Mapping[str, int] = {"short": 1, "medium": 2, "long": 3}

_WORDING: Mapping[str, Mapping[str, str]] = {
    "professional": {
        "subject": "Website improvement plan for {business_name}",
        "greeting": "Hi {salutation},",
        "observation": "I took a close look at the {business_name} website{location_clause} "
        "and a few things look worth addressing.",
        "insight": "Specifically, I noticed {fact_phrase}. Each of these affects how new "
        "customers find, judge and reach {business_name}.",
        "opportunity": "The clearest opportunity here is {opportunity_label}.",
        "offer": "I help local businesses with work like {services_phrase} - no long "
        "contracts - and I can start with a short, no-pressure plan.",
        "cta": "Would you be open to a quick 10-minute call this week? Reply with a time "
        "that works and I'll fit your schedule.",
        "closing": "Best regards,\n- Your Name",
    },
    "friendly": {
        "subject": "A few ideas for {business_name}",
        "greeting": "Hi {salutation},",
        "observation": "I had a quick look at the {business_name} website{location_clause} - "
        "there's a lot to like, but a few things are quietly holding it back.",
        "insight": "A couple of things stood out: {fact_phrase}. Fixing these usually means "
        "more people actually reach out.",
        "opportunity": "The good news? There's a clear opportunity to fix this.",
        "offer": "This is exactly the kind of thing I do - happy to send over 2-3 concrete "
        "suggestions, no strings attached.",
        "cta": "Would you be up for a quick chat this week? Just reply - happy to work "
        "around you.",
        "closing": "Thanks,\n- Your Name",
    },
    "consultative": {
        "subject": "Ideas for strengthening {business_name}",
        "greeting": "Hi {salutation},",
        "observation": "I spent some time reviewing how {business_name} presents itself "
        "online{location_clause} - a few things stood out.",
        "insight": "A few specifics caught my attention: {fact_phrase}. Each directly "
        "influences whether a visitor becomes a customer.",
        "opportunity": "From where I sit, the highest-impact move is {opportunity_label}.",
        "offer": "If it's useful, I can outline the priorities and a rough timeline for "
        "{services_phrase} - no obligation.",
        "cta": "Would it be useful to walk through this together for about 15 minutes? "
        "Happy to fit your schedule.",
        "closing": "Best regards,\n- Your Name",
    },
    "short_intro": {
        "subject": "Quick note about {business_name}",
        "greeting": "Hi {salutation},",
        "observation": "I came across {business_name}{location_clause} and took a look at "
        "the website.",
        "insight": "A couple of things stood out: {fact_phrase}.",
        "opportunity": "",
        "offer": "",
        "cta": "If it's useful, I can send 2-3 specific suggestions - no obligation.",
        "closing": "Thanks,\n- Your Name",
    },
    "follow_up": {
        "subject": "Following up on {business_name}",
        "greeting": "Hi {salutation},",
        "observation": "Following up on my last message about the {business_name} website"
        "{location_clause}.",
        "insight": "Just in case it slipped by, the main items I noticed were {fact_phrase}.",
        "opportunity": "",
        "offer": "If it would help, I can still send the short list of suggested fixes.",
        "cta": "Would a quick call this week help move this forward?",
        "closing": "Thanks,\n- Your Name",
    },
    "linkedin_message": {
        "subject": "",
        "greeting": "Hi {salutation},",
        "observation": "I came across {business_name} and noticed a few things about the "
        "website.",
        "insight": "One thing that stood out: {fact_phrase}.",
        "opportunity": "",
        "offer": "I could send a couple of specific, low-effort fixes if useful.",
        "cta": "Open to a quick chat?",
        "closing": "",
    },
}

_FALLBACK_PHRASE = "a few opportunities to improve the website"
_FALLBACK_OPPORTUNITY = "a clear opportunity to modernize the website"
_FALLBACK_SERVICES = "website improvements"

# No-website leads: never claim a website review happened. A neutral
# introduction plus the factual observation that no active website was found.
_NO_WEBSITE_OBSERVATION = "I came across {business_name}{location_clause} and wanted to reach out."
_NO_WEBSITE_INSIGHT = "It looks like there is no active website for {business_name} yet."


def styles() -> Sequence[str]:
    return STYLES


def lengths() -> Sequence[str]:
    return LENGTHS


def section_names(style: str, length: str) -> Sequence[str]:
    """Ordered sections to compose for a style/length combination."""
    return _SECTION_ORDER.get(length, _SECTION_ORDER["medium"])


def facts_per_length(length: str) -> int:
    return _FACTS_PER_LENGTH.get(length, 2)


def has_subject(style: str) -> bool:
    return bool(_read(style).get("subject"))


def fact_phrase(facts: Sequence[Any]) -> str:
    """Join fact phrases into one prose clause (``a and b`` / ``a, b and c``)."""
    phrases = [str(getattr(fact, "phrase", "") or "").strip() for fact in facts]
    phrases = [p for p in phrases if p]
    if not phrases:
        return _FALLBACK_PHRASE
    if len(phrases) == 1:
        return phrases[0]
    return ", ".join(phrases[:-1]) + " and " + phrases[-1]


def render_section(
    section: str, context: Mapping[str, Any], style: str, facts: Sequence[Any]
) -> str:
    """Render one section ("" when the style intentionally omits it)."""
    builder = _SECTION_BUILDERS.get(section)
    if builder is None:
        return ""
    return builder(context, style, facts)


def render_subject(style: str, context: Mapping[str, Any]) -> str:
    subject = _read(style).get("subject", "")
    if not subject:
        return ""
    return subject.format(**_values(context))


def _read(style: str) -> Mapping[str, str]:
    return _WORDING.get(style, _WORDING["professional"])


def _values(context: Mapping[str, Any]) -> dict[str, str]:
    business = context.get("business") or {}
    contact = context.get("contact") or {}
    location = context.get("location") or {}
    city = str(location.get("city") or "").strip()
    state = str(location.get("state") or "").strip()
    location_clause = ""
    if city or state:
        location_clause = f" in {', '.join(part for part in (city, state) if part)}"
    name = str(business.get("business_name") or "").strip() or "your business"
    owner = str(contact.get("owner_name") or "").strip()
    return {
        "business_name": name,
        "salutation": owner or name,
        "location_clause": location_clause,
        "website": str(contact.get("website_url") or "").strip(),
        "business_summary": (
            str(context.get("business_summary") or "").strip() or name
        ),
        "opportunity_label": _opportunity_text(context),
        "services_phrase": _services_phrase(context),
    }


def _opportunity_text(context: Mapping[str, Any]) -> str:
    if not _has_website(context):
        name = str((context.get("business") or {}).get("business_name") or "").strip()
        return f"getting {name or 'the business'} online with a working website"
    tops = context.get("top_opportunities") or []
    label = str((tops[0].get("label") or "").strip()) if tops else ""
    return label or _FALLBACK_OPPORTUNITY


def _services_phrase(context: Mapping[str, Any]) -> str:
    services: list[str] = []
    for item in context.get("top_opportunities") or []:
        services.extend(item.get("recommended_services") or [])
    summary = context.get("opportunity_summary") or {}
    services += list(summary.get("recommended_services") or [])
    cleaned = list(dict.fromkeys(str(s).strip() for s in services if str(s).strip()))
    if cleaned:
        return ", ".join(cleaned)
    return _FALLBACK_SERVICES


def _has_website(context: Mapping[str, Any]) -> bool:
    contact = context.get("contact") or {}
    return bool(str(contact.get("website_url") or "").strip())


def _greeting(context: Mapping[str, Any], style: str, facts: Sequence[Any]) -> str:
    return _read(style).get("greeting", "").format(**_values(context))


def _observation(context: Mapping[str, Any], style: str, facts: Sequence[Any]) -> str:
    if not _has_website(context):
        return _NO_WEBSITE_OBSERVATION.format(**_values(context))
    return _read(style).get("observation", "").format(
        **_values(context), fact_phrase=fact_phrase(facts)
    )


def _insight(context: Mapping[str, Any], style: str, facts: Sequence[Any]) -> str:
    if not _has_website(context):
        return _NO_WEBSITE_INSIGHT.format(**_values(context))
    return _read(style).get("insight", "").format(
        **_values(context), fact_phrase=fact_phrase(facts)
    )


def _business_context(context: Mapping[str, Any], style: str, facts: Sequence[Any]) -> str:
    summary = str(context.get("business_summary") or "").strip()
    if not summary:
        return ""
    return f"For context, {summary}."


def _opportunity(context: Mapping[str, Any], style: str, facts: Sequence[Any]) -> str:
    return _read(style).get("opportunity", "").format(**_values(context))


def _offer(context: Mapping[str, Any], style: str, facts: Sequence[Any]) -> str:
    return _read(style).get("offer", "").format(**_values(context))


def _cta(context: Mapping[str, Any], style: str, facts: Sequence[Any]) -> str:
    return _read(style).get("cta", "").format(**_values(context))


def _closing(context: Mapping[str, Any], style: str, facts: Sequence[Any]) -> str:
    return _read(style).get("closing", "").format(**_values(context))


_SECTION_BUILDERS: Mapping[str, Callable[..., str]] = {
    "greeting": _greeting,
    "observation": _observation,
    "insight": _insight,
    "business_context": _business_context,
    "opportunity": _opportunity,
    "offer": _offer,
    "cta": _cta,
    "closing": _closing,
}