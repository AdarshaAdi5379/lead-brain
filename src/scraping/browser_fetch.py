from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlsplit

from src.net.url_guard import ALLOWED_SCHEMES, UnsafeUrlError, validate_public_http_url

# Schemes that never open a network connection and are harmless as embedded
# subresources (inline images/fonts/iframes). Everything else that is not
# http(s) is aborted at the routing layer.
_NON_NETWORK_REQUEST_SCHEMES = frozenset({"data", "blob", "about"})


def _route_request_allowed(url: str, host_cache: dict[str, bool]) -> bool:
    """Trust-boundary check for Playwright route interception (sync, off-loop).

    Runs in an executor for every request Chromium makes, including redirect
    hops and frame navigations: a page must not be able to send the browser to
    ``file://``, localhost, or private/internal IPs.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    scheme = (parts.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        return scheme in _NON_NETWORK_REQUEST_SCHEMES

    host = (parts.hostname or "").strip().rstrip(".").lower()
    allowed = host_cache.get(host)
    if allowed is None:
        try:
            validate_public_http_url(url)  # full check incl. DNS resolution
        except UnsafeUrlError:
            allowed = False
        else:
            allowed = True
        if host:
            # Only successes are cached; failures are re-evaluated each time
            # so a transient DNS outage can't poison the boundary.
            host_cache[host] = allowed
    return allowed


@dataclass(frozen=True)
class FetchResult:
    url: str
    final_url: Optional[str]
    success: bool
    status: Optional[int]
    html: Optional[str]
    text: Optional[str]
    error: Optional[str]
    headers: Optional[dict[str, str]] = None
    cookies: Optional[list[dict]] = None


@dataclass(frozen=True)
class ScreenshotResult:
    url: str
    final_url: Optional[str]
    width: int
    height: int
    full_page: bool
    probe: dict
    error: Optional[str] = None


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

    async def _install_route_guard(self, context) -> None:
        """Abort any requested URL that fails the public-URL trust boundary.

        Chromium routes every request (documents, redirect hop destinations,
        frames, subresources) through this handler, so a malicious site cannot
        bounce the browser to file://, localhost, link-local or RFC1918 targets.

        Known limitation (documented, accepted): a classic TOCTOU DNS-rebinding
        race between our validation and Chromium's own connect cannot be fully
        closed without proxying all browser traffic; this resolves the hostname
        at request time and validates every returned address instead.
        """
        host_cache: dict[str, bool] = {}

        async def _guard(route) -> None:
            try:
                ok = await asyncio.get_running_loop().run_in_executor(
                    None, _route_request_allowed, route.request.url, host_cache
                )
            except Exception:
                ok = False
            try:
                if ok:
                    await route.continue_()
                else:
                    await route.abort()
            except Exception:  # pragma: no cover - page/route already gone
                pass

        await context.route("**/*", _guard)

    async def fetch(self, url: str) -> FetchResult:
        if self._browser is None:
            raise RuntimeError("PlaywrightFetcher must be used as an async context manager")

        # Trust boundary before any navigation: unsafe URLs never reach Chromium.
        try:
            validated_url = validate_public_http_url(url)
        except UnsafeUrlError as exc:
            return FetchResult(
                url=url,
                final_url=None,
                success=False,
                status=None,
                html=None,
                text=None,
                error=str(exc),
            )

        context = await self._browser.new_context()
        await self._install_route_guard(context)
        page = await context.new_page()

        try:
            try:
                response = await page.goto(
                    validated_url,
                    wait_until=self._wait_until,
                    timeout=self._timeout_ms,
                )
            except Exception as nav_exc:
                # If networkidle timed out, check if the DOM already loaded
                if "networkidle" in str(nav_exc).lower() or "timeout" in str(nav_exc).lower():
                    try:
                        content_check = await page.content()
                        if len(content_check) > 500:
                            response = None
                        else:
                            raise nav_exc
                    except Exception:
                        raise nav_exc
                else:
                    raise nav_exc

            status = response.status if response is not None else 200
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

            headers: dict[str, str] | None = None
            cookies: list[dict] | None = None
            try:
                if response is not None:
                    headers = dict(response.headers)
            except Exception:  # pragma: no cover - best effort
                headers = None
            try:
                cookies = await context.cookies()
            except Exception:  # pragma: no cover - best effort
                cookies = None

            return FetchResult(
                url=url,
                final_url=final_url,
                success=meaningful,
                status=status,
                html=html_limited or None,
                text=text_limited or None,
                error=None if meaningful else "Empty or blocked page",
                headers=headers,
                cookies=cookies,
            )
        except Exception as exc:
            # Salvage partial content if page loaded but timed out or threw
            try:
                html = await page.content()
                try:
                    text = await page.evaluate("() => document.body ? document.body.innerText : ''")
                except Exception:
                    text = ""
                html_limited = _limit_chars(html, self._max_html_chars) if html else ""
                text_limited = _limit_chars(text or "", self._max_text_chars)
                if len(text_limited.strip()) > 50 or len(html_limited.strip()) > 500:
                    return FetchResult(
                        url=url,
                        final_url=page.url or url,
                        success=True,
                        status=200,
                        html=html_limited,
                        text=text_limited,
                        error=None,
                    )
            except Exception:
                pass

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

    async def screenshot(
        self,
        url: str,
        output_path: str,
        *,
        width: int = 1365,
        height: int = 900,
        max_full_height: int = 12_000,
        timeout_ms: int = 20_000,
    ) -> Optional[ScreenshotResult]:
        """
        Capture a rendered screenshot at a fixed viewport size.

        Navigates with wait_until="load" (shorter timeout than fetch), runs a
        lightweight JS probe (viewport, overflow, CTA counts, body background),
        then saves a full-page PNG when the page is not taller than
        max_full_height, otherwise a viewport-only PNG. Returns None on any
        failure so the visual audit never breaks the pipeline.
        """
        if self._browser is None:
            raise RuntimeError("PlaywrightFetcher must be used as an async context manager")

        # Trust boundary before any navigation: unsafe URLs never reach Chromium.
        try:
            validated_url = validate_public_http_url(url)
        except UnsafeUrlError as exc:
            return ScreenshotResult(
                url=url,
                final_url=None,
                width=width,
                height=height,
                full_page=False,
                probe={},
                error=str(exc),
            )

        context = await self._browser.new_context(
            viewport={"width": width, "height": height},
            device_scale_factor=1,
        )
        await self._install_route_guard(context)
        page = await context.new_page()

        try:
            response = await page.goto(validated_url, wait_until="load", timeout=timeout_ms)
            final_url = page.url

            probe: dict = {}
            try:
                probe = await page.evaluate(
                    """() => {
                        const w = window;
                        const doc = document.documentElement;
                        const body = document.body;
                        const bgOf = (el) => el ? w.getComputedStyle(el).backgroundColor : '';
                        const bodyBg = bgOf(body) || bgOf(doc) || '';
                        const cta = Array.from(doc.querySelectorAll('button, a')).filter((el) => {
                            const cls = (el.className && String(el.className)) || '';
                            const txt = (el.textContent || '').trim().toLowerCase();
                            return /btn|cta|button/i.test(cls)
                                || /(get started|start|book|contact|call|quote|learn more|schedule|order|buy|request)/i.test(txt);
                        }).length;
                        return {
                            inner_width: w.innerWidth,
                            inner_height: w.innerHeight,
                            scroll_width: doc.scrollWidth,
                            scroll_height: doc.scrollHeight,
                            horizontal_overflow: doc.scrollWidth > w.innerWidth + 1,
                            cta_count: cta,
                            tel_links: doc.querySelectorAll('a[href^="tel:"]').length,
                            mailto_links: doc.querySelectorAll('a[href^="mailto:"]').length,
                            body_bg: bodyBg,
                        };
                    }"""
                )
            except Exception:
                probe = {}

            scroll_height = int(probe.get("scroll_height") or 0)
            full_page = scroll_height <= max_full_height

            if full_page:
                await page.screenshot(path=output_path, full_page=True)
            else:
                await page.screenshot(path=output_path, clip={"x": 0, "y": 0, "width": width, "height": height})

            return ScreenshotResult(
                url=url,
                final_url=final_url,
                width=width,
                height=height,
                full_page=full_page,
                probe=probe,
            )
        except Exception as exc:
            # If load timed out, try capturing a viewport screenshot anyway
            try:
                await page.screenshot(path=output_path, clip={"x": 0, "y": 0, "width": width, "height": height})
                return ScreenshotResult(
                    url=url,
                    final_url=page.url or url,
                    width=width,
                    height=height,
                    full_page=False,
                    probe={},
                    error=None,
                )
            except Exception:
                pass

            return ScreenshotResult(
                url=url,
                final_url=None,
                width=width,
                height=height,
                full_page=False,
                probe={},
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

