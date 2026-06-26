#!/usr/bin/env python3
"""
btc_funding_rates_window.py

Interactive Binance BTCUSDT Perpetual Funding Rates chart window.
Follows the draw() + plt.show() pattern used by other scripts in btc_charts_v2.

UPDATED: Now uses a rolling Z-Score on funding rates (instead of fixed absolute thresholds)
to identify when funding is statistically "too high" or "too low" relative to recent history.
This is more adaptive and useful given how tightly BTC funding rates cluster near zero.

Top panel: Daily average funding rate with positive/negative fills.
Bottom panel: Funding rate Z-Score with statistical reference lines (+2 / +3 / -2 / -3).

Run directly to open an interactive matplotlib window.
"""

import requests
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta, timezone
from pathlib import Path

from plotting_utils import add_date_formatters

# ====================== CONFIG ======================
SYMBOL = "BTCUSDT"
LOOKBACK_YEARS = 2          # Default lookback. Change here or pass to draw()

# Z-Score configuration (recommended way to judge "too high / too low")
ZSCORE_WINDOW_DAYS = 180    # Rolling window in days. 90-365 is reasonable.
                            # Longer window = slower to adapt to regime changes.
ZSCORE_COLOR = '#d62728'

# Optional light absolute reference lines in top panel (economic "pain" levels)
# These are kept mild because BTC funding rarely stays high for long.
SHOW_ABSOLUTE_REFS = True
ABS_MODERATE = 0.025        # ~0.025% = noticeable but not extreme
ABS_HIGH     = 0.04         # ~0.04% = getting expensive for one side

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


def add_funding_zscore(daily_series: pd.Series, window: int = 180) -> pd.Series:
    """Compute rolling z-score of daily funding rates.

    Z = (value - rolling_mean) / rolling_std
    Uses min_periods so we get values reasonably early.
    """
    rolling_mean = daily_series.rolling(window=window, min_periods=max(30, window // 3)).mean()
    rolling_std = daily_series.rolling(window=window, min_periods=max(30, window // 3)).std()
    rolling_std = rolling_std.replace(0, np.nan)
    zscore = (daily_series - rolling_mean) / rolling_std
    return zscore


def print_stats(df, years: int, zscore_window: int):
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
    print(f"Z-Score window:  {zscore_window} days (used in chart)")
    print("=" * 55 + "\n")


def draw(lookback_years: int = LOOKBACK_YEARS,
         zscore_window: int = ZSCORE_WINDOW_DAYS,
         block_window: bool = True):
    """Main function to fetch data and display interactive funding rates + z-score chart."""
    df = load_or_update_cache(lookback_years)
    if df.empty:
        print("No funding rate data available.")
        return

    print_stats(df, lookback_years, zscore_window)

    df = df.set_index("timestamp").sort_index()
    daily = df["funding_rate"].resample("D").mean() * 100

    # Compute funding rate z-score
    daily_z = add_funding_zscore(daily, window=zscore_window)

    # === Create 2-panel figure (Funding Rate on top, Z-Score below) ===
    fig, (ax1, ax2) = plt.subplots(
        2, 1,
        figsize=(13, 9),
        gridspec_kw={"height_ratios": [2.2, 1]},
        sharex=True
    )
    plt.style.use("fast")

    # --- Top panel: Daily Funding Rate ---
    ax1.plot(daily.index, daily, color="#1f77b4", linewidth=1.5, label="Daily Avg Funding Rate")
    ax1.fill_between(daily.index, daily, 0,
                     where=(daily >= 0), color="#2ca02c", alpha=0.30, label="Positive (longs pay)")
    ax1.fill_between(daily.index, daily, 0,
                     where=(daily < 0), color="#d62728", alpha=0.30, label="Negative (shorts pay)")

    ax1.axhline(0, color="#333333", linewidth=1.0, linestyle="--", alpha=0.7, label="Zero (neutral)")

    # Light absolute reference lines (optional economic context)
    if SHOW_ABSOLUTE_REFS:
        ax1.axhline(ABS_MODERATE, color="#ff7f0e", linestyle=":", linewidth=1.0, alpha=0.6,
                    label=f"+{ABS_MODERATE:.3f}% Moderate elevated")
        ax1.axhline(-ABS_MODERATE, color="#ff7f0e", linestyle=":", linewidth=1.0, alpha=0.6)
        ax1.axhline(ABS_HIGH, color="#d62728", linestyle=":", linewidth=1.0, alpha=0.5,
                    label=f"+{ABS_HIGH:.3f}% High (expensive)")
        ax1.axhline(-ABS_HIGH, color="#2ca02c", linestyle=":", linewidth=1.0, alpha=0.5)

    ax1.set_ylabel("Funding Rate (%)", fontsize=12)
    ax1.set_title(f"Binance BTCUSDT Perpetual Funding Rates + Z-Score ({zscore_window}d window) | Last {lookback_years} Years",
                  fontsize=14, pad=12)
    ax1.legend(loc="upper left", fontsize=9, framealpha=0.9)
    ax1.grid(True, alpha=0.3)
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.3f}%"))

    # --- Bottom panel: Funding Z-Score ---
    ax2.plot(daily.index, daily_z, color=ZSCORE_COLOR, linewidth=1.6, label=f"Funding Z-Score ({zscore_window}d)")

    # Statistical reference lines (main way to judge "too high / too low")
    ax2.axhline(0, color="black", linestyle="-", linewidth=0.9, alpha=0.8, label="Mean (0)")
    ax2.axhline(2, color="#d62728", linestyle="--", linewidth=1.2, alpha=0.85,
                label="+2σ — Elevated (longs paying more than usual)")
    ax2.axhline(-2, color="#2ca02c", linestyle="--", linewidth=1.2, alpha=0.85,
                label="-2σ — Depressed (shorts paying more than usual)")
    ax2.axhline(3, color="#8B0000", linestyle=":", linewidth=1.1, alpha=0.7,
                label="+3σ — Very High / Extreme")
    ax2.axhline(-3, color="#006400", linestyle=":", linewidth=1.1, alpha=0.7,
                label="-3σ — Very Low / Extreme")

    ax2.set_ylabel("Z-Score", fontsize=12)
    ax2.set_xlabel("Date")
    ax2.legend(loc="upper left", fontsize=8, framealpha=0.9)
    ax2.grid(True, alpha=0.3)

    # Date formatting on shared x-axis
    add_date_formatters(ax2)
    plt.xticks(rotation=0)

    plt.tight_layout()
    plt.show(block=block_window)


if __name__ == "__main__":
    draw()
