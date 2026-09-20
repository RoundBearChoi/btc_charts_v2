"""Daily close + volume from CoinGecko.

Used by 21/50/200 and other close-based charts.

Demo / Basic: ``/coins/{id}/market_chart`` (daily when days > 90).
Analyst: same endpoint with ``days=max`` when no cap.

Cache: src/coingecko_data/daily/{gecko_id}.csv

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
    # Collapse intra-day points (hourly windows) to one UTC day.
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


def _trim_to_plan(df: pd.DataFrame, days: int) -> pd.DataFrame:
    if df.empty:
        return df
    cutoff = df.index.max() - pd.Timedelta(days=days - 1)
    return df.loc[df.index >= cutoff]


def get_price_data(
    coin: str = "BTC",
    days: Optional[int] = None,
    force_download: bool = False,
) -> pd.DataFrame:
    plan = cg.get_plan()
    coin_id = cg.gecko_id_for(coin)
    lookback = cg.clamp_days(days, plan)
    path = cg.daily_cache_path(coin_id)

    logger.info(
        "CoinGecko daily %s (%s) plan=%s days=%s cache=%s",
        coin.upper(),
        coin_id,
        plan.name,
        lookback,
        path,
    )

    cached = pd.DataFrame() if force_download else cg.load_csv(path)
    expected = cg.expected_latest_utc_date()

    if not cached.empty:
        latest = cached.index.max().date()
        behind = (expected - latest).days
        if behind <= 0:
            print(f"✅ Daily cache up to date ({coin_id}, latest {latest}).")
            return _trim_to_plan(cached, lookback)
        fetch_days = min(lookback, max(behind + 3, 2))
        logger.info("Daily cache %s day(s) behind — fetching %s days", behind, fetch_days)
    else:
        fetch_days = lookback
        logger.info("No daily cache for %s — fetching %s days", coin_id, fetch_days)

    days_param: int | str = "max" if plan.max_days is None and days is None else fetch_days
    fresh = _market_chart(coin_id, days_param)
    if fresh.empty:
        if not cached.empty:
            logger.warning("CoinGecko returned no new daily rows; using cache.")
            return _trim_to_plan(cached, lookback)
        raise RuntimeError(f"CoinGecko returned no daily prices for {coin_id}")

    if cached.empty:
        combined = fresh
    else:
        combined = pd.concat([cached, fresh])
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()

    combined = _trim_to_plan(combined, lookback)
    cg.save_csv(combined, path)
    print(
        f"✅ {coin.upper()} daily: {len(combined)} rows  "
        f"{combined.index.min().date()} → {combined.index.max().date()}"
    )
    return combined


def get_btc_price_data(force_download: bool = False) -> pd.DataFrame:
    return get_price_data(coin="BTC", force_download=force_download)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(f"plan={cg.get_plan().name}")
    df = get_price_data("BTC", days=360)
    print(df.tail())
    print(f"{len(df)} rows  {df.index.min().date()} → {df.index.max().date()}")
