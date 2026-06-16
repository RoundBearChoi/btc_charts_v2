import pandas as pd
import os
import requests
import datetime as dt
import time
import logging
from typing import Optional, Dict, Any

"""
download_data_coingecko.py

Two main capabilities:
1. download_btc_recent_market_data(days=30)   → Clean daily data for recent N days
2. download_btc_full_daily_history()            → Full history back to ~2010 (chunked safely)

Both return a clean DataFrame with exactly one row per day (close + optional market_cap/volume).
Data saved in src/coingecko_data/
"""

# ==================== CONFIGURATION ====================
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
            response = requests.get(url, params=params, headers=headers, timeout=25)
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
    """Convert CoinGecko market_chart response into clean daily DataFrame."""
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

    # Deduplicate (keep last value of each day)
    df = df[~df.index.duplicated(keep="last")]
    return df.dropna(how="all")


def download_btc_recent_market_data(
    days: int = 30,
    precision: Optional[int] = None,
    force_download: bool = False
) -> pd.DataFrame:
    """Download clean daily data for the last N days."""
    CSV_FILE = _get_cache_file_path("coingecko_btc_recent_market_data.csv")

    if not force_download and os.path.exists(CSV_FILE):
        try:
            df = pd.read_csv(CSV_FILE, index_col=0, parse_dates=True)
            if len(df) >= max(3, days - 2) and (dt.date.today() - df.index.max().date()).days <= 1:
                logger.info("Using cached recent data (%s rows)", len(df))
                return df
        except Exception:
            pass

    logger.info("Downloading last %s days (daily) from CoinGecko...", days)
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
    logger.info("Saved %s daily rows → %s", len(df), CSV_FILE)
    return df


def download_btc_full_daily_history(
    start_year: int = 2010,
    force_download: bool = False
) -> pd.DataFrame:
    """
    Download **full daily BTC history** from CoinGecko back to ~2010.

    Uses chunked requests ( ~365 days per call ) + the range endpoint
    to safely get 15+ years of clean daily closes.

    This is the function you want for "all the way back to 2010".
    """
    CSV_FILE = _get_cache_file_path("coingecko_btc_full_history_daily.csv")

    if not force_download and os.path.exists(CSV_FILE):
        try:
            df = pd.read_csv(CSV_FILE, index_col=0, parse_dates=True)
            if len(df) > 3000:  # roughly 8+ years
                logger.info("Using cached full history (%s rows, %s → %s)",
                            len(df), df.index.min().date(), df.index.max().date())
                return df
        except Exception:
            pass

    logger.info("=== Building full daily BTC history back to %s ===", start_year)

    end_date = dt.date.today()
    start_date = dt.date(start_year, 1, 1)

    all_chunks = []
    current_end = end_date

    chunk_days = 365
    request_count = 0

    while current_end > start_date:
        chunk_start = current_end - dt.timedelta(days=chunk_days)
        if chunk_start < start_date:
            chunk_start = start_date

        from_ts = int(dt.datetime.combine(chunk_start, dt.time.min).timestamp())
        to_ts   = int(dt.datetime.combine(current_end, dt.time.min).timestamp())

        logger.info("Fetching chunk: %s → %s (%s days)", chunk_start, current_end, (current_end - chunk_start).days)

        params = {
            "vs_currency": "usd",
            "from": from_ts,
            "to": to_ts,
            "interval": "daily",
        }

        try:
            raw = _make_api_request("/coins/bitcoin/market_chart/range", params)
            chunk_df = _parse_market_chart(raw)
            if not chunk_df.empty:
                all_chunks.append(chunk_df)
        except Exception as e:
            logger.warning("Chunk %s–%s failed: %s", chunk_start, current_end, e)

        current_end = chunk_start - dt.timedelta(days=1)
        request_count += 1

        # Be nice to free/demo rate limits
        time.sleep(1.2 if key_type == "demo" else 0.8)

    if not all_chunks:
        raise ValueError("No data retrieved for full history.")

    full_df = pd.concat(all_chunks).sort_index()
    full_df = full_df[~full_df.index.duplicated(keep="last")]

    logger.info("Final full history: %s daily rows from %s to %s",
                len(full_df), full_df.index.min().date(), full_df.index.max().date())

    full_df.to_csv(CSV_FILE)
    logger.info("Saved full history → %s", CSV_FILE)
    return full_df


# Backwards compatible
get_btc_30d_closing_prices = lambda force=False: download_btc_recent_market_data(days=30, force_download=force)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    print("\n=== CoinGecko BTC Downloader ===")
    print(f"Key type: {key_type} | Endpoint: {BASE_URL}")

    # Recent example
    df_recent = download_btc_recent_market_data(days=30)
    print(f"\nRecent 30 days: {len(df_recent)} clean daily rows")

    # Full history example (this is what you asked for)
    print("\nBuilding full history back to 2010 (this may take 30–60 seconds)...")
    df_full = download_btc_full_daily_history(start_year=2010, force_download=True)
    print(f"\nFull history ready: {len(df_full):,} daily rows from {df_full.index.min().date()} to {df_full.index.max().date()}")
    print("Latest 5 closes:")
    print(df_full[["close"]].tail())
