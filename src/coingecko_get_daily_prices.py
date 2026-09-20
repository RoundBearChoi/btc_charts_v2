"""Daily close + volume from CoinGecko.

Used by 21/50/200 and other close-based charts.

Demo / Basic: ``/coins/{id}/market_chart`` (daily when days > 90).
Analyst: same endpoint with ``days=max`` when asking for more than 365 days.

Cache: src/coingecko_data/daily/{gecko_id}.csv

The cache is append-only. Plan caps only limit live API requests, so an
Analyst backfill stays on disk after you switch to Basic.

On Demo, high/low equal close and open is the previous close.
That is enough for volume bar coloring and MA/RSI work.
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

import coingecko_client as cg

logger = logging.getLogger(__name__)


def _market_chart(coin_id: str, days: int | str) -> pd.DataFrame:
    payload = cg.request_json(
        f"/coins/{coin_id}/market_chart",
        {"vs_currency": "usd", "days": days},
    )
    prices = cg.series_from_pairs(payload.get("prices") or [])
    volumes = cg.series_from_pairs(payload.get("total_volumes") or [])
    if prices.empty:
        return pd.DataFrame()

    frame = pd.DataFrame({"close": prices})
    frame["volumeto"] = volumes.reindex(frame.index)
    frame = frame.tz_convert("UTC")
    daily = pd.DataFrame(
        {
            "close": frame["close"].resample("1D").last(),
            "volumeto": frame["volumeto"].resample("1D").last(),
        }
    ).dropna(subset=["close"])
    daily["open"] = daily["close"].shift(1)
    daily["high"] = daily["close"]
    daily["low"] = daily["close"]
    daily["volumefrom"] = float("nan")
    daily["open"] = daily["open"].fillna(daily["close"])
    daily.index = daily.index.tz_localize(None)
    daily.index.name = "time"
    return daily[["open", "high", "low", "close", "volumefrom", "volumeto"]]


def _days_param(plan, requested: Optional[int], fetch_days: int) -> int | str:
    """Analyst can ask for days=max; Demo/Basic must stay inside the plan cap."""
    if plan.max_days is None and (requested is None or requested > 365):
        return "max"
    return fetch_days


def get_price_data(
    coin: str = "BTC",
    days: Optional[int] = None,
    force_download: bool = False,
) -> pd.DataFrame:
    plan = cg.get_plan()
    coin_id = cg.gecko_id_for(coin)
    api_days = cg.clamp_days(days, plan)
    path = cg.daily_cache_path(coin_id)

    logger.info(
        "CoinGecko daily %s (%s) plan=%s api_days=%s visible=%s cache=%s",
        coin.upper(),
        coin_id,
        plan.name,
        api_days,
        days,
        path,
    )

    cached = pd.DataFrame() if force_download else cg.load_csv(path)
    expected = cg.expected_latest_utc_date()

    if not cached.empty:
        latest = cached.index.max().date()
        behind = (expected - latest).days
        if behind <= 0:
            print(
                f"✅ Daily cache up to date ({coin_id}, "
                f"{len(cached)} rows, latest {latest})."
            )
            return cg.slice_visible(cached, days)
        fetch_days = min(api_days, max(behind + 3, 2))
        logger.info("Daily cache %s day(s) behind — fetching %s days", behind, fetch_days)
    else:
        fetch_days = api_days
        logger.info("No daily cache for %s — fetching %s days", coin_id, fetch_days)

    fresh = _market_chart(coin_id, _days_param(plan, days, fetch_days))
    if fresh.empty:
        if not cached.empty:
            logger.warning("CoinGecko returned no new daily rows; using cache.")
            return cg.slice_visible(cached, days)
        raise RuntimeError(f"CoinGecko returned no daily prices for {coin_id}")

    if cached.empty:
        combined = fresh
    else:
        combined = pd.concat([cached, fresh])
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()

    cg.save_csv(combined, path)
    print(
        f"✅ {coin.upper()} daily cache: {len(combined)} rows  "
        f"{combined.index.min().date()} → {combined.index.max().date()}"
    )
    return cg.slice_visible(combined, days)


def get_btc_price_data(force_download: bool = False) -> pd.DataFrame:
    return get_price_data(coin="BTC", force_download=force_download)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(f"plan={cg.get_plan().name}")
    df = get_price_data("BTC", days=360)
    print(df.tail())
    print(f"{len(df)} rows  {df.index.min().date()} → {df.index.max().date()}")
