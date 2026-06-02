"""Common plotting helpers and styling for consistent charts."""

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import matplotlib.dates as mdates
from typing import Optional


def apply_financial_styling(ax, title: str = "", ylabel: str = "Price (USD)"):
    """Apply consistent styling used across btc_charts_v2."""
    ax.set_title(title, fontsize=14, pad=20)
    ax.set_ylabel(ylabel)
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f"${int(x):,}"))


def add_date_formatters(ax):
    """Add nice year/month formatting to x-axis."""
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_minor_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))


def create_price_volume_rsi_figure(figsize=(14, 10)):
    """Create the common 3-panel layout used in 21/50/200 style charts."""
    fig, (ax1, ax2, ax3) = plt.subplots(
        3, 1,
        figsize=figsize,
        gridspec_kw={"height_ratios": [3, 1, 1]},
        sharex=True
    )
    plt.style.use("fast")
    return fig, (ax1, ax2, ax3)
