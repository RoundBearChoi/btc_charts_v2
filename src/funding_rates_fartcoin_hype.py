#!/usr/bin/env python3
"""
funding_rates_fartcoin_hype.py

Interactive 3-panel chart for FARTCOIN on Hyperliquid:
  1. FARTCOIN Price (top) with 50-day and 111-day SMAs
  2. Daily Funding Rate (middle)  -- averaged from hourly Hyperliquid data
  3. Funding Rate Z-Score (bottom)

This gives excellent context: you can see how price action (with key moving averages)
relates to funding pressure and statistical extremes on Hyperliquid perps.

Adapted from funding_rates_btc_binance.py but uses Hyperliquid's fundingHistory endpoint
instead of Binance, and CryptoCompare price data for FARTCOIN (memecoin support).

Follows the draw() + plt.show() pattern used by other scripts in btc_charts_v2.

Run directly to open an interactive matplotlib window.
(Requires internet + the local modules: plotting_utils.py and get_price_data_cryptocompare.py
 in the same directory or PYTHONPATH.)

Hyperliquid notes:
- Funding is paid hourly (effective rate per hour).
- The fundingHistory endpoint returns records ~hourly with 'fundingRate' (as decimal string)
  and 'time' (ms). We resample to daily mean for consistency with the BTC version.
- History for FARTCOIN starts from its perp launch (~late 2024); LOOKBACK_YEARS=2 is safe
  and will just return available data.
"""

import requests
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta, timezone
from pathlib import Path

from plotting_utils import add_date_formatters
import get_price_data_cryptocompare as price_data

# ====================== CONFIG ======================
COIN = "FARTCOIN"           # Hyperliquid perpetual symbol (confirm in HL app/meta if needed)
LOOKBACK_YEARS = 2          # Default lookback; FARTCOIN history is shorter (~1.5y as of mid-2026)

# Z-Score configuration
ZSCORE_WINDOW_DAYS = 180    # Rolling window for funding z-score
ZSCORE_COLOR = '#d62728'

# Light absolute reference lines in funding panel (economic context)
# NOTE: For volatile memecoins like FARTCOIN these may trigger more often; adjust if desired.
SHOW_ABSOLUTE_REFS = True
ABS_MODERATE = 0.025
ABS_HIGH     = 0.04

CACHE_DIR = Path("hyperliquid_fartcoin_funding_data")
CACHE_FILE = CACHE_DIR / "fartcoin_funding_rates.csv"

CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_start_date(years: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=years * 365 + 30)).strftime("%Y-%m-%d")


def fetch_hyperliquid_funding_history(coin: str, years: int):
    """Fetch historical funding rates from Hyperliquid using the official info endpoint."""
    start_date = get_start_date(years)
    url = "https://api.hyperliquid.xyz/info"
    all_records = []
    start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    current_start = start_ts

    print(f"Fetching {coin} funding rates from Hyperliquid (last {years} years or available history)...")
    while True:
        payload = {
            "type": "fundingHistory",
            "coin": coin,
            "startTime": current_start
        }
        try:
            resp = requests.post(url, json=payload, timeout=30)
            resp.raise_for_status()
            batch = resp.json()
            if not isinstance(batch, list) or not batch:
                break
            all_records.extend(batch)
            last_ts = batch[-1]["time"]
            current_start = last_ts + 1
            # Safety: if we got a small batch at the end, or to avoid infinite loop on error
            if len(batch) < 500:   # heuristic; adjust if HL returns fixed page sizes
                # Try one more call with advanced start to confirm end
                payload2 = {"type": "fundingHistory", "coin": coin, "startTime": current_start}
                resp2 = requests.post(url, json=payload2, timeout=15)
                if resp2.status_code == 200:
                    batch2 = resp2.json()
                    if not isinstance(batch2, list) or not batch2:
                        break
                    all_records.extend(batch2)
                break
        except Exception as e:
            print(f"Error fetching data from Hyperliquid: {e}")
            break

    if not all_records:
        return pd.DataFrame()

    df = pd.DataFrame(all_records)
    df["timestamp"] = pd.to_datetime(df["time"], unit="ms", utc=True)
    df["funding_rate"] = pd.to_numeric(df["fundingRate"], errors="coerce")
    df = df[["timestamp", "funding_rate"]].dropna().drop_duplicates().sort_values("timestamp").reset_index(drop=True)
    return df


def load_or_update_cache(years: int = LOOKBACK_YEARS):
    cutoff = datetime.now(timezone.utc) - timedelta(days=years * 365 + 30)

    if CACHE_FILE.exists():
        df = pd.read_csv(CACHE_FILE, parse_dates=["timestamp"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], format="mixed", utc=True)
        df = df[df["timestamp"] >= cutoff]

        if (datetime.now(timezone.utc) - df["timestamp"].max()).days > 1:
            new_df = fetch_hyperliquid_funding_history(COIN, years)
            if not new_df.empty:
                df = pd.concat([df, new_df]).drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
                df.to_csv(CACHE_FILE, index=False)
    else:
        df = fetch_hyperliquid_funding_history(COIN, years)
        if not df.empty:
            df.to_csv(CACHE_FILE, index=False)
    return df


def add_funding_zscore(daily_series: pd.Series, window: int = 180) -> pd.Series:
    """Compute rolling z-score of daily funding rates."""
    rolling_mean = daily_series.rolling(window=window, min_periods=max(30, window // 3)).mean()
    rolling_std = daily_series.rolling(window=window, min_periods=max(30, window // 3)).std()
    rolling_std = rolling_std.replace(0, np.nan)
    zscore = (daily_series - rolling_mean) / rolling_std
    return zscore


def print_stats(df, years: int, zscore_window: int):
    if df.empty:
        return
    r = df["funding_rate"] * 100
    print("=" * 60)
    print(f"FARTCOIN (Hyperliquid) Funding Rates + Price Context (Last {years} years / available)")
    print("=" * 60)
    print(f"Period:          {df['timestamp'].min().date()} → {df['timestamp'].max().date()}")
    print(f"# Funding Periods: {len(df):,}")
    print(f"Mean / Median:   {r.mean():.5f}% / {r.median():.5f}%")
    print(f"Std / Max / Min: {r.std():.5f}% / {r.max():.5f}% / {r.min():.5f}%")
    print(f"% Positive:      {(r > 0).mean() * 100:.1f}%")
    print(f"Z-Score window:  {zscore_window} days")
    print("=" * 60 + "\n")


def draw(lookback_years: int = LOOKBACK_YEARS,
         zscore_window: int = ZSCORE_WINDOW_DAYS,
         block_window: bool = True):
    """Main function: 3-panel chart with FARTCOIN Price (with SMAs) + Funding Rate + Z-Score."""
    # === Load Funding Data ===
    funding_df = load_or_update_cache(lookback_years)
    if funding_df.empty:
        print("No funding rate data available. Check Hyperliquid API or coin symbol.")
        return

    print_stats(funding_df, lookback_years, zscore_window)

    funding_df = funding_df.set_index("timestamp").sort_index()
    daily_funding = funding_df["funding_rate"].resample("D").mean() * 100
    daily_z = add_funding_zscore(daily_funding, window=zscore_window)

    # === Load FARTCOIN Price Data (reuse existing generic module) ===
    print("Loading FARTCOIN price data from CryptoCompare...")
    price_df = price_data.get_price_data(coin=COIN)

    # Align price to funding date range (with a little buffer)
    # Note: funding index is tz-aware (UTC), price index is tz-naive → convert for slicing
    funding_start = (daily_funding.index.min() - timedelta(days=5)).tz_localize(None)
    funding_end = (daily_funding.index.max() + timedelta(days=5)).tz_localize(None)
    price_df = price_df.loc[funding_start:funding_end].copy()

    if price_df.empty:
        print("Warning: No overlapping FARTCOIN price data found.")
        price_df = None
    else:
        # Add SMAs similar to other charts in the repo
        price_df['SMA111'] = price_df['close'].rolling(window=111).mean()
        price_df['SMA50']  = price_df['close'].rolling(window=50).mean()

    # === Create 3-panel figure ===
    fig = plt.figure(figsize=(14, 11))
    gs = fig.add_gridspec(3, 1, height_ratios=[2.5, 1.8, 1.2], hspace=0.08)

    ax1 = fig.add_subplot(gs[0])   # FARTCOIN Price
    ax2 = fig.add_subplot(gs[1], sharex=ax1)  # Funding Rate
    ax3 = fig.add_subplot(gs[2], sharex=ax1)  # Z-Score

    plt.style.use("fast")

    # --- Panel 1: FARTCOIN Price with SMAs ---
    if price_df is not None:
        ax1.plot(price_df.index, price_df["close"], color="#1f77b4", linewidth=1.3, label="FARTCOIN Close")
        ax1.plot(price_df.index, price_df["SMA111"], color="#ff7f0e", linewidth=1.15, label="111-Day SMA")
        ax1.plot(price_df.index, price_df["SMA50"],  color="#2ca02c", linewidth=1.15, label="50-Day SMA")
        ax1.set_ylabel("FARTCOIN Price (USD)", fontsize=11)
        ax1.legend(loc="upper left", fontsize=9)
        ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"${int(x):,}"))
    else:
        ax1.text(0.5, 0.5, "FARTCOIN price data unavailable", ha="center", va="center", transform=ax1.transAxes)
    ax1.set_title(f"FARTCOIN Price + Funding Rates + Z-Score ({zscore_window}d) on Hyperliquid | Last {lookback_years} Years",
                  fontsize=14, pad=12)
    ax1.grid(True, alpha=0.3)

    # --- Panel 2: Funding Rate ---
    ax2.plot(daily_funding.index, daily_funding, color="#1f77b4", linewidth=1.5, label="Daily Avg Funding Rate (HL)")
    ax2.fill_between(daily_funding.index, daily_funding, 0,
                     where=(daily_funding >= 0), color="#2ca02c", alpha=0.30)
    ax2.fill_between(daily_funding.index, daily_funding, 0,
                     where=(daily_funding < 0), color="#d62728", alpha=0.30)

    ax2.axhline(0, color="#333333", linewidth=1.0, linestyle="--", alpha=0.7, label="Zero")

    if SHOW_ABSOLUTE_REFS:
        ax2.axhline(ABS_MODERATE, color="#ff7f0e", linestyle=":", linewidth=1.0, alpha=0.6, label=f"+{ABS_MODERATE:.3f}% Moderate")
        ax2.axhline(-ABS_MODERATE, color="#ff7f0e", linestyle=":", linewidth=1.0, alpha=0.6)
        ax2.axhline(ABS_HIGH, color="#d62728", linestyle=":", linewidth=1.0, alpha=0.5, label=f"+{ABS_HIGH:.3f}% High")
        ax2.axhline(-ABS_HIGH, color="#2ca02c", linestyle=":", linewidth=1.0, alpha=0.5)

    ax2.set_ylabel("Funding Rate (%)", fontsize=11)
    ax2.legend(loc="upper left", fontsize=8, framealpha=0.9)
    ax2.grid(True, alpha=0.3)
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.3f}%"))

    # --- Panel 3: Funding Z-Score ---
    ax3.plot(daily_funding.index, daily_z, color=ZSCORE_COLOR, linewidth=1.6, label=f"Funding Z-Score ({zscore_window}d)")

    ax3.axhline(0, color="black", linestyle="-", linewidth=0.9, alpha=0.8)
    ax3.axhline(2, color="#d62728", linestyle="--", linewidth=1.2, alpha=0.85,
                label="+2σ Elevated (longs paying more)")
    ax3.axhline(-2, color="#2ca02c", linestyle="--", linewidth=1.2, alpha=0.85,
                label="-2σ Depressed (shorts paying more)")
    ax3.axhline(3, color="#8B0000", linestyle=":", linewidth=1.1, alpha=0.7, label="+3σ Very High / Extreme")
    ax3.axhline(-3, color="#006400", linestyle=":", linewidth=1.1, alpha=0.7, label="-3σ Very Low / Extreme")

    ax3.set_ylabel("Z-Score", fontsize=11)
    ax3.set_xlabel("Date")
    ax3.legend(loc="upper left", fontsize=8, framealpha=0.9)
    ax3.grid(True, alpha=0.3)

    # Shared date formatting
    add_date_formatters(ax3)
    plt.setp(ax1.get_xticklabels(), visible=False)
    plt.setp(ax2.get_xticklabels(), visible=False)

    plt.tight_layout()
    plt.show(block=block_window)


if __name__ == "__main__":
    draw()
