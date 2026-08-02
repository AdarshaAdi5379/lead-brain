from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit

from src.scraping.browser_fetch import ScreenshotResult
from src.visual.base import PAGE_TYPE_HOME, PAGE_TYPE_INTERNAL, VARIANT_DESKTOP, VARIANT_MOBILE
from src.visual.config import VisualConfig

# Screenshot planning + capture. Bounded (max 5 screenshots per lead), hash
# based on-disk paths, best-effort reuse of existing PNGs. Nothing here runs
# when the visual stage is disabled or Playwright is unavailable.

PROBE_SIDECAR = "probe.json"
_HASH_PREFIX = 16


@dataclass(frozen=True)
class CaptureJob:
    url: str
    page_type: str
    variant: str
    width: int
    height: int


@dataclass(frozen=True)
class ScreenshotRef:
    url: str
    page_type: str
    variant: str
    path: str
    width: int
    height: int
    full_page: bool
    probe: dict
    screenshot_hash: str
    file_size: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "page_type": self.page_type,
            "variant": self.variant,
            "path": self.path,
            "width": self.width,
            "height": self.height,
            "full_page": self.full_page,
            "probe": self.probe,
            "screenshot_hash": self.screenshot_hash,
            "file_size": self.file_size,
        }


def normalize_capture_url(url: str) -> str:
    """Normalize a URL for dedupe (scheme/host lowercase, no fragment, no slash)."""
    url = (url or "").strip()
    if not url:
        return ""
    parts = urlsplit(url)
    path = parts.path.rstrip("/")
    query = f"?{parts.query}" if parts.query else ""
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}{path}{query}"


def lead_screenshot_dir(config: VisualConfig, home_url: str) -> Path:
    digest = hashlib.sha256(normalize_capture_url(home_url).encode("utf-8")).hexdigest()
    return Path(config.screenshot_dir) / digest[:_HASH_PREFIX]


def plan_captures(
    home_url: str,
    crawl_pages: Any,
    config: VisualConfig,
) -> list[CaptureJob]:
    """Plan at most ``max_screenshots`` capture jobs per lead.

    Homepage always gets desktop + mobile variants; up to ``max_internal_pages``
    crawled pages get a desktop variant only. Pages are deduped by normalized
    URL and the home URL itself is never re-captured as an internal page.
    """
    jobs: list[CaptureJob] = []
    home_norm = normalize_capture_url(home_url)
    desktop_w, desktop_h = config.viewport_desktop
    mobile_w, mobile_h = config.viewport_mobile

    jobs.append(
        CaptureJob(home_url, PAGE_TYPE_HOME, VARIANT_DESKTOP, desktop_w, desktop_h)
    )
    if len(jobs) < config.max_screenshots:
        jobs.append(CaptureJob(home_url, PAGE_TYPE_HOME, VARIANT_MOBILE, mobile_w, mobile_h))

    seen = {home_norm}
    for page in _iter_pages(crawl_pages):
        if len(jobs) >= config.max_screenshots:
            break
        url = str(page.get("url") or "").strip()
        if not url:
            continue
        if normalize_capture_url(url) in seen:
            continue
        seen.add(normalize_capture_url(url))
        jobs.append(
            CaptureJob(url, PAGE_TYPE_INTERNAL, VARIANT_DESKTOP, desktop_w, desktop_h)
        )
    return jobs


def _iter_pages(crawl_pages: Any) -> list[dict]:
    if crawl_pages is None:
        return []
    if isinstance(crawl_pages, (list, tuple)):
        return [p for p in crawl_pages if isinstance(p, dict)]
    if isinstance(crawl_pages, dict):
        return [p for p in crawl_pages.get("pages", []) if isinstance(p, dict)]
    return []


def capture_for_lead(
    fetcher: Any,
    home_url: str,
    crawl_pages: Any,
    config: VisualConfig,
    run_cache: Optional[dict[str, str]] = None,
) -> list[ScreenshotRef]:
    """Capture (or reuse) the planned screenshots for one lead.

    Synchronous wrapper around the async fetcher used by the pipeline; the
    fetcher is expected to implement ``async screenshot(...)``. Screenshots
    are skipped silently on failure so the audit never breaks the run.
    """
    import asyncio

    return asyncio.run(
        _capture_for_lead_async(fetcher, home_url, crawl_pages, config, run_cache)
    )


async def _capture_for_lead_async(
    fetcher: Any,
    home_url: str,
    crawl_pages: Any,
    config: VisualConfig,
    run_cache: Optional[dict[str, str]] = None,
) -> list[ScreenshotRef]:
    cache = run_cache if run_cache is not None else {}
    lead_dir = lead_screenshot_dir(config, home_url)
    probes = _load_probes(lead_dir)

    refs: list[ScreenshotRef] = []
    for index, job in enumerate(plan_captures(home_url, crawl_pages, config)):
        cache_key = (job.url, job.variant)
        if cache_key in cache:
            continue
        path = lead_dir / f"{index}_{job.page_type}_{job.variant}.png"
        probe = probes.get(f"{job.variant}:{normalize_capture_url(job.url)}", {})
        ref = await _capture_one(fetcher, job, path, probe, config)
        if ref is None:
            continue
        cache[cache_key] = ref.path
        probes[f"{job.variant}:{normalize_capture_url(job.url)}"] = ref.probe or probe
        refs.append(ref)

    _save_probes(lead_dir, probes)
    return refs


async def _capture_one(
    fetcher: Any,
    job: CaptureJob,
    path: Path,
    probe: dict,
    config: VisualConfig,
) -> Optional[ScreenshotRef]:
    if path.exists() and not config.recapture:
        result = _reuse_screenshot(job, path, probe, config)
    else:
        result = await _shoot(fetcher, job, path, config)
    return build_ref(job, result, path, config)


def _reuse_screenshot(
    job: CaptureJob, path: Path, probe: dict, config: VisualConfig
) -> Optional[ScreenshotResult]:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return ScreenshotResult(
        url=job.url,
        final_url=job.url,
        width=job.width,
        height=job.height,
        full_page=False,
        probe=probe,
    )


async def _shoot(
    fetcher: Any,
    job: CaptureJob,
    path: Path,
    config: VisualConfig,
) -> Optional[ScreenshotResult]:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = await fetcher.screenshot(
            job.url,
            str(path),
            width=job.width,
            height=job.height,
            max_full_height=config.fullpage_max_height,
        )
    except Exception:
        return None
    if result is None or result.error:
        return None
    return result


def screenshot_metadata(path: Path) -> Optional[dict[str, Any]]:
    """Best-effort hash + size for a PNG already on disk."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return {
        "screenshot_hash": hashlib.sha256(data).hexdigest(),
        "file_size": len(data),
    }


def build_ref(
    job: CaptureJob,
    result: Optional[ScreenshotResult],
    path: Path,
    config: VisualConfig,
) -> Optional[ScreenshotRef]:
    if result is None:
        return None
    meta = screenshot_metadata(path)
    if meta is None:
        return None
    return ScreenshotRef(
        url=job.url,
        page_type=job.page_type,
        variant=job.variant,
        path=str(path),
        width=job.width,
        height=job.height,
        full_page=result.full_page,
        probe=result.probe or {},
        screenshot_hash=meta["screenshot_hash"],
        file_size=meta["file_size"],
    )


def _load_probes(lead_dir: Path) -> dict[str, Any]:
    try:
        with (lead_dir / PROBE_SIDECAR).open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_probes(lead_dir: Path, probes: dict[str, Any]) -> None:
    if not probes:
        return
    try:
        lead_dir.mkdir(parents=True, exist_ok=True)
        with (lead_dir / PROBE_SIDECAR).open("w", encoding="utf-8") as handle:
            json.dump(probes, handle, ensure_ascii=False)
    except OSError:
        pass
