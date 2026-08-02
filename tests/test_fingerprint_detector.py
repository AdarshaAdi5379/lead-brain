import unittest

from src.fingerprinting.base import Detection, Signal
from src.fingerprinting.detector import (
    FingerprintResult,
    SiteEvidence,
    TechnologyDetector,
    build_site_evidence,
)

WORDPRESS_PAGE = """<html><head>
<meta name="generator" content="WordPress 6.5">
<title>Acme Plumbing</title>
</head><body><div class="wp-container">
<script src="/wp-content/themes/acme/js/main.js"></script>
<link rel="stylesheet" href="/wp-content/themes/acme/style.css">
</div></body></html>"""

SHOPIFY_PAGE = """<html><head><title>Shop</title></head><body>
<script src="https://cdn.shopify.com/s/files/t/1/0000/0000/assets/main.js"></script>
<script>window.ShopifyAnalytics = window.ShopifyAnalytics || {};</script>
</body></html>"""

REACT_NEXT_PAGE = """<html><head>
<meta name="generator" content="Next.js 14.0">
<script src="/_next/static/chunks/main.js"></script>
<script src="https://cdn.example.com/react.production.min.js"></script>
</head><body><script id="__NEXT_DATA__" type="application/json">{}</script>
<div id="root"></div></body></html>"""

BOOTSTRAP_PAGE = """<html><head>
<link rel="stylesheet" href="https://cdn.example.com/bootstrap.min.css">
</head><body><div class="container col-md-8 row">hello</div>
<script src="https://cdn.example.com/jquery.min.js"></script>
</body></html>"""

BACKEND_PAGE = """<html><body><form><input name="csrfmiddlewaretoken"></form></body></html>"""

CLOUDFLARE_HEADERS = {
    "server": "cloudflare",
    "cf-ray": "abc-123",
    "content-type": "text/html; charset=utf-8",
}

GA_JS = """(function(w){
  w.dataLayer = w.dataLayer || [];
  w.dataLayer.push(arguments);
})(window);"""


def _detect(
    html: str,
    headers: dict[str, str] | None = None,
    cookies: list[dict] | None = None,
    min_confidence: int = 25,
) -> FingerprintResult:
    evidence: SiteEvidence = build_site_evidence(html, headers=headers, cookies=cookies)
    return TechnologyDetector(min_confidence=min_confidence).detect(
        evidence, site_url="https://example.com/"
    )


class TestTechnologyDetector(unittest.TestCase):
    def test_wordpress_detected(self) -> None:
        result = _detect(WORDPRESS_PAGE)
        self.assertGreaterEqual(result.confidence("WordPress"), 25)

    def test_shopify_detected_via_markup_and_global(self) -> None:
        result = _detect(SHOPIFY_PAGE)
        self.assertGreaterEqual(result.confidence("Shopify"), 25)

    def test_next_js_and_react_detected(self) -> None:
        result = _detect(REACT_NEXT_PAGE)
        self.assertGreaterEqual(result.confidence("Next.js"), 25)
        self.assertGreaterEqual(result.confidence("React"), 25)

    def test_bootstrap_and_jquery_detected(self) -> None:
        result = _detect(BOOTSTRAP_PAGE)
        self.assertGreaterEqual(result.confidence("Bootstrap"), 25)
        self.assertGreaterEqual(result.confidence("jQuery"), 25)

    def test_django_backend_detected_via_cookie(self) -> None:
        result = _detect(
            BACKEND_PAGE,
            cookies=[{"name": "csrftoken", "value": "abc123"}],
        )
        self.assertGreaterEqual(result.confidence("Django"), 25)

    def test_cloudflare_detected_from_headers(self) -> None:
        result = _detect("<html></html>", headers=CLOUDFLARE_HEADERS)
        self.assertGreaterEqual(result.confidence("Cloudflare"), 25)

    def test_analytics_detected_from_inline_js(self) -> None:
        html = (
            "<html><head>"
            '<script async src="https://www.googletagmanager.com/gtag/js?id=G-ABC123"></script>'
            "</head><body><script>" + GA_JS + "</script></body></html>"
        )
        result = _detect(html)
        self.assertGreaterEqual(result.confidence("Google Analytics"), 25)

    def test_unknown_site_no_false_positives(self) -> None:
        html = "<html><head><title>Blank</title></head><body><p>hello world</p></body></html>"
        result = _detect(html)
        # Very little should collide with a blank page.
        self.assertLess(len(result.detections), 3)

    def test_min_confidence_filters(self) -> None:
        result = _detect(WORDPRESS_PAGE, min_confidence=90)
        self.assertNotIn("WordPress", [d.name for d in result.detections])

    def test_result_api(self) -> None:
        result = _detect(WORDPRESS_PAGE)
        self.assertTrue(result.has("WordPress"))
        self.assertEqual(result.site_url, "https://example.com/")
        cms = result.by_category("cms")
        self.assertGreaterEqual(len(cms), 1)
        for detection in result.detections:
            self.assertLessEqual(detection.confidence, 100)

    def test_platform_override_mapping_full_game(self) -> None:
        result = _detect(WORDPRESS_PAGE)
        detections = result.detections
        self.assertTrue(any(d.name == "WordPress" for d in detections))


if __name__ == "__main__":
    unittest.main()