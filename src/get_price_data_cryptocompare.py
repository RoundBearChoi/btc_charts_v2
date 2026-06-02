import pandas as pd
import os
import cryptocompare
import math
import datetime as dt
import time

# ==================== CONFIGURATION ====================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "cryptocompare_data")
# =======================================================

def _get_cache_file_path(coin: str) -> str:
    """Return the correct CSV path for a coin (BTC keeps original name)."""
    if coin.upper() == "BTC":
        return os.path.join(DATA_DIR, 'cryptocompare_historic_btc_price.csv')
    return os.path.join(DATA_DIR, f'cryptocompare_historic_{coin.lower()}_price.csv')


def _clean_price_dataframe(df: pd.DataFrame, coin: str = "BTC") -> pd.DataFrame:
    """
    Clean price DataFrame:
      - Remove rows where ALL price/volume columns are zero (pre-trading artifacts).
      - Drop unnecessary API metadata columns.
    """
    if df.empty:
        return df

    numeric_cols = ['high', 'low', 'open', 'volumefrom', 'volumeto', 'close']
    zero_mask = (df[numeric_cols] == 0).all(axis=1)
    removed_count = zero_mask.sum()

    if removed_count > 0:
        df = df[~zero_mask].copy()
        print(f"Removed {removed_count:,} all-zero pre-trading rows for {coin}.")
    else:
        print(f"No all-zero pre-trading rows found for {coin}.")

    metadata_cols = ['conversionType', 'conversionSymbol']
    dropped = []
    for col in metadata_cols:
        if col in df.columns:
            df = df.drop(columns=[col])
            dropped.append(col)
    if dropped:
        print(f"Dropped metadata columns for {coin}: {', '.join(dropped)}")

    return df


def _download_historic_daily(coin: str, currency: str, years: float, end_date: dt.date = None) -> pd.DataFrame:
    """Core download function (chunked to respect CryptoCompare 2000-day limit)."""
    if end_date is None:
        end_date = dt.date.today()
    
    total_days = math.ceil(years * 365.25)
    print(f"\nDownloading ~{years} years ({total_days} days) of {coin}/{currency} data ending on {end_date}...")

    data = []
    days_per_chunk = 2000
    num_full_chunks = total_days // days_per_chunk
    remaining_days = total_days % days_per_chunk

    current_end = end_date

    for i in range(num_full_chunks):
        chunk_data = cryptocompare.get_historical_price_day(
            coin, currency=currency, limit=days_per_chunk, toTs=current_end
        )
        data.extend(chunk_data)
        current_end = current_end - dt.timedelta(days=days_per_chunk)
        time.sleep(0.5)

    if remaining_days > 0:
        chunk_data = cryptocompare.get_historical_price_day(
            coin, currency=currency, limit=remaining_days, toTs=current_end
        )
        data.extend(chunk_data)

    if not data:
        print(f"No data returned for {coin}.")
        return pd.DataFrame()

    df = pd.DataFrame(data)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    df = df.sort_index()

    print(f"Downloaded {len(df):,} days of raw {coin} data.")
    return df


def _download_full_historic_df(coin: str, currency: str = "USD", years_per_batch: float = 8.0) -> pd.DataFrame:
    print(f"\n=== Downloading full history for {coin}/{currency} ===")
    today = dt.date.today()

    df_recent = _download_historic_daily(coin, currency, years_per_batch)

    time.sleep(1)

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

    # Final cleaning (once)
    full_df = _clean_price_dataframe(full_df, coin=coin)

    # Deduplicate any accidental overlap
    if not full_df.empty:
        full_df = full_df[~full_df.index.duplicated(keep='first')]

    if not full_df.empty:
        print(f"\nFinal cleaned {coin} DataFrame: {len(full_df):,} rows "
              f"from {full_df.index.min().date()} to {full_df.index.max().date()}")
    else:
        print(f"\nNo data available for {coin}.")

    return full_df


def _load_price_data(coin: str) -> pd.DataFrame:
    """Load cached data for any coin."""
    CSV_FILE = _get_cache_file_path(coin)
    if not os.path.exists(CSV_FILE):
        raise FileNotFoundError(
            f"❌ '{CSV_FILE}' not found for {coin}.\n"
            f"Please run get_price_data(coin='{coin}') with force_download=True first.")
    
    print(f"\nLoading {coin} data from {CSV_FILE}...")
    df = pd.read_csv(CSV_FILE, index_col=0, parse_dates=True)
    print(f"Loaded {len(df):,} rows for {coin} (latest date: {df.index.max().date()})")
    return df


# ==================== PUBLIC API ====================

def get_price_data(coin: str = "BTC", force_download: bool = False) -> pd.DataFrame:
    """Get price data for ANY coin (BTC, FARTCOIN, TROLL, PEPE...)"""
    coin = coin.upper()
    CSV_FILE = _get_cache_file_path(coin)

    if not force_download and os.path.exists(CSV_FILE):
        try:
            print(f"\n📁 Existing cached {coin} data detected.")
            df_cached = _load_price_data(coin)
            print(f"Current cache: {df_cached.index.min().date()} → {df_cached.index.max().date()}")
            response = input(f"\n🔄 Download fresh full history for {coin}? (y/n): ").strip().lower()
            if response not in ['y', 'yes']:
                print(f"✅ Using cached {coin} data.")
                return df_cached
        except Exception as e:
            print(f"⚠️ {e} — downloading fresh...")

    print(f"\n🚀 Starting fresh {coin} download from CryptoCompare...")
    daily = _download_full_historic_df(coin, years_per_batch=8.0)
    
    os.makedirs(DATA_DIR, exist_ok=True)
    daily.to_csv(CSV_FILE)
    print(f"✅ {coin} data saved → {os.path.abspath(CSV_FILE)}")
    return daily


def get_btc_price_data(force_download: bool = False) -> pd.DataFrame:
    return get_price_data(coin="BTC", force_download=force_download)


# ==================== DEMO / CLI ====================
if __name__ == "__main__":
    print("=== Crypto Price Data Fetcher (CryptoCompare) ===")
    df_btc = get_btc_price_data()
    print(f"BTC ready: {len(df_btc):,} rows")
    print("✅ Ready for FARTCOIN, TROLL, or any ticker!")
