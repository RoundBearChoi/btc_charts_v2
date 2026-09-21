"""CoinGecko Demo hourly increment fetcher.

File: src_v3/cgdemo_get_hourly_data_increments.py

This script only tops up recent hourly snapshots. It does not backfill
months of history. A later Analyst-tier script owns the long tail.

Coin pick comes from src_v3/coin_menu.py + src_v3/coins.csv.

On disk (only these two files per symbol):
    src_v3/cg_data/{SYMBOL}_data_hourly.csv
        hourly snapshots: time, price, volume
    src_v3/cg_data/{SYMBOL}_data_daily.csv
        daily OHLC derived from those hours:
        time, open, high, low, close, volumeto

volume / volumeto is CoinGecko's sliding 24h sum, not session volume.
Daily volumeto is the last 24h-volume snapshot of that UTC day.

Daily OHLC from hourly snapshots:
    open  = first hourly price of the UTC day
    high  = max hourly price of the UTC day
    low   = min hourly price of the UTC day
    close = last hourly price of the UTC day

Rules:
    - No cache  -> seed latest UTC midnight back 60 days.
    - Cache gap <= 60 days -> fetch the missing tail and merge.
    - Cache gap  > 60 days -> error (use the long-term script).
    - Daily CSV is always rebuilt from the full hourly cache.
      It is not a separate Demo download.

Env:
    COINGECKO_DEMO_API_KEY   Demo API key only (export in ~/.bashrc).
    This file never reads COINGECKO_API_KEY or a Pro/Analyst key.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

from coin_menu import get_coin_choice

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR / "cg_data"

DEMO_HOST = "https://api.coingecko.com/api/v3"
DEMO_KEY_HEADER = "x-cg-demo-api-key"
DEMO_KEY_ENV = "COINGECKO_DEMO_API_KEY"

DEFAULT_SYMBOL = "BTC"
GECKO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "XMR": "monero",
    "FARTCOIN": "fartcoin",
    "TROLL": "troll-2",
}

MAX_INCREMENT_DAYS = 60
MIN_FETCH_DAYS = 2
OVERLAP = timedelta(hours=2)


class CacheTooStaleError(RuntimeError):
    """Existing cache is more than MAX_INCREMENT_DAYS behind UTC midnight."""


def latest_utc_midnight(now: datetime | None = None) -> datetime:
    """Most recent 00:00 UTC. Daily bars are closed through this instant."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)
    return current.replace(minute=0, second=0, microsecond=0, hour=0)


def gecko_id_for(symbol: str) -> str:
    ticker = symbol.strip().upper()
    if ticker not in GECKO_IDS:
        known = ", ".join(GECKO_IDS)
        raise ValueError(f"Unsupported symbol {ticker!r}. Known: {known}")
    return GECKO_IDS[ticker]


def hourly_cache_path(symbol: str = DEFAULT_SYMBOL) -> Path:
    return DATA_DIR / f"{symbol.strip().upper()}_data_hourly.csv"


def daily_cache_path(symbol: str = DEFAULT_SYMBOL) -> Path:
    return DATA_DIR / f"{symbol.strip().upper()}_data_daily.csv"


def _legacy_hourly_path(symbol: str = DEFAULT_SYMBOL) -> Path:
    return DATA_DIR / f"{symbol.strip().upper()}_data.csv"


def cache_path(symbol: str = DEFAULT_SYMBOL) -> Path:
    """Hourly cache path. Kept as an alias."""
    return hourly_cache_path(symbol)


def demo_api_key() -> str:
    """Read the Demo key only. Does not fall back to a Pro/Analyst key."""
    value = os.getenv(DEMO_KEY_ENV, "").strip()
    if not value:
        raise RuntimeError(
            f"No Demo API key found. Export {DEMO_KEY_ENV} in ~/.bashrc "
            "and open a new shell (or run: source ~/.bashrc)."
        )
    return value


def _naive_utc_index(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.index = pd.to_datetime(out.index)
    if getattr(out.index, "tz", None) is not None:
        out.index = out.index.tz_convert("UTC").tz_localize(None)
    out.index.name = "time"
    return out.sort_index()


def _read_hourly_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    if df.empty:
        return pd.DataFrame(columns=["price", "volume"])
    df = _naive_utc_index(df)
    for col in ("price", "volume"):
        if col not in df.columns:
            df[col] = float("nan")
    return df[["price", "volume"]]


def load_hourly(symbol: str = DEFAULT_SYMBOL) -> pd.DataFrame:
    path = hourly_cache_path(symbol)
    if path.exists():
        return _read_hourly_csv(path)
    legacy = _legacy_hourly_path(symbol)
    if legacy.exists():
        print(f"Found legacy hourly cache {legacy.name}; will save as {path.name}.")
        return _read_hourly_csv(legacy)
    return pd.DataFrame(columns=["price", "volume"])


def save_hourly(df: pd.DataFrame, symbol: str = DEFAULT_SYMBOL) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = hourly_cache_path(symbol)
    out = _naive_utc_index(df)
    out = out[~out.index.duplicated(keep="last")]
    out[["price", "volume"]].to_csv(path)
    legacy = _legacy_hourly_path(symbol)
    if legacy.exists() and legacy != path:
        legacy.unlink()
        print(f"Removed legacy file {legacy.name}.")
    return path


def save_daily(df: pd.DataFrame, symbol: str = DEFAULT_SYMBOL) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = daily_cache_path(symbol)
    out = _naive_utc_index(df)
    out = out[~out.index.duplicated(keep="last")]
    cols = ["open", "high", "low", "close", "volumeto"]
    out[cols].to_csv(path)
    return path


def _series_from_pairs(pairs: list) -> pd.Series:
    if not pairs:
        return pd.Series(dtype="float64")
    idx = pd.to_datetime([int(ts) for ts, _ in pairs], unit="ms", utc=True)
    values = [float(val) for _, val in pairs]
    series = pd.Series(values, index=idx, dtype="float64")
    return series[~series.index.duplicated(keep="last")].sort_index()


def _request_json(path: str, params: dict, retries: int = 3) -> dict:
    headers = {DEMO_KEY_HEADER: demo_api_key()}
    url = f"{DEMO_HOST}{path}"
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            if response.status_code == 429:
                wait = 2 ** attempt
                print(f"CoinGecko 429 — sleeping {wait}s")
                time.sleep(wait)
                continue
            if response.status_code in {401, 403}:
                raise RuntimeError(
                    f"CoinGecko auth failed ({response.status_code}). "
                    f"Check {DEMO_KEY_ENV} (Demo key + {DEMO_KEY_HEADER})."
                )
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict) and data.get("error"):
                raise RuntimeError(f"CoinGecko error: {data['error']}")
            return data
        except requests.exceptions.RequestException as exc:
            last_error = exc
            print(f"Request failed ({attempt + 1}/{retries}): {exc}")
            if attempt == retries - 1:
                break
            time.sleep(2 ** attempt)
    raise RuntimeError(f"CoinGecko request failed after {retries} tries: {path}") from last_error


def fetch_hourly_range(symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
    """One Demo /market_chart/range call. Window must stay inside 2–60 days."""
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    if end <= start:
        return pd.DataFrame(columns=["price", "volume"])

    span_days = (end - start).total_seconds() / 86400
    if span_days > MAX_INCREMENT_DAYS:
        raise CacheTooStaleError(
            f"Fetch window is {span_days:.1f} days. "
            f"This script only covers {MAX_INCREMENT_DAYS} days."
        )

    coin_id = gecko_id_for(symbol)
    payload = _request_json(
        f"/coins/{coin_id}/market_chart/range",
        {
            "vs_currency": "usd",
            "from": int(start.timestamp()),
            "to": int(end.timestamp()),
        },
    )
    prices = _series_from_pairs(payload.get("prices") or [])
    volumes = _series_from_pairs(payload.get("total_volumes") or [])
    if prices.empty:
        return pd.DataFrame(columns=["price", "volume"])

    frame = pd.DataFrame({"price": prices})
    frame["volume"] = volumes.reindex(frame.index)
    return _naive_utc_index(frame)


def hourly_to_daily(hourly: pd.DataFrame) -> pd.DataFrame:
    """Resample hourly snapshots to daily OHLC + last 24h volume print."""
    if hourly.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volumeto"])

    price = hourly["price"].copy()
    price.index = pd.to_datetime(price.index)
    if price.index.tz is None:
        price.index = price.index.tz_localize("UTC")
    else:
        price.index = price.index.tz_convert("UTC")

    daily = price.resample("1D").ohlc()
    daily.columns = ["open", "high", "low", "close"]

    if "volume" in hourly.columns:
        vol = hourly["volume"].copy()
        vol.index = pd.to_datetime(vol.index)
        if vol.index.tz is None:
            vol.index = vol.index.tz_localize("UTC")
        else:
            vol.index = vol.index.tz_convert("UTC")
        daily["volumeto"] = vol.resample("1D").last()
    else:
        daily["volumeto"] = float("nan")

    daily = daily.dropna(subset=["close"])
    daily.index = daily.index.tz_localize(None)
    daily.index.name = "time"
    return daily[["open", "high", "low", "close", "volumeto"]]


def _plan_window(cached: pd.DataFrame) -> tuple[str, datetime, datetime]:
    """Decide seed / increment / current / stale against latest UTC midnight."""
    utc0 = latest_utc_midnight()
    seed_start = utc0 - timedelta(days=MAX_INCREMENT_DAYS)

    if cached.empty:
        return "seed", seed_start, utc0

    latest = cached.index.max()
    if not isinstance(latest, datetime):
        latest = pd.Timestamp(latest).to_pydatetime()
    if latest.tzinfo is None:
        latest_utc = latest.replace(tzinfo=timezone.utc)
    else:
        latest_utc = latest.astimezone(timezone.utc)

    gap = utc0 - latest_utc
    gap_days = gap.total_seconds() / 86400

    if gap_days <= 0:
        return "current", utc0, utc0

    if gap_days > MAX_INCREMENT_DAYS:
        latest_txt = latest_utc.strftime("%Y-%m-%d %H:%M UTC")
        need_txt = utc0.strftime("%Y-%m-%d %H:%M UTC")
        raise CacheTooStaleError(
            f"Cache is {gap_days:.1f} days behind "
            f"(latest {latest_txt}, need through {need_txt}). "
            f"cgdemo_get_hourly_data_increments.py only fills up to "
            f"{MAX_INCREMENT_DAYS} days. Run the long-term Analyst script first."
        )

    start = latest_utc - OVERLAP
    min_start = utc0 - timedelta(days=MIN_FETCH_DAYS)
    if start > min_start:
        start = min_start
    return "increment", start, utc0


def get_hourly_data_increments(symbol: str = DEFAULT_SYMBOL) -> pd.DataFrame:
    """Update the hourly cache if needed, write both CSVs, return daily OHLC."""
    symbol = symbol.strip().upper()
    cached = load_hourly(symbol)
    action, start, end = _plan_window(cached)

    if action == "current":
        print(
            f"{symbol} hourly cache is current through {end.strftime('%Y-%m-%d %H:%M UTC')} "
            f"({len(cached)} hourly rows)."
        )
        combined = cached
    else:
        if action == "seed":
            print(
                f"No {symbol} hourly cache. Seeding {MAX_INCREMENT_DAYS} days "
                f"{start.strftime('%Y-%m-%d')} → {end.strftime('%Y-%m-%d')} UTC."
            )
        else:
            print(
                f"{symbol} hourly increment "
                f"{start.strftime('%Y-%m-%d %H:%M')} → {end.strftime('%Y-%m-%d %H:%M')} UTC."
            )

        fresh = fetch_hourly_range(symbol, start, end)
        if fresh.empty:
            if cached.empty:
                raise RuntimeError(f"CoinGecko returned no hourly prices for {symbol}")
            print("No new hourly rows; using existing cache.")
            combined = cached
        elif cached.empty:
            combined = fresh
        else:
            combined = pd.concat([cached, fresh])
            combined = combined[~combined.index.duplicated(keep="last")].sort_index()

    hourly_path = save_hourly(combined, symbol)
    daily = hourly_to_daily(combined)
    daily_path = save_daily(daily, symbol)
    print(
        f"Saved {len(combined)} hourly rows → {hourly_path}\n"
        f"Saved {len(daily)} daily rows → {daily_path}\n"
        f"Daily OHLC from hourly: {len(daily)} days  "
        f"{daily.index.min().date()} → {daily.index.max().date()}"
    )
    return daily


def get_increments(symbol: str = DEFAULT_SYMBOL) -> pd.DataFrame:
    """Alias for get_hourly_data_increments."""
    return get_hourly_data_increments(symbol)


def get_hourly(symbol: str = DEFAULT_SYMBOL) -> pd.DataFrame:
    """Update if needed, then return the hourly snapshot cache."""
    get_hourly_data_increments(symbol)
    return load_hourly(symbol)


def main() -> None:
    choices = get_coin_choice()
    total = len(choices)
    for i, (name, symbol) in enumerate(choices, start=1):
        print(f"\n[{i}/{total}] {name} ({symbol})")
        try:
            daily = get_hourly_data_increments(symbol)
            print()
            print(daily.tail())
        except Exception as exc:
            print(f"✘ {name} ({symbol}) failed: {exc}")
            continue


if __name__ == "__main__":
    main()
