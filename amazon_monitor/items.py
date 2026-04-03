"""
Scrapy Item definitions for the Amazon price monitor.

These fields map 1-to-1 with what MonitoringRepository.record_product_snapshot()
expects.  All field names are snake_case to match the DB schema.
"""
import scrapy


class ProductSnapshotItem(scrapy.Item):
    # ── Core product identifiers ──────────────────────────────────────────────
    asin            = scrapy.Field()   # str  — Amazon Standard Identification Number
    title           = scrapy.Field()   # str
    brand           = scrapy.Field()   # str | None
    category        = scrapy.Field()   # str | None
    sub_category    = scrapy.Field()   # str | None
    image_url       = scrapy.Field()   # str | None
    product_url     = scrapy.Field()   # str | None

    # ── Buy-box / representative price ───────────────────────────────────────
    price           = scrapy.Field()   # float | None  — buy-box price
    mrp             = scrapy.Field()   # float | None  — Maximum Retail Price (strikethrough)
    currency        = scrapy.Field()   # str, default "INR"

    # ── Buy-box seller ────────────────────────────────────────────────────────
    seller_id       = scrapy.Field()   # str | None  — marketplace seller ID (e.g. A1B2C3D4)
    seller_name     = scrapy.Field()   # str | None  — display name
    buy_box_seller  = scrapy.Field()   # str | None  — alias kept for backward compat
    buy_box_seller_id = scrapy.Field() # str | None
    fulfillment_type= scrapy.Field()   # "FBA" | "FBM" | "Amazon"
    is_fba          = scrapy.Field()   # bool

    # ── Listing metadata ──────────────────────────────────────────────────────
    availability    = scrapy.Field()   # str  e.g. "In Stock", "Out of Stock"
    delivery_days   = scrapy.Field()   # int | None
    rating          = scrapy.Field()   # float | None  — product star rating
    review_count    = scrapy.Field()   # int | None

    # ── Geo / session context ─────────────────────────────────────────────────
    location        = scrapy.Field()   # str — pincode used for this request
    captured_at     = scrapy.Field()   # datetime (UTC)
    source          = scrapy.Field()   # str — "scraper" | "api" | "manual"

    # ── Competing offers: list[dict] ─────────────────────────────────────────
    # Each dict may contain:
    #   seller_id, seller_name, price, mrp, currency,
    #   is_buybox, is_fba, availability, seller_rating,
    #   fulfillment_type, delivery_days
    offers          = scrapy.Field()

    # ── Internal pipeline fields (stripped before DB write) ───────────────────
    _raw_html       = scrapy.Field()   # str — full page HTML (RawHtmlPipeline)
    _source_url     = scrapy.Field()   # str — original request URL
