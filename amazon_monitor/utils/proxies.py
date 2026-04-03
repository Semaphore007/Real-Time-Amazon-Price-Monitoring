from __future__ import annotations

import random
import time
import logging
import statistics
from typing import Any

from config.settings import get_settings

logger = logging.getLogger(__name__)


class ProxyPool:
    """
    Production proxy pool manager supporting 100+ IPs.

    Features:
    - Weighted random selection (better proxies chosen more often)
    - Failure tracking with cool-down
    - Response-time tracking
    - Automatic proxy health scoring
    - Supports HTTP/HTTPS/SOCKS5 proxies
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self._proxies: list[str] = list(self.settings.proxy_pool) if self.settings.proxy_pool else []
        self._fail_count: dict[str, int] = {}
        self._success_count: dict[str, int] = {}
        self._response_times: dict[str, list[float]] = {}
        self._cooldown_until: dict[str, float] = {}
        self._max_fails = 3
        self._cooldown_seconds = 300  # 5 minutes

    # ── Public API ────────────────────────────────────────────────────────────

    def get_proxy(self, exclude: set[str] | None = None) -> str | None:
        """Return the best available proxy using weighted scoring."""
        if not self._proxies:
            return None

        now = time.time()
        exclude = exclude or set()
        available = [
            p for p in self._proxies
            if p not in exclude
            and self._fail_count.get(p, 0) < self._max_fails
            and self._cooldown_until.get(p, 0) < now
        ]

        if not available:
            # All proxies exhausted; reset fail counts and try again
            logger.warning("All proxies penalised — resetting fail counters.")
            self._fail_count.clear()
            self._cooldown_until.clear()
            available = self._proxies[:]

        # Weighted selection: higher score = higher probability
        weights = [self._score(p) for p in available]
        total = sum(weights)
        if total == 0:
            return random.choice(available)

        r = random.uniform(0, total)
        cumulative = 0.0
        for proxy, w in zip(available, weights):
            cumulative += w
            if r <= cumulative:
                return proxy
        return available[-1]

    def record_success(self, proxy: str, elapsed_ms: float) -> None:
        """Call after a successful response."""
        self._success_count[proxy] = self._success_count.get(proxy, 0) + 1
        if proxy not in self._response_times:
            self._response_times[proxy] = []
        times = self._response_times[proxy]
        times.append(elapsed_ms)
        if len(times) > 20:
            times.pop(0)
        # Partial recovery of fail count on success
        if self._fail_count.get(proxy, 0) > 0:
            self._fail_count[proxy] = max(0, self._fail_count[proxy] - 1)

    def record_failure(self, proxy: str) -> None:
        """Call after a failed request."""
        self._fail_count[proxy] = self._fail_count.get(proxy, 0) + 1
        if self._fail_count[proxy] >= self._max_fails:
            cooldown = self._cooldown_seconds * (2 ** (self._fail_count[proxy] - self._max_fails))
            self._cooldown_until[proxy] = time.time() + min(cooldown, 3600)
            logger.warning("Proxy %s in cooldown for %.0fs", proxy, min(cooldown, 3600))

    def add_proxies(self, proxies: list[str]) -> None:
        """Dynamically add more proxies (e.g. from an API)."""
        new = [p for p in proxies if p not in self._proxies]
        self._proxies.extend(new)
        logger.info("Added %d new proxies (total=%d)", len(new), len(self._proxies))

    @property
    def stats(self) -> dict[str, Any]:
        now = time.time()
        return {
            "total": len(self._proxies),
            "active": sum(
                1 for p in self._proxies
                if self._fail_count.get(p, 0) < self._max_fails
                and self._cooldown_until.get(p, 0) < now
            ),
            "in_cooldown": sum(1 for p in self._proxies if self._cooldown_until.get(p, 0) >= now),
            "total_successes": sum(self._success_count.values()),
            "total_failures": sum(self._fail_count.values()),
        }

    # ── Private ───────────────────────────────────────────────────────────────

    def _score(self, proxy: str) -> float:
        """
        Score = success_rate * speed_bonus
        Returns a value in (0, 1] used for weighted random selection.
        """
        successes = self._success_count.get(proxy, 0)
        fails = self._fail_count.get(proxy, 0)
        total = successes + fails

        success_rate = (successes + 1) / (total + 1)  # Laplace smoothing

        times = self._response_times.get(proxy, [])
        if times:
            avg_ms = statistics.mean(times)
            # Faster proxies get a bonus; cap speed bonus at 2×
            speed_bonus = min(2.0, 2000.0 / max(avg_ms, 100))
        else:
            speed_bonus = 1.0

        return success_rate * speed_bonus
