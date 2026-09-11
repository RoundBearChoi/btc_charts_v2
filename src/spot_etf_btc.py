#!/usr/bin/env python3
"""
spot_etf_btc.py

Interactive 3-panel chart for US spot Bitcoin ETF flows:
  1. BTC price (top)
  2. Daily net ETF flow in USD (middle) — green inflow / red outflow
  3. Cumulative net flow since launch (bottom)

Also prints a recent per-fund breakdown (IBIT, FBTC, ARKB, GBTC, …).

Primary source: TFTC open dataset (SoSoValue + Farside tabulations)
  https://www.tftc.io/bitcoin-etf-flows/data.json  (CC BY 4.0)
Fallback: BGeometrics free API (flows in BTC, converted with local BTC prices)
  https://bitcoin-data.com/v1/etf-flow-btc

Follows the draw() + plt.show() pattern used by other scripts in btc_charts_v2.

Run from repo root:
    python src/spot_etf_btc.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import pandas as pd
import requests

from plotting_utils import add_date_formatters
import get_price_data_cryptocompare as price_data

# ====================== CONFIG ======================
LOOKBACK_DAYS = 0          # 0 = full history since ETF launch (Jan 2024)
RECENT_TABLE_ROWS = 12     # printed per-fund table length
CACHE_MAX_AGE_HOURS = 12   # refresh cached JSON after this many hours

TFTC_URL = "https://www.tftc.io/bitcoin-etf-flows/data.json"
BGEOMETRICS_FLOW_URL = "https://bitcoin-data.com/v1/etf-flow-btc"
BGEOMETRICS_TOTAL_URL = "https://bitcoin-data.com/v1/etf-btc-total"

# Largest / most-watched funds first in the printed table
FUND_ORDER = [
    "IBIT", "FBTC", "GBTC", "ARKB", "BITB", "HODL",
    "BTCO", "BRRR", "EZBC", "BTCW", "MSBT", "BTC",
]

SCRIPT_DIR = Path(__file__).resolve().parent
CACHE_DIR = SCRIPT_DIR / "spot_etf_data"
CACHE_FILE = CACHE_DIR / "us_spot_btc_etf_flows.json"

CACHE_DIR.mkdir(parents=True, exist_ok=True)

REQUEST_HEADERS = {
    "User-Agent": "btc_charts_v2/spot_etf_btc (+https://github.com/RoundBearChoi/btc_charts_v2)",
    "Accept": "application/json",
}


def _cache_is_fresh() -> bool:
    if not CACHE_FILE.exists():
        return False
    age_hours = (datetime.now(timezone.utc).timestamp() - CACHE_FILE.stat().st_mtime) / 3600
    return age_hours < CACHE_MAX_AGE_HOURS


def _http_get_json(url: str, timeout: int = 30):
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def fetch_tftc_payload() -> dict:
    print("Fetching US spot Bitcoin ETF flows from TFTC...")
    payload = _http_get_json(TFTC_URL)
    if not isinstance(payload, dict) or "days" not in payload:
        raise ValueError("Unexpected TFTC payload shape")
    CACHE_FILE.write_text(json.dumps(payload), encoding="utf-8")
    print(
        f"Cached TFTC data through {payload.get('updatedThrough')} "
        f"({len(payload.get('days', []))} days) → {CACHE_FILE}"
    )
    return payload


def load_tftc_payload() -> dict | None:
    if _cache_is_fresh():
        print(f"Using cached ETF flow data ({CACHE_FILE.name})")
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    try:
        return fetch_tftc_payload()
    except Exception as exc:
        print(f"TFTC fetch failed: {exc}")
        if CACHE_FILE.exists():
            print("Falling back to older cache.")
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        return None


def tftc_to_frame(payload: dict) -> pd.DataFrame:
    rows = []
    for day in payload.get("days", []):
        per = day.get("perEtfUsd") or {}
        row = {
            "date": pd.to_datetime(day.get("date")),
            "net_flow_usd": day.get("netFlowUsd"),
            "aum_usd": day.get("totalNetAssetsUsd"),
            "btc_close_usd": day.get("btcCloseUsd"),
        }
        for ticker, value in per.items():
            row[f"flow_{ticker}"] = value
        rows.append(row)
    df = pd.DataFrame(rows).dropna(subset=["date"]).sort_values("date")
    df = df.set_index("date")
    df["net_flow_usd"] = pd.to_numeric(df["net_flow_usd"], errors="coerce")
    df["cumulative_flow_usd"] = df["net_flow_usd"].cumsum()
    return df


def fetch_bgeometrics_fallback() -> pd.DataFrame:
    """Flows in BTC from BGeometrics, converted to USD with local BTC prices."""
    print("Fetching ETF flows from BGeometrics (BTC units)...")
    flow_raw = _http_get_json(BGEOMETRICS_FLOW_URL)
    total_raw = []
    try:
        total_raw = _http_get_json(BGEOMETRICS_TOTAL_URL)
    except Exception as exc:
        print(f"BGeometrics holdings fetch skipped: {exc}")

    flow = pd.DataFrame(flow_raw)
    flow["date"] = pd.to_datetime(flow["d"])
    flow["flow_btc"] = pd.to_numeric(flow["etfFlow"], errors="coerce")
    flow = flow.set_index("date").sort_index()[["flow_btc"]]

    if total_raw:
        total = pd.DataFrame(total_raw)
        total["date"] = pd.to_datetime(total["d"])
        total["etf_btc_held"] = pd.to_numeric(total["etfBtcTotal"], errors="coerce")
        total = total.set_index("date").sort_index()[["etf_btc_held"]]
        flow = flow.join(total, how="left")

    print("Loading BTC price data to convert flows to USD...")
    price_df = price_data.get_btc_price_data()
    close = price_df["close"].copy()
    close.index = pd.to_datetime(close.index).tz_localize(None)
    flow = flow.join(close.rename("btc_close_usd"), how="left")
    flow["btc_close_usd"] = flow["btc_close_usd"].ffill()
    flow["net_flow_usd"] = flow["flow_btc"] * flow["btc_close_usd"]
    flow["cumulative_flow_usd"] = flow["net_flow_usd"].cumsum()
    if "etf_btc_held" in flow.columns:
        flow["aum_usd"] = flow["etf_btc_held"] * flow["btc_close_usd"]
    return flow


def load_etf_frame() -> tuple[pd.DataFrame, str]:
    payload = load_tftc_payload()
    if payload is not None:
        df = tftc_to_frame(payload)
        if not df.empty and df["net_flow_usd"].notna().any():
            source = (
                f"TFTC / SoSoValue + Farside "
                f"(updated through {payload.get('updatedThrough', 'n/a')})"
            )
            return df, source
    try:
        return fetch_bgeometrics_fallback(), "BGeometrics etf-flow-btc (USD approx via BTC close)"
    except Exception as exc:
        raise RuntimeError(
            "Could not load ETF flow data from TFTC or BGeometrics."
        ) from exc


def _usd_millions(value) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "—"
    millions = value / 1_000_000
    sign = "+" if millions > 0 else ""
    return f"{sign}{millions:,.1f}"


def print_stats(df: pd.DataFrame, source: str):
    flows = df["net_flow_usd"].dropna()
    if flows.empty:
        return

    last = df.dropna(subset=["net_flow_usd"]).iloc[-1]
    last_date = df.dropna(subset=["net_flow_usd"]).index[-1].date()
    last7 = flows.tail(7).sum()
    last30 = flows.tail(30).sum()
    cumulative = flows.sum()
    inflow_days = (flows > 0).sum()
    outflow_days = (flows < 0).sum()

    print("=" * 64)
    print("US Spot Bitcoin ETF Flows")
    print("=" * 64)
    print(f"Source:          {source}")
    print(f"Period:          {df.index.min().date()} → {df.index.max().date()}")
    print(f"Trading days:    {len(flows):,}  (in {inflow_days} / out {outflow_days} / flat {len(flows) - inflow_days - outflow_days})")
    print(f"Latest day:      {last_date}   {_usd_millions(last['net_flow_usd'])} M")
    print(f"Last 7 days:     {_usd_millions(last7)} M")
    print(f"Last 30 days:    {_usd_millions(last30)} M")
    print(f"Cumulative net:  {_usd_millions(cumulative)} M")
    if pd.notna(last.get("aum_usd")):
        print(f"Latest AUM:      ${_usd_millions(last['aum_usd']).replace('+', '')} B".replace(" M", ""))
        # _usd_millions is in millions; print AUM in billions separately
        print(f"Latest AUM:      ${last['aum_usd'] / 1_000_000_000:,.1f} B")
    print("=" * 64)

    fund_cols = [c for c in (f"flow_{t}" for t in FUND_ORDER) if c in df.columns]
    extra = [c for c in df.columns if c.startswith("flow_") and c not in fund_cols]
    fund_cols.extend(sorted(extra))
    if not fund_cols:
        print()
        return

    recent = df.dropna(subset=["net_flow_usd"]).tail(RECENT_TABLE_ROWS)
    tickers = [c.replace("flow_", "") for c in fund_cols]
    header = f"{'Date':<12}{'Total':>10}" + "".join(f"{t:>9}" for t in tickers)
    print("\nRecent daily net flows (USD millions)")
    print(header)
    print("-" * len(header))
    for ts, row in recent.iterrows():
        line = f"{ts.date()!s:<12}{_usd_millions(row['net_flow_usd']):>10}"
        for col in fund_cols:
            line += f"{_usd_millions(row.get(col)):>9}"
        print(line)
    print()
    print("Positive = inflow (ETF demand). Negative = outflow (redemptions).")
    print("A net outflow usually means ETF shares were redeemed and BTC left the funds.\n")


def draw(lookback_days: int = LOOKBACK_DAYS, block_window: bool = True):
    df, source = load_etf_frame()
    if df.empty:
        print("No ETF flow data available.")
        return

    if lookback_days and lookback_days > 0:
        cutoff = df.index.max() - pd.Timedelta(days=lookback_days)
        df = df.loc[df.index >= cutoff].copy()
        if "net_flow_usd" in df.columns:
            df["cumulative_flow_usd"] = df["net_flow_usd"].cumsum()

    print_stats(df, source)

    print("Loading BTC price data...")
    price_df = price_data.get_btc_price_data()
    price_df = price_df.copy()
    price_df.index = pd.to_datetime(price_df.index).tz_localize(None)
    start = df.index.min() - pd.Timedelta(days=5)
    end = df.index.max() + pd.Timedelta(days=5)
    price_df = price_df.loc[start:end]

    fig = plt.figure(figsize=(14, 11))
    gs = fig.add_gridspec(3, 1, height_ratios=[2.4, 1.6, 1.4], hspace=0.08)
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax3 = fig.add_subplot(gs[2], sharex=ax1)
    plt.style.use("fast")

    if not price_df.empty:
        ax1.plot(price_df.index, price_df["close"], color="#1f77b4", linewidth=1.3, label="BTC Close")
        ax1.set_ylabel("BTC Price (USD)", fontsize=11)
        ax1.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _p: f"${int(x):,}"))
        ax1.legend(loc="upper left", fontsize=9)
    else:
        ax1.text(0.5, 0.5, "BTC price data unavailable", ha="center", va="center", transform=ax1.transAxes)

    title_range = f"{df.index.min().date()} to {df.index.max().date()}"
    ax1.set_title(f"BTC Price + US Spot Bitcoin ETF Flows | {title_range}", fontsize=14, pad=12)
    ax1.grid(True, alpha=0.3)

    flow_m = df["net_flow_usd"] / 1_000_000
    colors = np.where(flow_m.fillna(0) >= 0, "#2ca02c", "#d62728")
    ax2.bar(df.index, flow_m.fillna(0), color=colors, width=1.2, alpha=0.85, label="Daily net flow")
    ax2.axhline(0, color="#333333", linewidth=1.0, linestyle="--", alpha=0.7)
    ax2.set_ylabel("Daily Flow (USD m)", fontsize=11)
    ax2.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _p: f"{x:,.0f}"))
    ax2.legend(loc="upper left", fontsize=8, framealpha=0.9)
    ax2.grid(True, alpha=0.3)

    cum_b = df["cumulative_flow_usd"] / 1_000_000_000
    ax3.plot(df.index, cum_b, color="#6a3d9a", linewidth=1.6, label="Cumulative net flow")
    ax3.fill_between(df.index, cum_b, 0, color="#6a3d9a", alpha=0.12)
    ax3.axhline(0, color="#333333", linewidth=0.9, linestyle="--", alpha=0.7)
    if "aum_usd" in df.columns and df["aum_usd"].notna().any():
        aum_b = df["aum_usd"] / 1_000_000_000
        ax3.plot(df.index, aum_b, color="#ff7f0e", linewidth=1.15, alpha=0.85, label="Reported AUM")
    ax3.set_ylabel("USD billions", fontsize=11)
    ax3.set_xlabel("Date")
    ax3.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _p: f"{x:,.1f}"))
    ax3.legend(loc="upper left", fontsize=8, framealpha=0.9)
    ax3.grid(True, alpha=0.3)

    add_date_formatters(ax3)
    plt.setp(ax1.get_xticklabels(), visible=False)
    plt.setp(ax2.get_xticklabels(), visible=False)

    fig.text(
        0.01,
        0.01,
        "ETF flow data: TFTC (CC BY 4.0) — tftc.io/bitcoin-etf-flows. Not investment advice.",
        fontsize=8,
        color="#555555",
    )

    plt.tight_layout()
    plt.show(block=block_window)


if __name__ == "__main__":
    draw()
