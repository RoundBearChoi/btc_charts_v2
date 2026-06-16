import pandas as pd
import os
import requests
import datetime as dt
import time
import logging
from typing import Optional, Dict, Any

"""
download_data_coingecko.py

Clean daily BTC data from CoinGecko (Demo key friendly).

Main function:
    download_btc_recent_market_data(days=30)  → Exactly 1 clean row per day

Full history function exists but is disabled by default
(because free/demo keys are limited to ~365 days).
"""

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "coingecko_data")
logger = logging.getLogger(__name__)

# Key detection
DEMO_KEY_RAW = os.getenv("COINGECKO_DEMO_API_KEY")
PRO_KEY_RAW  = os.getenv("COINGECKO_API_KEY") or os.getenv("COINGECKO_PRO_API_KEY")
raw_key = DEMO_KEY_RAW or PRO_KEY_RAW

if raw_key:
    if DEMO_KEY_RAW or str(raw_key).startswith("CG-"):
        API_KEY = raw_key
        KEY_HEADER_NAME = "x-cg-demo-api-key"
        BASE_URL = "https://api.coingecko.com/api/v3"
        key_type = "demo"
    else:
        API_KEY = raw_key
        KEY_HEADER_NAME = "x-cg-pro-api-key"
        BASE_URL = "https://pro-api.coingecko.com/api/v3"
        key_type = "pro"
else:
    API_KEY = None
    KEY_HEADER_NAME = None
    BASE_URL = "https://api.coingecko.com/api/v3"
    key_type = "none"


def _get_cache_file_path(filename: str) -> str:
    os.makedirs(DATA_DIR, exist_ok=True)
    return os.path.join(DATA_DIR, filename)


def _make_api_request(endpoint: str, params: Dict[str, Any], retries: int = 3) -> Dict[str, Any]:
    headers: Dict[str, str] = {}
    if API_KEY and KEY_HEADER_NAME:
        headers[KEY_HEADER_NAME] = API_KEY
    url = f"{BASE_URL}{endpoint}"
    last_exception = None
    for attempt in range(retries):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=20)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict) and data.get("error"):
                raise ValueError(f"CoinGecko API Error: {data['error']}")
            return data
        except requests.exceptions.RequestException as e:
            last_exception = e
            logger.warning("Request failed (attempt %s/%s): %s", attempt + 1, retries, e)
            if hasattr(e, 'response') and e.response is not None:
                try:
                    logger.warning("Server response: %s", e.response.text[:400])
                except Exception:
                    pass
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise
        except Exception as e:
            logger.error("API processing error: %s", e)
            raise
    raise last_exception


def _parse_market_chart(raw: dict) -> pd.DataFrame:
    prices = raw.get("prices", [])
    market_caps = raw.get("market_caps", [])
    total_volumes = raw.get("total_volumes", [])
    if not prices:
        return pd.DataFrame()

    df = pd.DataFrame(prices, columns=["timestamp_ms", "close"])
    df["date"] = pd.to_datetime(df["timestamp_ms"], unit="ms").dt.normalize()
    df = df.set_index("date").sort_index()
    df = df.drop(columns=["timestamp_ms"])

    if market_caps:
        df_mc = pd.DataFrame(market_caps, columns=["ts", "market_cap"])
        df_mc["date"] = pd.to_datetime(df_mc["ts"], unit="ms").dt.normalize()
        df = df.join(df_mc.set_index("date")[["market_cap"]], how="left")
    if total_volumes:
        df_vol = pd.DataFrame(total_volumes, columns=["ts", "total_volume"])
        df_vol["date"] = pd.to_datetime(df_vol["ts"], unit="ms").dt.normalize()
        df = df.join(df_vol.set_index("date")[["total_volume"]], how="left")

    df = df[~df.index.duplicated(keep="last")]
    return df.dropna(how="all")


def download_btc_recent_market_data(
    days: int = 30,
    precision: Optional[int] = None,
    force_download: bool = False
) -> pd.DataFrame:
    """Get clean daily BTC data for the last N days (recommended function)."""
    CSV_FILE = _get_cache_file_path("coingecko_btc_recent_market_data.csv")

    if not force_download and os.path.exists(CSV_FILE):
        try:
            df = pd.read_csv(CSV_FILE, index_col=0, parse_dates=True)
            if len(df) >= max(3, days-2) and (dt.date.today() - df.index.max().date()).days <= 1:
                logger.info("Using cached %s-day data (%s rows)", days, len(df))
                return df
        except Exception:
            pass

    logger.info("Downloading last %s days of daily BTC data from CoinGecko...", days)
    params = {
        "vs_currency": "usd",
        "days": str(days),
        "interval": "daily",
    }
    if precision is not None:
        params["precision"] = str(precision)

    raw = _make_api_request("/coins/bitcoin/market_chart", params)
    df = _parse_market_chart(raw)

    df.to_csv(CSV_FILE)
    logger.info("Saved %s clean daily rows → %s", len(df), CSV_FILE)
    return df


def download_btc_full_daily_history(start_year: int = 2010, force_download: bool = False) -> pd.DataFrame:
    """Full history function (only works with paid CoinGecko plan)."""
    CSV_FILE = _get_cache_file_path("coingecko_btc_full_history_daily.csv")
    if not force_download and os.path.exists(CSV_FILE):
        try:
            return pd.read_csv(CSV_FILE, index_col=0, parse_dates=True)
        except Exception:
            pass
    raise NotImplementedError(
        "Full history requires a paid CoinGecko plan. "
        "Free/demo keys are limited to the past 365 days."
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    print("\n=== CoinGecko BTC Daily Data (Demo friendly) ===")
    print(f"Key type: {key_type}")

    # Default: clean last 30 days
    df = download_btc_recent_market_data(days=30)
    print(f"\nLoaded {len(df)} clean daily rows (last 30 days)")
    print("\nLatest 7 days:")
    print(df[["close"]].tail(7).to_string())
    print("\nData saved to: src/coingecko_data/coingecko_btc_recent_market_data.csv")
    print("\nTip: You can change days with download_btc_recent_market_data(days=90)")
