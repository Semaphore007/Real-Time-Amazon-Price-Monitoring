"""
AnalyticsService — derives business insights from raw repository data.

All methods return plain Python dicts or Pandas DataFrames so callers
(FastAPI routes, Streamlit dashboards, notebooks) stay decoupled.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from database.repository import MonitoringRepository

UTC = timezone.utc


class AnalyticsService:
    def __init__(self, repository: MonitoringRepository) -> None:
        self.repo = repository

    # -----------------------------------------------------------------------
    # Summary dashboard
    # -----------------------------------------------------------------------

    def build_summary(self, asin: str | None = None) -> dict:
        """
        Aggregate KPIs for the main dashboard card grid.

        Returns:
            price_points, products_tracked, average_market_price,
            min_price_seller, frequent_price_changers,
            buy_box_win_rate, undercutting_events,
            seller_market_share, price_drop_events
        """
        prices   = self.repo.price_history_frame(asin)
        buy_box  = self.repo.buy_box_frame(asin)
        listings = self.repo.latest_market_snapshot()

        if asin and not listings.empty:
            listings = listings[listings["asin"] == asin]

        EMPTY = {
            "price_points": 0,
            "products_tracked": 0,
            "average_market_price": None,
            "min_price_seller": None,
            "frequent_price_changers": [],
            "buy_box_win_rate": [],
            "undercutting_events": [],
            "seller_market_share": [],
            "price_drop_events": [],
        }
        if prices.empty:
            return EMPTY

        # --- Frequent price changers ---
        changes = (
            prices.sort_values("timestamp")
            .assign(
                prev=lambda df: df.groupby(["asin", "seller_name"])["price"].shift(1)
            )
            .assign(changed=lambda df: df["price"] != df["prev"])
            .groupby("seller_name", dropna=True)["changed"]
            .sum()
            .sort_values(ascending=False)
            .head(10)
        )

        # --- Market share (unique ASINs covered by seller) ---
        seller_market_share: list[dict] = []
        if not listings.empty:
            total_asins = listings["asin"].nunique()
            seller_market_share = (
                listings.groupby("seller_name")["asin"]
                .nunique()
                .div(total_asins)
                .mul(100)
                .round(2)
                .reset_index(name="market_share_pct")
                .to_dict(orient="records")
            )

        # --- Buy-box win rate ---
        buy_box_win_rate: list[dict] = []
        if not buy_box.empty:
            buy_box_win_rate = (
                buy_box.groupby("seller_name")["asin"]
                .count()
                .div(len(buy_box))
                .mul(100)
                .round(2)
                .reset_index(name="win_rate_pct")
                .to_dict(orient="records")
            )

        # --- Cheapest seller in marketplace ---
        min_price_seller = None
        if not listings.empty and "price" in listings.columns:
            min_row = listings.sort_values("price").iloc[0]
            min_price_seller = {
                "seller_name": min_row.get("seller_name"),
                "price":       float(min_row["price"]),
                "asin":        min_row["asin"],
            }

        return {
            "price_points":          int(len(prices)),
            "products_tracked":      int(prices["asin"].nunique()),
            "average_market_price":  round(float(prices["price"].dropna().mean()), 2),
            "min_price_seller":      min_price_seller,
            "frequent_price_changers": [
                {"seller_name": seller, "changes": int(n)}
                for seller, n in changes.items()
            ],
            "buy_box_win_rate":      buy_box_win_rate,
            "undercutting_events":   self.detect_undercutting(listings),
            "seller_market_share":   seller_market_share,
            "price_drop_events":     self.detect_price_drops(prices, threshold_pct=5.0),
        }

    # -----------------------------------------------------------------------
    # Price-drop detection
    # -----------------------------------------------------------------------

    def detect_price_drops(
        self,
        prices: pd.DataFrame | None = None,
        asin: str | None = None,
        threshold_pct: float = 5.0,
    ) -> list[dict]:
        """
        Return rows where price fell by >= threshold_pct vs previous reading.
        Operates on a pre-built DataFrame or fetches from repository.
        """
        if prices is None:
            prices = self.repo.price_history_frame(asin)
        if prices.empty:
            return []

        df = (
            prices.sort_values("timestamp")
            .copy()
        )
        df["prev_price"] = df.groupby("asin")["price"].shift(1)
        df = df.dropna(subset=["prev_price"])
        df["drop_pct"] = ((df["prev_price"] - df["price"]) / df["prev_price"] * 100).round(2)
        drops = df[df["drop_pct"] >= threshold_pct].copy()
        drops = drops.sort_values("drop_pct", ascending=False)

        return [
            {
                "asin":       row["asin"],
                "prev_price": float(row["prev_price"]),
                "new_price":  float(row["price"]),
                "drop_pct":   float(row["drop_pct"]),
                "seller_name":row.get("seller_name"),
                "timestamp":  row["timestamp"].isoformat() if hasattr(row["timestamp"], "isoformat") else str(row["timestamp"]),
            }
            for _, row in drops.iterrows()
        ]

    # -----------------------------------------------------------------------
    # Undercutting detection
    # -----------------------------------------------------------------------

    def detect_undercutting(self, listings: pd.DataFrame | None = None) -> list[dict]:
        """
        For each ASIN, flag when the cheapest seller is > 0% cheaper than
        the second-cheapest (i.e. someone is undercutting the market).
        """
        if listings is None:
            listings = self.repo.latest_market_snapshot()
        if listings.empty:
            return []

        records: list[dict] = []
        price_col = "price" if "price" in listings.columns else "offer_price"
        for asin, group in listings.groupby("asin"):
            prices_sorted = group[price_col].dropna().sort_values()
            if len(prices_sorted) < 2:
                continue
            min_p    = prices_sorted.iloc[0]
            second_p = prices_sorted.iloc[1]
            delta_pct = round((second_p - min_p) / second_p * 100, 2)
            if delta_pct <= 0:
                continue
            winner_row = group.loc[group[price_col] == min_p].iloc[0]
            records.append({
                "asin":        str(asin),
                "seller_name": winner_row.get("seller_name"),
                "price":       float(min_p),
                "undercut_pct": delta_pct,
            })
        return sorted(records, key=lambda r: r["undercut_pct"], reverse=True)

    # -----------------------------------------------------------------------
    # OHLC price bars
    # -----------------------------------------------------------------------

    def price_ohlc(self, asin: str, period: str = "D") -> pd.DataFrame:
        """
        Return open/high/low/close bars grouped by `period` ('D'=daily, 'W'=weekly).
        Tries the DB view first; falls back to in-memory computation.
        """
        try:
            df = self.repo.daily_price_ohlc(asin)
            if not df.empty:
                return df
        except Exception:
            pass

        raw = self.repo.price_history_frame(asin)
        if raw.empty:
            return raw

        raw["bucket"] = raw["timestamp"].dt.to_period(period).dt.start_time
        grp = raw.groupby("bucket")["price"]
        ohlc = grp.agg(
            low="min", high="max",
            open=lambda s: s.iloc[0],
            close=lambda s: s.iloc[-1],
            avg_price="mean",
            sample_count="count",
        ).reset_index().rename(columns={"bucket": "day"})
        return ohlc

    # -----------------------------------------------------------------------
    # Seller competitiveness
    # -----------------------------------------------------------------------

    def seller_competitiveness(self, asin: str) -> pd.DataFrame:
        """Buybox win-rate + avg price per seller for a given ASIN."""
        return self.repo.seller_competitiveness_frame(asin)

    # -----------------------------------------------------------------------
    # Price heatmap
    # -----------------------------------------------------------------------

    def price_heatmap(self, asin: str | None = None) -> pd.DataFrame:
        """Pivot: seller (rows) × location (cols) → min price."""
        listings = self.repo.latest_market_snapshot()
        if asin and not listings.empty:
            listings = listings[listings["asin"] == asin]
        if listings.empty:
            return listings

        price_col = "price" if "price" in listings.columns else "offer_price"
        return listings.pivot_table(
            index="seller_name",
            columns="location",
            values=price_col,
            aggfunc="min",
        )

    # -----------------------------------------------------------------------
    # Buy-box ownership %
    # -----------------------------------------------------------------------

    def buy_box_ownership(self, asin: str | None = None) -> list[dict]:
        """Return pct of buy-box captures per seller [× ASIN]."""
        df = self.repo.buy_box_frame(asin)
        if df.empty:
            return []

        grouped = (
            df.groupby(["asin", "seller_name"])
            .size()
            .reset_index(name="events")
        )
        totals = df.groupby("asin").size().reset_index(name="total")
        merged = grouped.merge(totals, on="asin")
        merged["ownership_pct"] = (merged["events"] / merged["total"] * 100).round(2)
        return merged.sort_values("ownership_pct", ascending=False).to_dict(orient="records")

    # -----------------------------------------------------------------------
    # Alert rule evaluation (called by scheduler / pipeline)
    # -----------------------------------------------------------------------

    def evaluate_alert_rules(self) -> list[dict]:
        """
        Check every active alert rule against the latest price data.
        Returns list of newly fired alert payloads (caller should persist them).
        """
        rules = self.repo.list_alert_rules(active_only=True)
        fired: list[dict] = []

        for rule in rules:
            asin      = rule["asin"]
            cond      = rule["condition"]
            cond_type = cond.get("type")
            seller_id = rule.get("seller_id")

            history = self.repo.get_price_history(asin, seller_id=seller_id)
            if len(history) < 2:
                continue

            latest = history[0]   # DESC order → newest first
            prev   = history[1]

            triggered = False
            msg        = ""
            old_val    = prev["price"]
            new_val    = latest["price"]

            if cond_type == "price_drop":
                threshold = float(cond.get("threshold_pct", 5))
                if old_val and new_val < old_val:
                    drop_pct = (old_val - new_val) / old_val * 100
                    if drop_pct >= threshold:
                        triggered = True
                        msg = f"Price dropped {drop_pct:.1f}% (₹{old_val} → ₹{new_val}) for {asin}"

            elif cond_type == "price_above":
                threshold = float(cond.get("value", 0))
                if new_val and new_val > threshold:
                    triggered = True
                    msg = f"Price ₹{new_val} exceeded threshold ₹{threshold} for {asin}"

            elif cond_type == "price_below":
                threshold = float(cond.get("value", 0))
                if new_val and new_val < threshold:
                    triggered = True
                    msg = f"Price ₹{new_val} fell below threshold ₹{threshold} for {asin}"

            elif cond_type == "oos":
                consecutive = int(cond.get("consecutive_checks", 3))
                recent = history[:consecutive]
                if all(r.get("availability", "").lower() in ("out of stock", "unavailable") for r in recent):
                    triggered = True
                    msg = f"Product {asin} has been out of stock for {consecutive} consecutive checks"

            if triggered:
                # Cooldown check — don't re-fire same rule within 60 min
                if not self.repo.has_recent_alert(
                    cond_type, asin, seller_id=seller_id, cooldown_minutes=60
                ):
                    fired.append({
                        "rule_id":   rule["id"],
                        "asin":      asin,
                        "seller_id": seller_id,
                        "condition": cond,
                        "message":   msg,
                        "severity":  rule["severity"],
                        "old_value": old_val,
                        "new_value": new_val,
                    })
        return fired
