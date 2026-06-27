#!/usr/bin/env python3

import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as ticker

# Import the shared indicators module (sibling import works when running
# `python src/ratio_btc_fartcoin.py` from repo root, same as other scripts)
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
FIGURE_SIZE = (14, 9)        # (14, 8) original single panel; (14, 9-10) recommended when bottom indicator enabled for better proportions

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
# BOTTOM PANEL: Ratio Extremes / Overextension Indicator (NEW FEATURE)
# Shows whether the recent ratio has moved "too far up or down" statistically or via momentum.
# This directly addresses your request for visibility into ratio extremes.
# =============================================================================
ADD_BOTTOM_INDICATOR = True
BOTTOM_INDICATOR = "zscore"   # RECOMMENDED: "zscore" for statistical "how extreme vs recent mean"
                              # Alternative: "rsi" for classic momentum overbought/oversold
                              # Set to None or False to disable and use original single-panel chart

# Z-Score settings (best for "has the ratio gone up too much or down?")
ZSCORE_WINDOW = 90            # Rolling window in days.
                              # 30 = very responsive to recent swings (noisy)
                              # 90 = good balance for "recent regime" (quarterly context) ← recommended starting point
                              # 180-365 = longer-term historical norm (more stable but slower to react)
RSI_WINDOW = 14               # Standard for RSI momentum

# Visual thresholds (horizontal reference lines)
ZSCORE_OVER = 2.0             # +2 std devs = ratio unusually HIGH (potential overextension / mean-reversion candidate)
ZSCORE_UNDER = -2.0           # -2 std devs = ratio unusually LOW
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

# Bottom panel styling
BOTTOM_LINE_COLOR_Z = '#C0392B'   # Strong red for Z-score visibility
BOTTOM_LINE_COLOR_RSI = '#8E44AD' # Purple for RSI
THRESHOLD_COLOR_HIGH = '#E74C3C'
THRESHOLD_COLOR_LOW = '#27AE60'
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


def add_extremes_indicator(ratio_df: pd.DataFrame) -> pd.DataFrame:
    """Add Z-score or RSI indicator for the bottom panel.
    
    Reuses your existing battle-tested indicators.add_zscore() and add_rsi()
    from indicators.py. This keeps the implementation DRY and consistent
    with the rest of your btc_charts_v2 toolkit.
    """
    if not ADD_BOTTOM_INDICATOR or not BOTTOM_INDICATOR:
        return ratio_df

    print(f"\nAdding bottom extremes indicator ({BOTTOM_INDICATOR.upper()}) on the ratio...")

    if BOTTOM_INDICATOR == "zscore":
        out_col = f"ZScore{ZSCORE_WINDOW}"
        indicators.add_zscore(
            ratio_df,
            window=ZSCORE_WINDOW,
            price_col="close",
            out_col=out_col
        )
        print(f"  Added {out_col} (rolling {ZSCORE_WINDOW}d window)")
        print(f"    → Current Z-Score will show how many std devs the ratio is from its recent mean.")
        print(f"    → |Z| > {ZSCORE_OVER} often flags statistically extended moves (good for mean-reversion awareness).")

    elif BOTTOM_INDICATOR == "rsi":
        indicators.add_rsi(
            ratio_df,
            window=RSI_WINDOW,
            price_col="close",
            out_col="RSI"
        )
        print(f"  Added RSI (Wilder smoothed, {RSI_WINDOW}-period)")
        print(f"    → RSI > {RSI_OVERBOUGHT} = ratio momentum overbought (rising too fast recently)")
        print(f"    → RSI < {RSI_OVERSOLD}  = ratio momentum oversold (falling too fast recently)")

    else:
        print(f"  [WARN] BOTTOM_INDICATOR='{BOTTOM_INDICATOR}' not recognized. Supported: 'zscore', 'rsi'. Skipping bottom panel.")

    return ratio_df


def draw_chart(ratio_df: pd.DataFrame):
    """Render the ratio + MAs (top) and optional extremes indicator (bottom) with professional styling.
    
    When bottom indicator is enabled, uses shared x-axis for easy date correlation between
    ratio level and its statistical/momentum state. This is the key UX improvement for
    spotting when the ratio has \"gone up too much or down\".
    """
    has_bottom = bool(ADD_BOTTOM_INDICATOR and BOTTOM_INDICATOR in ("zscore", "rsi"))

    plt.style.use('fast')

    if has_bottom:
        fig, axs = plt.subplots(
            2, 1,
            figsize=FIGURE_SIZE,
            sharex=True,
            gridspec_kw={"height_ratios": [3.0, 1.15]}
        )
        ax_top = axs[0]
        ax_bot = axs[1]
    else:
        fig, ax_top = plt.subplots(figsize=FIGURE_SIZE)
        ax_bot = None

    # ========== TOP PANEL: Ratio + Moving Averages ==========
    # Main ratio line
    ax_top.plot(
        ratio_df.index,
        ratio_df['close'],
        label=RATIO_NAME,
        color=RATIO_COLOR,
        linewidth=RATIO_WIDTH,
        alpha=0.92
    )

    # Moving average lines (cycle colors and linestyles if many)
    ma_cols = [c for c in ratio_df.columns if c.startswith(('SMA', 'EMA'))]
    for idx, col in enumerate(ma_cols):
        color = MA_COLORS[idx % len(MA_COLORS)]
        linestyle = MA_LINESTYLES[idx % len(MA_LINESTYLES)]
        ax_top.plot(
            ratio_df.index,
            ratio_df[col],
            label=col,
            color=color,
            linewidth=MA_WIDTH,
            linestyle=linestyle,
            alpha=0.88
        )

    # Dynamic title with context
    start_date = ratio_df.index.min().strftime('%Y-%m-%d')
    end_date = ratio_df.index.max().strftime('%Y-%m-%d')
    ma_desc = " + ".join([f"{w}d {'EMA' if USE_EMA_INSTEAD else 'SMA'}" for w in MA_WINDOWS])
    title = f"{TITLE_PREFIX}  •  {start_date} to {end_date}"
    if DAYS_BACK:
        title += f"  (last {DAYS_BACK} days)"
    title += f"\n{ma_desc} overlay"
    if has_bottom:
        if BOTTOM_INDICATOR == "zscore":
            title += f"   •   Z-Score {ZSCORE_WINDOW}d (ratio extremes)"
        elif BOTTOM_INDICATOR == "rsi":
            title += f"   •   RSI {RSI_WINDOW} (ratio momentum)"
    if LOG_SCALE:
        ax_top.set_yscale('log')
        title += "  (LOG scale)"

    ax_top.set_title(title, fontsize=12, pad=12, fontweight='medium')
    ax_top.set_ylabel(Y_LABEL, fontsize=11)
    if not has_bottom:
        ax_top.set_xlabel('Date', fontsize=10)

    ax_top.legend(loc='upper left', framealpha=0.92, fontsize=9)
    if SHOW_GRID:
        ax_top.grid(True, alpha=0.22, linestyle='--')

    # Robust date axis handling (only set on top if no bottom; bottom will control shared axis)
    if not has_bottom:
        ax_top.xaxis.set_major_locator(mdates.AutoDateLocator())
        ax_top.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        fig.autofmt_xdate(rotation=30, ha='right')

    # Y-axis: comma for large numbers or scientific for tiny ratios
    if ratio_df['close'].max() > 1000:
        ax_top.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f'{x:,.0f}'))
    else:
        ax_top.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f'{x:,.2f}'))

    # Subtle annotation for current value on top
    current = ratio_df['close'].iloc[-1]
    ax_top.annotate(
        f'Current: {current:,.2f}',
        xy=(ratio_df.index[-1], current),
        xytext=(12, 12),
        textcoords='offset points',
        fontsize=9,
        bbox=dict(boxstyle='round,pad=0.25', facecolor='white', alpha=0.9, edgecolor='gray'),
        arrowprops=dict(arrowstyle='->', color='gray', lw=0.7)
    )

    # ========== BOTTOM PANEL: Extremes Indicator (Z-score or RSI) ==========
    if has_bottom and ax_bot is not None:
        if BOTTOM_INDICATOR == "zscore":
            z_col = f"ZScore{ZSCORE_WINDOW}"
            if z_col in ratio_df.columns:
                zseries = ratio_df[z_col]
                ax_bot.plot(
                    ratio_df.index,
                    zseries,
                    label=z_col,
                    color=BOTTOM_LINE_COLOR_Z,
                    linewidth=1.35,
                    alpha=0.95
                )

                # Reference lines for statistical extremes
                ax_bot.axhline(0, color='#5D6D7E', linewidth=1.0, linestyle='-', alpha=0.65, label='Mean (0)')
                ax_bot.axhline(ZSCORE_OVER, color=THRESHOLD_COLOR_HIGH, linewidth=1.15, linestyle='--', alpha=0.9,
                               label=f'High (+{ZSCORE_OVER}σ)')
                ax_bot.axhline(ZSCORE_UNDER, color=THRESHOLD_COLOR_LOW, linewidth=1.15, linestyle='--', alpha=0.9,
                               label=f'Low ({ZSCORE_UNDER}σ)')

                # Light background shading for extreme zones (subtle)
                ylim_top = max(zseries.max() + 0.3, ZSCORE_OVER + 0.8)
                ylim_bot = min(zseries.min() - 0.3, ZSCORE_UNDER - 0.8)
                ax_bot.axhspan(ZSCORE_OVER, ylim_top, alpha=0.06, color='red')
                ax_bot.axhspan(ylim_bot, ZSCORE_UNDER, alpha=0.06, color='green')

                ax_bot.set_ylabel(f"Z-Score\n({ZSCORE_WINDOW}d)", fontsize=9)
                ax_bot.set_ylim(ylim_bot, ylim_top)

                current_z = zseries.iloc[-1]
                ax_bot.annotate(
                    f'Current Z: {current_z:.2f}',
                    xy=(ratio_df.index[-1], current_z),
                    xytext=(10, -12 if current_z > 0 else 12),
                    textcoords='offset points',
                    fontsize=8,
                    bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.92, edgecolor='gray'),
                    arrowprops=dict(arrowstyle='->', color='gray', lw=0.6)
                )

                # Interpretation hint in legend area
                ax_bot.legend(loc='upper left', fontsize=7.5, framealpha=0.88, ncol=1)

        elif BOTTOM_INDICATOR == "rsi":
            rsi_col = "RSI"
            if rsi_col in ratio_df.columns:
                rseries = ratio_df[rsi_col]
                ax_bot.plot(
                    ratio_df.index,
                    rseries,
                    label="RSI",
                    color=BOTTOM_LINE_COLOR_RSI,
                    linewidth=1.35,
                    alpha=0.95
                )

                # Classic RSI levels
                ax_bot.axhline(RSI_OVERBOUGHT, color=THRESHOLD_COLOR_HIGH, linewidth=1.15, linestyle='--', alpha=0.9,
                               label=f'Overbought ({RSI_OVERBOUGHT})')
                ax_bot.axhline(RSI_OVERSOLD, color=THRESHOLD_COLOR_LOW, linewidth=1.15, linestyle='--', alpha=0.9,
                               label=f'Oversold ({RSI_OVERSOLD})')
                ax_bot.axhline(50, color='#5D6D7E', linewidth=0.9, linestyle='-', alpha=0.55, label='Neutral (50)')

                ax_bot.set_ylabel("RSI", fontsize=10)
                ax_bot.set_ylim(0, 100)

                current_r = rseries.iloc[-1]
                ax_bot.annotate(
                    f'Current: {current_r:.1f}',
                    xy=(ratio_df.index[-1], current_r),
                    xytext=(10, 8),
                    textcoords='offset points',
                    fontsize=8,
                    bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.92, edgecolor='gray'),
                    arrowprops=dict(arrowstyle='->', color='gray', lw=0.6)
                )

                ax_bot.legend(loc='upper left', fontsize=7.5, framealpha=0.88)

        # Common bottom panel setup
        if SHOW_GRID:
            ax_bot.grid(True, alpha=0.18, linestyle=':')

        ax_bot.set_xlabel('Date', fontsize=10)

        # Date formatting only on the bottom axis (shared with top)
        ax_bot.xaxis.set_major_locator(mdates.AutoDateLocator())
        ax_bot.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        fig.autofmt_xdate(rotation=30, ha='right')

        # Subtle bottom panel title / interpretation
        if BOTTOM_INDICATOR == "zscore":
            ax_bot.set_title(
                "Z-Score of Ratio: Positive = ratio unusually HIGH vs its recent average  |  Negative = unusually LOW  |  |Z| > 2 often signals extended move",
                fontsize=8, pad=4, style='italic', color='#34495E'
            )
        elif BOTTOM_INDICATOR == "rsi":
            ax_bot.set_title(
                "RSI on Ratio: >70 momentum overbought (ratio rose too fast)  |  <30 momentum oversold (ratio fell too fast)",
                fontsize=8, pad=4, style='italic', color='#34495E'
            )

    plt.tight_layout()
    plt.show(block=BLOCK_WINDOW)


def main():
    print("=" * 72)
    print("BTC / FARTCOIN RATIO CHART  (offline mode - existing data only)")
    print("This script strictly uses pre-existing cryptocompare_data/ CSVs.")
    if ADD_BOTTOM_INDICATOR and BOTTOM_INDICATOR:
        print(f"Bottom panel enabled: {BOTTOM_INDICATOR.upper()}  (Z-score recommended for ratio overextension detection)")
    print("=" * 72)

    try:
        ratio_df = load_and_align_data()
        ratio_df = add_moving_averages(ratio_df)
        ratio_df = add_extremes_indicator(ratio_df)
        draw_chart(ratio_df)

    except FileNotFoundError as e:
        print(f"\n[ERROR] {e}")
    except Exception as e:
        print(f"\n[ERROR] Unexpected issue: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
