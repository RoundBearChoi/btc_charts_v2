"""Common plotting helpers and styling for consistent charts."""

from __future__ import annotations

from typing import Optional

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import pandas as pd


def format_price(value: float) -> str:
    """Format a USD price across BTC and low-priced alts."""
    if value is None or pd.isna(value):
        return "n/a"
    abs_v = abs(value)
    if abs_v >= 100:
        return f"${value:,.0f}"
    if abs_v >= 1:
        return f"${value:,.2f}"
    if abs_v >= 0.01:
        return f"${value:,.4f}"
    return f"${value:.6f}"


def price_axis_formatter(x, _p) -> str:
    return format_price(x)


def volume_axis_formatter(x, _p) -> str:
    if x >= 1e9:
        return f"${x / 1e9:.1f}B"
    if x >= 1e6:
        return f"${x / 1e6:.0f}M"
    return f"${x:,.0f}"


def apply_financial_styling(ax, title: str = "", ylabel: str = "Price (USD)"):
    """Apply consistent styling used across btc_charts_v2."""
    ax.set_title(title, fontsize=14, pad=20)
    ax.set_ylabel(ylabel)
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(price_axis_formatter))


def apply_grid(
    ax,
    *,
    enabled: bool = True,
    color: str = "gray",
    linewidth: float = 1.0,
    alpha: float = 0.7,
    linestyle: str = ":",
):
    """Toggle a grid with the same knobs the chart CONFIG blocks use."""
    if not enabled:
        ax.grid(False)
        return
    ax.grid(True, color=color, linewidth=linewidth, alpha=alpha, linestyle=linestyle)


def add_date_formatters(ax):
    """Add nice year/month formatting to x-axis."""
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_minor_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))


def add_window_date_formatters(ax, days_back: Optional[int]):
    """Pick tick density from the visible window length."""
    if days_back is None or days_back > 2000:
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_minor_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    elif days_back > 900:
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        ax.xaxis.set_minor_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    elif days_back > 240:
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        ax.xaxis.set_minor_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    else:
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        ax.xaxis.set_minor_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.tick_params(axis="x", which="major", labelsize=9)


def create_price_volume_rsi_figure(figsize=(14, 10)):
    """Create the common 3-panel layout used in 21/50/200 style charts."""
    fig, (ax1, ax2, ax3) = plt.subplots(
        3, 1,
        figsize=figsize,
        gridspec_kw={"height_ratios": [3, 1, 1]},
        sharex=True,
    )
    plt.style.use("fast")
    return fig, (ax1, ax2, ax3)
