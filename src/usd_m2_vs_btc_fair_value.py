"""BTC month-end close vs a rolling US-M2 implied fair value.

Companion to usd_m2_vs_btc.py.

usd_m2_vs_btc.py plots the two raw series.
This script asks a different question: given the last N months of
log(BTC) ~ log(M2), what price does the current M2 stock imply?

Fair value at month t uses ONLY months before t (no look-ahead):

    log(BTC) = a + b * log(M2)

    fair_t = exp(a + b * log(M2_t))

US M2SL lags by a few weeks, so the latest BTC month reuses the
last published M2 print. That is a snapshot against the money stock,
not a forecast and not a valuation floor.

Run from repo root:
    python src/m2_fair_value_btc.py
"""

from __future__ import annotations

import matplotlib

try:
    matplotlib.use("TkAgg")
except Exception:
    pass

from io import StringIO
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import pandas as pd
import requests
from pandas.tseries.offsets import MonthEnd

import get_price_data_cryptocompare as price_data
from plotting_utils import format_price

# ==================================================
# CONFIGURATION
# ==================================================
WINDOW = 48                  # months in the log-log regression
MIN_PERIODS = 24             # skip the fit until this many months exist
BLOCK_WINDOW = True
SHOW_GRID = True
FIGURE_SIZE = (13, 8)

Z_BAND = 1.5                 # dashed reference on the residual panel
M2_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=M2SL"

SPOT_COLOR = "#222222"
FAIR_COLOR = "#1f77b4"
RICH_COLOR = "#d62728"
CHEAP_COLOR = "#2ca02c"

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"
# ==================================================


def _backend_is_interactive() -> bool:
    backend = matplotlib.get_backend().lower()
    return backend not in {"agg", "svg", "pdf", "ps", "cairo", "template"}


def load_us_m2() -> pd.Series:
    print("\nDownloading latest US M2 data from FRED (CSV)...")
    response = requests.get(M2_URL, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f"Failed to download M2 data (status {response.status_code})")

    m2 = pd.read_csv(
        StringIO(response.text),
        parse_dates=["observation_date"],
        index_col="observation_date",
    )["M2SL"]
    m2.index = m2.index + MonthEnd(0)
    m2 = m2[~m2.index.duplicated(keep="last")].sort_index()
    print(f"M2 range: {m2.index.min().date()} → {m2.index.max().date()}  ({len(m2)} months)")
    return m2


def rolling_loglog_fair(btc: pd.Series, m2: pd.Series) -> pd.DataFrame:
    """Rolling log-log fair value. Fit at t uses months strictly before t."""
    df = pd.DataFrame({"BTC": btc, "M2": m2})
    df["M2"] = df["M2"].ffill()
    df = df.dropna(subset=["BTC", "M2"])

    log_btc = np.log(df["BTC"].to_numpy())
    log_m2 = np.log(df["M2"].to_numpy())
    fair = np.full(len(df), np.nan)
    beta = np.full(len(df), np.nan)
    alpha = np.full(len(df), np.nan)

    for i in range(len(df)):
        start = max(0, i - WINDOW)
        y = log_btc[start:i]
        x = log_m2[start:i]
        if len(y) < MIN_PERIODS:
            continue
        design = np.column_stack([np.ones(len(x)), x])
        a, b = np.linalg.lstsq(design, y, rcond=None)[0]
        alpha[i] = a
        beta[i] = b
        fair[i] = np.exp(a + b * log_m2[i])

    df["fair"] = fair
    df["beta"] = beta
    df["alpha"] = alpha
    df["gap"] = df["BTC"] / df["fair"] - 1.0
    resid = np.log(df["BTC"]) - np.log(df["fair"])
    df["z"] = resid.rolling(WINDOW, min_periods=MIN_PERIODS).apply(
        lambda s: (s.iloc[-1] - s.mean()) / s.std(ddof=0) if s.std(ddof=0) else np.nan,
        raw=False,
    )
    return df


def print_snapshot(df: pd.DataFrame) -> None:
    last = df.iloc[-1]
    print("=" * 64)
    print("BTC vs US M2 fair value")
    print("=" * 64)
    print(f"Month:           {last.name.date()}")
    print(f"BTC close:       {format_price(float(last['BTC']))}")
    print(f"M2 (FRED):       ${last['M2']:,.1f}B")
    print(f"Fair value:      {format_price(float(last['fair']))}")
    print(f"Gap:             {last['gap'] * 100:+.1f}%")
    z_txt = f"{last['z']:.2f}" if pd.notna(last["z"]) else "n/a"
    b_txt = f"{last['beta']:.2f}" if pd.notna(last["beta"]) else "n/a"
    print(f"Residual z:      {z_txt}")
    print(f"Rolling beta:    {b_txt}   (window={WINDOW}m)")
    print()
    print("Fit: log(BTC) = a + b * log(M2), prior months only.")
    print("Green / negative gap = spot below the money-stock fit.")
    print("Not a floor, not global M2, not a one-month forecast.")
    print("=" * 64 + "\n")


def draw(block_window: bool = BLOCK_WINDOW) -> None:
    daily = price_data.get_btc_price_data()
    monthly_btc = daily.sort_index().resample("ME").agg({"close": "last"})["close"]
    us_m2 = load_us_m2()

    df = rolling_loglog_fair(monthly_btc, us_m2).dropna(subset=["fair"])
    if df.empty:
        raise RuntimeError("Not enough overlapping BTC / M2 history to fit the window.")

    print_snapshot(df)
    last = df.iloc[-1]

    fig, (ax1, ax2) = plt.subplots(
        2, 1,
        figsize=FIGURE_SIZE,
        gridspec_kw={"height_ratios": [3, 1.15]},
        sharex=True,
    )
    plt.style.use("fast")

    ax1.set_yscale("log")
    ax1.fill_between(
        df.index, df["BTC"], df["fair"],
        where=df["BTC"] >= df["fair"],
        color=RICH_COLOR, alpha=0.12, interpolate=True,
        label="Spot above fair (rich)",
    )
    ax1.fill_between(
        df.index, df["BTC"], df["fair"],
        where=df["BTC"] < df["fair"],
        color=CHEAP_COLOR, alpha=0.12, interpolate=True,
        label="Spot below fair (cheap)",
    )
    ax1.plot(df.index, df["fair"], color=FAIR_COLOR, linewidth=1.6,
             label=f"US M2 fair value ({WINDOW}m log-log)")
    ax1.plot(df.index, df["BTC"], color=SPOT_COLOR, linewidth=1.15,
             label="BTC month-end close")

    ax1.annotate(
        f"spot  {format_price(float(last['BTC']))}\n"
        f"fair  {format_price(float(last['fair']))}\n"
        f"gap   {last['gap'] * 100:+.1f}%",
        xy=(last.name, last["BTC"]),
        xytext=(-8, -28),
        textcoords="offset points",
        ha="right", va="top",
        fontsize=8, family="monospace",
        bbox=dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor="#cccccc", alpha=0.92),
    )

    ax1.set_title(
        f"BTC vs US M2 fair value  •  rolling {WINDOW}-month log(BTC) ~ log(M2)\n"
        f"Latest: {format_price(float(last['BTC']))} spot  vs  "
        f"{format_price(float(last['fair']))} implied  ({last['gap'] * 100:+.1f}%)",
        fontsize=13, pad=12,
    )
    ax1.set_ylabel("USD (log)")
    ax1.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _p: f"${x:,.0f}"))
    ax1.legend(loc="upper left", fontsize=8, framealpha=0.92)
    if SHOW_GRID:
        ax1.grid(True, which="both", alpha=0.25)

    ax2.axhline(0, color="black", linewidth=0.8)
    ax2.fill_between(df.index, df["z"], 0, where=df["z"] >= 0, color=RICH_COLOR, alpha=0.35)
    ax2.fill_between(df.index, df["z"], 0, where=df["z"] < 0, color=CHEAP_COLOR, alpha=0.35)
    ax2.plot(df.index, df["z"], color="#333333", linewidth=1.1)
    ax2.axhline(Z_BAND, color=RICH_COLOR, linestyle="--", alpha=0.5, linewidth=0.8)
    ax2.axhline(-Z_BAND, color=CHEAP_COLOR, linestyle="--", alpha=0.5, linewidth=0.8)
    ax2.set_ylabel("Residual z-score")
    ax2.set_xlabel("Date")
    if SHOW_GRID:
        ax2.grid(True, alpha=0.25)

    ax2.xaxis.set_major_locator(mdates.YearLocator())
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax2.xaxis.set_minor_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
    ax2.xaxis.set_minor_formatter(mdates.DateFormatter("%b"))
    ax2.tick_params(axis="x", which="major", labelsize=9)

    fig.text(
        0.01, 0.01,
        "US M2SL (FRED). Fit uses prior months only. "
        "Latest BTC month reuses the last published M2 print. "
        "Cheap vs the fit is not a guarantee the next month rises.",
        fontsize=7.5, color="#555555",
    )
    plt.tight_layout(rect=(0, 0.03, 1, 1))

    if not _backend_is_interactive():
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_file = OUTPUT_DIR / "m2_fair_value_btc.png"
        plt.savefig(output_file, dpi=150, bbox_inches="tight", facecolor="white")
        print(f"Chart saved to: {output_file}")
        plt.close(fig)
        return

    print(f"Using interactive backend: {matplotlib.get_backend()}")
    plt.show(block=block_window)
    if block_window:
        plt.close(fig)


if __name__ == "__main__":
    draw()
