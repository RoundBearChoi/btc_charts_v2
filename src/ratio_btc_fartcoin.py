#!/usr/bin/env python3

import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as ticker

# Import the shared indicators module (sibling import works when running
# `python src/btc_fartcoin_ratio_chart.py` from repo root, same as other scripts)
import indicators

# =============================================================================
# CONFIGURATION - Edit these values as needed (no code changes below required)
# =============================================================================
# Data paths (relative to this script's location - same structure as repo)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "cryptocompare_data")
BTC_CSV = os.path.join(DATA_DIR, "cryptocompare_historic_btc_price.csv")
FART_CSV = os.path.join(DATA_DIR, "cryptocompare_historic_fartcoin_price.csv")

# Chart behavior
BLOCK_WINDOW = True          # True = script waits for you to close plot window
DAYS_BACK = None             # e.g. 365*2 for last 2 years; None = full overlapping history
SHOW_GRID = True
FIGURE_SIZE = (14, 8)        # Wider for ratio detail; increase for 4K monitors

# Moving Average settings (you can add more by extending the list)
MA_WINDOWS = [7, 30]         # SMA windows in days. 7=short-term noise filter, 30=monthly trend
USE_EMA_INSTEAD = False      # If True, uses EMA instead of SMA for all windows above
EMA_SPAN_FACTOR = 1.0        # For EMA, effective span = window * factor (1.0 = standard)

# Ratio calculation
RATIO_INVERTED = False       # False = BTC/FARTCOIN (how many FART per 1 BTC). True = FART/BTC
RATIO_NAME = "BTC / FARTCOIN" if not RATIO_INVERTED else "FARTCOIN / BTC"

# Styling (consistent with other charts in the repo)
RATIO_COLOR = '#2E86AB'      # Nice blue for main ratio line
RATIO_WIDTH = 1.1
MA_COLORS = ['#E8871E', '#C73E1D', '#6B4226']  # Distinct warm colors for MAs (cycle if more windows)
MA_WIDTH = 1.6
MA_LINESTYLES = ['-', '--', '-.']  # Solid, dashed, dash-dot

# Title / labeling
TITLE_PREFIX = "BTC : FARTCOIN Ratio"
LOG_SCALE = False            # Rarely useful for ratios (can compress early explosive moves)
Y_LABEL = f"Price Ratio ({RATIO_NAME})"

# =============================================================================
# END OF CONFIGURATION
# =============================================================================


def load_and_align_data():
    print(f"\nLoading existing data (NO downloads, only local CSVs)...")
    print(f"  BTC cache   : {BTC_CSV}")
    print(f"  FARTCOIN cache: {FART_CSV}")

    if not os.path.exists(BTC_CSV):
        raise FileNotFoundError(
            f"BTC data file not found: {BTC_CSV}\n"
            "Run `python src/get_price_data_cryptocompare.py` (or with coin=BTC) first to create it."
        )
    if not os.path.exists(FART_CSV):
        raise FileNotFoundError(
            f"FARTCOIN data file not found: {FART_CSV}\n"
            "Run the data downloader for FARTCOIN first (it supports custom tickers now)."
        )

    btc_df = pd.read_csv(BTC_CSV, index_col=0, parse_dates=True)
    fart_df = pd.read_csv(FART_CSV, index_col=0, parse_dates=True)

    print(f"  BTC rows loaded      : {len(btc_df):,}  ({btc_df.index.min().date()} → {btc_df.index.max().date()})")
    print(f"  FARTCOIN rows loaded : {len(fart_df):,}  ({fart_df.index.min().date()} → {fart_df.index.max().date()})")

    # Align on exact matching timestamps (inner join on datetime index)
    common_index = btc_df.index.intersection(fart_df.index)
    overlap_days = len(common_index)

    if overlap_days < 5:
        raise ValueError(
            f"Only {overlap_days} overlapping trading days found between BTC and FARTCOIN.\n"
            "FARTCOIN data is much shorter (memecoin). Ensure both CSVs cover a common recent period."
        )

    print(f"  Overlapping days     : {overlap_days:,}  ({common_index.min().date()} → {common_index.max().date()})")

    btc_aligned = btc_df.loc[common_index]
    fart_aligned = fart_df.loc[common_index]

    # Compute ratio (handle potential zero prices defensively, though CryptoCompare cleans most)
    if RATIO_INVERTED:
        ratio_series = fart_aligned['close'] / btc_aligned['close']
    else:
        ratio_series = btc_aligned['close'] / fart_aligned['close']

    # Create clean ratio DataFrame (we treat ratio as the 'price' for indicator reuse)
    ratio_df = pd.DataFrame({'close': ratio_series}, index=common_index)
    ratio_df.index = pd.to_datetime(ratio_df.index)  # Defensive: ensure proper DatetimeIndex
    ratio_df = ratio_df.sort_index()

    # Optional recent window filter (applied after alignment)
    if DAYS_BACK is not None and DAYS_BACK > 0:
        ratio_df = ratio_df.iloc[-min(DAYS_BACK, len(ratio_df)):]
        print(f"  Filtered to last     : {DAYS_BACK} days → {len(ratio_df)} rows")

    # Basic sanity on ratio values
    current_ratio = ratio_df['close'].iloc[-1]
    min_ratio = ratio_df['close'].min()
    max_ratio = ratio_df['close'].max()
    print(f"  Current ratio        : {current_ratio:,.4f}")
    print(f"  Ratio range in window: {min_ratio:,.4f} → {max_ratio:,.4f}")

    return ratio_df


def add_moving_averages(ratio_df: pd.DataFrame) -> pd.DataFrame:
    """Add SMA or EMA columns using the shared indicators module.
    
    This reuses the exact same battle-tested rolling logic from indicators.py
    (Wilder-style where applicable, but SMA/EMA are simple rolling/ewm).
    """
    ma_type = "EMA" if USE_EMA_INSTEAD else "SMA"
    print(f"\nCalculating {ma_type}s on ratio series...")

    for i, window in enumerate(MA_WINDOWS):
        out_col = f"{ma_type}{window}"
        if USE_EMA_INSTEAD:
            span = int(window * EMA_SPAN_FACTOR)
            indicators.add_ema(
                ratio_df,
                span=span,
                price_col="close",
                out_col=out_col
            )
            print(f"  Added {out_col} (span={span})")
        else:
            indicators.add_sma(
                ratio_df,
                window=window,
                price_col="close",
                out_col=out_col
            )
            print(f"  Added {out_col}")

    return ratio_df


def draw_chart(ratio_df: pd.DataFrame):
    """Render the ratio + moving average(s) chart with professional financial styling."""
    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    plt.style.use('fast')

    # Main ratio line
    ax.plot(
        ratio_df.index,
        ratio_df['close'],
        label=RATIO_NAME,
        color=RATIO_COLOR,
        linewidth=RATIO_WIDTH,
        alpha=0.9
    )

    # Moving average lines (cycle colors and linestyles if many)
    ma_cols = [c for c in ratio_df.columns if c.startswith(('SMA', 'EMA'))]
    for idx, col in enumerate(ma_cols):
        color = MA_COLORS[idx % len(MA_COLORS)]
        linestyle = MA_LINESTYLES[idx % len(MA_LINESTYLES)]
        ax.plot(
            ratio_df.index,
            ratio_df[col],
            label=col,
            color=color,
            linewidth=MA_WIDTH,
            linestyle=linestyle,
            alpha=0.85
        )

    # Dynamic title with context
    start_date = ratio_df.index.min().strftime('%Y-%m-%d')
    end_date = ratio_df.index.max().strftime('%Y-%m-%d')
    ma_desc = " + ".join([f"{w}d {'EMA' if USE_EMA_INSTEAD else 'SMA'}" for w in MA_WINDOWS])
    title = f"{TITLE_PREFIX}  •  {start_date} to {end_date}"
    if DAYS_BACK:
        title += f"  (last {DAYS_BACK} days)"
    title += f"\n{ma_desc} overlay"
    if LOG_SCALE:
        ax.set_yscale('log')
        title += "  (LOG scale)"

    ax.set_title(title, fontsize=13, pad=15, fontweight='medium')
    ax.set_ylabel(Y_LABEL, fontsize=11)
    ax.set_xlabel('Date', fontsize=10)

    ax.legend(loc='upper left', framealpha=0.9)
    if SHOW_GRID:
        ax.grid(True, alpha=0.25, linestyle='--')

    # Robust date axis handling
    # AutoDateLocator + fig.autofmt_xdate() adapts well to different time spans.
    # Using '%Y-%m-%d' so individual days are visible on the x-axis.
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))

    # Handles rotation, spacing, and prevents labels from being clipped
    fig.autofmt_xdate(rotation=30, ha='right')

    # Y-axis: comma for large numbers or scientific for tiny ratios
    if ratio_df['close'].max() > 1000:
        ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f'{x:,.0f}'))
    else:
        ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f'{x:,.2f}'))

    # Subtle annotation for current value
    current = ratio_df['close'].iloc[-1]
    ax.annotate(
        f'Current: {current:,.2f}',
        xy=(ratio_df.index[-1], current),
        xytext=(15, 15),
        textcoords='offset points',
        fontsize=9,
        bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8, edgecolor='gray'),
        arrowprops=dict(arrowstyle='->', color='gray', lw=0.8)
    )

    plt.tight_layout()
    plt.show(block=BLOCK_WINDOW)


def main():
    print("=" * 70)
    print("BTC / FARTCOIN RATIO CHART  (offline mode - existing data only)")
    print("This script strictly uses pre-existing cryptocompare_data/ CSVs.")
    print("=" * 70)

    try:
        ratio_df = load_and_align_data()
        ratio_df = add_moving_averages(ratio_df)
        draw_chart(ratio_df)

    except FileNotFoundError as e:
        print(f"\n[ERROR] {e}")
    except Exception as e:
        print(f"\n[ERROR] Unexpected issue: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
