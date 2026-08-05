from __future__ import annotations

"""Interactive OpenStreetMap dashboard (Phase 17).

A small, dependency-light map feature: it reads the latitude/longitude already
stored on leads (populated by OSM discovery and CSV seeds), filters and groups
the cohort in pure functions, and renders an OpenStreetMap view with folium
(when installed). No geocoding, no paid mapping APIs, no new tables.
"""

from src.map.map_data import MapLead, load_map_leads, option_values
from src.map.map_filters import (
    filter_leads,
    score_group,
    valid_coordinates,
)
from src.map.map_markers import (
    MARKER_COLORS,
    contact_presence,
    legend_items,
    marker_color,
    marker_payload,
    popup_html,
    website_presence,
)
from src.map.map_render import build_map, folium_available, map_html
from src.map.map_service import MapService