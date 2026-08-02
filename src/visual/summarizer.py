from __future__ import annotations

import base64
import io
from typing import Any, Optional

from PIL import Image

from src.visual.base import PAGE_TYPE_HOME
from src.visual.capture import ScreenshotRef
from src.visual.config import VisualConfig

# Optional multimodal summarizer. Gated by VISUAL_LLM_ENABLED so the pipeline
# runs fully offline by default; every failure degrades to None (the
# deterministic report still stands on its own).

_LLM_MAX_EDGE = 512
_LLM_JPEG_QUALITY = 70
_LLM_MAX_TOKENS = 400

_PROMPT = (
    "You are reviewing screenshots of a small business website. "
    "Return ONLY a JSON object with exactly these keys: "
    '"summary" (one sentence, <=200 chars, neutral and specific), '
    '"issues" (array of <=4 short issue strings), '
    '"strengths" (array of <=3 short strength strings). '
    "Do not invent facts; if unsure, keep the summary generic."
)


def summarize_visual(refs: list[ScreenshotRef], config: VisualConfig) -> Optional[dict[str, Any]]:
    """Optional LLM summary from the homepage screenshots; None when gated off.

    Returns a dict with ``summary`` (str), ``issues`` (list[str]) and
    ``strengths`` (list[str]) when the model responds with structured JSON;
    None on any failure so the deterministic report stands on its own.
    """
    if not config.llm_enabled:
        return None
    try:
        from src.llm.openai_responses import create_vision_response
    except Exception:
        return None

    images = _pick_homepage_images(refs, config.llm_max_images)
    if not images:
        return None

    try:
        result = create_vision_response(
            images=images,
            model=config.llm_model,
            prompt=_PROMPT,
            max_tokens=_LLM_MAX_TOKENS,
        )
    except Exception:
        return None
    return _extract_result(result)


def _pick_homepage_images(refs: list[ScreenshotRef], limit: int) -> list[str]:
    picked: list[str] = []
    for ref in refs:
        if len(picked) >= limit:
            break
        if ref.page_type != PAGE_TYPE_HOME:
            continue
        data = _image_to_jpeg_base64(ref.path)
        if data is not None:
            picked.append(data)
    return picked


def _image_to_jpeg_base64(path: str) -> Optional[str]:
    """Downscaled JPEG base64 payload; None for unreadable images."""
    try:
        with Image.open(path) as image:
            scale = min(1.0, _LLM_MAX_EDGE / max(image.width, image.height))
            width = max(1, int(image.width * scale))
            height = max(1, int(image.height * scale))
            resized = image.convert("RGB").resize((width, height))
            buffer = io.BytesIO()
            resized.save(buffer, format="JPEG", quality=_LLM_JPEG_QUALITY)
            return base64.b64encode(buffer.getvalue()).decode("ascii")
    except (OSError, ValueError, SyntaxError):
        return None


def _extract_result(result: Any) -> Optional[dict[str, Any]]:
    """Normalize the model's JSON into a summary/issues/strengths dict."""
    if not isinstance(result, dict):
        return None
    summary = result.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        return None
    issues = [
        str(item) for item in (result.get("issues") or [])
        if isinstance(item, (str, int, float))
    ][:4]
    strengths = [
        str(item) for item in (result.get("strengths") or [])
        if isinstance(item, (str, int, float))
    ][:3]
    return {"summary": summary.strip(), "issues": issues, "strengths": strengths}
