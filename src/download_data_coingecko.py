import pandas as pd
import os
import requests
import datetime as dt
import time
import logging
from typing import Optional, Dict, Any

"""
download_data_coingecko.py

Fetches recent N days of BTC market data (closing prices + market cap + volume)
from CoinGecko API using direct requests.

Auto-detects Demo vs Pro keys (Demo keys usually start with 'CG-').
Uses correct endpoint automatically:
  - Demo / free → https://api.coingecko.com/api/v3
  - Pro       → https://pro-api.coingecko.com/api/v3

Caches to src/coingecko_data/coingecko_btc_recent_market_data.csv
"""

# ==================== CONFIGURATION ====================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "coingecko_data")

logger = logging.getLogger(__name__)

# ====================== KEY DETECTION (robust) ======================
# Check all common env var names
DEMO_KEY_RAW = os.getenv("COINGECKO_DEMO_API_KEY")
PRO_KEY_RAW  = os.getenv("COINGECKO_API_KEY") or os.getenv("COINGECKO_PRO_API_KEY")

raw_key = DEMO_KEY_RAW or PRO_KEY_RAW

if raw_key:
    # Demo keys from CoinGecko start with "CG-"
    if DEMO_KEY_RAW or raw_key.startswith("CG-"):
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


def _get_cache_file_path() -> str:
    """Return path for the recent market data cache."""
    os.makedirs(DATA_DIR, exist_ok=True)
    return os.path.join(DATA_DIR, "coingecko_btc_recent_market_data.csv")


def _make_api_request(
    endpoint: str, params: Dict[str, Any], retries: int = 3
) -> Dict[str, Any]:
    """Robust request with retries + server error details."""
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
                    logger.warning("Server response: %s", e.response.text[:600])
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


def download_btc_recent_market_data(
    days: int = 30,
    precision: Optional[int] = None,
    force_download: bool = False
) -> pd.DataFrame:
    """
    Download recent BTC market data from CoinGecko.

    Args:
        days: How many days back (default 30). Works well for 1–90 days.
        precision: Optional decimal places (e.g. 2). Usually leave as None.
        force_download: Force fresh download even if cache is good.
    """
    CSV_FILE = _get_cache_file_path()

    if not force_download and os.path.exists(CSV_FILE):
        try:
            df_cached = pd.read_csv(CSV_FILE, index_col=0, parse_dates=True)
            if not df_cached.empty:
                last_date = df_cached.index.max().date()
                data_age = (dt.date.today() - last_date).days
                if data_age <= 1 and len(df_cached) >= max(3, days - 2):
                    logger.info("Using cached data (%s rows, last %s)", len(df_cached), last_date)
                    return df_cached
                logger.info("Cache stale or too short — refreshing...")
        except Exception as e:
            logger.warning("Cache problem (%s) — fresh download.", e)

    logger.info("=== Downloading last %s days of BTC data from CoinGecko ===", days)

    endpoint = "/coins/bitcoin/market_chart"
    params: Dict[str, Any] = {
        "vs_currency": "usd",
        "days": str(days),
    }
    if precision is not None:
        params["precision"] = str(precision)

    raw = _make_api_request(endpoint, params)

    prices = raw.get("prices", [])
    market_caps = raw.get("market_caps", [])
    total_volumes = raw.get("total_volumes", [])

    if not prices:
        raise ValueError("No price data returned. Check your API key / rate limits.")

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

    df = df.dropna(how="all")
    if df.empty:
        raise ValueError("Empty result after processing CoinGecko data.")

    logger.info("Got %s records: %s → %s", len(df), df.index.min().date(), df.index.max().date())

    df.to_csv(CSV_FILE)
    logger.info("Saved → %s", os.path.abspath(CSV_FILE))
    return df


# Backwards compatible names
def download_btc_30d_market_data(force_download: bool = False) -> pd.DataFrame:
    return download_btc_recent_market_data(days=30, force_download=force_download)

def get_btc_30d_closing_prices(force_download: bool = False) -> pd.DataFrame:
    return download_btc_recent_market_data(days=30, force_download=force_download)

def get_btc_30d_market_data(force_download: bool = False) -> pd.DataFrame:
    return download_btc_recent_market_data(days=30, force_download=force_download)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    print("\n=== CoinGecko BTC Recent Market Data Downloader ===")
    print(f"API key loaded: {'Yes (' + key_type + ')' if API_KEY else 'No (public)'}")
    print(f"Endpoint: {BASE_URL}")
    print("Cache dir:", DATA_DIR)

    try:
        print("\n--- Last 30 days ---")
        df30 = download_btc_recent_market_data(days=30)
        print(f"Loaded {len(df30)} days | Latest close: ${df30['close'].iloc[-1]:,.2f}")

        print("\n--- Last 5 days (your request) ---")
        df5 = download_btc_recent_market_data(days=5, force_download=True)
        print(df5[["close"]].to_string())

        print("\n✓ Success! You can now use this data in your charts.")
    except Exception as exc:
        print(f"\nERROR: {exc}")
        print("\nQuick fix for most users:")
        print("  Add this line to your ~/.bashrc (use the CORRECT variable name):")
        print("    export COINGECKO_DEMO_API_KEY=\"CG-yourkeyhere\"")
        print("  Then run: source ~/.bashrc")
        print("  Demo keys must use the public endpoint (api.coingecko.com), not pro-api.")
