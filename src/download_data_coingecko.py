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

Supports both Demo keys (free higher limits) and Pro keys.
- Pro keys automatically use https://pro-api.coingecko.com
- Demo / no key use the public endpoint.

Caches results locally in src/coingecko_data/
Robust retries, logging, and smart cache refresh.

Usage examples:
    import src.download_data_coingecko as cg
    df = cg.download_btc_recent_market_data(days=30)
    df5 = cg.download_btc_recent_market_data(days=5, force_download=True)

Or run directly: python src/download_data_coingecko.py
"""

# ==================== CONFIGURATION ====================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "coingecko_data")

logger = logging.getLogger(__name__)

# Load API key from environment (set in ~/.bashrc)
# Demo (free): export COINGECKO_DEMO_API_KEY="CG-..."
# Pro (paid):  export COINGECKO_API_KEY="..."  or COINGECKO_PRO_API_KEY="..."
DEMO_KEY = os.getenv("COINGECKO_DEMO_API_KEY")
PRO_KEY = os.getenv("COINGECKO_API_KEY") or os.getenv("COINGECKO_PRO_API_KEY")

if DEMO_KEY:
    API_KEY = DEMO_KEY
    KEY_HEADER_NAME = "x-cg-demo-api-key"
    BASE_URL = "https://api.coingecko.com/api/v3"
elif PRO_KEY:
    API_KEY = PRO_KEY
    KEY_HEADER_NAME = "x-cg-pro-api-key"
    BASE_URL = "https://pro-api.coingecko.com/api/v3"   # <-- Important for Pro keys
else:
    API_KEY = None
    KEY_HEADER_NAME = None
    BASE_URL = "https://api.coingecko.com/api/v3"


def _get_cache_file_path() -> str:
    """Return path for the recent market data cache."""
    os.makedirs(DATA_DIR, exist_ok=True)
    return os.path.join(DATA_DIR, "coingecko_btc_recent_market_data.csv")


def _make_api_request(
    endpoint: str, params: Dict[str, Any], retries: int = 3
) -> Dict[str, Any]:
    """Robust request with retries. Logs response body on final failure for debugging."""
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
            # Try to show server response body if available
            if hasattr(e, 'response') and e.response is not None:
                try:
                    logger.warning("Server response: %s", e.response.text[:500])
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
    Download (or load from cache) recent BTC market data from CoinGecko.

    Args:
        days: Number of days of history (default 30). CoinGecko supports up to ~365 for daily.
        precision: Decimal places for prices (e.g. 2). Omit for default server precision.
        force_download: Ignore cache and fetch fresh.

    Returns DataFrame with datetime index and columns: close, [market_cap], [total_volume]
    """
    CSV_FILE = _get_cache_file_path()

    # Smart cache check (only reuse if we have enough recent data)
    if not force_download and os.path.exists(CSV_FILE):
        try:
            df_cached = pd.read_csv(CSV_FILE, index_col=0, parse_dates=True)
            if not df_cached.empty:
                last_date = df_cached.index.max().date()
                data_age_days = (dt.date.today() - last_date).days
                # Reuse if cache covers at least the requested days and is fresh
                if data_age_days <= 1 and len(df_cached) >= max(3, days - 2):
                    logger.info("Using cached CoinGecko data (%s rows, last: %s)", len(df_cached), last_date)
                    return df_cached
                else:
                    logger.info("Cache insufficient or stale (age=%s days, rows=%s) — refreshing...", data_age_days, len(df_cached))
        except Exception as e:
            logger.warning("Cache load failed (%s) — downloading fresh.", e)

    logger.info("=== Downloading fresh last %s days of BTC data from CoinGecko ===", days)

    endpoint = "/coins/bitcoin/market_chart"
    params: Dict[str, Any] = {
        "vs_currency": "usd",
        "days": str(days),
    }
    if precision is not None:
        params["precision"] = str(precision)

    # Note: We intentionally omit 'interval' param.
    # CoinGecko returns appropriate granularity; for days<=90 it is usually daily.
    # Adding interval=daily can sometimes trigger 400 on Pro endpoint.

    raw = _make_api_request(endpoint, params)

    prices = raw.get("prices", [])
    market_caps = raw.get("market_caps", [])
    total_volumes = raw.get("total_volumes", [])

    if not prices:
        raise ValueError("No price data returned from CoinGecko. Check key, rate limits, or params.")

    # Build clean DataFrame
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
        raise ValueError("Empty DataFrame after processing CoinGecko response.")

    logger.info("Downloaded %s records for BTC: %s → %s", len(df), df.index.min().date(), df.index.max().date())

    df.to_csv(CSV_FILE)
    logger.info("Saved to %s", os.path.abspath(CSV_FILE))

    return df


# Backwards-compatible aliases (so existing imports don't break)
def download_btc_30d_market_data(force_download: bool = False) -> pd.DataFrame:
    return download_btc_recent_market_data(days=30, force_download=force_download)

def get_btc_30d_closing_prices(force_download: bool = False) -> pd.DataFrame:
    return download_btc_recent_market_data(days=30, force_download=force_download)

def get_btc_30d_market_data(force_download: bool = False) -> pd.DataFrame:
    return download_btc_recent_market_data(days=30, force_download=force_download)


# ==================== CLI / DEMO ====================
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    print("\n=== CoinGecko BTC Recent Market Data Downloader ===")
    key_type = "demo" if DEMO_KEY else ("pro" if PRO_KEY else "none")
    print(f"API key loaded: {'Yes (' + key_type + ')' if API_KEY else 'No (public limits)'}")
    print(f"Using endpoint: {BASE_URL}")
    print("Cache folder:", DATA_DIR)

    try:
        # Default: last 30 days
        print("\n--- Fetching last 30 days ---")
        df30 = download_btc_recent_market_data(days=30)
        print(f"Loaded {len(df30)} days. Latest close: ${df30['close'].iloc[-1]:,.2f}")

        # Quick test for your request: last 5 days
        print("\n--- Fetching last 5 days (as you requested) ---")
        df5 = download_btc_recent_market_data(days=5, force_download=True)
        print("Last 5 days of closing prices:")
        print(df5[["close"]].to_string())

        print("\nSuccess! Data is cached and ready for your charts or analysis.")
        print("You can now import and use: download_btc_recent_market_data(days=5) etc.")

    except Exception as exc:
        print(f"\nERROR: {exc}")
        print("Tips:")
        print("  - Double-check your COINGECKO_*_API_KEY in ~/.bashrc (and source it)")
        print("  - For Pro keys we now correctly use pro-api.coingecko.com")
        print("  - Try without precision first, or test with smaller 'days' value")
        print("  - Check CoinGecko status or your key's remaining credits")
