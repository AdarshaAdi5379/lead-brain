from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Optional, Sequence

from src.map.map_data import MapLead, load_map_leads, option_values
from src.map.map_filters import filter_leads, valid_coordinates
from src.map.map_render import build_map, folium_available, map_html

logger = logging.getLogger("lead.map.service")

# Facade for the dashboard map view. Thin and never raises: missing data and
# render failures degrade to None so the rest of the dashboard stays usable.


class MapService:
    """Read leads with coordinates and render an OpenStreetMap view."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)

    def folium_available(self) -> bool:
        return folium_available()

    def load_leads(self) -> list[MapLead]:
        if not self._db_path.exists():
            return []
        connection = sqlite3.connect(str(self._db_path))
        try:
            connection.row_factory = sqlite3.Row
            return load_map_leads(connection)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Map lead load failed: %s", exc)
            return []
        finally:
            connection.close()

    def option_values(self, leads: Sequence[MapLead]) -> dict[str, list[str]]:
        return option_values(leads)

    def filter(self, leads: Sequence[MapLead], **filters: Any) -> list[MapLead]:
        return list(filter_leads(leads, **filters))

    def render(
        self,
        leads: Sequence[MapLead],
        *,
        cluster: bool = True,
        view_city: Optional[str] = None,
    ) -> Optional[str]:
        """Render the cohort to OSM HTML (None when folium is missing or empty)."""
        if not folium_available():
            return None
        geolocated = [
            lead for lead in leads if valid_coordinates(lead.latitude, lead.longitude)
        ]
        if not geolocated:
            return None
        try:
            return map_html(build_map(geolocated, cluster=cluster, view_city=view_city))
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Map render failed: %s", exc)
            return None