import pandas as pd
import os
import requests
import math
import datetime as dt
import time
import logging
from typing import Optional, Dict, Any

# ==================== CONFIGURATION ====================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "cryptocompare_data")

logger = logging.getLogger(__name__)

# Optional API key for higher limits (get free at https://min-api.cryptocompare.com/)
API_KEY = os.getenv("CRYPTOCOMPARE_API_KEY")

BASE_URL = "https://min-api.cryptocompare.com/data/v2/histoday"


def _get_cache_file_path(coin: str) -> str:
    """Return the correct CSV path for a coin (BTC keeps original name)."""
    if coin.upper() == "BTC":
        return os.path.join(DATA_DIR, "cryptocompare_historic_btc_price.csv")
    return os.path.join(DATA_DIR, f"cryptocompare_historic_{coin.lower()}_price.csv")


def _clean_price_dataframe(df: pd.DataFrame, coin: str = "BTC") -> pd.DataFrame:
    """
    Clean price DataFrame:
      - Remove rows where ALL price/volume columns are zero (pre-trading artifacts).
      - Drop unnecessary API metadata columns.
    """
    if df.empty:
        return df

    numeric_cols = ["high", "low", "open", "volumefrom", "volumeto", "close"]
    zero_mask = (df[numeric_cols] == 0).all(axis=1)
    removed_count = zero_mask.sum()

    if removed_count > 0:
        df = df[~zero_mask].copy()
        logger.info("Removed %s all-zero pre-trading rows for %s.", removed_count, coin)
    else:
        logger.debug("No all-zero pre-trading rows found for %s.", coin)

    metadata_cols = ["conversionType", "conversionSymbol"]
    dropped = []
    for col in metadata_cols:
        if col in df.columns:
            df = df.drop(columns=[col])
            dropped.append(col)
    if dropped:
        logger.debug("Dropped metadata columns for %s: %s", coin, ", ".join(dropped))

    return df


def _make_api_request(params: Dict[str, Any], retries: int = 3) -> Dict:
    """Robust API request with error handling and rate limiting."""
    headers = {}
    if API_KEY:
        headers["authorization"] = f"Apikey {API_KEY}"

    for attempt in range(retries):
        try:
            response = requests.get(BASE_URL, params=params, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()

            if data.get("Response") == "Error":
                error_msg = data.get("Message", "Unknown error")
                raise ValueError(f"CryptoCompare API Error: {error_msg}")

            if "Data" not in data or "Data" not in data.get("Data", {}):
                raise ValueError(f"Unexpected API response structure: {list(data.keys())}")

            return data

        except requests.exceptions.RequestException as e:
            logger.warning(f"Request failed (attempt {attempt+1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # exponential backoff
            else:
                raise
        except Exception as e:
            logger.error(f"API error: {e}")
            raise


def _download_historic_daily(
    coin: str, currency: str, years: float, end_date: Optional[dt.date] = None
) -> pd.DataFrame:
    """Core download function using direct v2 API (more reliable)."""
    if end_date is None:
        end_date = dt.date.today()

    total_days = math.ceil(years * 365.25)
    logger.info("Downloading ~%s years (%s days) of %s/%s data ending on %s...",
                years, total_days, coin, currency, end_date)

    data = []
    days_per_chunk = 2000
    current_end_ts = int(end_date.timestamp())

    while total_days > 0:
        limit = min(days_per_chunk, total_days)

        params = {
            "fsym": coin,
            "tsym": currency,
            "limit": limit,
            "toTs": current_end_ts
        }

        api_response = _make_api_request(params)
        chunk = api_response["Data"]["Data"]

        if not chunk:
            logger.warning("Empty chunk received for %s.", coin)
            break

        data.extend(chunk)

        # Move to previous period
        if chunk:
            current_end_ts = chunk[0]["time"] - 1
        else:
            current_end_ts -= (limit * 86400)
        total_days -= limit

        time.sleep(1.2)  # Respect rate limits

    if not data:
        logger.warning("No data returned for %s.", coin)
        return pd.DataFrame()

    df = pd.DataFrame(data)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    df = df.sort_index()

    logger.info("Downloaded %s days of raw %s data.", len(df), coin)
    return df


def _download_full_historic_df(
    coin: str, currency: str = "USD", years_per_batch: float = 8.0
) -> pd.DataFrame:
    logger.info("=== Downloading full history for %s/%s ===", coin, currency)
    today = dt.date.today()

    df_recent = _download_historic_daily(coin, currency, years_per_batch)

    time.sleep(1.5)

    if not df_recent.empty:
        older_end_date = df_recent.index.min().date() - dt.timedelta(days=1)
        df_older = _download_historic_daily(coin, currency, years_per_batch, end_date=older_end_date)
    else:
        df_older = pd.DataFrame()

    # Combine
    if not df_older.empty and not df_recent.empty:
        full_df = pd.concat([df_older, df_recent])
    elif not df_older.empty:
        full_df = df_older
    else:
        full_df = df_recent

    full_df = full_df.sort_index()

    # Final cleaning
    full_df = _clean_price_dataframe(full_df, coin=coin)

    if not full_df.empty:
        full_df = full_df[~full_df.index.duplicated(keep="first")]

    if not full_df.empty:
        logger.info("Final cleaned %s DataFrame: %s rows from %s to %s",
                    coin, len(full_df), full_df.index.min().date(), full_df.index.max().date())
    else:
        logger.warning("No data available for %s.", coin)

    return full_df


def _load_price_data(coin: str) -> pd.DataFrame:
    """Load cached data for any coin."""
    CSV_FILE = _get_cache_file_path(coin)
    if not os.path.exists(CSV_FILE):
        raise FileNotFoundError(
            f"'{CSV_FILE}' not found for {coin}.\n"
            f"Please run get_price_data(coin='{coin}') with force_download=True first.")

    logger.info("Loading %s data from %s...", coin, CSV_FILE)
    df = pd.read_csv(CSV_FILE, index_col=0, parse_dates=True)
    logger.info("Loaded %s rows for %s (latest date: %s)", len(df), coin, df.index.max().date())
    return df


# ==================== PUBLIC API ====================

def get_price_data(coin: str = "BTC", force_download: bool = False) -> pd.DataFrame:
    """Get price data for ANY coin with robust direct API calls."""
    coin = coin.upper()
    CSV_FILE = _get_cache_file_path(coin)

    if not force_download and os.path.exists(CSV_FILE):
        try:
            logger.info("Existing cached %s data detected.", coin)
            df_cached = _load_price_data(coin)
            logger.info("Current cache: %s → %s", df_cached.index.min().date(), df_cached.index.max().date())
            response = input(f"\nDownload fresh full history for {coin}? (y/n): ").strip().lower()
            if response not in ["y", "yes"]:
                logger.info("Using cached %s data.", coin)
                return df_cached
        except Exception as e:
            logger.warning("%s — downloading fresh...", e)

    logger.info("Starting fresh %s download from CryptoCompare...", coin)
    daily = _download_full_historic_df(coin, years_per_batch=8.0)

    os.makedirs(DATA_DIR, exist_ok=True)
    daily.to_csv(CSV_FILE)
    logger.info("%s data saved → %s", coin, os.path.abspath(CSV_FILE))
    return daily


def get_btc_price_data(force_download: bool = False) -> pd.DataFrame:
    return get_price_data(coin="BTC", force_download=force_download)


# ==================== DEMO / CLI ====================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=== Crypto Price Data Fetcher (Reliable v2) ===")
    df_btc = get_btc_price_data()
    print(f"BTC ready: {len(df_btc):,} rows")
    print("Ready for FARTCOIN, TROLL, or any ticker!")