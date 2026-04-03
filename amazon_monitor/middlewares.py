from __future__ import annotations

import random
import time
import logging
from typing import Any

from scrapy import signals
from scrapy.http import Request, Response
from scrapy.exceptions import IgnoreRequest

from amazon_monitor.utils.proxies import ProxyPool
from config.settings import get_settings

logger = logging.getLogger(__name__)

# ─── User-Agent pool (100+ agents) ────────────────────────────────────────────
_USER_AGENTS: list[str] = [
    # Chrome – Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    # Chrome – macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    # Chrome – Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    # Firefox – Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    # Firefox – macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13.6; rv:123.0) Gecko/20100101 Firefox/123.0",
    # Safari – macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
    # Edge
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
    # Mobile – Android Chrome
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.6312.86 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-A546B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36",
    # Mobile – iOS Safari
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
]

_ACCEPT_LANGUAGES = [
    "en-IN,en;q=0.9,hi;q=0.7",
    "en-IN,en-GB;q=0.9,en;q=0.8",
    "en-IN,en;q=0.9",
    "en-US,en;q=0.9,en-IN;q=0.8",
    "en-GB,en;q=0.9,en-IN;q=0.8,hi;q=0.5",
]

_ACCEPT_ENCODINGS = ["gzip, deflate, br", "gzip, deflate", "br, gzip"]

_ACCEPT_HEADERS = [
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
]

_SEC_CH_UA_LIST = [
    '"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"',
    '"Chromium";v="122", "Not:A-Brand";v="24", "Google Chrome";v="122"',
    '"Google Chrome";v="121", "Not:A-Brand";v="8", "Chromium";v="121"',
]


# ─── Middleware: Random User-Agent + Header Fingerprint ───────────────────────
class RandomUserAgentMiddleware:
    """Randomises User-Agent and all associated fingerprinting headers per request."""

    def process_request(self, request: Request, spider: Any) -> None:
        ua = random.choice(_USER_AGENTS)
        request.headers["User-Agent"] = ua
        request.headers["Accept"] = random.choice(_ACCEPT_HEADERS)
        request.headers["Accept-Language"] = random.choice(_ACCEPT_LANGUAGES)
        request.headers["Accept-Encoding"] = random.choice(_ACCEPT_ENCODINGS)
        request.headers["DNT"] = "1"
        request.headers["Upgrade-Insecure-Requests"] = "1"
        request.headers["Cache-Control"] = random.choice(["no-cache", "max-age=0", ""])

        # Chrome-specific headers (only when UA is Chrome)
        if "Chrome" in ua and "Mobile" not in ua:
            request.headers["Sec-Ch-Ua"] = random.choice(_SEC_CH_UA_LIST)
            request.headers["Sec-Ch-Ua-Mobile"] = "?0"
            request.headers["Sec-Ch-Ua-Platform"] = random.choice(['"Windows"', '"macOS"', '"Linux"'])
            request.headers["Sec-Fetch-Dest"] = "document"
            request.headers["Sec-Fetch-Mode"] = "navigate"
            request.headers["Sec-Fetch-Site"] = random.choice(["none", "same-origin"])
            request.headers["Sec-Fetch-User"] = "?1"


# ─── Middleware: Proxy Rotation ───────────────────────────────────────────────
class ProxyRotationMiddleware:
    """
    Rotates over a configurable proxy pool with retry-aware selection.
    Failed proxies are temporarily penalised (cool-down counter).
    """

    def __init__(self) -> None:
        self.proxy_pool = ProxyPool()
        self._fail_count: dict[str, int] = {}
        self._max_fails = 3

    def process_request(self, request: Request, spider: Any) -> None:
        proxy = self.proxy_pool.get_proxy(exclude=self._bad_proxies())
        if proxy:
            request.meta["proxy"] = proxy
            request.meta["_used_proxy"] = proxy
            logger.debug("Using proxy %s for %s", proxy, request.url)

    def process_response(self, request: Request, response: Response, spider: Any) -> Response:
        # Amazon CAPTCHA / block page
        if response.status in (503, 429) or b"robot" in response.body[:1000].lower():
            proxy = request.meta.get("_used_proxy")
            if proxy:
                self._fail_count[proxy] = self._fail_count.get(proxy, 0) + 1
                logger.warning("Proxy %s penalised (fails=%d)", proxy, self._fail_count[proxy])
        return response

    def process_exception(self, request: Request, exception: Exception, spider: Any) -> None:
        proxy = request.meta.get("_used_proxy")
        if proxy:
            self._fail_count[proxy] = self._fail_count.get(proxy, 0) + 1

    def _bad_proxies(self) -> set[str]:
        return {p for p, n in self._fail_count.items() if n >= self._max_fails}


# ─── Middleware: Exponential Back-off Retry ───────────────────────────────────
class ExponentialBackoffRetryMiddleware:
    """
    Overrides Scrapy's default flat retry with exponential back-off.
    Retries on: 429, 503, 403, connection errors, CAPTCHA responses.
    """

    MAX_RETRIES = 6
    BASE_DELAY  = 2.0   # seconds
    MAX_DELAY   = 120.0 # seconds

    RETRY_HTTP_CODES = {429, 503, 403, 408, 500, 502, 504}

    def process_response(self, request: Request, response: Response, spider: Any) -> Any:
        retries = request.meta.get("retry_count", 0)

        captcha = (
            b"captcha" in response.body[:4096].lower()
            or b"robot check" in response.body[:4096].lower()
            or b"sorry, we just need" in response.body[:4096].lower()
        )

        if (response.status in self.RETRY_HTTP_CODES or captcha) and retries < self.MAX_RETRIES:
            return self._retry(request, response.status, spider)
        return response

    def process_exception(self, request: Request, exception: Exception, spider: Any) -> Any | None:
        retries = request.meta.get("retry_count", 0)
        if retries < self.MAX_RETRIES:
            return self._retry(request, type(exception).__name__, spider)
        return None

    def _retry(self, request: Request, reason: Any, spider: Any) -> Request:
        retries = request.meta.get("retry_count", 0) + 1
        delay = min(self.BASE_DELAY * (2 ** (retries - 1)) + random.uniform(0, 1), self.MAX_DELAY)

        logger.info(
            "Retry %d/%d for %s (reason=%s) — back-off %.1fs",
            retries, self.MAX_RETRIES, request.url, reason, delay
        )
        time.sleep(delay)

        new_request = request.copy()
        new_request.meta["retry_count"] = retries
        new_request.dont_filter = True
        return new_request


# ─── Middleware: Request Throttle with Jitter ─────────────────────────────────
class HumanDelayMiddleware:
    """
    Injects a human-like random delay before each request.
    Normal range: 1–4s. Occasionally adds a 5–12s "reading" pause.
    """

    def process_request(self, request: Request, spider: Any) -> None:
        if request.meta.get("playwright"):
            # Playwright handles its own timing; add slight extra jitter
            jitter = random.uniform(0.3, 1.5)
        elif random.random() < 0.08:
            # 8% chance of a long "reading" pause
            jitter = random.uniform(5.0, 12.0)
        else:
            jitter = random.uniform(1.0, 4.0)
        time.sleep(jitter)


# ─── Middleware: Cookie Session Management ─────────────────────────────────────
class SessionCookieMiddleware:
    """
    Maintains a session cookie jar per proxy to simulate real browser sessions.
    Rotates session every ~30–60 requests.
    """

    def __init__(self) -> None:
        self._request_count: dict[str, int] = {}
        self._rotate_every = random.randint(30, 60)

    def process_request(self, request: Request, spider: Any) -> None:
        proxy = request.meta.get("proxy", "direct")
        count = self._request_count.get(proxy, 0) + 1
        self._request_count[proxy] = count

        if count % self._rotate_every == 0:
            # Force new cookie jar by clearing any stored cookies for this proxy
            request.meta["dont_merge_cookies"] = True
            logger.debug("Rotating cookie session for proxy %s", proxy)
