"""Shared CoinGecko auth, plan limits, coin IDs, and HTTP helpers.

Plan is selected with ``COINGECKO_PLAN`` (demo | basic | analyst).
Upgrade later by changing that env var and using a Pro key — fetchers
read caps from here instead of hard-coding Demo limits.

Keys checked in order:
  COINGECKO_API_KEY
  COINGECKO_DEMO_API_KEY
  COINGECKO_PRO_API_KEY
  CG_DEMO_API_KEY
  CG_API_KEY
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR / "coingecko_data"
DAILY_DIR = DATA_DIR / "daily"
HOURLY_DIR = DATA_DIR / "hourly"

GECKO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "XMR": "monero",
    "FARTCOIN": "fartcoin",
    "TROLL": "troll-2",
}

KEY_ENV_VARS = (
    "COINGECKO_API_KEY",
    "COINGECKO_DEMO_API_KEY",
    "COINGECKO_PRO_API_KEY",
    "CG_DEMO_API_KEY",
    "CG_API_KEY",
)


@dataclass(frozen=True)
class Plan:
    name: str
    host: str
    key_header: str
    max_days: Optional[int]
    has_ohlc_range: bool
    hourly_chunk_days: int
    request_pause_sec: float


PLANS = {
    "demo": Plan(
        name="demo",
        host="https://api.coingecko.com/api/v3",
        key_header="x-cg-demo-api-key",
        max_days=365,
        has_ohlc_range=False,
        hourly_chunk_days=90,
        request_pause_sec=0.35,
    ),
    "basic": Plan(
        name="basic",
        host="https://pro-api.coingecko.com/api/v3",
        key_header="x-cg-pro-api-key",
        max_days=730,
        has_ohlc_range=False,
        hourly_chunk_days=90,
        request_pause_sec=0.2,
    ),
    "analyst": Plan(
        name="analyst",
        host="https://pro-api.coingecko.com/api/v3",
        key_header="x-cg-pro-api-key",
        max_days=None,
        has_ohlc_range=True,
        hourly_chunk_days=100,
        request_pause_sec=0.15,
    ),
}


def get_plan() -> Plan:
    raw = os.getenv("COINGECKO_PLAN", "demo").strip().lower()
    if raw in {"pro"}:
        raw = "analyst"
    if raw not in PLANS:
        known = ", ".join(PLANS)
        raise RuntimeError(f"Unknown COINGECKO_PLAN={raw!r}. Use one of: {known}")
    return PLANS[raw]


def api_key() -> str:
    for name in KEY_ENV_VARS:
        value = os.getenv(name, "").strip()
        if value:
            return value
    raise RuntimeError(
        "No CoinGecko API key found. Export one of: " + ", ".join(KEY_ENV_VARS)
    )


def gecko_id_for(coin: str) -> str:
    ticker = coin.strip().upper()
    if ticker in GECKO_IDS:
        return GECKO_IDS[ticker]
    return coin.strip().lower()


def clamp_days(days: Optional[int], plan: Optional[Plan] = None) -> int:
    """Resolve requested lookback against the active plan cap."""
    plan = plan or get_plan()
    if days is None:
        return 365 if plan.max_days is None else plan.max_days
    days = int(days)
    if days < 2:
        raise ValueError("days must be at least 2")
    if plan.max_days is not None:
        return min(days, plan.max_days)
    return days


def daily_cache_path(coin_id: str) -> Path:
    return DAILY_DIR / f"{coin_id}.csv"


def hourly_cache_path(coin_id: str) -> Path:
    return HOURLY_DIR / f"{coin_id}.csv"


def ensure_cache_dirs() -> None:
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    HOURLY_DIR.mkdir(parents=True, exist_ok=True)


def naive_index(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.index = pd.to_datetime(df.index)
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_convert("UTC").tz_localize(None)
    df.index.name = "time"
    return df.sort_index()


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    if df.empty:
        return df
    return naive_index(df)


def save_csv(df: pd.DataFrame, path: Path) -> None:
    ensure_cache_dirs()
    out = naive_index(df)
    out = out[~out.index.duplicated(keep="last")]
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path)
    logger.info("Saved %s rows → %s", len(out), path)


def expected_latest_utc_date():
    """Last completed UTC day. Gecko publishes it ~00:35 UTC."""
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    latest = now.date() - timedelta(days=1)
    if now.hour == 0 and now.minute < 40:
        latest = latest - timedelta(days=1)
    return latest


def series_from_pairs(pairs: list) -> pd.Series:
    if not pairs:
        return pd.Series(dtype="float64")
    idx = pd.to_datetime([int(ts) for ts, _ in pairs], unit="ms", utc=True)
    values = [float(val) for _, val in pairs]
    series = pd.Series(values, index=idx, dtype="float64")
    return series[~series.index.duplicated(keep="last")].sort_index()


def request_json(path: str, params: dict[str, Any], retries: int = 3) -> dict | list:
    plan = get_plan()
    headers = {plan.key_header: api_key()}
    url = f"{plan.host}{path}"

    for attempt in range(retries):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            if response.status_code == 429:
                wait = 2 ** attempt
                logger.warning("CoinGecko 429 — sleeping %ss", wait)
                time.sleep(wait)
                continue
            if response.status_code in {401, 403}:
                raise RuntimeError(
                    f"CoinGecko auth failed ({response.status_code}). "
                    f"Plan={plan.name}, header={plan.key_header}. "
                    "Check COINGECKO_PLAN and the key type (Demo vs Pro)."
                )
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict) and data.get("error"):
                raise RuntimeError(f"CoinGecko error: {data['error']}")
            return data
        except requests.exceptions.RequestException as exc:
            logger.warning("Request failed (%s/%s): %s", attempt + 1, retries, exc)
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError(f"CoinGecko request failed after {retries} tries: {path}")
