#!/usr/bin/env python3
"""
resistance_and_support_btc.py

Two-panel BTC chart:
  1. Price + EMA21 / SMA50 / SMA200 as *dynamic* support or resistance
     plus the latest swing high / swing low as *static* levels
  2. Volume (up-day / down-day bars) + volume SMA

Rule used for moving averages:
  price above the MA  -> that MA is treated as support
  price below the MA  -> that MA is treated as resistance

Swing levels are calculated, not eyeballed:
  a bar is a swing high if its high is the max of `SWING_LEFT` bars before
  and `SWING_RIGHT` bars after. Same idea inverted for swing lows.
  The most recent swing high above price is marked resistance.
  The most recent swing low below price is marked support.

Run from repo root:
    python src/resistance_and_support_btc.py
"""

from __future__ import annotations

import matplotlib

try:
    matplotlib.use("TkAgg")
except Exception:
    pass

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import pandas as pd

import get_price_data_cryptocompare as price_data
from indicators import add_ema, add_sma
from plotting_utils import add_date_formatters

# ====================== CONFIG ======================
DAYS_BACK = 360            # chart window; None = full history
BLOCK_WINDOW = True

EMA_FAST = 21
SMA_MID = 50
SMA_SLOW = 200

SWING_LEFT = 8             # bars on each side to confirm a pivot
SWING_RIGHT = 8

VOLUME_SMA_DAYS = 20

FIGURE_SIZE = (14, 9)
CLOSE_COLOR = "#1f77b4"
EMA_COLOR = "#E15FC3"
SMA50_COLOR = "#2ca02c"
SMA200_COLOR = "#C80C01"
SUPPORT_COLOR = "#2ca02c"
RESISTANCE_COLOR = "#d62728"
# ====================================================


def _backend_is_interactive() -> bool:
    backend = matplotlib.get_backend().lower()
    return backend not in {"agg", "svg", "pdf", "ps", "cairo", "template"}


def add_swing_points(df: pd.DataFrame, left: int = 8, right: int = 8) -> pd.DataFrame:
    """Mark confirmed swing highs / lows. Right window means the newest
    `right` bars cannot be confirmed yet (they still need future bars)."""
    high = df["high"]
    low = df["low"]
    swing_high = pd.Series(False, index=df.index)
    swing_low = pd.Series(False, index=df.index)

    last_confirmable = len(df) - right
    for i in range(left, last_confirmable):
        window_high = high.iloc[i - left: i + right + 1]
        window_low = low.iloc[i - left: i + right + 1]
        if high.iloc[i] >= window_high.max():
            swing_high.iloc[i] = True
        if low.iloc[i] <= window_low.min():
            swing_low.iloc[i] = True

    df["swing_high"] = swing_high
    df["swing_low"] = swing_low
    return df


def classify_ma(price: float, ma_value: float) -> str:
    if pd.isna(ma_value):
        return "n/a"
    if price >= ma_value:
        return "support"
    return "resistance"


def latest_static_levels(df: pd.DataFrame) -> dict:
    """Most recent confirmed swing high above price, swing low below price."""
    last = df.iloc[-1]
    price = float(last["close"])
    highs = df[df["swing_high"]]
    lows = df[df["swing_low"]]

    res = highs[highs["high"] > price]
    sup = lows[lows["low"] < price]

    resistance = None
    support = None
    if not res.empty:
        row = res.iloc[-1]
        resistance = {"date": row.name, "price": float(row["high"])}
    if not sup.empty:
        row = sup.iloc[-1]
        support = {"date": row.name, "price": float(row["low"])}
    return {"price": price, "resistance": resistance, "support": support}


def print_levels(df: pd.DataFrame, swings: dict):
    last = df.iloc[-1]
    price = float(last["close"])
    print("=" * 64)
    print("BTC dynamic S/R from moving averages + latest swing levels")
    print("=" * 64)
    print(f"Latest close:    ${price:,.0f}   ({df.index[-1].date()})")
    print()
    print(f"{'MA':<10}{'Value':>12}{'Role':>14}{'Distance':>12}")
    print("-" * 48)
    for label, col in (
        (f"EMA{EMA_FAST}", f"EMA{EMA_FAST}"),
        (f"SMA{SMA_MID}", f"SMA{SMA_MID}"),
        (f"SMA{SMA_SLOW}", f"SMA{SMA_SLOW}"),
    ):
        value = float(last[col]) if pd.notna(last[col]) else float("nan")
        role = classify_ma(price, value)
        dist = "n/a" if pd.isna(value) else f"{(price - value) / value * 100:+.1f}%"
        value_s = "n/a" if pd.isna(value) else f"${value:,.0f}"
        print(f"{label:<10}{value_s:>12}{role:>14}{dist:>12}")

    print()
    if swings["resistance"]:
        r = swings["resistance"]
        print(
            f"Latest swing resistance: ${r['price']:,.0f}  "
            f"({r['date'].date()})   "
            f"{((price - r['price']) / r['price'] * 100):+.1f}% vs price"
        )
    else:
        print("Latest swing resistance: none above current price in this window")

    if swings["support"]:
        s = swings["support"]
        print(
            f"Latest swing support:    ${s['price']:,.0f}  "
            f"({s['date'].date()})   "
            f"{((price - s['price']) / s['price'] * 100):+.1f}% vs price"
        )
    else:
        print("Latest swing support: none below current price in this window")
    print()
    print("MA rule: above the average = support, below = resistance.")
    print("Swing rule: last confirmed pivot high/low, not an eyeballed round number.")
    print("=" * 64 + "\n")


def draw(days_back: int | None = DAYS_BACK, block_window: bool = BLOCK_WINDOW):
    print("Loading BTC price data...")
    df = price_data.get_btc_price_data().copy()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df = df.sort_index()

    if days_back:
        df = df.iloc[-days_back:]

    df = add_ema(df, EMA_FAST)
    df = add_sma(df, SMA_MID)
    df = add_sma(df, SMA_SLOW)
    df = add_swing_points(df, left=SWING_LEFT, right=SWING_RIGHT)
    df["vol_sma"] = df["volumeto"].rolling(window=VOLUME_SMA_DAYS).mean()
    df["up_day"] = df["close"] >= df["open"]

    swings = latest_static_levels(df)
    print_levels(df, swings)

    last = df.iloc[-1]
    price = float(last["close"])

    fig, (ax1, ax2) = plt.subplots(
        2, 1,
        figsize=FIGURE_SIZE,
        gridspec_kw={"height_ratios": [3.2, 1]},
        sharex=True,
    )
    plt.style.use("fast")

    ax1.plot(df.index, df["close"], color=CLOSE_COLOR, linewidth=1.25, label="BTC Close")
    ax1.plot(df.index, df[f"EMA{EMA_FAST}"], color=EMA_COLOR, linewidth=1.2, label=f"EMA{EMA_FAST}")
    ax1.plot(df.index, df[f"SMA{SMA_MID}"], color=SMA50_COLOR, linewidth=1.2, label=f"SMA{SMA_MID}")
    ax1.plot(
        df.index, df[f"SMA{SMA_SLOW}"],
        color=SMA200_COLOR, linewidth=1.4, linestyle="--", label=f"SMA{SMA_SLOW}",
    )

    # Tiny markers on confirmed pivots
    sh = df[df["swing_high"]]
    sl = df[df["swing_low"]]
    ax1.scatter(sh.index, sh["high"], color=RESISTANCE_COLOR, s=18, zorder=5, label="Swing high")
    ax1.scatter(sl.index, sl["low"], color=SUPPORT_COLOR, s=18, zorder=5, label="Swing low")

    # Extend the latest live levels across the chart
    if swings["resistance"]:
        ax1.axhline(
            swings["resistance"]["price"],
            color=RESISTANCE_COLOR, linestyle=":", linewidth=1.2, alpha=0.85,
            label=f"Swing R ${swings['resistance']['price']:,.0f}",
        )
    if swings["support"]:
        ax1.axhline(
            swings["support"]["price"],
            color=SUPPORT_COLOR, linestyle=":", linewidth=1.2, alpha=0.85,
            label=f"Swing S ${swings['support']['price']:,.0f}",
        )

    # Right-edge labels for each MA's current role
    x_last = df.index[-1]
    for col, color in (
        (f"EMA{EMA_FAST}", EMA_COLOR),
        (f"SMA{SMA_MID}", SMA50_COLOR),
        (f"SMA{SMA_SLOW}", SMA200_COLOR),
    ):
        value = last[col]
        if pd.isna(value):
            continue
        role = classify_ma(price, float(value))
        tag = "S" if role == "support" else "R"
        ax1.annotate(
            f"{col} {tag} ${float(value):,.0f}",
            xy=(x_last, value),
            xytext=(8, 0),
            textcoords="offset points",
            color=color,
            fontsize=8,
            va="center",
        )

    title = "BTC • Moving-average S/R + latest swing levels + volume"
    if days_back:
        title += f" — last {days_back} days"
    ax1.set_title(title, fontsize=14, pad=12)
    ax1.set_ylabel("Price (USD)")
    ax1.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _p: f"${int(x):,}"))
    ax1.legend(loc="upper left", fontsize=8, ncol=2, framealpha=0.92)
    ax1.grid(True, alpha=0.3)

    vol_colors = ["#2ca02c" if up else "#d62728" for up in df["up_day"]]
    ax2.bar(df.index, df["volumeto"], color=vol_colors, width=1.0, alpha=0.75, label="Volume")
    ax2.plot(
        df.index, df["vol_sma"],
        color="#263549", linewidth=1.4, label=f"{VOLUME_SMA_DAYS}d vol SMA",
    )
    ax2.set_ylabel("Volume (USD)")
    ax2.set_xlabel("Date")
    ax2.yaxis.set_major_formatter(
        ticker.FuncFormatter(
            lambda x, _p: f"${x/1e9:.1f}B" if x >= 1e9 else f"${x/1e6:.0f}M"
        )
    )
    ax2.legend(loc="upper left", fontsize=8)
    ax2.grid(True, alpha=0.3)
    add_date_formatters(ax2)

    plt.tight_layout()

    if not _backend_is_interactive():
        out = "btc_resistance_and_support.png"
        plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
        print(f"Chart saved to: {out}")
        plt.close(fig)
        return

    print(f"Using interactive backend: {matplotlib.get_backend()}")
    plt.show(block=block_window)
    if block_window:
        plt.close(fig)


if __name__ == "__main__":
    draw()
