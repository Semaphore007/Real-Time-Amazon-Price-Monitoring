"""
Celery application for async scrape task dispatch.

Workers can be started with::

    celery -A scheduler.celery_app worker --loglevel=info --concurrency=2

Tasks::

    from scheduler.celery_app import scrape_asin, scrape_all
    scrape_asin.delay("B0SKF6205")          # single ASIN
    scrape_all.delay()                       # full search crawl
"""
from __future__ import annotations

import logging
import subprocess
import sys

from celery import Celery

from config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

app = Celery(
    "amazon_monitor",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    # Retry failed tasks up to 3 times with 60s delay
    task_max_retries=3,
    task_default_retry_delay=60,
    # Beat schedule – periodic price refresh every 30 minutes
    beat_schedule={
        "full-search-crawl": {
            "task": "scheduler.celery_app.scrape_all",
            "schedule": 1800,  # 30 minutes
        },
    },
)


@app.task(bind=True, name="scheduler.celery_app.scrape_all", max_retries=3)
def scrape_all(self):
    """Run the full SearchSpider crawl."""
    logger.info("Celery task scrape_all — starting full crawl")
    try:
        subprocess.run(
            [sys.executable, "-m", "scrapy", "crawl", "amazon_search"],
            check=True,
            timeout=3600,  # 1 hour max
        )
    except subprocess.CalledProcessError as exc:
        logger.error("Scrapy crawl failed: %s", exc)
        raise self.retry(exc=exc, countdown=120)


@app.task(bind=True, name="scheduler.celery_app.scrape_asin", max_retries=3)
def scrape_asin(self, asin: str):
    """Refresh price for a single ASIN across all configured locations."""
    logger.info("Celery task scrape_asin — ASIN=%s", asin)
    try:
        subprocess.run(
            [
                sys.executable, "-m", "scrapy", "crawl", "product_detail",
                "-a", f"asins={asin}",
            ],
            check=True,
            timeout=600,  # 10 minutes per ASIN
        )
    except subprocess.CalledProcessError as exc:
        logger.error("Scrape failed for ASIN %s: %s", asin, exc)
        raise self.retry(exc=exc, countdown=60)


@app.task(name="scheduler.celery_app.scrape_asins_batch")
def scrape_asins_batch(asins: list[str]):
    """Dispatch individual scrape tasks for each ASIN in the list."""
    for asin in asins:
        scrape_asin.delay(asin)
    logger.info("Dispatched %d ASIN scrape tasks", len(asins))
