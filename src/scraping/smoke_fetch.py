from __future__ import annotations

import argparse
from dataclasses import asdict

from src.scraping.browser_fetch import fetch_page_sync


def main() -> None:
    parser = argparse.ArgumentParser(description="Playwright fetch smoke test (v1).")
    parser.add_argument("url", help="URL to fetch (e.g. https://example.com)")
    args = parser.parse_args()

    result = fetch_page_sync(args.url)
    payload = asdict(result)
    # Avoid dumping huge HTML to console; show lengths instead.
    html = payload.pop("html")
    text = payload.pop("text")
    payload["html_chars"] = len(html or "")
    payload["text_chars"] = len(text or "")
    print(payload)


if __name__ == "__main__":
    main()

