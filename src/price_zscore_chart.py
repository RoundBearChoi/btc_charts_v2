import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as ticker
import pandas as pd
import numpy as np

import get_price_data_cryptocompare as price_data
from indicators import add_zscore


# ==================================================
# CONFIGURATION - Edit these values as needed
# ==================================================
DAYS_BACK = None               # e.g. 360*2 for last 2 years; None = full history
BLOCK_WINDOW = True            # False = script continues immediately after show()
SHOW_GRID = True
FIGURE_SIZE = (14, 8)

# Z-Score Configuration
ZSCORE_WINDOW = 365            # Rolling window in days (365 = ~1 year)
ZSCORE_COLOR = '#d62728'

# Price chart styling
CLOSE_COLOR = '#1f77b4'
CLOSE_WIDTH = 1.2
SMA200_COLOR = '#ff7f0e'
SMA200_WIDTH = 1.5

LOG_SCALE = False              # Set True for log y-axis on price

# ==================================================
# END OF CONFIGURATION
# ==================================================


def get_coin_choice() -> str:
    """Expanded & future-proof coin selector (same as other scripts)"""
    print("\n" + "="*60)
    print("BTC Price + Z-Score Chart - Coin Selection")
    print("="*60)
    print("1) BTC")
    print("2) FARTCOIN")
    print("3) TROLL")
    print("4) Any Other → type ticker (PEPE, DOGE, SOL, etc.)")
    print("="*60)
    while True:
        choice = input("\nEnter 1-4 or type ticker: ").strip().upper()
        if choice in ["1", "BTC"]:
            return "BTC"
        elif choice in ["2", "FARTCOIN"]:
            return "FARTCOIN"
        elif choice in ["3", "TROLL"]:
            return "TROLL"
        elif choice and len(choice) >= 2:  # free-form ticker
            print(f"→ Using custom ticker → {choice}")
            return choice
        else:
            print("Invalid. Try 1, 2, 3 or type a ticker.")


def draw(block_window=BLOCK_WINDOW, log_scale=LOG_SCALE, days_back=DAYS_BACK, zscore_window=ZSCORE_WINDOW):
    coin_ticker = get_coin_choice()

    # Beautiful display names
    coin_display_names = {
        "BTC": "Bitcoin",
        "FARTCOIN": "Fartcoin",
        "TROLL": "Troll",
    }
    coin_name = coin_display_names.get(coin_ticker, coin_ticker)

    print(f"\nLoading data for {coin_name} ({coin_ticker})...")
    if coin_ticker == "BTC":
        data_frame = price_data.get_btc_price_data()
    else:
        data_frame = price_data.get_price_data(coin=coin_ticker)

    if days_back is not None:
        data_frame = data_frame.sort_index().iloc[-days_back:]

    # Add 200 SMA for context on price chart (optional but useful)
    data_frame = add_zscore(data_frame, window=zscore_window)
    if len(data_frame) >= 200:
        data_frame['SMA200'] = data_frame['close'].rolling(window=200).mean()

    z_col = f"ZScore_{zscore_window}d"

    # === Create 2-panel figure (Price on top, Z-Score bottom) ===
    fig, (ax1, ax2) = plt.subplots(
        2, 1,
        figsize=FIGURE_SIZE,
        gridspec_kw={"height_ratios": [3, 1]},
        sharex=True
    )
    plt.style.use("fast")

    # --- Top panel: Price chart ---
    ax1.plot(
        data_frame.index,
        data_frame["close"],
        label=f"{coin_name} Close",
        color=CLOSE_COLOR,
        linewidth=CLOSE_WIDTH
    )

    if "SMA200" in data_frame.columns:
        ax1.plot(
            data_frame.index,
            data_frame["SMA200"],
            label="200 SMA",
            color=SMA200_COLOR,
            linewidth=SMA200_WIDTH,
            linestyle="--"
        )

    title = f"{coin_name} Price + Rolling Z-Score ({zscore_window}d window)"
    if log_scale:
        ax1.set_yscale("log")
        title += " (LOG SCALE)"
    if days_back:
        title += f" — Last {days_back} days"

    ax1.set_title(title, fontsize=14, pad=20)
    ax1.set_ylabel("Price (USD)")
    ax1.legend(loc="upper left")
    if SHOW_GRID:
        ax1.grid(True, alpha=0.3)
    ax1.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f"${int(x):,}"))

    # --- Bottom panel: Z-Score ---
    ax2.plot(
        data_frame.index,
        data_frame[z_col],
        label=f"Z-Score ({zscore_window}d)",
        color=ZSCORE_COLOR,
        linewidth=1.5
    )

    # Reference lines for statistical significance
    ax2.axhline(0, color="black", linestyle="-", linewidth=0.9, alpha=0.8, label="Mean (0)")
    ax2.axhline(2, color="red", linestyle="--", alpha=0.7, label="+2σ (Overbought / Expensive)")
    ax2.axhline(-2, color="green", linestyle="--", alpha=0.7, label="-2σ (Oversold / Cheap)")
    ax2.axhline(3, color="darkred", linestyle=":", alpha=0.6)
    ax2.axhline(-3, color="darkgreen", linestyle=":", alpha=0.6)

    ax2.set_ylabel("Z-Score")
    ax2.legend(loc="upper left", fontsize=9)
    if SHOW_GRID:
        ax2.grid(True, alpha=0.3)

    # Nice date formatting on shared x-axis
    ax2.xaxis.set_major_locator(mdates.YearLocator())
    ax2.xaxis.set_minor_locator(mdates.MonthLocator())
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.xticks(rotation=0)
    plt.xlabel("Date")

    plt.tight_layout()

    print(f"Drawing {coin_name} Price + Z-Score chart (window={zscore_window}d)...")
    plt.show(block=block_window)


if __name__ == "__main__":
    draw()
