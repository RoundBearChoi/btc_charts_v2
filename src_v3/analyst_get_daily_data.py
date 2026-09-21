"""CoinGecko Analyst daily fetcher.

File: src_v3/analyst_get_daily_data.py

Daily sibling of src_v3/analyst_get_hourly_data.py.
Same daily schema and cache path as
src_v3/demo_get_daily_data.py.
This script never writes hourly CSVs.

Coin pick comes from src_v3/coin_menu.py + src_v3/coins.csv.

On disk (daily only):
    src_v3/cg_data/{SYMBOL}_data_daily.csv
        time, open, high, low, close, volumeto

Source is /coins/{id}/market_chart/range?interval=daily
(Analyst / Pro host). That endpoint returns one UTC-midnight
price + sliding 24h volume per day — the same volume meaning
as the hourly scripts.

OHLC from that daily print:
    close    = CoinGecko daily price at 00:00 UTC
    high     = close
    low      = close
    open     = previous day's close (first row uses close)
    volumeto = CoinGecko sliding 24h volume at that midnight

That matches the column layout demo_get_daily_data.py writes.

Rules:
    - No cache -> seed HISTORY_START through latest UTC midnight
      in DAYS_PER_BATCH windows.
    - Cache exists -> fill last cached UTC midnight through latest
      UTC midnight. No backfill behind the earliest row.
    - No stale-gap error: a 5-year-old daily file is just a long
      increment.
    - Each successful chunk is saved so a mid-seed rerun can resume.

Env:
    COINGECKO_ANALYST_API_KEY   Analyst / Pro API key only.
    This file never reads COINGECKO_DEMO_API_KEY or COINGECKO_API_KEY.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

from coin_menu import get_coin_choice

# --- config ---
DAYS_PER_BATCH = 180          # range window per request; raise to cut call count
HISTORY_START = datetime(2013, 1, 1, tzinfo=timezone.utc)
MIN_FETCH_DAYS = 2            # tiny gaps still request at least this much
OVERLAP_DAYS = 1              # overlap into cached tail / between chunks
REQUEST_PAUSE_SEC = 0.25

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR / "cg_data"

ANALYST_HOST = "https://pro-api.coingecko.com/api/v3"
ANALYST_KEY_HEADER = "x-cg-pro-api-key"
ANALYST_KEY_ENV = "COINGECKO_ANALYST_API_KEY"

DEFAULT_SYMBOL = "BTC"
GECKO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "XMR": "monero",
    "FARTCOIN": "fartcoin",
    "TROLL": "troll-2",
}

DAILY_COLS = ["open", "high", "low", "close", "volumeto"]
OVERLAP = timedelta(days=OVERLAP_DAYS)
