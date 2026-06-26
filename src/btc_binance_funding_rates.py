#!/usr/bin/env python3
"""
btc_binance_funding_rates.py

Clean script for Binance BTCUSDT funding rates.
Easy config at the top. Focused on recent period.

Final simplified version (2026-06-26):
- Single clean time series chart only (no histogram)
- Daily average with green/red fill
- Proper date formatting for 2-year view
"""

import requests
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ====================== CONFIG ======================
SYMBOL = "BTCUSDT"
LOOKBACK_YEARS = 2          # <--- Change this to 3, 4, 5 etc. if you want more history

CACHE_DIR = Path("src/binance_funding_data")
CACHE_FILE = CACHE_DIR / "btc_funding_rates.csv"
CHART_DIR = Path("src/charts")

CACHE_DIR.mkdir(parents=True, exist_ok=True)
CHART_DIR.mkdir(parents=True, exist_ok=True)


def get_start_date(years: int = LOOKBACK_YEARS) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=years * 365 + 30)).strftime("%Y-%m-%d")


def fetch_binance_funding_history(symbol: str = SYMBOL):
    start_date = get_start_date()
    url = "https://fapi.binance.com/fapi/v1/fundingRate"
    all_records = []
    limit = 1000
    start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    current_start = start_ts

    print(f"Fetching {symbol} funding rates (last {LOOKBACK_YEARS} years)...")
    while True:
        params = {"symbol": symbol, "startTime": current_start, "limit": limit}
        try:
            resp = requests.get(url, params=params, timeout=20)
            resp.raise_for_status()
            batch = resp.json()
            if not batch: break
            all_records.extend(batch)
            last_ts = batch[-1]["fundingTime"]
            current_start = last_ts + 1
            if len(batch) < limit: break
        except Exception as e:
            print(f"Error: {e}")
            break

    if not all_records: return pd.DataFrame()
    df = pd.DataFrame(all_records)
    df["timestamp"] = pd.to_datetime(df["fundingTime"], unit="ms", utc=True)
    df["funding_rate"] = pd.to_numeric(df["fundingRate"])
    df = df[["timestamp", "funding_rate"]].drop_duplicates().sort_values("timestamp").reset_index(drop=True)
    return df


def load_or_update_cache():
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_YEARS * 365 + 30)

    if CACHE_FILE.exists():
        df = pd.read_csv(CACHE_FILE, parse_dates=["timestamp"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], format="mixed", utc=True)
        df = df[df["timestamp"] >= cutoff]

        if (datetime.now(timezone.utc) - df["timestamp"].max()).days > 2:
            new_df = fetch_binance_funding_history()
            if not new_df.empty:
                df = pd.concat([df, new_df]).drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
                df.to_csv(CACHE_FILE, index=False)
    else:
        df = fetch_binance_funding_history()
        if not df.empty:
            df.to_csv(CACHE_FILE, index=False)
    return df


def print_stats(df):
    if df.empty: return
    r = df["funding_rate"] * 100
    print("="*55)
    print(f"BTCUSDT Funding Rates (Last {LOOKBACK_YEARS} years)")
    print("="*55)
    print(f"Period:          {df['timestamp'].min().date()} → {df['timestamp'].max().date()}")
    print(f"# Periods:       {len(df):,}")
    print(f"Mean / Median:   {r.mean():.5f}% / {r.median():.5f}%")
    print(f"Std / Max / Min: {r.std():.5f}% / {r.max():.5f}% / {r.min():.5f}%")
    print(f"% Positive:      {(r > 0).mean()*100:.1f}%")
    print(f"Cumulative long: {r.sum():.2f}%")
    print("="*55 + "\n")


def create_chart(df):
    if df.empty: return

    df = df.set_index("timestamp").sort_index()
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index, utc=True)

    daily = df["funding_rate"].resample("D").mean() * 100

    fig, ax = plt.subplots(figsize=(13, 7))

    ax.plot(daily.index, daily, color="#1f77b4", linewidth=1.4)
    ax.fill_between(daily.index, daily, 0, where=(daily >= 0), color="#2ca02c", alpha=0.28)
    ax.fill_between(daily.index, daily, 0, where=(daily < 0), color="#d62728", alpha=0.28)

    ax.axhline(0, color="#333333", linewidth=0.9, linestyle="--", alpha=0.65)
    ax.set_ylim(-0.08, 0.18)

    ax.set_ylabel("Funding Rate (%)", fontsize=12)
    ax.set_title(f"Binance BTCUSDT Perpetual Funding Rates | Last {LOOKBACK_YEARS} Years", fontsize=14, pad=10)
    ax.grid(True, alpha=0.3)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.2f}%"))

    # Clean date formatting for 2-year view
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonthday=1, interval=3))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_minor_locator(mdates.MonthLocator())

    plt.tight_layout()

    out_path = CHART_DIR / f"btc_funding_last{LOOKBACK_YEARS}y_{datetime.now().strftime('%Y%m%d_%H%M')}.png"
    plt.savefig(out_path, dpi=160, bbox_inches="tight", facecolor="white")
    print(f"Chart saved → {out_path}")
    plt.close()


if __name__ == "__main__":
    print("\n=== Binance BTC Funding Rates ===\n")
    df = load_or_update_cache()
    print_stats(df)
    create_chart(df)
    print("Done.\n")
