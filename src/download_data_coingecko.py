import pandas as pd
import os
import requests
import datetime as dt
import time
import logging
from typing import Optional, Dict, Any, Tuple

"""
download_data_coingecko.py

Fetches recent ~30 days of BTC market data (closing prices + optional market cap/volume)
from CoinGecko API using direct requests (no extra deps beyond pandas/requests).

- Uses demo/pro API key from environment if available (higher rate limits).
- Caches results locally in src/coingecko_data/
- Robust error handling, retries, and logging.
- Designed to be importable like get_price_data_cryptocompare.py

Usage:
    from src import download_data_coingecko as cg
    df = cg.get_btc_30d_market_data()
    print(df[['close']].tail())

Or run directly: python src/download_data_coingecko.py
"""

# ==================== CONFIGURATION ====================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "coingecko_data")

logger = logging.getLogger(__name__)

# Load API key from environment (set in ~/.bashrc)
# Recommended: export COINGECKO_DEMO_API_KEY="CG-..."  (free demo key from coingecko.com)
# Alternative: export COINGECKO_API_KEY="..." or COINGECKO_PRO_API_KEY for paid
DEMO_KEY = os.getenv("COINGECKO_DEMO_API_KEY")
PRO_KEY = os.getenv("COINGECKO_API_KEY") or os.getenv("COINGECKO_PRO_API_KEY")

if DEMO_KEY:
    API_KEY = DEMO_KEY
    KEY_HEADER_NAME = "x-cg-demo-api-key"
elif PRO_KEY:
    API_KEY = PRO_KEY
    KEY_HEADER_NAME = "x-cg-pro-api-key"
else:
    API_KEY = None
    KEY_HEADER_NAME = None

BASE_URL = "https://api.coingecko.com/api/v3"


def _get_cache_file_path() -> str:
    """Ensure data dir exists and return path to cached 30d BTC file."""
    os.makedirs(DATA_DIR, exist_ok=True)
    return os.path.join(DATA_DIR, "coingecko_btc_recent_30d_market_data.csv")


def _make_api_request(
    endpoint: str, params: Dict[str, Any], retries: int = 3
) -> Dict[str, Any]:
    """Make robust GET request to CoinGecko with retries and proper demo/pro key header."""
    headers: Dict[str, str] = {}
    if API_KEY and KEY_HEADER_NAME:
        headers[KEY_HEADER_NAME] = API_KEY

    url = f"{BASE_URL}{endpoint}"

    for attempt in range(retries):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=20)
            response.raise_for_status()
            data = response.json()

            # CoinGecko error responses are sometimes {"error": "..."}
            if isinstance(data, dict) and "error" in data:
                raise ValueError(f"CoinGecko API Error: {data['error']}")

            return data

        except requests.exceptions.RequestException as e:
            logger.warning("Request failed (attempt %s/%s): %s", attempt + 1, retries, e)
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # exponential backoff
            else:
                raise
        except Exception as e:
            logger.error("API processing error: %s", e)
            raise


def download_btc_30d_market_data(force_download: bool = False) -> pd.DataFrame:
    """
    Download (or load cached) recent ~30 days of BTC market data from CoinGecko.

    Uses /market_chart?interval=daily which provides reliable daily closing prices.
    Returns DataFrame indexed by date (datetime) with columns:
        close, market_cap (optional), total_volume (optional)

    Caches to CSV. Refreshes automatically if cache is stale (>1 day old).
    """
    CSV_FILE = _get_cache_file_path()

    # Try cache first
    if not force_download and os.path.exists(CSV_FILE):
        try:
            df_cached = pd.read_csv(CSV_FILE, index_col=0, parse_dates=True)
            if not df_cached.empty:
                last_date = df_cached.index.max().date()
                days_since = (dt.date.today() - last_date).days
                if days_since <= 1:
                    logger.info("Using cached CoinGecko 30d data (last date: %s)", last_date)
                    return df_cached
                else:
                    logger.info("Cache stale (%s days old), refreshing...", days_since)
        except Exception as e:
            logger.warning("Failed to load cache (%s) — downloading fresh data.", e)

    logger.info("=== Downloading fresh ~30-day BTC market data from CoinGecko ===")

    endpoint = "/coins/bitcoin/market_chart"
    params = {
        "vs_currency": "usd",
        "days": "30",
        "interval": "daily",
        "precision": "2",  # nice round numbers
    }

    raw = _make_api_request(endpoint, params)

    prices = raw.get("prices", [])
    market_caps = raw.get("market_caps", [])
    total_volumes = raw.get("total_volumes", [])

    if not prices:
        raise ValueError("No price data returned. Check API key/rate limits or network.")

    # Build DataFrame from prices (timestamp_ms, close_price)
    df = pd.DataFrame(prices, columns=["timestamp_ms", "close"])
    df["date"] = pd.to_datetime(df["timestamp_ms"], unit="ms").dt.normalize()
    df = df.set_index("date").sort_index()
    df = df.drop(columns=["timestamp_ms"])

    # Join optional market cap and volume data (align on date)
    if market_caps:
        df_mc = pd.DataFrame(market_caps, columns=["ts", "market_cap"])
        df_mc["date"] = pd.to_datetime(df_mc["ts"], unit="ms").dt.normalize()
        df = df.join(df_mc.set_index("date")[["market_cap"]], how="left")

    if total_volumes:
        df_vol = pd.DataFrame(total_volumes, columns=["ts", "total_volume"])
        df_vol["date"] = pd.to_datetime(df_vol["ts"], unit="ms").dt.normalize()
        df = df.join(df_vol.set_index("date")[["total_volume"]], how="left")

    # Final cleanup
    df = df.dropna(how="all")
    if df.empty:
        raise ValueError("Empty dataset after processing CoinGecko response.")

    logger.info("Downloaded %s daily records for BTC: %s → %s",
                len(df), df.index.min().date(), df.index.max().date())

    # Persist
    df.to_csv(CSV_FILE)
    logger.info("Saved to %s", os.path.abspath(CSV_FILE))

    return df


def get_btc_30d_closing_prices(force_download: bool = False) -> pd.DataFrame:
    """Convenience wrapper returning the DataFrame focused on closing prices."""
    return download_btc_30d_market_data(force_download=force_download)


def get_btc_30d_market_data(force_download: bool = False) -> pd.DataFrame:
    """Alias for the main download function (includes close, market_cap, total_volume if available)."""
    return download_btc_30d_market_data(force_download=force_download)


# ==================== CLI / DEMO ====================
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    print("\n=== CoinGecko BTC Recent 30-Day Data Downloader ===")
    print(f"API key loaded: {'Yes (' + ('demo' if DEMO_KEY else 'pro') + ')' if API_KEY else 'No (public limits apply)'}")
    print("Data will be cached in:", DATA_DIR)

    try:
        df = get_btc_30d_market_data()
        print(f"\nSuccessfully loaded {len(df)} days of data.")
        print("\nLatest 7 days of closing prices:")
        print(df[["close"]].tail(7).to_string())
        if "market_cap" in df.columns:
            print("\nLatest market cap:", f"${df['market_cap'].iloc[-1]:,.0f}")
        if "total_volume" in df.columns:
            print("Latest 24h volume :", f"${df['total_volume'].iloc[-1]:,.0f}")
        print("\nReady to use! Example: df['close'].plot() or feed into your indicators.")
    except Exception as exc:
        print(f"\nERROR: {exc}")
        print("Tip: Check your COINGECKO_DEMO_API_KEY in ~/.bashrc or network connection.")
