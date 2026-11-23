FROM apify/actor-python-playwright:3.12

# Playwright + Chromium browsers are preinstalled in this base image.
COPY requirements-actor.txt ./
RUN pip install --no-cache-dir -r requirements-actor.txt

# Keep every ephemeral write off the (read-only-ish) app dir and out of the
# image: crawl/discovery/visual caches live under /tmp per run.
ENV PYTHONUNBUFFERED=1 \
    CRAWL_CACHE_DIR=/tmp/lead-cache/crawl \
    DISCOVERY_CACHE_DIR=/tmp/lead-cache/discovery \
    VISUAL_SCREENSHOT_DIR=/tmp/lead-cache/screenshots \
    SEARCH_CHROMA_DIR=/tmp/lead-cache/chroma

COPY . ./

CMD ["python", "-m", "src.apify_entry"]
