from __future__ import annotations

from typing import Any, Optional, Sequence

# OpenStreetMap rendering via folium (lazy import so the rest of the project —
# and the stdlib test suite — never depends on it). Markers are colored by the
# canonical score group, popups are the sanitized marker payloads, and nearby
# markers can be clustered with folium's built-in plugin. Only OSM tiles are
# used; no paid or custom tile providers.

_DEFAULT_LOCATION: list[float] = [39.8, -98.5]
_DEFAULT_ZOOM = 4


def folium_available() -> bool:
    try:  # pragma: no cover - environment probing
        import folium  # noqa: F401

        return True
    except Exception:
        return False


def build_map(
    leads: Sequence[Any],
    *,
    cluster: bool = True,
    view_city: Optional[str] = None,
) -> Any:
    """Create a folium Map with one colored marker per lead.

    ``view_city`` (a city name) zooms the view to that city's leads; None fits
    the whole cohort. Returns a folium Map object.
    """
    import folium
    from folium.plugins import MarkerCluster

    from src.map.map_markers import marker_color, popup_html

    m = folium.Map(location=_DEFAULT_LOCATION, zoom_start=_DEFAULT_ZOOM, tiles=None, control_scale=True)
    folium.TileLayer(
        tiles="OpenStreetMap",
        name="OpenStreetMap",
        attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    ).add_to(m)

    clusterer = MarkerCluster(name="clustered_markers").add_to(m) if cluster else None
    for lead in leads:
        popup = folium.Popup(popup_html(lead), max_width=300)
        icon = folium.Icon(color=marker_color(lead.lead_score), icon="info-sign", prefix="fa")
        marker = folium.Marker(
            location=[float(lead.latitude), float(lead.longitude)],
            popup=popup,
            icon=icon,
            tooltip=str(lead.business_name or f"Lead #{lead.id}"),
        )
        if clusterer is not None:
            clusterer.add_child(marker)
        else:
            marker.add_to(m)

    _fit_view(m, leads, view_city)
    return m


def map_html(folium_map: Any) -> str:
    """Render a folium Map object to a self-contained HTML string."""
    return folium_map.get_root().render()


def _fit_view(m: Any, leads: Sequence[Any], view_city: Optional[str]) -> None:
    city = str(view_city or "").strip().lower()
    wanted = [
        (float(lead.latitude), float(lead.longitude))
        for lead in leads
        if not city or str(lead.city or "").strip().lower() == city
    ]
    if not wanted:
        return
    lats = [point[0] for point in wanted]
    lons = [point[1] for point in wanted]
    if len(wanted) == 1:
        m.location = [lats[0], lons[0]]
        m.zoom_start = 15
        return
    m.fit_bounds(
        [[min(lats), min(lons)], [max(lats), max(lons)]],
        padding=(30, 30),
        max_zoom=16,
    )