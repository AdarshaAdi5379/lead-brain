from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class FetchResult:
    url: str
    final_url: Optional[str]
    success: bool
    status: Optional[int]
    html: Optional[str]
    text: Optional[str]
    error: Optional[str]


def _limit_chars(value: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    return value[:max_chars]


class PlaywrightFetcher:
    """
    Minimal Playwright-based page fetcher for v1.

    Notes:
    - Lazy-imports Playwright so the rest of the codebase can run without it installed.
    - Returns both rendered HTML and visible text, capped by max char limits.
    """

    def __init__(
        self,
        *,
        headless: bool = True,
        timeout_ms: int = 45_000,
        wait_until: str = "networkidle",
        max_html_chars: int = 800_000,
        max_text_chars: int = 120_000,
    ) -> None:
        self._headless = headless
        self._timeout_ms = timeout_ms
        self._wait_until = wait_until
        self._max_html_chars = max_html_chars
        self._max_text_chars = max_text_chars

        self._playwright = None
        self._browser = None

    async def __aenter__(self) -> "PlaywrightFetcher":
        try:
            from playwright.async_api import async_playwright  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "Playwright is not installed. Install it with `pip install playwright` "
                "and then run `playwright install`."
            ) from exc

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self._headless)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()

    async def fetch(self, url: str) -> FetchResult:
        if self._browser is None:
            raise RuntimeError("PlaywrightFetcher must be used as an async context manager")

        context = await self._browser.new_context()
        page = await context.new_page()

        try:
            response = await page.goto(
                url,
                wait_until=self._wait_until,
                timeout=self._timeout_ms,
            )

            status = response.status if response is not None else None
            final_url = page.url

            html = await page.content()
            # Visible text (best-effort). On some sites, this can throw; treat as optional.
            try:
                text = await page.evaluate("() => document.body ? document.body.innerText : ''")
            except Exception:
                text = ""

            html_limited = _limit_chars(html, self._max_html_chars) if html else ""
            text_limited = _limit_chars(text or "", self._max_text_chars)

            # Basic blocked/empty detection: success if we got meaningful content.
            meaningful = len(text_limited.strip()) > 50 or len(html_limited.strip()) > 500
            return FetchResult(
                url=url,
                final_url=final_url,
                success=bool(response) and meaningful,
                status=status,
                html=html_limited or None,
                text=text_limited or None,
                error=None if meaningful else "Empty or blocked page",
            )
        except Exception as exc:
            return FetchResult(
                url=url,
                final_url=None,
                success=False,
                status=None,
                html=None,
                text=None,
                error=str(exc),
            )
        finally:
            await page.close()
            await context.close()


def fetch_page_sync(
    url: str,
    *,
    headless: bool = True,
    timeout_ms: int = 45_000,
    wait_until: str = "networkidle",
    max_html_chars: int = 800_000,
    max_text_chars: int = 120_000,
) -> FetchResult:
    async def _run() -> FetchResult:
        async with PlaywrightFetcher(
            headless=headless,
            timeout_ms=timeout_ms,
            wait_until=wait_until,
            max_html_chars=max_html_chars,
            max_text_chars=max_text_chars,
        ) as fetcher:
            return await fetcher.fetch(url)

    return asyncio.run(_run())

