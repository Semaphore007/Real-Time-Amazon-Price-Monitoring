"""
ProductDetailSpider – targeted ASIN scraper.

Use this when you already know the ASINs and want to refresh prices
without running a full search crawl.

Run with::

    # Single ASIN
    scrapy crawl product_detail -a asins=B0SKF6205

    # Multiple ASINs (comma-separated)
    scrapy crawl product_detail -a asins=B0SKF6205,B0SKF6203,B0SKF6202

    # From a file (one ASIN per line)
    scrapy crawl product_detail -a asin_file=asins.txt
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import scrapy
from bs4 import BeautifulSoup

from amazon_monitor.items import ProductSnapshotItem
from config.settings import get_settings

logger = logging.getLogger(__name__)


class ProductDetailSpider(scrapy.Spider):
    """
    Modular spider for direct ASIN → price refresh.
    Shares pipelines/middlewares with SearchSpider.
    """

    name = "product_detail"
    allowed_domains = ["amazon.in"]

    def __init__(
        self,
        asins: str | None = None,
        asin_file: str | None = None,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        settings = get_settings()
        self._locations: list[str] = list(settings.location_pincodes)

        asin_list: list[str] = []
        if asins:
            asin_list = [a.strip() for a in asins.split(",") if a.strip()]
        elif asin_file:
            fp = Path(asin_file)
            if fp.exists():
                asin_list = [line.strip() for line in fp.read_text().splitlines() if line.strip()]
            else:
                logger.warning("asin_file %s not found", asin_file)

        if not asin_list:
            raise ValueError("ProductDetailSpider requires 'asins' or 'asin_file' argument")

        self._asins = asin_list
        logger.info("ProductDetailSpider initialised with %d ASINs", len(self._asins))

    # ── Seed requests ─────────────────────────────────────────────────────────

    def start_requests(self):
        for asin in self._asins:
            for location in self._locations:
                yield scrapy.Request(
                    f"https://www.amazon.in/dp/{asin}",
                    callback=self.parse_product,
                    errback=self.handle_error,
                    meta={
                        "asin":     asin,
                        "location": location,
                        "playwright": True,
                        "playwright_context": "default",
                        "playwright_page_coroutines": self._page_coroutines(),
                    },
                    headers={
                        "Accept-Language": "en-IN,en;q=0.9",
                        "Cookie": f"i18n-prefs=INR; lc-acbin=en_IN; pincode={location}",
                    },
                )

    # ── Parse product detail ──────────────────────────────────────────────────

    def parse_product(self, response):
        asin     = response.meta["asin"]
        location = response.meta["location"]
        soup     = BeautifulSoup(response.text, "html.parser")

        # CAPTCHA / bot wall detection
        if self._is_blocked(response):
            logger.warning("Bot wall detected for ASIN %s — retrying", asin)
            yield response.request.copy()
            return

        title = (
            self._text(response.css("#productTitle::text").get())
            or self._soup_text(soup, "productTitle")
            or f"Amazon Product {asin}"
        )

        price = (
            response.css(".a-price.aok-align-center .a-offscreen::text").get()
            or response.css(".a-price .a-offscreen::text").get()
            or response.css("#priceblock_ourprice::text").get()
        )

        merchant_texts = response.css("#merchant-info *::text").getall()
        seller_name    = self._clean_text(merchant_texts) or self._soup_text(soup, "merchant-info")
        is_fba         = "fulfilled by amazon" in " ".join(merchant_texts).lower()

        rating       = response.css("span[data-hook='rating-out-of-text']::text").re_first(r"([\d.]+)")
        review_count = response.css("#acrCustomerReviewText::text").re_first(r"([\d,]+)")
        availability = self._text(response.css("#availability span::text").get()) or "Unknown"

        # Synthesise a stable seller_id from the display name when not available
        synthesised_seller_id = (
            re.sub(r"\s+", "_", seller_name.upper().strip())[:64]
            if seller_name else None
        )

        # MRP (original / strike-through price)
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
            seller_id        = synthesised_seller_id,
            seller_name      = seller_name,
            availability     = availability,
            rating           = rating,
            review_count     = review_count,
            buy_box_seller   = seller_name,
            buy_box_seller_id= synthesised_seller_id,
            is_fba           = is_fba,
            fulfillment_type = "FBA" if is_fba else "FBM",
            location         = location,
            captured_at      = datetime.now(tz=timezone.utc),
            source           = "scraper",
            offers           = [],
            _raw_html        = response.text,
            _source_url      = response.url,
        )

        # Fetch competing offers
        offers_url = (
            f"https://www.amazon.in/gp/offer-listing/{asin}"
            "/ref=dp_olp_NEW_mbc?condition=new"
        )
        yield response.follow(
            offers_url,
            callback=self.parse_offers,
            errback=self.handle_error,
            meta={
                "item":     item,
                "location": location,
                "playwright": True,
                "playwright_context": "default",
            },
        )

    # ── Parse offer listing ───────────────────────────────────────────────────

    def parse_offers(self, response):
        item   = response.meta["item"]
        soup   = BeautifulSoup(response.text, "html.parser")
        offers: list[dict] = []

        cards = (
            response.css("div[data-csa-c-content-id='olpOffer']")
            or response.css(".olpOffer")
        )
        for card in cards:
            raw_text  = " ".join(card.css("*::text").getall())
            raw_lower = raw_text.lower()
            name      = (
                self._text(card.css("h3 *::text").get())
                or self._text(card.css(".olpSellerName::text").get())
                or "Unknown Seller"
            )
            offer_price_raw = card.css(".a-price .a-offscreen::text").get()
            offer_is_fba    = "fulfilled by amazon" in raw_lower
            bb_name         = (item.get("buy_box_seller") or "").lower()
            is_bb           = bb_name in name.lower()
            sid             = re.sub(r"\s+", "_", name.upper().strip())[:64]
            offers.append({
                "seller_id":     sid,
                "seller_name":   name,
                "price":         offer_price_raw,
                "mrp":           None,
                "currency":      "INR",
                "availability":  self._text(card.css(".olpAvailability::text").get()) or "Unknown",
                "is_buybox":     is_bb,
                "is_fba":        offer_is_fba,
                "fulfillment_type": "FBA" if offer_is_fba else "FBM",
                "seller_rating": self._find_rating(raw_lower),
            })

        # BS4 fallback
        if not offers:
            for blk in soup.select(".olpOffer"):
                h3   = blk.select_one("h3")
                p_el = blk.select_one(".a-price .a-offscreen")
                name = h3.get_text(strip=True) if h3 else "Unknown Seller"
                offers.append({
                    "seller_id":   re.sub(r"\s+", "_", name.upper().strip())[:64],
                    "seller_name": name,
                    "price":       p_el.get_text(strip=True) if p_el else None,
                    "mrp":         None,
                    "currency":    "INR",
                    "availability": "Unknown",
                    "is_buybox":   False,
                    "is_fba":      False,
                    "fulfillment_type": "FBM",
                    "seller_rating": None,
                })

        item["offers"] = offers
        logger.info("ASIN %s → %d offers", item.get("asin"), len(offers))
        yield item

    # ── Error handler ─────────────────────────────────────────────────────────

    def handle_error(self, failure):
        logger.error("Request error: %s — %s", failure.request.url, repr(failure.value))

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _page_coroutines():
        from scrapy_playwright.page import PageMethod
        return [
            PageMethod("wait_for_load_state", "domcontentloaded"),
            PageMethod("wait_for_selector", "#productTitle", timeout=20_000),
            PageMethod("evaluate", "window.scrollBy(0, Math.floor(Math.random()*500+200))"),
        ]

    @staticmethod
    def _is_blocked(response) -> bool:
        body_lower = response.body[:2048].lower()
        return (
            b"captcha" in body_lower
            or b"robot check" in body_lower
            or b"sorry, we just need" in body_lower
            or response.status in (429, 503)
        )

    @staticmethod
    def _text(value: str | None) -> str | None:
        s = (value or "").strip()
        return s or None

    @staticmethod
    def _clean_text(parts: list[str]) -> str | None:
        joined = " ".join(p.strip() for p in parts if p.strip())
        return joined or None

    @staticmethod
    def _soup_text(soup: BeautifulSoup, element_id: str) -> str | None:
        node = soup.find(id=element_id)
        return node.get_text(" ", strip=True) if node else None

    @staticmethod
    def _extract_brand(response, soup: BeautifulSoup) -> str | None:
        for row in response.css("#detailBullets_feature_div li"):
            label = " ".join(row.css("span::text").getall()).lower()
            if "brand" in label:
                parts = [p.strip() for p in row.css("span::text").getall() if p.strip()]
                return " ".join(parts).split(":")[-1].strip()
        byline = soup.select_one("#bylineInfo")
        return (
            byline.get_text(strip=True)
                  .replace("Visit the ", "")
                  .replace(" Store", "")
            if byline else None
        )

    @staticmethod
    def _find_rating(text: str) -> float | None:
        for token in text.split():
            try:
                val = float(token.replace("/5", ""))
                if 0 <= val <= 5:
                    return val
            except ValueError:
                continue
        return None
