from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse

from src.contact.helpers import normalize_absolute_url

# Hosts that are never stored as a business website: social profiles and
# aggregator/directory landing pages (only the actual business domain counts).
_SOCIAL_HOSTS = frozenset(
    {
        "facebook.com",
        "m.facebook.com",
        "instagram.com",
        "linkedin.com",
        "twitter.com",
        "x.com",
        "youtube.com",
        "m.youtube.com",
        "youtu.be",
        "tiktok.com",
        "pinterest.com",
        "snapchat.com",
        "wa.me",
        "api.whatsapp.com",
        "web.whatsapp.com",
        "t.me",
    }
)

_DIRECTORY_HOSTS = frozenset(
    {
        "yelp.com",
        "yellowpages.com",
        "manta.com",
        "thumbtack.com",
        "angi.com",
        "angieslist.com",
        "superpages.com",
        "houzz.com",
        "mapquest.com",
        "bbb.org",
        "citysearch.com",
        "merchantcircle.com",
        "nextdoor.com",
        "foursquare.com",
        "tripadvisor.com",
        "brownbook.net",
        "yellowbook.com",
        "dexknows.com",
        "hotfrog.com",
        "find-us-here.com",
    }
)

_REJECTED_HOSTS = _SOCIAL_HOSTS | _DIRECTORY_HOSTS


def rejected_host(url: str) -> bool:
    """Whether the URL points at a social/directory host (never stored)."""
    host = urlparse(url).netloc.lower()
    if not host:
        return True
    return any(host == entry or host.endswith("." + entry) for entry in _REJECTED_HOSTS)


def clean_candidate_url(raw: object) -> Optional[str]:
    """Normalize a candidate URL for storage, or None when unusable.

    Reuses the pipeline's URL normalizer (http/https only, tracking query
    parameters and fragments stripped) and rejects social/directory hosts,
    malformed URLs and non-web schemes.
    """
    url = normalize_absolute_url(raw)
    if not url:
        return None
    if rejected_host(url):
        return None
    return url