"""
AlertEngine + AlertDispatcher for the Amazon Price Monitor.

AlertEngine:   evaluates price/buy-box/stock changes against active alert rules
               and persists triggered Alert rows via MonitoringRepository.

AlertDispatcher: sends notifications via Email, Slack, or generic HTTP webhook.
"""
from __future__ import annotations

import json
import logging
import smtplib
from email.message import EmailMessage
from typing import Any
from urllib import request as urllib_request

from config.settings import AppSettings
from database.repository import MonitoringRepository

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dispatcher — notification channels
# ---------------------------------------------------------------------------

class AlertDispatcher:
    """
    Routes a fired alert to all configured notification channels.
    Failures are logged but never raised (non-blocking).
    """

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def dispatch(self, subject: str, body: str, severity: str = "info") -> None:
        prefix = f"[{severity.upper()}]"
        if self.settings.alert_email_from and self.settings.alert_email_to:
            self._send_email(f"{prefix} {subject}", body)
        if self.settings.slack_webhook_url:
            emoji = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}.get(severity, "📢")
            self._post_json(
                self.settings.slack_webhook_url,
                {"text": f"{emoji} *{subject}*\n{body}"},
            )
        if self.settings.generic_webhook_url:
            self._post_json(
                self.settings.generic_webhook_url,
                {"subject": subject, "body": body, "severity": severity},
            )

    # ── Channel implementations ───────────────────────────────────────────────

    def _send_email(self, subject: str, body: str) -> None:
        try:
            msg = EmailMessage()
            msg["From"]    = self.settings.alert_email_from
            msg["To"]      = self.settings.alert_email_to
            msg["Subject"] = subject
            msg.set_content(body)
            with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port) as smtp:
                if self.settings.smtp_use_tls:
                    smtp.starttls()
                if self.settings.smtp_username:
                    smtp.login(self.settings.smtp_username, self.settings.smtp_password or "")
                smtp.send_message(msg)
            logger.info("Alert email sent: %s", subject)
        except Exception as exc:                    # noqa: BLE001
            logger.error("Email dispatch failed: %s", exc)

    @staticmethod
    def _post_json(url: str, payload: dict[str, Any]) -> None:
        try:
            req = urllib_request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib_request.urlopen(req, timeout=10).read()
        except Exception as exc:                    # noqa: BLE001
            logger.error("Webhook dispatch failed (%s): %s", url, exc)


# ---------------------------------------------------------------------------
# Engine — rule evaluation (legacy / standalone mode)
# ---------------------------------------------------------------------------

class AlertEngine:
    """
    Standalone alert evaluation engine (used by scheduler when full
    AnalyticsService is not available).

    Evaluates three alert types from raw DataFrame data:
      • price_drop      — price fell ≥ threshold since last snapshot
      • buy_box_change  — buy-box owner changed
      • undercut        — cheapest seller is ≥ threshold below next best

    For rule-based evaluation (JSONB conditions), use AnalyticsService.evaluate_alert_rules().
    """

    def __init__(
        self,
        repository: MonitoringRepository,
        settings: AppSettings,
        dispatcher: AlertDispatcher,
    ) -> None:
        self.repository = repository
        self.settings   = settings
        self.dispatcher = dispatcher

    def evaluate(self) -> list[dict]:
        """Run all checks and return list of fired alert payloads."""
        events: list[dict] = []
        events.extend(self._check_price_drops())
        events.extend(self._check_buy_box_changes())
        events.extend(self._check_undercutting())
        return events

    # ── Price drop check ──────────────────────────────────────────────────────

    def _check_price_drops(self) -> list[dict]:
        frame = self.repository.price_history_frame()
        if frame.empty:
            return []

        results: list[dict] = []
        frame = frame.sort_values("timestamp")

        for (asin, seller_name, location), group in frame.groupby(
            ["asin", "seller_name", "location"], dropna=False
        ):
            if len(group) < 2:
                continue

            latest   = group.iloc[-1]
            previous = group.iloc[-2]
            p_new    = latest["price"]
            p_old    = previous["price"]

            if p_new is None or p_old is None or p_old == 0:
                continue

            drop_pct = round((p_old - p_new) / p_old * 100, 2)
            if drop_pct >= self.settings.price_drop_threshold_pct:
                msg = (
                    f"Price drop {drop_pct}% — {asin} | seller: {seller_name} "
                    f"| location: {location} | ₹{p_old} → ₹{p_new}"
                )
                results.append(
                    self._fire(
                        alert_type="price_drop",
                        asin=str(asin),
                        message=msg,
                        severity="warning",
                        seller_id=None,
                        condition={"type": "price_drop", "threshold_pct": self.settings.price_drop_threshold_pct},
                        old_value=float(p_old),
                        new_value=float(p_new),
                    )
                )

        return results

    # ── Buy-box change check ──────────────────────────────────────────────────

    def _check_buy_box_changes(self) -> list[dict]:
        buy_box = self.repository.buy_box_frame()
        if buy_box.empty:
            return []

        results: list[dict] = []
        buy_box = buy_box.sort_values("captured_at")

        for (asin, location), group in buy_box.groupby(["asin", "location"], dropna=False):
            if len(group) < 2:
                continue
            latest   = group.iloc[-1]
            previous = group.iloc[-2]
            if latest["seller_name"] != previous["seller_name"]:
                msg = (
                    f"Buy Box changed — {asin} | location: {location} | "
                    f"{previous['seller_name']} → {latest['seller_name']}"
                )
                results.append(
                    self._fire(
                        alert_type="buy_box_change",
                        asin=str(asin),
                        message=msg,
                        severity="critical",
                        seller_id=None,
                        condition={"type": "buybox_change"},
                        old_value=float(previous["price"]) if previous["price"] is not None else None,
                        new_value=float(latest["price"])   if latest["price"]   is not None else None,
                    )
                )

        return results

    # ── Undercutting check ────────────────────────────────────────────────────

    def _check_undercutting(self) -> list[dict]:
        offers = self.repository.latest_market_snapshot()
        if offers.empty:
            return []

        # Column may be 'price' or 'offer_price' depending on frame source
        price_col = "price" if "price" in offers.columns else "offer_price"
        results: list[dict] = []

        for asin, group in offers.groupby("asin"):
            ranked = group.dropna(subset=[price_col]).sort_values(price_col)
            if len(ranked) < 2:
                continue
            low       = ranked.iloc[0]
            next_best = ranked.iloc[1]
            gap_pct   = round(
                (next_best[price_col] - low[price_col]) / next_best[price_col] * 100, 2
            )
            if gap_pct >= self.settings.undercut_threshold_pct:
                msg = (
                    f"Undercut alert — {asin} | {low['seller_name']} is {gap_pct}% "
                    f"below next seller at ₹{low[price_col]}"
                )
                results.append(
                    self._fire(
                        alert_type="undercut",
                        asin=str(asin),
                        message=msg,
                        severity="warning",
                        seller_id=None,
                        condition={"type": "undercut", "threshold_pct": self.settings.undercut_threshold_pct},
                        old_value=float(next_best[price_col]),
                        new_value=float(low[price_col]),
                    )
                )

        return results

    # ── Internal helper ───────────────────────────────────────────────────────

    def _fire(
        self,
        alert_type: str,
        asin: str,
        message: str,
        severity: str,
        condition: dict[str, Any],
        seller_id: str | None = None,
        old_value: float | None = None,
        new_value: float | None = None,
    ) -> dict:
        # Cooldown guard
        if self.repository.has_recent_alert(
            alert_type, asin,
            seller_id=seller_id,
            cooldown_minutes=self.settings.alert_cooldown_minutes,
        ):
            logger.debug("Suppressed duplicate %s alert for %s", alert_type, asin)
            return {
                "alert_type": alert_type, "asin": asin,
                "severity": severity, "message": f"[suppressed] {message}",
            }

        alert_id = self.repository.fire_alert(
            asin=asin,
            condition=condition,
            message=message,
            severity=severity,
            seller_id=seller_id,
            old_value=old_value,
            new_value=new_value,
        )
        self.dispatcher.dispatch(
            subject=f"[{alert_type}] {asin}",
            body=message,
            severity=severity,
        )
        logger.info("Alert fired id=%d type=%s asin=%s", alert_id, alert_type, asin)
        return {
            "id": alert_id, "alert_type": alert_type,
            "asin": asin, "severity": severity, "message": message,
        }
