"""
Scrapy settings for amazon_monitor.

Loads app-level config from config.settings and wires up all middlewares,
pipelines, and Playwright integration.
"""
from __future__ import annotations

from config.settings import get_settings
from amazon_monitor.utils.fingerprint import random_viewport

app_settings = get_settings()
_vp = random_viewport()

BOT_NAME = "amazon_monitor"
SPIDER_MODULES = ["amazon_monitor.spiders"]
NEWSPIDER_MODULE = "amazon_monitor.spiders"

# ── Core crawl settings ────────────────────────────────────────────────────────
ROBOTSTXT_OBEY = False
DOWNLOAD_DELAY = 2
RANDOMIZE_DOWNLOAD_DELAY = True
CONCURRENT_REQUESTS = 4
CONCURRENT_REQUESTS_PER_DOMAIN = 2
DOWNLOAD_TIMEOUT = 45

# ── AutoThrottle ───────────────────────────────────────────────────────────────
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 2
AUTOTHROTTLE_MAX_DELAY = 15
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.5
AUTOTHROTTLE_DEBUG = False

# ── Retry ─────────────────────────────────────────────────────────────────────
RETRY_ENABLED = True
RETRY_TIMES = 5
RETRY_HTTP_CODES = [429, 500, 502, 503, 504, 403, 408]

# ── Cookies ───────────────────────────────────────────────────────────────────
COOKIES_ENABLED = True

# ── Pipelines ─────────────────────────────────────────────────────────────────
# Execution order:
#   100  ValidationPipeline     — drop invalid items
#   200  RawHtmlPipeline        — persist gzip HTML
#   250  JsonExportPipeline     — rolling JSONL backup
#   300  NormalisationPipeline  — clean numerics, synthesise seller_id
#   400  AmazonMonitoringPipeline — write to PostgreSQL + log scrape job
#   500  AlertEvaluationPipeline — fire alert rules
ITEM_PIPELINES = {
    "amazon_monitor.pipelines.ValidationPipeline":       100,
    "amazon_monitor.pipelines.RawHtmlPipeline":          200,
    "amazon_monitor.pipelines.JsonExportPipeline":       250,
    "amazon_monitor.pipelines.NormalisationPipeline":    300,
    "amazon_monitor.pipelines.AmazonMonitoringPipeline": 400,
    "amazon_monitor.pipelines.AlertEvaluationPipeline":  500,
}

# ── Middlewares ────────────────────────────────────────────────────────────────
DOWNLOADER_MIDDLEWARES = {
    # Disable Scrapy's built-in UA middleware
    "scrapy.downloadermiddlewares.useragent.UserAgentMiddleware": None,
    # Our custom stack (lower number = runs first on request)
    "amazon_monitor.middlewares.RandomUserAgentMiddleware": 300,
    "amazon_monitor.middlewares.ProxyRotationMiddleware": 350,
    "amazon_monitor.middlewares.SessionCookieMiddleware": 380,
    "amazon_monitor.middlewares.HumanDelayMiddleware": 390,
    # Disable Scrapy's default retry; use our exponential back-off instead
    "scrapy.downloadermiddlewares.retry.RetryMiddleware": None,
    "amazon_monitor.middlewares.ExponentialBackoffRetryMiddleware": 550,
    # Playwright
    "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler": 800,
}

DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}

# ── Playwright browser configuration ──────────────────────────────────────────
PLAYWRIGHT_BROWSER_TYPE = "chromium"
PLAYWRIGHT_LAUNCH_OPTIONS = {
    "headless": True,
    "args": [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--disable-extensions",
        "--disable-dev-shm-usage",
        "--disable-web-security",
        "--ignore-certificate-errors",
        "--lang=en-IN",
        f"--window-size={_vp['width']},{_vp['height']}",
    ],
}
PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = 45_000   # ms
PLAYWRIGHT_CONTEXTS = {
    "default": {
        "viewport": _vp,
        "locale": "en-IN",
        "timezone_id": "Asia/Kolkata",
        "geolocation": {"longitude": 80.2707, "latitude": 13.0827},  # Chennai
        "permissions": ["geolocation"],
        "java_script_enabled": True,
        "bypass_csp": True,
        "color_scheme": "light",
        "extra_http_headers": {
            "Accept-Language": "en-IN,en;q=0.9",
        },
    }
}

# ── Default headers ────────────────────────────────────────────────────────────
DEFAULT_REQUEST_HEADERS = {
    "Accept-Language": "en-IN,en;q=0.9,hi;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Upgrade-Insecure-Requests": "1",
}

# ── Feed exports (raw JSON backup) ────────────────────────────────────────────
FEEDS = {
    "output/scraped_%(time)s.jsonl": {
        "format": "jsonlines",
        "encoding": "utf8",
        "overwrite": False,
        "indent": None,
    }
}

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL = "INFO"
