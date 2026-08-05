from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Optional

from src.chat.base import (
    Intent,
    IntentRoute,
    RetrievalStrategy,
    RetrievedContext,
    RetrievedLead,
)
from src.chat.config import ChatConfig
from src.chat.router import RouteHints, route_query
from src.search.query import SearchError, SearchQuery, build_metadata_filter, validate_filters
from src.search.search_service import SearchService
from src.search.config import from_settings as search_config_from_settings
from src.storage.db import connect, init_db
from src.storage import search as search_storage

logger = logging.getLogger("lead.chat")

# Retrieval layer for the chat assistant. Two paths:
#   * semantic path — the existing SearchService (vector + keyword + metadata
#     filters) over the lead_embeddings index;
#   * SQL fallback — deterministic, parameterized queries over leads + scores +
#     audits + opportunities, used when the index is empty or unavailable.
# Both paths feed the same RetrievedContext contract, so the rest of the
# assistant does not care which path produced the records.


class LeadRetriever:
    """Fetch relevant leads for a question using search and/or SQL."""

    def __init__(
        self,
        db_path: Path,
        config: ChatConfig,
        search_service: Optional[SearchService] = None,
    ) -> None:
        self._db_path = Path(db_path)
        self.config = config
        self._search_service = search_service
        self._hints: Optional[RouteHints] = None

    # -- routing -------------------------------------------------------------

    def route(self, query: str) -> IntentRoute:
        return route_query(query, hints=self.hints())

    def hints(self) -> RouteHints:
        if self._hints is None:
            self._hints = self._build_hints()
        return self._hints

    # -- main entry ----------------------------------------------------------

    def retrieve(self, route: IntentRoute, *, filters: Optional[dict[str, Any]] = None) -> RetrievedContext:
        """Retrieve context for a routed question."""
        merged = _merge_filters(route.params, filters)
        intent = route.intent

        if intent is Intent.SIMILAR:
            lead_id = self._resolve_lead_id(route)
            if lead_id is None:
                return RetrievedContext(
                    query=route.raw_query,
                    intent=intent,
                    strategy=RetrievalStrategy.NONE,
                    filters_used=merged,
                )
            return self.similar(lead_id, top_k=route.top_n or 10)

        if intent is Intent.DETAIL:
            lead_id = self._resolve_lead_id(route)
            if lead_id is None:
                return RetrievedContext(
                    query=route.raw_query,
                    intent=intent,
                    strategy=RetrievalStrategy.NONE,
                    filters_used=merged,
                )
            return self.context_for_lead_ids([lead_id], strategy=RetrievalStrategy.LEAD_DETAIL)

        if intent is Intent.COMPARE:
            lead_ids = self._lead_ids_for_compare(route, merged)
            if not lead_ids:
                return RetrievedContext(
                    query=route.raw_query,
                    intent=intent,
                    strategy=RetrievalStrategy.NONE,
                    filters_used=merged,
                )
            return self.context_for_lead_ids(lead_ids, strategy=RetrievalStrategy.COMPARE)

        return self.search(route.raw_query, filters=merged, top_k=route.top_n or self.config.top_k)

    # -- search --------------------------------------------------------------

    def search(
        self,
        query_text: str,
        *,
        filters: Optional[dict[str, Any]] = None,
        top_k: Optional[int] = None,
    ) -> RetrievedContext:
        """Hybrid semantic search, or the SQL fallback when no index exists."""
        merged = _merge_filters({}, filters)
        limit = int(top_k or self.config.top_k)
        if self._index_available():
            return self._semantic_search(query_text, _flatten_for_semantic(merged), limit)
        return self._sql_search(query_text, merged, limit)

    def similar(self, lead_id: int, top_k: int = 10) -> RetrievedContext:
        """Top similar leads via stored embeddings (category fallback in SQL)."""
        limit = max(1, int(top_k))
        try:
            if self._index_available():
                results = self.search_service.similar(lead_id, top_k=limit)
                ids = [result.lead_id for result in results]
                intel = self._intelligence(ids)
                retrieved = [
                    RetrievedLead(
                        lead_id=result.lead_id,
                        intel=intel.get(result.lead_id, {}),
                        rationale=_rationale_for_result(result),
                        similarity=result.similarity,
                    )
                    for result in results
                ]
                return RetrievedContext(
                    query=f"similar to lead #{lead_id}",
                    intent=Intent.SIMILAR,
                    strategy=RetrievalStrategy.SIMILARITY,
                    retrieved_leads=retrieved,
                )
        except SearchError as exc:
            logger.debug("Similarity search unavailable for lead %s: %s", lead_id, exc)
        return self._sql_similar(lead_id, limit)

    def context_for_lead_ids(
        self,
        lead_ids: list[int],
        *,
        strategy: RetrievalStrategy,
        query: str = "",
    ) -> RetrievedContext:
        """Build a context from explicit lead ids (detail / compare paths)."""
        ids = [int(i) for i in lead_ids if int(i) > 0]
        if not ids:
            return RetrievedContext(query=query, strategy=strategy)
        intel = self._intelligence(ids)
        retrieved = [
            RetrievedLead(lead_id=lead_id, intel=intel.get(lead_id, {}), rationale="explicit selection")
            for lead_id in ids
            if lead_id in intel
        ]
        return RetrievedContext(
            query=query,
            intent=Intent.DETAIL if strategy is RetrievalStrategy.LEAD_DETAIL else Intent.COMPARE,
            strategy=strategy,
            retrieved_leads=retrieved,
        )

    def by_lead_id(self, lead_id: int) -> Optional[RetrievedLead]:
        context = self.context_for_lead_ids([lead_id], strategy=RetrievalStrategy.LEAD_DETAIL)
        return context.retrieved_leads[0] if context.retrieved_leads else None

    # -- internals -----------------------------------------------------------

    @property
    def search_service(self) -> SearchService:
        if self._search_service is None:
            self._search_service = SearchService(self._db_path, config=search_config_from_settings())
        return self._search_service

    def index_count(self) -> int:
        try:
            with self._connect() as connection:
                return search_storage.count_embeddings(connection)
        except Exception as exc:
            logger.debug("Could not count embeddings: %s", exc)
            return 0

    def _index_available(self) -> bool:
        return self.index_count() > 0

    def _semantic_search(
        self, query_text: str, filters: dict[str, Any], limit: int
    ) -> RetrievedContext:
        validated = validate_filters(filters)
        results = self.search_service.search(
            SearchQuery(text=query_text, mode="hybrid", top_k=limit, filters=validated)
        )
        ids = [result.lead_id for result in results]
        intel = self._intelligence(ids)
        retrieved = [
            RetrievedLead(
                lead_id=result.lead_id,
                intel=intel.get(result.lead_id, {}),
                rationale=_rationale_for_result(result),
                similarity=result.similarity,
            )
            for result in results
        ]
        return RetrievedContext(
            query=query_text,
            intent=Intent.SEARCH,
            strategy=RetrievalStrategy.SEMANTIC_SEARCH,
            filters_used=validated,
            retrieved_leads=retrieved,
            index_count=self.index_count(),
        )

    def _sql_search(self, query_text: str, filters: dict[str, Any], limit: int) -> RetrievedContext:
        validated = _validate_sql_filters(filters)
        try:
            rows = _sql_select_leads(self._connect, validated, limit)
        except sqlite3.Error as exc:
            logger.debug("SQL retrieval failed: %s", exc)
            return RetrievedContext(query=query_text, strategy=RetrievalStrategy.NONE, filters_used=validated)
        rows = [dict(row) for row in rows]
        ids = [int(row["lead_id"]) for row in rows]
        intel = self._intelligence(ids)
        retrieved = [
            RetrievedLead(
                lead_id=row["lead_id"],
                intel=intel.get(row["lead_id"], {}),
                rationale=_rationale_for_sql_row(row, validated),
            )
            for row in rows
            if row["lead_id"] in intel
        ]
        return RetrievedContext(
            query=query_text,
            intent=Intent.SEARCH,
            strategy=RetrievalStrategy.SQL_FILTERS,
            filters_used=validated,
            retrieved_leads=retrieved,
            index_count=0,
        )

    def _sql_similar(self, lead_id: int, limit: int) -> RetrievedContext:
        try:
            rows = _sql_similar_leads(self._connect, lead_id, limit)
        except sqlite3.Error as exc:
            logger.debug("SQL similarity failed: %s", exc)
            return RetrievedContext(strategy=RetrievalStrategy.NONE)
        ids = [int(row["lead_id"]) for row in rows]
        intel = self._intelligence(ids)
        retrieved = [
            RetrievedLead(
                lead_id=row["lead_id"],
                intel=intel.get(row["lead_id"], {}),
                rationale=f"same category as lead #{lead_id}, ranked by lead score",
            )
            for row in rows
            if row["lead_id"] in intel
        ]
        return RetrievedContext(
            query=f"similar to lead #{lead_id}",
            intent=Intent.SIMILAR,
            strategy=RetrievalStrategy.SIMILARITY,
            retrieved_leads=retrieved,
        )

    def _resolve_lead_id(self, route: IntentRoute) -> Optional[int]:
        lead_id = route.params.get("lead_id")
        if isinstance(lead_id, int) and lead_id > 0:
            return lead_id
        name = route.params.get("business_name")
        if not name:
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id FROM leads WHERE lower(business_name) = lower(?) "
                "ORDER BY extracted_at DESC LIMIT 1",
                (str(name),),
            ).fetchone()
            if row is None:
                row = connection.execute(
                    "SELECT id FROM leads WHERE lower(business_name) LIKE lower(?) "
                    "ORDER BY extracted_at DESC LIMIT 1",
                    (f"%{str(name)}%",),
                ).fetchone()
        return int(row["id"]) if row else None

    def _lead_ids_for_compare(
        self, route: IntentRoute, filters: dict[str, Any]
    ) -> list[int]:
        names = [
            name
            for name in (
                route.params.get("business_name"),
                *[v for v in route.params.get("business_names", [])],
            )
            if name
        ]
        ids: list[int] = []
        for name in names:
            lead_id = self._resolve_lead_id(
                IntentRoute(intent=Intent.DETAIL, params={"business_name": name})
            )
            if lead_id is not None:
                ids.append(lead_id)
        if not ids and filters:
            context = self.search("", filters=filters, top_k=route.top_n or 3)
            ids = [lead.lead_id for lead in context.retrieved_leads]
        return ids

    def _build_hints(self) -> RouteHints:
        try:
            with self._connect() as connection:
                def distinct(column: str) -> tuple[str, ...]:
                    rows = connection.execute(
                        f"SELECT DISTINCT {column} FROM leads "
                        f"WHERE {column} IS NOT NULL AND {column} != '' ORDER BY 1"
                    ).fetchall()
                    return tuple(str(row[0]) for row in rows)

                names = connection.execute(
                    "SELECT DISTINCT business_name FROM leads "
                    "WHERE business_name IS NOT NULL AND business_name != '' ORDER BY 1"
                ).fetchall()
        except sqlite3.Error as exc:
            logger.debug("Could not build route hints: %s", exc)
            return RouteHints.empty()
        return RouteHints(
            categories=distinct("category"),
            cities=distinct("city"),
            states=distinct("state"),
            countries=distinct("country"),
            platforms=distinct("platform"),
            business_names=tuple(str(row[0]) for row in names),
        )

    def _intelligence(self, lead_ids: list[int]) -> dict[int, dict[str, Any]]:
        if not lead_ids:
            return {}
        with self._connect() as connection:
            return search_storage.leads_intelligence(connection, lead_ids=[int(i) for i in lead_ids])

    def _connect(self):
        connection = connect(self._db_path)
        init_db(connection)
        return connection


def _merge_filters(route_params: dict[str, Any], extra: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Combine route-extracted filters with explicit UI filters (UI wins)."""
    merged = {
        key: value
        for key, value in route_params.items()
        if key in {"category", "city", "state", "country", "platform", "priority",
                   "website_present", "seo_score", "lead_score", "visual_score",
                   "opportunity_score", "technologies"}
    }
    for key, value in (extra or {}).items():
        if value is not None:
            merged[key] = value
    return merged


_LIST_FILTER_KEYS = frozenset(
    {"category", "city", "state", "country", "platform", "priority", "technologies"}
)
_RANGE_KEYS = frozenset({"seo_score", "lead_score", "visual_score", "opportunity_score"})


def _validate_sql_filters(filters: dict[str, Any]) -> dict[str, Any]:
    """Whitelist validation for the SQL retrieval path.

    Mirrors ``validate_filters`` but additionally accepts list values for
    category/city/state/country/platform/priority (rendered as parameterized
    ``IN`` clauses). Raises ``SearchError`` on unknown keys or bad types —
    nothing user-supplied reaches SQL unvalidated.
    """
    from src.search.query import ALLOWED_FILTERS, SearchError

    cleaned: dict[str, Any] = {}
    for key, value in (filters or {}).items():
        key = str(key).strip().lower()
        if key not in ALLOWED_FILTERS:
            raise SearchError(f"Unknown filter {key!r}")
        if key in _RANGE_KEYS:
            if not isinstance(value, dict):
                raise SearchError(f"Filter {key!r} must be a dict with 'min'/'max'")
            bounds: dict[str, Any] = {}
            if value.get("min") is not None:
                bounds["min"] = int(value["min"])
            if value.get("max") is not None:
                bounds["max"] = int(value["max"])
            cleaned[key] = bounds
        elif key == "website_present":
            if not isinstance(value, bool):
                raise SearchError(f"Filter {key!r} must be a boolean")
            cleaned[key] = value
        else:
            if isinstance(value, (list, tuple)):
                items = [str(item).strip() for item in value if str(item).strip()]
                if not items:
                    raise SearchError(f"Filter {key!r} contains only empty values")
                cleaned[key] = items
            else:
                item = str(value).strip()
                if not item:
                    raise SearchError(f"Filter {key!r} must be a non-empty string")
                cleaned[key] = item
    return cleaned


def _flatten_for_semantic(filters: dict[str, Any]) -> dict[str, Any]:
    """Reduce list-valued filters to the scalar form the vector engine accepts.

    The semantic index stores one value per lead for category/city/state/etc.;
    multi-select choices are narrowed to the first for that path (the SQL
    fallback keeps the full list via IN clauses).
    """
    flattened: dict[str, Any] = {}
    for key, value in (filters or {}).items():
        if key in _LIST_FILTER_KEYS and isinstance(value, (list, tuple)):
            flattened[key] = str(value[0])
        else:
            flattened[key] = value
    return flattened


def _rationale_for_result(result: Any) -> str:
    parts = [f"semantic relevance {result.similarity:.2f} (combined rank {result.combined_score:.3f})"]
    return "; ".join(parts)


def _rationale_for_sql_row(row: dict[str, Any], filters: dict[str, Any]) -> str:
    parts = []
    if filters:
        rendered = []
        for key, value in filters.items():
            if isinstance(value, dict):
                bounds = ", ".join(f"{op} {num}" for op, num in value.items())
                rendered.append(f"{key} {bounds}")
            else:
                rendered.append(f"{key}={value}")
        parts.append("matched filters: " + ", ".join(rendered))
    if row.get("lead_score") is not None:
        parts.append(f"lead score {row['lead_score']}/100")
    if row.get("top_opportunity_score") is not None:
        parts.append(f"top opportunity {row['top_opportunity_score']}/100")
    return "; ".join(parts) or "retrieved by query"


def _sql_select_leads(
    connection_factory, filters: dict[str, Any], limit: int
) -> list[sqlite3.Row]:
    """Deterministic SQL retrieval: parameterized, whitelist-validated filters."""
    clauses: list[str] = []
    params: list[Any] = []

    def _range_clause(column: str, value: dict[str, Any], *, table: str) -> None:
        if value.get("min") is not None:
            clauses.append(f"{table}.{column} >= ?")
            params.append(int(value["min"]))
        if value.get("max") is not None:
            clauses.append(f"{table}.{column} <= ?")
            params.append(int(value["max"]))

    for key, value in filters.items():
        if key == "category":
            _in_clause("l.category", value, clauses, params)
        elif key == "city":
            _in_clause("l.city", value, clauses, params)
        elif key == "state":
            _in_clause("l.state", value, clauses, params)
        elif key == "country":
            _in_clause("l.country", value, clauses, params)
        elif key == "platform":
            _in_clause("l.platform", value, clauses, params)
        elif key == "priority":
            clauses.append("l.priority = ?")
            params.append(str(value))
        elif key == "website_present":
            if value:
                clauses.append("l.website_url IS NOT NULL AND l.website_url != ''")
            else:
                clauses.append("(l.website_url IS NULL OR l.website_url = '')")
        elif key == "technologies":
            placeholders = ",".join("?" * len(value))
            clauses.append(
                f"EXISTS (SELECT 1 FROM technology_detections t "
                f"WHERE t.lead_id = l.id AND t.technology_name IN ({placeholders}))"
            )
            params.extend(str(item) for item in value)
        elif key == "lead_score":
            if value.get("min") is not None:
                clauses.append("COALESCE(ls.final_score, l.score) >= ?")
                params.append(int(value["min"]))
            if value.get("max") is not None:
                clauses.append("COALESCE(ls.final_score, l.score) <= ?")
                params.append(int(value["max"]))
        elif key == "seo_score":
            _range_clause("site_score", value, table="a")
        elif key == "visual_score":
            _range_clause("visual_score", value, table="v")
        elif key == "opportunity_score":
            _range_clause("score", value, table="o")

    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"""
        SELECT l.id AS lead_id,
               COALESCE(ls.final_score, l.score) AS lead_score,
               MAX(o.score) AS top_opportunity_score,
               l.extracted_at
        FROM leads l
        LEFT JOIN lead_scores ls ON ls.lead_id = l.id
        LEFT JOIN business_opportunities o ON o.lead_id = l.id
        LEFT JOIN seo_audits a ON a.lead_id = l.id
        LEFT JOIN visual_audits v ON v.lead_id = l.id
        {where}
        GROUP BY l.id
        ORDER BY COALESCE(ls.final_score, l.score) DESC,
                 MAX(o.score) DESC,
                 (CASE WHEN l.phone IS NOT NULL AND l.phone != '' THEN 1 ELSE 0 END +
                  CASE WHEN l.email IS NOT NULL AND l.email != '' THEN 1 ELSE 0 END) DESC,
                 l.extracted_at DESC,
                 l.id
        LIMIT ?
    """
    params.append(int(limit))
    with connection_factory() as connection:
        return connection.execute(sql, params).fetchall()


def _sql_similar_leads(connection_factory, lead_id: int, limit: int) -> list[sqlite3.Row]:
    """Category-first similarity fallback (deterministic, offline)."""
    sql = """
        SELECT l.id AS lead_id,
               COALESCE(ls.final_score, l.score) AS lead_score,
               MAX(o.score) AS top_opportunity_score,
               (CASE WHEN lower(l.category) = lower(src.category) THEN 0 ELSE 1 END) AS same_category
        FROM leads l
        LEFT JOIN lead_scores ls ON ls.lead_id = l.id
        LEFT JOIN business_opportunities o ON o.lead_id = l.id
        JOIN leads src ON src.id = ?
        WHERE l.id != ?
        GROUP BY l.id
        ORDER BY same_category, COALESCE(ls.final_score, l.score) DESC,
                 (CASE WHEN l.phone IS NOT NULL AND l.phone != '' THEN 1 ELSE 0 END +
                  CASE WHEN l.email IS NOT NULL AND l.email != '' THEN 1 ELSE 0 END) DESC,
                 l.extracted_at DESC
        LIMIT ?
    """
    with connection_factory() as connection:
        return connection.execute(sql, (int(lead_id), int(lead_id), int(limit))).fetchall()


def _in_clause(column: str, value: Any, clauses: list[str], params: list[Any]) -> None:
    items = list(value) if isinstance(value, (list, tuple)) else [value]
    placeholders = ",".join("?" * len(items))
    clauses.append(f"{column} IN ({placeholders})")
    params.extend(str(item) for item in items)
