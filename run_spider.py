#!/usr/bin/env python3
"""
run_spider.py – Convenience entry point for running spiders locally.

Usage::

    # Full search crawl (all configured queries + locations)
    python run_spider.py

    # Search with custom queries
    python run_spider.py --spider search --queries "SKF bearing 6205,SKF bearing 6203"

    # Targeted ASIN refresh
    python run_spider.py --spider product --asins B0SKF6205,B0SKF6203

    # Read ASINs from file
    python run_spider.py --spider product --asin-file asins.txt

    # Limit pagination
    python run_spider.py --spider search --max-pages 2
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Ensure the project root is on sys.path
ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("SCRAPY_SETTINGS_MODULE", "amazon_monitor.settings")

from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Amazon Bearing Price Monitor – spider launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--spider",
        choices=["search", "product"],
        default="search",
        help="Which spider to run (default: search)",
    )
    parser.add_argument(
        "--queries",
        default=None,
        help="Comma-separated search queries (search spider only). "
             "Defaults to SCRAPE_QUERIES env var.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=5,
        help="Max pagination pages per query (search spider only, default: 5)",
    )
    parser.add_argument(
        "--asins",
        default=None,
        help="Comma-separated ASINs to refresh (product spider only)",
    )
    parser.add_argument(
        "--asin-file",
        default=None,
        help="Path to a file with one ASIN per line (product spider only)",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    settings = get_project_settings()
    process  = CrawlerProcess(settings)

    if args.spider == "search":
        from amazon_monitor.spiders.search_spider import SearchSpider
        spider_kwargs: dict = {"max_pages": args.max_pages}
        if args.queries:
            spider_kwargs["queries"] = args.queries
        logger.info("Starting SearchSpider  (max_pages=%d)", args.max_pages)
        process.crawl(SearchSpider, **spider_kwargs)

    else:  # product
        from amazon_monitor.spiders.product_spider import ProductDetailSpider
        if not args.asins and not args.asin_file:
            logger.error("--asins or --asin-file is required for the product spider")
            sys.exit(1)
        spider_kwargs = {}
        if args.asins:
            spider_kwargs["asins"] = args.asins
        if args.asin_file:
            spider_kwargs["asin_file"] = args.asin_file
        logger.info("Starting ProductDetailSpider (ASINs=%s file=%s)", args.asins, args.asin_file)
        process.crawl(ProductDetailSpider, **spider_kwargs)

    process.start()
    logger.info("Crawl finished.")


if __name__ == "__main__":
    main()
