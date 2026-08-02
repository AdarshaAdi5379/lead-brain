from __future__ import annotations

import warnings
from typing import Optional

from src.discovery.base import BusinessCandidate, DiscoveryProvider, ProviderError
from src.discovery.models import DiscoveryQuery
from src.discovery.places import PlaceCandidate, place_details, text_search
from src.settings import PLACES_TEXT_SEARCH_RADIUS
from src.storage.normalization import normalize_url_for_dedupe

_DEPRECATION_MSG = (
    "The Google Places discovery provider is deprecated and discouraged: it "
    "requires the paid Google Maps Platform and a GOOGLE_MAPS_API_KEY. "
    "Prefer the free, keyless OpenStreetMap provider (--provider osm)."
)


def _as_candidate(place: PlaceCandidate, category: str) -> BusinessCandidate:
    website = place.website
    if website:
        website = normalize_url_for_dedupe(website) or website
    return BusinessCandidate(
        business_name=place.name,
        category=category,
        url=website,
        phone=place.phone,
        address=place.address,
        latitude=None,
        longitude=None,
        osm_id=place.place_id,
        osm_type="google:place",
        source="google",
        raw=place.raw,
    )


class GooglePlacesProvider(DiscoveryProvider):
    """Deprecated Google Places adapter.

    Wraps the existing ``src.discovery.places`` module behind the same
    :class:`DiscoveryProvider` interface so existing behaviour (and any call
    sites that pin ``--provider google``) keeps working. New code should use
    the default ``osm`` provider.
    """

    name = "google"

    def search(
        self,
        query: DiscoveryQuery,
        *,
        radius: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> list[BusinessCandidate]:
        warnings.warn(_DEPRECATION_MSG, DeprecationWarning, stacklevel=2)

        try:
            candidates = text_search(
                query.category, query.location, radius=int(radius or PLACES_TEXT_SEARCH_RADIUS)
            )
        except RuntimeError as exc:
            raise ProviderError(str(exc)) from exc

        results: list[BusinessCandidate] = []
        for candidate in candidates:
            enriched = candidate
            if not candidate.website:
                try:
                    enriched = place_details(candidate.place_id)
                except Exception:
                    enriched = candidate
            results.append(_as_candidate(enriched, query.category))

        if limit is not None:
            results = results[:max(0, int(limit))]
        return results