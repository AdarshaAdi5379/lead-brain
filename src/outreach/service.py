from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Optional, Sequence

from src.chat.llm import LLMBackend, NoLLMBackend, get_backend
from src.outreach import templates
from src.outreach.config import OutreachConfig, from_settings
from src.outreach.context import outreach_context_for_lead
from src.outreach.generator import (
    CONTACT_LABELS,
    OutreachDraft,
    available_contact_methods,
    generate_outreach,
)

logger = logging.getLogger("lead.outreach.service")

# Public service layer for the outreach engine. The dashboard calls these
# methods instead of touching storage, templates or the LLM directly. Like the
# chat service, everything is best-effort: generate() never raises -- failures
# degrade to a template draft (or a no-data draft when the lead is missing).


class OutreachService:
    """Grounded outreach generation over the lead intelligence database."""

    def __init__(
        self,
        db_path: Path,
        config: Optional[OutreachConfig] = None,
    ) -> None:
        self._db_path = Path(db_path)
        self.config = config or from_settings()
        self._backend: Optional[LLMBackend] = None

    # -- public API ----------------------------------------------------------

    def styles(self) -> Sequence[str]:
        return templates.STYLES

    def lengths(self) -> Sequence[str]:
        return templates.LENGTHS

    def backend_name(self) -> str:
        return self.backend().name

    def generate(
        self,
        lead_id: int,
        *,
        style: Optional[str] = None,
        length: Optional[str] = None,
        contact_method: str = "auto",
    ) -> OutreachDraft:
        """Generate an outreach draft for one lead (never raises)."""
        context = self._context_for(lead_id)
        if context is None:
            return OutreachDraft(
                message="No stored intelligence found for this lead.",
                style=style or self.config.default_style,
                length=length or self.config.default_length,
                mode="template",
                contact_method=None,
                contact_target=None,
                facts_used=[],
                facts_available=[],
                warnings=["The lead was not found in the database."],
                valid=False,
                issues=("missing lead",),
            )
        return generate_outreach(
            context,
            style=style or self.config.default_style,
            length=length or self.config.default_length,
            contact_method=contact_method,
            backend=self.backend(),
            config=self.config,
        )

    def contact_methods(self, lead_id: int) -> list[str]:
        """Available contact channels (plus "auto") for the dashboard."""
        context = self._context_for(lead_id)
        available = (
            available_contact_methods(context) if context is not None else []
        )
        return ["auto"] + available

    def contact_method_labels(self) -> dict[str, str]:
        return dict(CONTACT_LABELS)

    # -- internals -----------------------------------------------------------

    def backend(self) -> LLMBackend:
        if self._backend is None:
            try:
                self._backend = get_backend(self.config.to_chat_config())
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("Backend resolution failed: %s", exc)
                self._backend = NoLLMBackend()
        return self._backend

    def _context_for(self, lead_id: int) -> Optional[dict[str, Any]]:
        try:
            connection = sqlite3.connect(str(self._db_path))
            try:
                connection.row_factory = sqlite3.Row
                return outreach_context_for_lead(connection, int(lead_id))
            finally:
                connection.close()
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Context load failed for lead %s: %s", lead_id, exc)
            return None