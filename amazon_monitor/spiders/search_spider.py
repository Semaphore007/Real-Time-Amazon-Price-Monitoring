"""
SearchSpider – Amazon.in bearing search + product detail + offer listing.

Flow:
  1. start_requests()  →  Amazon search results (Playwright)
  2. parse_search()    →  extract ASINs, follow pagination
  3. parse_product()   →  product detail page (Playwright + stealth)
  4. parse_offers()    →  /gp/offer-listing/ for every competing seller

Anti-bot measures:
  - Random viewport & stealth JS via fingerprint.py
  - Human-like mouse movement + scroll via page_coroutines
  - Random delays (handled by HumanDelayMiddleware)
  - Proxy rotation (ProxyRotationMiddleware)
  - Exponential back-off retry (ExponentialBackoffRetryMiddleware)
  - Raw HTML stored for every product page (RawHtmlPipeline)
"""
from __future__ import annotations

import asyncio
import logging
import re
import random
from datetime import datetime, timezone
from urllib.parse import urlencode

import scrapy
from bs4 import BeautifulSoup

from amazon_monitor.items import ProductSnapshotItem
from amazon_monitor.utils.fingerprint import apply_stealth, human_mouse_movement, random_scroll
from config.settings import get_settings

logger = logging.getLogger(__name__)

# Pincode → (city, state) mapping for request headers
_PINCODE_MAP: dict[str, tuple[str, str]] = {
    "600001": ("Chennai", "Tamil Nadu"),
    "560001": ("Bangalore", "Karnataka"),
    "110001": ("Delhi", "Delhi"),
    "400001": ("Mumbai", "Maharashtra"),
    "700001": ("Kolkata", "West Bengal"),
}


class SearchSpider(scrapy.Spider):
    """
    Main entry-point spider.

    Run with::

        scrapy crawl amazon_search
        scrapy crawl amazon_search -a queries="SKF bearing 6205,SKF bearing 6203"
        scrapy crawl amazon_search -a max_pages=3
    """

    name = "amazon_search"
    allowed_domains = ["amazon.in"]

    def __init__(
        self,
        queries: str | None = None,
        max_pages: int = 5,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        settings = get_settings()
        self._queries: list[str] = (
            [q.strip() for q in queries.split(",") if q.strip()]
            if queries
            else list(settings.scrape_queries)
        )
        self._locations: list[str] = list(settings.location_pincodes)
        self._max_pages = int(max_pages)

    # ── 1. Seed requests ──────────────────────────────────────────────────────

    def start_requests(self):
        for query in self._queries:
            for location in self._locations:
                url = f"https://www.amazon.in/s?{urlencode({'k': query})}"
                yield scrapy.Request(
                    url,
                    callback=self.parse_search,
                    errback=self.handle_error,
                    meta=self._playwright_meta(
                        query=query,
                        location=location,
                        page_num=1,
                        page_coroutines=self._search_coroutines(),
                    ),
                    headers=self._location_headers(location),
                )

    # ── 2. Parse search results page ─────────────────────────────────────────

    def parse_search(self, response):
        products = response.css("div[data-component-type='s-search-result']")
        logger.info(
            "Search page: found %d products [query=%s location=%s page=%d]",
            len(products),
            response.meta.get("query"),
            response.meta.get("location"),
            response.meta.get("page_num", 1),
        )

        for product in products:
            asin = product.attrib.get("data-asin", "").strip()
            if not asin:
                continue
            yield scrapy.Request(
                f"https://www.amazon.in/dp/{asin}",
                callback=self.parse_product,
                errback=self.handle_error,
                meta=self._playwright_meta(
                    query=response.meta.get("query"),
                    location=response.meta.get("location"),
                    asin=asin,
                    page_coroutines=self._product_coroutines(),
                ),
                headers=self._location_headers(response.meta.get("location", "")),
            )

        # ── Pagination ────────────────────────────────────────────────────────
        page_num = response.meta.get("page_num", 1)
        if page_num < self._max_pages:
            next_href = response.css("a.s-pagination-next::attr(href)").get()
            if next_href:
                yield response.follow(
                    next_href,
                    callback=self.parse_search,
                    errback=self.handle_error,
                    meta=self._playwright_meta(
                        query=response.meta.get("query"),
                        location=response.meta.get("location"),
                        page_num=page_num + 1,
                        page_coroutines=self._search_coroutines(),
                    ),
                    headers=self._location_headers(response.meta.get("location", "")),
                )

    # ── 3. Parse product detail ───────────────────────────────────────────────

    def parse_product(self, response):
        asin     = response.meta["asin"]
        location = response.meta.get("location", "")
        soup     = BeautifulSoup(response.text, "html.parser")

        # --- title
        title = (
            self._text(response.css("#productTitle::text").get())
            or self._soup_text(soup, "productTitle")
            or f"Amazon Product {asin}"
        )

        # --- price (try multiple selectors)
        price = (
            response.css(".a-price.aok-align-center .a-offscreen::text").get()
            or response.css(".a-price .a-offscreen::text").get()
            or response.css("#priceblock_ourprice::text").get()
            or response.css("#priceblock_dealprice::text").get()
        )

        # --- seller / buy box
        merchant_texts: list[str] = response.css("#merchant-info *::text").getall()
        seller_name   = self._clean_text(merchant_texts) or self._soup_text(soup, "merchant-info")
        buy_box_seller = seller_name
        is_fba        = "fulfilled by amazon" in " ".join(merchant_texts).lower()

        # --- listing metadata
        rating       = response.css("span[data-hook='rating-out-of-text']::text").re_first(r"([\d.]+)")
        review_count = response.css("#acrCustomerReviewText::text").re_first(r"([\d,]+)")
        availability = (
            self._text(response.css("#availability span::text").get())
            or "Unknown"
        )

        # Synthesise a stable seller_id from display name
        synthesised_sid = (
            re.sub(r"\s+", "_", seller_name.upper().strip())[:64]
            if seller_name else None
        )

        # MRP (strike-through / original price)
        mrp_raw = (
            response.css(".a-text-strike .a-offscreen::text").get()
            or response.css(".basisPrice .a-offscreen::text").get()
        )

        item = ProductSnapshotItem(
            asin             = asin,
            title            = title,
            brand            = self._extract_brand(response, soup),
            category         = "Bearings",
            price            = price,
            mrp              = mrp_raw,
            currency         = "INR",
            seller_id        = synthesised_sid,
            seller_name      = seller_name,
            availability     = availability,
            rating           = rating,
            review_count     = review_count,
            buy_box_seller   = buy_box_seller,
            buy_box_seller_id= synthesised_sid,
            is_fba           = is_fba,
            fulfillment_type = "FBA" if is_fba else "FBM",
            location         = location,
            captured_at      = datetime.now(tz=timezone.utc),
            source           = "scraper",
            offers           = [],
            _raw_html        = response.text,
            _source_url      = response.url,
        )

        # Follow offer listing page for competing sellers
        offers_url = (
            f"https://www.amazon.in/gp/offer-listing/{asin}"
            "/ref=dp_olp_NEW_mbc?condition=new"
        )
        yield response.follow(
            offers_url,
            callback=self.parse_offers,
            errback=self.handle_error,
            meta={
                "item": item,
                "location": location,
                "playwright": True,
                "playwright_context": "default",
                "playwright_page_coroutines": self._offers_coroutines(),
            },
            headers=self._location_headers(location),
        )

    # ── 4. Parse offer listing ────────────────────────────────────────────────

    def parse_offers(self, response):
        item = response.meta["item"]
        soup = BeautifulSoup(response.text, "html.parser")
        offers: list[dict] = []

        # Modern offer card selector
        cards = (
            response.css("div[data-csa-c-content-id='olpOffer']")
            or response.css(".olpOffer")
        )

        for card in cards:
            raw_text   = " ".join(card.css("*::text").getall())
            raw_lower  = raw_text.lower()
            offer_name = (
                self._text(card.css("h3 *::text").get())
                or self._text(card.css(".olpSellerName::text").get())
                or "Unknown Seller"
            )
            offer_price      = card.css(".a-price .a-offscreen::text").get()
            offer_avail      = self._text(card.css(".olpAvailability::text").get()) or "Unknown"
            offer_is_fba     = "fulfilled by amazon" in raw_lower
            buy_box_name     = (item.get("buy_box_seller") or "").lower()
            sid              = re.sub(r"\s+", "_", offer_name.upper().strip())[:64]
            offers.append({
                "seller_id":      sid,
                "seller_name":    offer_name,
                "price":          offer_price,
                "mrp":            None,
                "currency":       "INR",
                "availability":   offer_avail,
                "is_buybox":      buy_box_name in offer_name.lower(),
                "is_fba":         offer_is_fba,
                "fulfillment_type": "FBA" if offer_is_fba else "FBM",
                "seller_rating":  self._extract_seller_rating(raw_lower),
            })

        # BS4 fallback for older page structure
        if not offers:
            for block in soup.select(".olpOffer"):
                h3   = block.select_one("h3")
                p_el = block.select_one(".a-price .a-offscreen")
                name = h3.get_text(strip=True) if h3 else "Unknown Seller"
                offers.append({
                    "seller_id":     re.sub(r"\s+", "_", name.upper().strip())[:64],
                    "seller_name":   name,
                    "price":         p_el.get_text(strip=True) if p_el else None,
                    "mrp":           None,
                    "currency":      "INR",
                    "availability":  "Unknown",
                    "is_buybox":     False,
                    "is_fba":        False,
                    "fulfillment_type": "FBM",
                    "seller_rating": None,
                })

        item["offers"] = offers
        logger.info(
            "ASIN %s → %d competing offers (location=%s)",
            item.get("asin"),
            len(offers),
            item.get("location"),
        )
        yield item

    # ── Error handler ─────────────────────────────────────────────────────────

    def handle_error(self, failure):
        logger.error(
            "Request failed: %s — %s",
            failure.request.url,
            repr(failure.value),
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _playwright_meta(**kwargs) -> dict:
        """Build a meta dict that activates Playwright for this request."""
        page_coroutines = kwargs.pop("page_coroutines", [])
        meta: dict = {
            "playwright": True,
            "playwright_context": "default",
            "playwright_include_page": False,
        }
        if page_coroutines:
            meta["playwright_page_coroutines"] = page_coroutines
        meta.update(kwargs)
        return meta

    @staticmethod
    def _search_coroutines():
        """Async page actions for search result pages."""
        from scrapy_playwright.page import PageMethod
        return [
            PageMethod("wait_for_load_state", "domcontentloaded"),
            PageMethod("wait_for_selector", "div[data-component-type='s-search-result']", timeout=15_000),
            # Random scroll to simulate reading
            PageMethod("evaluate", "window.scrollBy(0, Math.floor(Math.random()*400+200))"),
        ]

    @staticmethod
    def _product_coroutines():
        """Async page actions for product detail pages."""
        from scrapy_playwright.page import PageMethod
        return [
            PageMethod("wait_for_load_state", "domcontentloaded"),
            PageMethod("wait_for_selector", "#productTitle", timeout=20_000),
            PageMethod("evaluate", "window.scrollBy(0, Math.floor(Math.random()*600+300))"),
        ]

    @staticmethod
    def _offers_coroutines():
        """Async page actions for offer listing pages."""
        from scrapy_playwright.page import PageMethod
        return [
            PageMethod("wait_for_load_state", "domcontentloaded"),
            PageMethod("evaluate", "window.scrollBy(0, 400)"),
        ]

    @staticmethod
    def _location_headers(pincode: str) -> dict:
        """
        Amazon uses the 'x-amz-checkout-csrf-token' cookie / 'X-Requested-With'
        for pincode-based routing.  Simpler approach: set a pincode cookie
        that Amazon reads for delivery address context.
        """
        return {
            "Cookie": f"x-main=; i18n-prefs=INR; lc-acbin=en_IN; "
                      f"session-id=; ubid-acbin=; sp-cdn=L5Z9:IN; "
                      f"pincode={pincode}",
            "Accept-Language": "en-IN,en;q=0.9",
        }

    @staticmethod
    def _text(value: str | None) -> str | None:
        if value is None:
            return None
        s = value.strip()
        return s or None

    @staticmethod
    def _soup_text(soup: BeautifulSoup, element_id: str) -> str | None:
        node = soup.find(id=element_id)
        return node.get_text(" ", strip=True) if node else None

    @staticmethod
    def _clean_text(parts: list[str]) -> str | None:
        joined = " ".join(p.strip() for p in parts if p.strip())
        return joined or None

    @staticmethod
    def _extract_brand(response, soup: BeautifulSoup) -> str | None:
        for row in response.css("#detailBullets_feature_div li"):
            labels = " ".join(row.css("span::text").getall()).lower()
            if "brand" in labels:
                parts = [p.strip() for p in row.css("span::text").getall() if p.strip()]
                text  = " ".join(parts)
                return text.split(":")[-1].strip()
        byline = soup.select_one("#bylineInfo")
        return (
            byline.get_text(strip=True)
                  .replace("Visit the ", "")
                  .replace(" Store", "")
            if byline else None
        )

    @staticmethod
    def _extract_seller_rating(text: str) -> float | None:
        for token in text.split():
            cleaned = token.replace("/5", "")
            try:
                val = float(cleaned)
                if 0 <= val <= 5:
                    return val
            except ValueError:
                continue
        return None
