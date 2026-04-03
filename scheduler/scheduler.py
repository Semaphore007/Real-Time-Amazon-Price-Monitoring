"""
APScheduler-based job scheduler for the Amazon price monitoring system.

Jobs:
  1. run_scraper          — launches Scrapy crawl  (configurable interval)
  2. run_alerts           — evaluates alert rules   (every interval)
  3. refresh_views        — refreshes PostgreSQL materialized views (hourly)
  4. run_product_refresh  — targeted ASIN refresh for high-priority products
"""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from analytics.price_analysis import AnalyticsService
from config.settings import get_settings
from database.connection import get_session_factory, refresh_materialized_views
from database.repository import MonitoringRepository

logger   = logging.getLogger(__name__)
UTC      = timezone.utc
settings = get_settings()


# ---------------------------------------------------------------------------
# Job functions
# ---------------------------------------------------------------------------

def run_scraper(spider: str = "amazon_search") -> None:
    """Launch the Scrapy spider in a subprocess."""
    logger.info("[scheduler] Starting scraper — spider=%s", spider)
    result = subprocess.run(
        [sys.executable, "-m", "scrapy", "crawl", spider],
        capture_output=False,
    )
    if result.returncode != 0:
        logger.error("[scheduler] Spider exited with code %d", result.returncode)
    else:
        logger.info("[scheduler] Spider finished OK")


def run_product_refresh(asins: list[str] | None = None) -> None:
    """
    Targeted refresh of specific ASINs using ProductDetailSpider.
    Falls back to all tracked products when no list supplied.
    """
    if not asins:
        repo  = MonitoringRepository(get_session_factory(settings.database_url))
        items = repo.list_products(active_only=True)
        asins = [p["asin"] for p in items]

    if not asins:
        logger.warning("[scheduler] No ASINs to refresh")
        return

    asin_arg = ",".join(asins)
    logger.info("[scheduler] Refreshing %d ASINs via product_detail spider", len(asins))
    result = subprocess.run(
        [sys.executable, "-m", "scrapy", "crawl", "product_detail", "-a", f"asins={asin_arg}"],
        capture_output=False,
    )
    if result.returncode != 0:
        logger.error("[scheduler] product_detail spider exited with code %d", result.returncode)


def run_alerts() -> None:
    """
    Evaluate all active alert rules against the latest price data
    and persist any newly triggered alerts.
    """
    logger.info("[scheduler] Evaluating alert rules — %s", datetime.now(UTC).isoformat())
    try:
        repo      = MonitoringRepository(get_session_factory(settings.database_url))
        analytics = AnalyticsService(repo)
        fired     = analytics.evaluate_alert_rules()
        for payload in fired:
            alert_id = repo.fire_alert(**payload)
            logger.info(
                "[scheduler] Alert fired — id=%d asin=%s msg=%s",
                alert_id, payload["asin"], payload["message"],
            )
        logger.info("[scheduler] Alert evaluation done — %d fired", len(fired))
    except Exception as exc:                    # noqa: BLE001
        logger.exception("[scheduler] Alert evaluation failed: %s", exc)


def refresh_views() -> None:
    """Refresh PostgreSQL materialized views used by the dashboard."""
    logger.info("[scheduler] Refreshing materialized views")
    try:
        sf = get_session_factory(settings.database_url)
        refresh_materialized_views(sf)
        logger.info("[scheduler] Materialized views refreshed OK")
    except Exception as exc:                    # noqa: BLE001
        logger.warning("[scheduler] View refresh failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Amazon Price Monitor — job scheduler")
    parser.add_argument(
        "--interval-minutes", type=int, default=30,
        help="How often to run the full search crawl and alert evaluation (default: 30 min)",
    )
    parser.add_argument(
        "--refresh-minutes", type=int, default=60,
        help="How often to refresh PostgreSQL materialized views (default: 60 min)",
    )
    parser.add_argument(
        "--product-refresh-minutes", type=int, default=15,
        help="How often to run the targeted ASIN price refresh (default: 15 min)",
    )
    parser.add_argument(
        "--spider", default="amazon_search",
        help="Scrapy spider to use for full crawl (default: amazon_search)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    scheduler = BlockingScheduler(timezone="UTC")

    # 1. Full search crawl
    scheduler.add_job(
        lambda: run_scraper(args.spider),
        IntervalTrigger(minutes=args.interval_minutes),
        id="full_crawl",
        max_instances=1,
        coalesce=True,
        name="Full search crawl",
    )

    # 2. Alert rule evaluation
    scheduler.add_job(
        run_alerts,
        IntervalTrigger(minutes=args.interval_minutes),
        id="alert_evaluation",
        max_instances=1,
        coalesce=True,
        name="Alert rule evaluation",
    )

    # 3. Targeted product refresh (runs more frequently — price changes fast)
    scheduler.add_job(
        run_product_refresh,
        IntervalTrigger(minutes=args.product_refresh_minutes),
        id="product_refresh",
        max_instances=1,
        coalesce=True,
        name="Targeted ASIN refresh",
    )

    # 4. Materialized view refresh (hourly, on the hour)
    scheduler.add_job(
        refresh_views,
        CronTrigger(minute=0),        # e.g. 12:00, 13:00, 14:00 …
        id="mv_refresh",
        max_instances=1,
        coalesce=True,
        name="Materialized view refresh",
    )

    logger.info(
        "Scheduler started — crawl every %dmin | alerts every %dmin | "
        "ASIN refresh every %dmin | MV refresh hourly",
        args.interval_minutes,
        args.interval_minutes,
        args.product_refresh_minutes,
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
