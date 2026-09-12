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
