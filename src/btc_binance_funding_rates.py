#!/usr/bin/env python3
"""
btc_binance_funding_rates.py

Fetches historical BTCUSDT Perpetual funding rates from Binance Futures public API.
Caches results locally for fast subsequent runs.
Computes key statistics and generates a clean, publication-quality chart
with time series + distribution view.

Designed to fit the style and conventions of the btc_charts_v2 project
(other scripts: price_zscore_chart.py, indicators.py, get_price_data_cryptocompare.py, etc.).
"""

import os
import requests
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timezone
from pathlib import Path

# ====================== CONFIG ======================
SYMBOL = "BTCUSDT"
CACHE_DIR = Path("src/binance_funding_data")
CACHE_FILE = CACHE_DIR / "btc_funding_rates.csv"
CHART_DIR = Path("src/charts")

CACHE_DIR.mkdir(parents=True, exist_ok=True)
CHART_DIR.mkdir(parents=True, exist_ok=True)


# ====================== DATA FETCH ======================
def fetch_binance_funding_history(symbol: str = SYMBOL, start_date: str = "2019-09-01"):
    """
    Fetch complete historical funding rate data from Binance with pagination.
    Returns a clean pandas DataFrame.
    """
    url = "https://fapi.binance.com/fapi/v1/fundingRate"
    all_records = []
    limit = 1000

    start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    current_start = start_ts

    print(f"Fetching funding rates for {symbol} starting from {start_date}...")

    while True:
        params = {
            "symbol": symbol,
            "startTime": current_start,
            "limit": limit
        }
        try:
            response = requests.get(url, params=params, timeout=20)
            response.raise_for_status()
            batch = response.json()

            if not batch:
                break

            all_records.extend(batch)
            last_funding_time = batch[-1]["fundingTime"]
            current_start = last_funding_time + 1  # next page

            last_dt = datetime.fromtimestamp(last_funding_time / 1000, tz=timezone.utc)
            print(f"  + {len(batch)} records (up to {last_dt.date()}) | total so far: {len(all_records)}")

            if len(batch) < limit:
                break
        except requests.exceptions.RequestException as e:
            print(f"API request failed: {e}")
            break

    if not all_records:
        print("No data returned from Binance.")
        return pd.DataFrame()

    df = pd.DataFrame(all_records)
    df["timestamp"] = pd.to_datetime(df["fundingTime"], unit="ms", utc=True)
    df["funding_rate"] = pd.to_numeric(df["fundingRate"])
    df = df[["timestamp", "funding_rate"]].copy()
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

    print(f"\nSuccessfully fetched {len(df)} funding rate records.")
    return df


# ====================== CACHE ======================
def load_or_update_cache():
    """Load cached data or fetch + save fresh copy."""
    if CACHE_FILE.exists():
        print("Loading cached funding rate data...")
        df = pd.read_csv(CACHE_FILE, parse_dates=["timestamp"])
        # If cache older than ~2 days, refresh
        if (datetime.now(timezone.utc) - df["timestamp"].max()).days > 2:
            print("Cache is outdated — fetching latest data...")
            new_df = fetch_binance_funding_history()
            if not new_df.empty:
                # Merge and dedup
                df = pd.concat([df, new_df]).drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
                df.to_csv(CACHE_FILE, index=False)
                print(f"Updated cache with latest data ({len(df)} total records).")
        else:
            print(f"Cache is fresh (latest: {df['timestamp'].max().date()}).")
    else:
        print("No cache found — fetching full history from Binance...")
        df = fetch_binance_funding_history()
        if not df.empty:
            df.to_csv(CACHE_FILE, index=False)
            print(f"Created new cache file with {len(df)} records.")
    return df


# ====================== STATISTICS ======================
def print_funding_stats(df: pd.DataFrame):
    if df.empty:
        return
    rates_pct = df["funding_rate"] * 100
    print("\n" + "="*50)
    print("BTCUSDT Perpetual Funding Rate Statistics (Binance)")
    print("="*50)
    print(f"Date range:          {df['timestamp'].min().date()}  →  {df['timestamp'].max().date()}")
    print(f"Total 8-hour periods: {len(df):,}")
    print(f"Mean funding rate:    {rates_pct.mean():.5f} %")
    print(f"Median:               {rates_pct.median():.5f} %")
    print(f"Std deviation:        {rates_pct.std():.5f} %")
    print(f"Maximum:              {rates_pct.max():.5f} %")
    print(f"Minimum:              {rates_pct.min():.5f} %")
    pos_pct = (rates_pct > 0).mean() * 100
    print(f"Time positive:        {pos_pct:.1f} % of periods")
    print(f"Cumulative (long):    {rates_pct.sum():.2f} % over entire history")
    print("="*50 + "\n")


# ====================== CHART ======================
def create_funding_chart(df: pd.DataFrame):
    if df.empty:
        print("No data available for charting.")
        return

    df = df.set_index("timestamp")

    # Prepare daily average for smoother long-term view
    daily_avg = df["funding_rate"].resample("D").mean() * 100

    fig, (ax1, ax2) = plt.subplots(
        2, 1,
        figsize=(15, 10),
        gridspec_kw={"height_ratios": [3.5, 1]},
        sharex=True
    )

    # --- Top panel: Time series ---
    # Color points by sign
    colors = ["#27ae60" if r >= 0 else "#c0392b" for r in df["funding_rate"]]
    ax1.scatter(
        df.index, df["funding_rate"] * 100,
        c=colors, s=6, alpha=0.55, label="8h Funding Rate"
    )

    # 30-day rolling average (approx 90 periods of 8h)
    roll_mean = df["funding_rate"].rolling(window=90, min_periods=30).mean() * 100
    ax1.plot(
        roll_mean.index, roll_mean,
        color="#2980b9", linewidth=2.0, label="30-day Rolling Mean"
    )

    ax1.axhline(0, color="#2c3e50", linewidth=1.2, linestyle="--", alpha=0.8)
    ax1.set_ylabel("Funding Rate (%)", fontsize=12)
    ax1.set_title(
        f"Binance BTCUSDT Perpetual Funding Rates\n{df.index.min().strftime('%Y-%m-%d')} — {df.index.max().strftime('%Y-%m-%d')}",
        fontsize=14, pad=15
    )
    ax1.legend(loc="upper left", framealpha=0.9)
    ax1.grid(True, alpha=0.25)
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"{x:.3f}%"))

    # --- Bottom panel: Distribution ---
    ax2.hist(
        df["funding_rate"] * 100,
        bins=100,
        color="#8e44ad",
        alpha=0.75,
        edgecolor="white",
        linewidth=0.3
    )
    ax2.axvline(0, color="#2c3e50", linewidth=1.5)
    ax2.set_xlabel("Funding Rate (%)", fontsize=12)
    ax2.set_ylabel("Count", fontsize=11)
    ax2.set_title("Distribution of 8h Funding Rates", fontsize=12)
    ax2.grid(True, alpha=0.25, axis="y")

    # Add some stats text box
    stats_text = (
        f"Mean: { (df['funding_rate']*100).mean():.4f}%  |  "
        f"Median: {(df['funding_rate']*100).median():.4f}%  |  "
        f"Std: {(df['funding_rate']*100).std():.4f}%"
    )
    ax2.text(0.98, 0.95, stats_text, transform=ax2.transAxes,
             fontsize=9, verticalalignment="top", horizontalalignment="right",
             bbox=dict(boxstyle="round", facecolor="white", alpha=0.85))

    plt.tight_layout()
    plt.subplots_adjust(hspace=0.08)

    # Save high-res chart
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M")
    out_file = CHART_DIR / f"btc_binance_funding_rates_{timestamp_str}.png"
    plt.savefig(out_file, dpi=160, bbox_inches="tight", facecolor="white")
    print(f"\nChart saved → {out_file}")
    plt.close()


# ====================== MAIN ======================
if __name__ == "__main__":
    print("\n=== BTC Binance Funding Rates Chart ===\n")
    df = load_or_update_cache()
    print_funding_stats(df)
    create_funding_chart(df)
    print("Done!\n")
