"""Hourly CoinGecko snapshots, resampled to daily OHLC.

Used by resistance_and_support.py, which needs daily high/low for swings.

Demo / Basic: ``/market_chart/range`` in plan-sized windows (hourly when
the window is 2–90 days), then resample to UTC daily OHLC.

Analyst: prefer ``/coins/{id}/ohlc/range?interval=daily`` when the plan
flag says that endpoint exists.

Cache: src/coingecko_data/hourly/{gecko_id}.csv  (raw hourly points)
The cache is append-only. Plan caps only limit live API requests.
The returned frame is daily OHLCV, same columns as the daily fetcher.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd

import coingecko_client as cg

logger = logging.getLogger(__name__)


def _hourly_window(coin_id: str, start: datetime, end: datetime) -> pd.DataFrame:
    payload = cg.request_json(
        f"/coins/{coin_id}/market_chart/range",
        {
            "vs_currency": "usd",
            "from": int(start.timestamp()),
            "to": int(end.timestamp()),
        },
    )
    prices = cg.series_from_pairs(payload.get("prices") or [])
    volumes = cg.series_from_pairs(payload.get("total_volumes") or [])
    if prices.empty:
        return pd.DataFrame()
    out = pd.DataFrame({"price": prices})
    out["volume"] = volumes.reindex(out.index)
    return out.sort_index()


def _download_hourly(coin_id: str, days: int) -> pd.DataFrame:
    plan = cg.get_plan()
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = now - timedelta(days=days)
    chunks = []
    cursor = start
    while cursor < now:
        window_end = min(cursor + timedelta(days=plan.hourly_chunk_days), now)
        logger.info("  hourly window %s → %s", cursor.date(), window_end.date())
        part = _hourly_window(coin_id, cursor, window_end)
        if not part.empty:
            chunks.append(part)
        cursor = window_end
        if cursor < now:
            time.sleep(plan.request_pause_sec)
    if not chunks:
        return pd.DataFrame()
    hourly = pd.concat(chunks).sort_index()
    return hourly[~hourly.index.duplicated(keep="last")]


def _hourly_to_daily(hourly: pd.DataFrame) -> pd.DataFrame:
    if hourly.empty:
        return pd.DataFrame()
    price = hourly["price"]
    if price.index.tz is None:
        price = price.tz_localize("UTC")
    else:
        price = price.tz_convert("UTC")
    daily = price.resample("1D").ohlc()
    daily.columns = ["open", "high", "low", "close"]
    if "volume" in hourly.columns:
        vol = hourly["volume"]
        if vol.index.tz is None:
            vol = vol.tz_localize("UTC")
        else:
            vol = vol.tz_convert("UTC")
        daily["volumeto"] = vol.resample("1D").last()
    else:
        daily["volumeto"] = float("nan")
    daily["volumefrom"] = float("nan")
    daily = daily.dropna(subset=["close"])
    daily.index = daily.index.tz_localize(None)
    daily.index.name = "time"
    return daily[["open", "high", "low", "close", "volumefrom", "volumeto"]]


def _ohlc_range_daily(coin_id: str, days: int) -> pd.DataFrame:
    """Analyst+ native daily candles."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    payload = cg.request_json(
        f"/coins/{coin_id}/ohlc/range",
        {
            "vs_currency": "usd",
            "from": start.strftime("%Y-%m-%d"),
            "to": now.strftime("%Y-%m-%d"),
            "interval": "daily",
        },
    )
    if not payload:
        return pd.DataFrame()
    rows = []
    for item in payload:
        rows.append(
            {
                "time": pd.to_datetime(int(item[0]), unit="ms", utc=True),
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
            }
        )
    df = pd.DataFrame(rows).set_index("time")
    df["volumeto"] = float("nan")
    df["volumefrom"] = float("nan")
    df.index = df.index.tz_localize(None)
    return df[["open", "high", "low", "close", "volumefrom", "volumeto"]]


def get_price_data(
    coin: str = "BTC",
    days: Optional[int] = None,
    force_download: bool = False,
) -> pd.DataFrame:
    plan = cg.get_plan()
    coin_id = cg.gecko_id_for(coin)
    api_days = cg.clamp_days(days, plan)

    logger.info(
        "CoinGecko hourly→OHLC %s (%s) plan=%s api_days=%s visible=%s",
        coin.upper(),
        coin_id,
        plan.name,
        api_days,
        days,
    )

    if plan.has_ohlc_range:
        daily = _ohlc_range_daily(coin_id, api_days)
        if daily.empty:
            raise RuntimeError(f"CoinGecko ohlc/range returned nothing for {coin_id}")
        print(
            f"✅ {coin.upper()} OHLC (analyst range): {len(daily)} rows  "
            f"{daily.index.min().date()} → {daily.index.max().date()}"
        )
        return cg.slice_visible(daily.sort_index(), days)

    path = cg.hourly_cache_path(coin_id)
    cached = pd.DataFrame() if force_download else cg.load_csv(path)
    expected = cg.expected_latest_utc_date()

    if not cached.empty:
        latest = cached.index.max().date()
        behind = (expected - latest).days
        if behind <= 0 and not force_download:
            print(f"✅ Hourly cache up to date ({coin_id}, latest {latest}).")
            return cg.slice_visible(_hourly_to_daily(cached), days)
        fetch_days = min(api_days, max(behind + 3, 3))
        logger.info("Hourly cache %s day(s) behind — fetching %s days", behind, fetch_days)
    else:
        fetch_days = api_days
        logger.info("No hourly cache for %s — fetching %s days", coin_id, fetch_days)

    fresh = _download_hourly(coin_id, fetch_days)
    if fresh.empty:
        if not cached.empty:
            logger.warning("No new hourly rows; using cache.")
            return cg.slice_visible(_hourly_to_daily(cached), days)
        raise RuntimeError(f"CoinGecko returned no hourly prices for {coin_id}")

    if cached.empty:
        combined = fresh
    else:
        combined = pd.concat([cached, fresh])
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()

    hourly_out = combined.copy()
    if hourly_out.index.tz is not None:
        hourly_out.index = hourly_out.index.tz_convert("UTC").tz_localize(None)
    hourly_out.index.name = "time"
    cg.save_csv(hourly_out, path)

    daily = _hourly_to_daily(combined)
    visible = cg.slice_visible(daily, days)
    print(
        f"✅ {coin.upper()} daily OHLC from hourly: cache {len(daily)} rows, "
        f"visible {len(visible)}  "
        f"{visible.index.min().date()} → {visible.index.max().date()}"
    )
    return visible


def get_btc_price_data(force_download: bool = False) -> pd.DataFrame:
    return get_price_data(coin="BTC", force_download=force_download)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(f"plan={cg.get_plan().name}")
    df = get_price_data("BTC", days=360)
    print(df.tail())
    print(f"{len(df)} rows  {df.index.min().date()} → {df.index.max().date()}")
