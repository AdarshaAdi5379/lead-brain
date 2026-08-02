from __future__ import annotations

"""Deterministic, offline, local SEO audit engine (Phase 12).

No paid APIs, no cloud calls, no ML: every check runs locally over the HTML
the focused crawler already collected. The LLM only consumes the audit
summary as neutral prompt context; it never performs SEO detection.
"""
