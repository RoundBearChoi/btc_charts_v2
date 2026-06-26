#!/usr/bin/env python3
"""
btc_binance_funding_rates.py

Fetches historical BTCUSDT Perpetual funding rates from Binance Futures public API.
Caches results locally.
Generates clean statistics + a proper long-term chart with correct datetime x-axis.

Robust datetime parsing to handle existing cache files.
"""

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
    url = "https://fapi.binance.com/fapi/v1/fundingRate"
    all_records = []
    limit = 1000

    start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    current_start = start_ts

    print(f"Fetching funding rates for {symbol} from {start_date}...")

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
            print(f"  + {len(batch)} records (latest: {datetime.fromtimestamp(last_ts/1000, tz=timezone.utc).date()}) | total: {len(all_records)}")
            if len(batch) < limit:
                break
        except Exception as e:
            print(f"Fetch error: {e}")
            break

    if not all_records:
        return pd.DataFrame()

    df = pd.DataFrame(all_records)
    df["timestamp"] = pd.to_datetime(df["fundingTime"], unit="ms", utc=True)
    df["funding_rate"] = pd.to_numeric(df["fundingRate"])
    df = df[["timestamp", "funding_rate"]].drop_duplicates().sort_values("timestamp").reset_index(drop=True)
    print(f"Fetched {len(df)} records total.\n")
    return df


# ====================== CACHE ======================
def load_or_update_cache():
    if CACHE_FILE.exists():
        print("Loading cache...")
        df = pd.read_csv(CACHE_FILE, parse_dates=["timestamp"])
        # Robust parsing for existing cache files that may have microseconds + timezone
        df["timestamp"] = pd.to_datetime(df["timestamp"], format="mixed", utc=True)
        latest = df["timestamp"].max()
        if (datetime.now(timezone.utc) - latest).days > 2:
            print("Cache stale — fetching updates...")
            new_df = fetch_binance_funding_history()
            if not new_df.empty:
                df = pd.concat([df, new_df]).drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
                df.to_csv(CACHE_FILE, index=False)
        else:
            print(f"Cache fresh (up to {latest.date()}).")
    else:
        print("No cache — fetching full history...")
        df = fetch_binance_funding_history()
        if not df.empty:
            df.to_csv(CACHE_FILE, index=False)
    return df


# ====================== STATS ======================
def print_stats(df):
    if df.empty: return
    r = df["funding_rate"] * 100
    print("="*55)
    print("BTCUSDT Funding Rate Stats (Binance Perpetual)")
    print("="*55)
    print(f"Period:          {df['timestamp'].min().date()} → {df['timestamp'].max().date()}")
    print(f"# of 8h periods: {len(df):,}")
    print(f"Mean:            {r.mean():.5f}%")
    print(f"Median:          {r.median():.5f}%")
    print(f"Std Dev:         {r.std():.5f}%")
    print(f"Max / Min:       {r.max():.5f}% / {r.min():.5f}%")
    print(f"% Positive:      {(r > 0).mean()*100:.1f}%")
    print(f"Cumulative long: {r.sum():.2f}% over history")
    print("="*55 + "\n")


# ====================== CHART (FIXED) ======================
def create_chart(df):
    if df.empty:
        print("No data to plot.")
        return

    # Ensure proper DatetimeIndex
    df = df.set_index("timestamp").sort_index()
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index, utc=True)

    # Resample to daily average for clean long-term view
    daily = df["funding_rate"].resample("D").mean() * 100

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 9), gridspec_kw={"height_ratios": [3, 1]}, sharex=True)

    ax1.plot(daily.index, daily, color="#2980b9", linewidth=1.2, label="Daily Avg Funding Rate")

    ax1.fill_between(daily.index, daily, 0, where=(daily >= 0), color="#27ae60", alpha=0.25, label="Positive (longs pay)")
    ax1.fill_between(daily.index, daily, 0, where=(daily < 0), color="#c0392b", alpha=0.25, label="Negative (shorts pay)")

    ax1.axhline(0, color="#2c3e50", linewidth=1, linestyle="--", alpha=0.7)
    ax1.set_ylabel("Funding Rate (%)", fontsize=11)
    ax1.set_title(f"Binance BTCUSDT Perpetual Funding Rates\n{daily.index.min().strftime('%Y-%m-%d')} — {daily.index.max().strftime('%Y-%m-%d')}", fontsize=13, pad=10)
    ax1.legend(loc="upper left", fontsize=9, framealpha=0.95)
    ax1.grid(True, alpha=0.3)
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.3f}%"))

    ax1.xaxis.set_major_locator(mdates.YearLocator())
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax1.xaxis.set_minor_locator(mdates.MonthLocator(bymonth=[1, 7]))

    rates = df["funding_rate"] * 100
    ax2.hist(rates, bins=80, color="#8e44ad", alpha=0.7, edgecolor="white", linewidth=0.4)
    ax2.axvline(0, color="#2c3e50", linewidth=1.5)
    ax2.set_xlabel("Funding Rate (%)", fontsize=11)
    ax2.set_ylabel("Count", fontsize=10)
    ax2.set_title("Distribution of Daily-Averaged Funding Rates", fontsize=11)
    ax2.grid(True, alpha=0.3, axis="y")

    stats = f"Mean: {rates.mean():.4f}%  |  Median: {rates.median():.4f}%  |  Std: {rates.std():.4f}%"
    ax2.text(0.99, 0.96, stats, transform=ax2.transAxes, fontsize=9,
             ha="right", va="top", bbox=dict(boxstyle="round,pad=0.4", facecolor="white", alpha=0.9))

    plt.tight_layout()
    plt.subplots_adjust(hspace=0.1)

    out_path = CHART_DIR / f"btc_binance_funding_rates_{datetime.now().strftime('%Y%m%d_%H%M')}.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    print(f"Chart saved: {out_path}")
    plt.close()


if __name__ == "__main__":
    print("\n=== Binance BTC Funding Rates ===\n")
    df = load_or_update_cache()
    print_stats(df)
    create_chart(df)
    print("Done.\n")
