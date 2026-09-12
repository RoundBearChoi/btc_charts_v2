#!/usr/bin/env python3
"""
resistance_and_support.py

Two-panel chart for a coin from src/coins.csv, plus a compact MA snapshot
under the volume pane:
  1. Price + EMA21 / SMA50 / SMA200 as *dynamic* support or resistance
     plus recent swing highs / lows as *static* levels
  2. Volume (up-day / down-day bars) + volume SMA
  3. Footer table: MA value, support/resistance role, % distance from close

Rule used for moving averages:
  price above the MA  -> that MA is treated as support
  price below the MA  -> that MA is treated as resistance

Swing levels are calculated, not eyeballed:
  a bar is a swing high if its high is the max of `SWING_LEFT` bars before
  and `SWING_RIGHT` bars after. Same idea inverted for swing lows.

The terminal also prints market structure from the last two confirmed
swings: higher-high / higher-low vs lower-high / lower-low.

Startup prompt matches 21_50_200_chart.py: 1..N from coins.csv, plus ALL.

Run from repo root:
    python src/resistance_and_support.py
"""

from __future__ import annotations

import matplotlib

try:
    matplotlib.use("TkAgg")
except Exception:
    pass

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import pandas as pd

import get_price_data_cryptocompare as price_data
from coin_menu import get_coin_choice
from indicators import add_ema, add_sma

# ====================== CONFIG ======================
DAYS_BACK = 360            # chart window; None = full history
BLOCK_WINDOW = True
SHOW_GRID = True
LOG_SCALE = False

EMA_FAST = 21
SMA_MID = 50
SMA_SLOW = 200

SWING_LEFT = 8             # bars on each side to confirm a pivot
SWING_RIGHT = 8

VOLUME_SMA_DAYS = 20

FIGURE_SIZE = (14, 10.8)   # extra height reserved for the MA footer + gap
SHOW_MA_FOOTER = True      # table under volume: value / role / distance
SHOW_DISTANCE_ON_LABELS = True  # also append % distance to right-edge MA tags
FOOTER_GAP = 0.11          # figure-fraction gap between volume and the MA table

CLOSE_COLOR = "#1f77b4"
EMA_COLOR = "#E15FC3"
SMA50_COLOR = "#2ca02c"
SMA200_COLOR = "#C80C01"
SUPPORT_COLOR = "#2ca02c"
RESISTANCE_COLOR = "#d62728"
UNCONFIRMED_ALPHA = 0

# ====================================================


def _backend_is_interactive() -> bool:
    backend = matplotlib.get_backend().lower()
    return backend not in {"agg", "svg", "pdf", "ps", "cairo", "template"}


def format_price(value: float) -> str:
    if pd.isna(value):
        return "n/a"
    abs_v = abs(value)
    if abs_v >= 100:
        return f"${value:,.0f}"
    if abs_v >= 1:
        return f"${value:,.2f}"
    if abs_v >= 0.01:
        return f"${value:,.4f}"
    return f"${value:.6f}"


def price_axis_formatter(x, _p):
    return format_price(x)


def naive_index(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_convert("UTC").tz_localize(None)
    return df


def _day_ordinal(day: int) -> str:
    if 10 <= day % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def format_axis_date(x, _p=None) -> str:
    """Tick label like 'Sep 12th 2026'."""
    dt = mdates.num2date(x)
    return f"{dt.strftime('%b')} {_day_ordinal(dt.day)} {dt.year}"


def add_window_date_formatters(ax, days_back: int | None):
    """Readable calendar dates on the x-axis."""
    if days_back is None or days_back > 900:
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_minor_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    elif days_back > 240:
        # ~1 year: one labeled date per month, e.g. Sep 1st 2026
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        ax.xaxis.set_minor_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(ticker.FuncFormatter(format_axis_date))
    else:
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        ax.xaxis.set_minor_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
        ax.xaxis.set_major_formatter(ticker.FuncFormatter(format_axis_date))
    ax.tick_params(axis="x", which="major", labelsize=9, rotation=30)
    for label in ax.get_xticklabels():
        label.set_horizontalalignment("right")


def add_swing_points(df: pd.DataFrame, left: int = 8, right: int = 8) -> pd.DataFrame:
    """Mark confirmed swing highs / lows. The newest `right` bars cannot
    be confirmed yet because they still need future bars."""
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


def format_distance(price: float, ma_value: float) -> str:
    if pd.isna(ma_value) or ma_value == 0:
        return "n/a"
    return f"{(price - ma_value) / ma_value * 100:+.1f}%"


def ma_snapshot_rows(df: pd.DataFrame) -> list[dict]:
    """Latest MA value, S/R role, and % distance from close."""
    last = df.iloc[-1]
    price = float(last["close"])
    specs = (
        (f"EMA{EMA_FAST}", f"EMA{EMA_FAST}", EMA_COLOR),
        (f"SMA{SMA_MID}", f"SMA{SMA_MID}", SMA50_COLOR),
        (f"SMA{SMA_SLOW}", f"SMA{SMA_SLOW}", SMA200_COLOR),
    )
    rows = []
    for label, col, color in specs:
        value = float(last[col]) if pd.notna(last[col]) else float("nan")
        rows.append(
            {
                "label": label,
                "col": col,
                "color": color,
                "value": value,
                "role": classify_ma(price, value),
                "dist": format_distance(price, value),
            }
        )
    return rows


def swing_table(df: pd.DataFrame) -> pd.DataFrame:
    highs = df.loc[df["swing_high"], ["high"]].rename(columns={"high": "price"})
    highs["kind"] = "high"
    lows = df.loc[df["swing_low"], ["low"]].rename(columns={"low": "price"})
    lows["kind"] = "low"
    out = pd.concat([highs, lows]).sort_index()
    return out


def structure_from_swings(df: pd.DataFrame) -> dict:
    """Compare the last two confirmed highs and last two confirmed lows."""
    highs = df[df["swing_high"]]
    lows = df[df["swing_low"]]
    last_highs = [
        {"date": idx, "price": float(row["high"])}
        for idx, row in highs.tail(2).iterrows()
    ]
    last_lows = [
        {"date": idx, "price": float(row["low"])}
        for idx, row in lows.tail(2).iterrows()
    ]

    hh = hl = lh = ll = None
    if len(last_highs) == 2:
        hh = last_highs[1]["price"] > last_highs[0]["price"]
        lh = last_highs[1]["price"] < last_highs[0]["price"]
    if len(last_lows) == 2:
        hl = last_lows[1]["price"] > last_lows[0]["price"]
        ll = last_lows[1]["price"] < last_lows[0]["price"]

    if hh and hl:
        label = "uptrend (HH + HL)"
    elif lh and ll:
        label = "downtrend (LH + LL)"
    elif hh and ll:
        label = "mixed (HH + LL)"
    elif lh and hl:
        label = "mixed (LH + HL)"
    else:
        label = "not enough confirmed swings"

    price = float(df.iloc[-1]["close"])
    res_above = highs[highs["high"] > price]
    sup_below = lows[lows["low"] < price]
    nearest_res = None
    nearest_sup = None
    if not res_above.empty:
        row = res_above.iloc[-1]
        nearest_res = {"date": row.name, "price": float(row["high"])}
    if not sup_below.empty:
        row = sup_below.iloc[-1]
        nearest_sup = {"date": row.name, "price": float(row["low"])}

    return {
        "price": price,
        "label": label,
        "last_highs": last_highs,
        "last_lows": last_lows,
        "nearest_resistance": nearest_res,
        "nearest_support": nearest_sup,
    }


def print_levels(df: pd.DataFrame, structure: dict, coin_name: str, coin_ticker: str):
    last = df.iloc[-1]
    price = float(last["close"])
    print("=" * 64)
    print(f"{coin_name} ({coin_ticker})  dynamic S/R + swing structure")
    print("=" * 64)
    print(f"Latest close:    {format_price(price)}   ({df.index[-1].date()})")
    print(f"Structure:       {structure['label']}")
    print()
    print(f"{'MA':<10}{'Value':>14}{'Role':>14}")
    print("-" * 38)
    for row in ma_snapshot_rows(df):
        print(f"{row['label']:<10}{format_price(row['value']):>14}{row['role']:>14}")

    print()
    print("Last confirmed swing highs:")
    if structure["last_highs"]:
        for i, row in enumerate(structure["last_highs"], start=1):
            tag = "" if len(structure["last_highs"]) == 1 else ("prev" if i == 1 else "latest")
            print(f"  {tag:<7} {format_price(row['price'])}  ({row['date'].date()})")
    else:
        print("  none")

    print("Last confirmed swing lows:")
    if structure["last_lows"]:
        for i, row in enumerate(structure["last_lows"], start=1):
            tag = "" if len(structure["last_lows"]) == 1 else ("prev" if i == 1 else "latest")
            print(f"  {tag:<7} {format_price(row['price'])}  ({row['date'].date()})")
    else:
        print("  none")

    print()
    if structure["nearest_resistance"]:
        r = structure["nearest_resistance"]
        print(
            f"Nearest swing R above price: {format_price(r['price'])}  "
            f"({r['date'].date()})"
        )
    else:
        print("Nearest swing R above price: none in this window")

    if structure["nearest_support"]:
        s = structure["nearest_support"]
        print(
            f"Nearest swing S below price: {format_price(s['price'])}  "
            f"({s['date'].date()})"
        )
    else:
        print("Nearest swing S below price: none in this window")

    print()
    print("MA rule: above the average = support, below = resistance.")
    print("Swing rule: confirmed pivot only after SWING_RIGHT extra bars.")
    print("Structure uses the last two confirmed highs and last two lows.")
    print("Distance to each MA is on the chart footer / right-edge labels.")
    print("=" * 64 + "\n")


def draw_ma_footer(ax, df: pd.DataFrame, structure: dict):
    """Compact table under the volume pane. Not a third data plot."""
    ax.set_axis_off()
    last_date = df.index[-1].date()
    price = float(df.iloc[-1]["close"])
    rows = ma_snapshot_rows(df)

    ax.set_title(
        f"Close {format_price(price)}  ({last_date})   ·   {structure['label']}   ·   "
        "distance = (close − MA) / MA",
        fontsize=9,
        loc="left",
        pad=8,
        color="#333333",
    )

    cell_text = [
        [row["label"], format_price(row["value"]), row["role"], row["dist"]]
        for row in rows
    ]n