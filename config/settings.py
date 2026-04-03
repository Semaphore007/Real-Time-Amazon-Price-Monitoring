"""
Application-wide settings for the Amazon Price Monitor.

All values are read from environment variables so the app can be configured
via .env (development), Docker environment blocks (staging/production), or
Kubernetes ConfigMaps/Secrets.

Usage:
    from config.settings import get_settings
    settings = get_settings()          # cached singleton
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _csv(env: str, default: list[str]) -> list[str]:
    """Split a comma-separated env var; return default when empty."""
    values = [v.strip() for v in os.getenv(env, "").split(",") if v.strip()]
    return values or default


def _flag(env: str, default: bool) -> bool:
    """Parse a boolean env var ('1', 'true', 'yes', 'on' → True)."""
    raw = os.getenv(env)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(env: str, default: int) -> int:
    try:
        return int(os.getenv(env, str(default)))
    except ValueError:
        return default


def _float(env: str, default: float) -> float:
    try:
        return float(os.getenv(env, str(default)))
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# Settings dataclass
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class AppSettings:
    # ── App identity ──────────────────────────────────────────────────────────
    app_name:    str = field(default_factory=lambda: os.getenv("APP_NAME", "Amazon Price Monitor"))
    environment: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))

    # ── Infrastructure ────────────────────────────────────────────────────────
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///amazon_monitor.db")
    )
    redis_url: str = field(
        default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0")
    )
    api_host: str = field(default_factory=lambda: os.getenv("API_HOST", "0.0.0.0"))
    api_port: int = field(default_factory=lambda: _int("API_PORT", 8000))

    # ── Scraping ──────────────────────────────────────────────────────────────
    scrape_queries: list[str] = field(
        default_factory=lambda: _csv(
            "SCRAPE_QUERIES",
            ["SKF bearing 6205", "SKF bearing 6203", "SKF bearing 6202",
             "SKF bearing 6206", "SKF bearing 6207", "6001 deep groove bearing"],
        )
    )
    location_pincodes: list[str] = field(
        default_factory=lambda: _csv("LOCATION_PINCODES", ["600001", "560001", "110001"])
    )
    proxy_pool: list[str] = field(
        default_factory=lambda: _csv("PROXY_POOL", [])
    )
    user_agents: list[str] = field(
        default_factory=lambda: _csv(
            "USER_AGENT_POOL",
            [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0 Safari/537.36",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
                "(KHTML, like Gecko) Version/17.3 Safari/605.1.15",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
            ],
        )
    )

    # ── Analytics thresholds ──────────────────────────────────────────────────
    price_drop_threshold_pct: float = field(
        default_factory=lambda: _float("PRICE_DROP_THRESHOLD_PCT", 5.0)
    )
    undercut_threshold_pct: float = field(
        default_factory=lambda: _float("UNDERCUT_THRESHOLD_PCT", 3.0)
    )
    alert_cooldown_minutes: int = field(
        default_factory=lambda: _int("ALERT_COOLDOWN_MINUTES", 60)
    )

    # ── Email alerts (SMTP) ───────────────────────────────────────────────────
    alert_email_from: str = field(default_factory=lambda: os.getenv("ALERT_EMAIL_FROM", ""))
    alert_email_to:   str = field(default_factory=lambda: os.getenv("ALERT_EMAIL_TO", ""))
    smtp_host:        str = field(default_factory=lambda: os.getenv("SMTP_HOST", "localhost"))
    smtp_port:        int = field(default_factory=lambda: _int("SMTP_PORT", 587))
    smtp_use_tls:    bool = field(default_factory=lambda: _flag("SMTP_USE_TLS", True))
    smtp_username:    str = field(default_factory=lambda: os.getenv("SMTP_USERNAME", ""))
    smtp_password:    str = field(default_factory=lambda: os.getenv("SMTP_PASSWORD", ""))

    # ── Webhook / Slack alerts ────────────────────────────────────────────────
    slack_webhook_url:   str = field(default_factory=lambda: os.getenv("SLACK_WEBHOOK_URL", ""))
    generic_webhook_url: str = field(default_factory=lambda: os.getenv("GENERIC_WEBHOOK_URL", ""))

    # ── Scheduler cadence ─────────────────────────────────────────────────────
    crawl_interval_minutes:          int = field(default_factory=lambda: _int("CRAWL_INTERVAL_MINUTES", 30))
    product_refresh_interval_minutes: int = field(default_factory=lambda: _int("PRODUCT_REFRESH_INTERVAL_MINUTES", 15))
    mv_refresh_interval_minutes:      int = field(default_factory=lambda: _int("MV_REFRESH_INTERVAL_MINUTES", 60))

    # ── Development helpers ───────────────────────────────────────────────────
    seed_demo_data: bool = field(
        default_factory=lambda: _flag(
            "SEED_DEMO_DATA",
            os.getenv("APP_ENV", "development") != "production",
        )
    )
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    # ── Connection pool tuning (PostgreSQL) ────────────────────────────────────
    db_pool_size:     int = field(default_factory=lambda: _int("DB_POOL_SIZE", 10))
    db_max_overflow:  int = field(default_factory=lambda: _int("DB_MAX_OVERFLOW", 20))
    db_pool_timeout:  int = field(default_factory=lambda: _int("DB_POOL_TIMEOUT", 30))


# ---------------------------------------------------------------------------
# Cached singleton
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return a cached application settings singleton."""
    return AppSettings()
