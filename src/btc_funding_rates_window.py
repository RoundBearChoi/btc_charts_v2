#!/usr/bin/env python3
"""
btc_funding_rates_window.py

Interactive Binance BTCUSDT Perpetual Funding Rates chart window.
Follows the draw() + plt.show() pattern used by other scripts in btc_charts_v2.

Run directly to open an interactive matplotlib window.
"""

import requests
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta, timezone
from pathlib import Path

from plotting_utils import add_date_formatters

# ====================== CONFIG ======================
SYMBOL = "BTCUSDT"
LOOKBACK_YEARS = 2          # Default lookback. Change here or pass to draw()

CACHE_DIR = Path("src/binance_funding_data")
CACHE_FILE = CACHE_DIR / "btc_funding_rates.csv"

CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_start_date(years: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=years * 365 + 30)).strftime("%Y-%m-%d")


def fetch_binance_funding_history(symbol: str, years: int):
    start_date = get_start_date(years)
    url = "https://fapi.binance.com/fapi/v1/fundingRate"
    all_records = []
    limit = 1000
    start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    current_start = start_ts

    print(f"Fetching {symbol} funding rates (last {years} years)...")
    while True:
        params = {"symbol": symbol, "startTime": current_start, "limit": limit}
        try:
            resp = requests.get(url, params=params, timeout=20)
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            all_records.extend(batch)
            last_ts = batch[-1]["fundingTime"]
            current_start = last_ts + 1
            if len(batch) < limit:
                break
        except Exception as e:
            print(f"Error fetching data: {e}")
            break

    if not all_records:
        return pd.DataFrame()

    df = pd.DataFrame(all_records)
    df["timestamp"] = pd.to_datetime(df["fundingTime"], unit="ms", utc=True)
    df["funding_rate"] = pd.to_numeric(df["fundingRate"])
    df = df[["timestamp", "funding_rate"]].drop_duplicates().sort_values("timestamp").reset_index(drop=True)
    return df


def load_or_update_cache(years: int = LOOKBACK_YEARS):
    cutoff = datetime.now(timezone.utc) - timedelta(days=years * 365 + 30)

    if CACHE_FILE.exists():
        df = pd.read_csv(CACHE_FILE, parse_dates=["timestamp"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], format="mixed", utc=True)
        df = df[df["timestamp"] >= cutoff]

        if (datetime.now(timezone.utc) - df["timestamp"].max()).days > 2:
            new_df = fetch_binance_funding_history(SYMBOL, years)
            if not new_df.empty:
                df = pd.concat([df, new_df]).drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
                df.to_csv(CACHE_FILE, index=False)
    else:
        df = fetch_binance_funding_history(SYMBOL, years)
        if not df.empty:
            df.to_csv(CACHE_FILE, index=False)
    return df


def print_stats(df, years: int):
    if df.empty:
        return
    r = df["funding_rate"] * 100
    print("=" * 55)
    print(f"BTCUSDT Funding Rates (Last {years} years)")
    print("=" * 55)
    print(f"Period:          {df['timestamp'].min().date()} → {df['timestamp'].max().date()}")
    print(f"# Periods:       {len(df):,}")
    print(f"Mean / Median:   {r.mean():.5f}% / {r.median():.5f}%")
    print(f"Std / Max / Min: {r.std():.5f}% / {r.max():.5f}% / {r.min():.5f}%")
    print(f"% Positive:      {(r > 0).mean() * 100:.1f}%")
    print(f"Cumulative long: {r.sum():.2f}%")
    print("=" * 55 + "\n")


def draw(lookback_years: int = LOOKBACK_YEARS, block_window: bool = True):
    """Main function to fetch data and display interactive funding rates chart."""
    df = load_or_update_cache(lookback_years)
    if df.empty:
        print("No funding rate data available.")
        return

    print_stats(df, lookback_years)

    df = df.set_index("timestamp").sort_index()
    daily = df["funding_rate"].resample("D").mean() * 100

    fig, ax = plt.subplots(figsize=(13, 7))

    # Plot daily average funding rate
    ax.plot(daily.index, daily, color="#1f77b4", linewidth=1.4, label="Daily Avg")
    ax.fill_between(daily.index, daily, 0,
                    where=(daily >= 0), color="#2ca02c", alpha=0.28)
    ax.fill_between(daily.index, daily, 0,
                    where=(daily < 0), color="#d62728", alpha=0.28)

    ax.axhline(0, color="#333333", linewidth=0.9, linestyle="--", alpha=0.65)

    # Dynamic y-axis to reduce white space
    ymin = daily.min()
    ymax = daily.max()
    padding = (ymax - ymin) * 0.20
    ax.set_ylim(ymin - padding, ymax + padding)

    ax.set_ylabel("Funding Rate (%)", fontsize=12)
    ax.set_title(f"Binance BTCUSDT Perpetual Funding Rates | Last {lookback_years} Years",
                 fontsize=14, pad=12)

    # Use shared date formatting helper
    add_date_formatters(ax)

    # Percentage formatter (override default dollar formatter style)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.2f}%"))
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.show(block=block_window)


if __name__ == "__main__":
    draw()
