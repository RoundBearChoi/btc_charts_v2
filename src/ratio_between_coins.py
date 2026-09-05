#!/usr/bin/env python3

import os
from itertools import combinations
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as ticker

# Import the shared indicators module (sibling import works when running
# `python src/ratio_between_coins.py` from repo root, same as other scripts)
import indicators

# =============================================================================
# CONFIGURATION - Edit these values as needed (no code changes below required)
# =============================================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "cryptocompare_data")
COINS_CSV = Path(SCRIPT_DIR) / "coins.csv"

BASE_NAME = "BTC"
QUOTE_NAME = "FARTCOIN"
BASE_CSV = os.path.join(DATA_DIR, "cryptocompare_historic_btc_price.csv")
QUOTE_CSV = os.path.join(DATA_DIR, "cryptocompare_historic_fartcoin_price.csv")

BLOCK_WINDOW = True
DAYS_BACK = None
FIGURE_SIZE = (14, 9)

MA_WINDOWS = [7, 30]
USE_EMA_INSTEAD = False
EMA_SPAN_FACTOR = 1.0

RATIO_INVERTED = False
RATIO_NAME = "BTC / FARTCOIN" if not RATIO_INVERTED else "FARTCOIN / BTC"

RATIO_COLOR = "#2E86AB"
RATIO_WIDTH = 1.1
MA_COLORS = ["#E8871E", "#C73E1D", "#6B4226"]
MA_WIDTH = 1.6
MA_LINESTYLES = ["-", "--", "-."]

ADD_LONG_MA = True
LONG_MA_WINDOW = 365
LONG_MA_MIN_PERIODS = None
LONG_MA_COLOR = "#8FA3B8"
LONG_MA_WIDTH = 2.0
LONG_MA_ALPHA = 0.42
LONG_MA_STYLE = "-"

ADD_RANGE_ENVELOPE = True
RANGE_WINDOW = None
RANGE_HIGH_COLOR = "#9AA7B5"
RANGE_LOW_COLOR = "#9AA7B5"
RANGE_LINE_WIDTH = 1.05
RANGE_LINE_ALPHA = 0.50
RANGE_LINE_STYLE = ":"
RANGE_FILL_COLOR = "#8FA3B8"
RANGE_FILL_ALPHA = 0.07

TITLE_PREFIX = "BTC : FARTCOIN Ratio"
LOG_SCALE = False
Y_LABEL = f"Price Ratio ({RATIO_NAME})"

ADD_BOTTOM_INDICATOR = True
BOTTOM_INDICATOR = "zscore"
ZSCORE_WINDOW = 90
RSI_WINDOW = 14
ZSCORE_OVER = 2.0
ZSCORE_UNDER = -2.0
ZSCORE_EXTRA_LEVELS = [3.0, -3.0]
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
BOTTOM_LINE_COLOR_Z = "#C0392B"
BOTTOM_LINE_COLOR_RSI = "#8E44AD"
THRESHOLD_COLOR_HIGH = "#E74C3C"
THRESHOLD_COLOR_LOW = "#27AE60"
ZSCORE_LINE_WIDTH = 1.2
ZSCORE_MEAN_WIDTH = 1.1
ZSCORE_MEAN_ALPHA = 1.0
ZSCORE_THRESHOLD_WIDTH = 1.2
ZSCORE_EXTRA_WIDTH = 1.2
ZSCORE_MEAN_COLOR = "#707070"
ZSCORE_EXTRA_COLOR_HIGH = "#E74C3C"
ZSCORE_EXTRA_COLOR_LOW = "#27AE60"
BOTTOM_GRID = True
BOTTOM_GRID_COLOR = "#B0AFAB"
BOTTOM_GRID_WIDTH = 1.0
BOTTOM_GRID_ALPHA = 0.7
BOTTOM_GRID_STYLE = "--"
TOP_GRID = True
TOP_GRID_COLOR = "#B0AFAB"
TOP_GRID_WIDTH = 1.0
TOP_GRID_ALPHA = 0.7
TOP_GRID_STYLE = "--"


def load_coins(csv_path: Path = COINS_CSV) -> pd.DataFrame:
    if not csv_path.exists():
        raise FileNotFoundError(f"Coin list not found: {csv_path}")
    coins = pd.read_csv(csv_path)
    coins.columns = coins.columns.str.strip().str.lower()
    required = {"name", "symbol"}
    missing = required - set(coins.columns)
    if missing:
        raise ValueError(f"{csv_path} is missing columns: {sorted(missing)}")
    coins["name"] = coins["name"].astype(str).str.strip()
    coins["symbol"] = coins["symbol"].astype(str).str.strip().str.upper()
    coins = coins.dropna(subset=["name", "symbol"])
    coins = coins[(coins["name"] != "") & (coins["symbol"] != "")]
    if coins.empty:
        raise ValueError(f"{csv_path} has no usable name/symbol rows")
    return coins.reset_index(drop=True)


def _cache_path(symbol: str) -> str:
    return os.path.join(DATA_DIR, f"cryptocompare_historic_{symbol.lower()}_price.csv")


def build_pair_choices() -> list:
    coins = load_coins()
    if len(coins) < 2:
        raise ValueError("Need at least 2 coins in coins.csv to build a ratio")
    pairs = []
    for left, right in combinations(coins.itertuples(index=False), 2):
        pairs.append({
            "label": f"{left.name}:{right.name}",
            "base_name": left.name,
            "quote_name": right.name,
            "base_symbol": left.symbol,
            "quote_symbol": right.symbol,
            "base_csv": _cache_path(left.symbol),
            "quote_csv": _cache_path(right.symbol),
        })
    return pairs


def apply_pair_labels(base_name: str, quote_name: str):
    global BASE_NAME, QUOTE_NAME, RATIO_NAME, TITLE_PREFIX, Y_LABEL
    BASE_NAME = base_name
    QUOTE_NAME = quote_name
    if RATIO_INVERTED:
        RATIO_NAME = f"{quote_name} / {base_name}"
        TITLE_PREFIX = f"{quote_name} : {base_name} Ratio"
    else:
        RATIO_NAME = f"{base_name} / {quote_name}"
        TITLE_PREFIX = f"{base_name} : {quote_name} Ratio"
    Y_LABEL = f"Price Ratio ({RATIO_NAME})"


def prompt_user_for_pair():
    global BASE_CSV, QUOTE_CSV
    pairs = build_pair_choices()
    n = len(pairs)
    print()
    print("Select ratio pair (existing local CSVs only — no download):")
    width = len(str(n))
    for i, pair in enumerate(pairs, start=1):
        print(f"  {i:>{width}}) {pair['label']}")
    while True:
        raw = input(f"Choice [1-{n}]: ").strip()
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= n:
                pair = pairs[idx - 1]
                break
        print(f"  Please enter a number from 1 to {n}.")
    if not os.path.exists(pair["base_csv"]):
        raise FileNotFoundError(
            f"{pair['base_name']} data file not found.\nExpected: {pair['base_csv']}"
        )
    if not os.path.exists(pair["quote_csv"]):
        raise FileNotFoundError(
            f"{pair['quote_name']} data file not found.\nExpected: {pair['quote_csv']}"
        )
    BASE_CSV = pair["base_csv"]
    QUOTE_CSV = pair["quote_csv"]
    apply_pair_labels(pair["base_name"], pair["quote_name"])
    print(f"\nSelected: {pair['label']}")
    return pair


def load_and_align_data():
    print(f"\nLoading existing data (NO downloads, only local CSVs)...")
    print(f"  {BASE_NAME} cache  : {BASE_CSV}")
    print(f"  {QUOTE_NAME} cache : {QUOTE_CSV}")
    if not os.path.exists(BASE_CSV):
        raise FileNotFoundError(f"{BASE_NAME} data file not found: {BASE_CSV}")
    if not os.path.exists(QUOTE_CSV):
        raise FileNotFoundError(f"{QUOTE_NAME} data file not found: {QUOTE_CSV}")
    base_df = pd.read_csv(BASE_CSV, index_col=0, parse_dates=True)
    quote_df = pd.read_csv(QUOTE_CSV, index_col=0, parse_dates=True)
    print(f"  {BASE_NAME} rows loaded  : {len(base_df):,}  ({base_df.index.min().date()} → {base_df.index.max().date()})")
    print(f"  {QUOTE_NAME} rows loaded : {len(quote_df):,}  ({quote_df.index.min().date()} → {quote_df.index.max().date()})")
    common_index = base_df.index.intersection(quote_df.index)
    overlap_days = len(common_index)
    if overlap_days < 5:
        raise ValueError(f"Only {overlap_days} overlapping trading days found between {BASE_NAME} and {QUOTE_NAME}.")
    print(f"  Overlapping days       : {overlap_days:,}  ({common_index.min().date()} → {common_index.max().date()})")
    base_aligned = base_df.loc[common_index]
    quote_aligned = quote_df.loc[common_index]
    if RATIO_INVERTED:
        ratio_series = quote_aligned["close"] / base_aligned["close"]
    else:
        ratio_series = base_aligned["close"] / quote_aligned["close"]
    ratio_df = pd.DataFrame({"close": ratio_series}, index=common_index)
    ratio_df.index = pd.to_datetime(ratio_df.index)
    ratio_df = ratio_df.sort_index()
    if DAYS_BACK is not None and DAYS_BACK > 0:
        ratio_df = ratio_df.iloc[-min(DAYS_BACK, len(ratio_df)):]
        print(f"  Filtered to last       : {DAYS_BACK} days → {len(ratio_df)} rows")
    current_ratio = ratio_df["close"].iloc[-1]
    min_ratio = ratio_df["close"].min()
    max_ratio = ratio_df["close"].max()
    print(f"  Current ratio          : {current_ratio:,.4f}")
    print(f"  Ratio range in window  : {min_ratio:,.4f} → {max_ratio:,.4f}")
    return ratio_df


def add_moving_averages(ratio_df: pd.DataFrame) -> pd.DataFrame:
    ma_type = "EMA" if USE_EMA_INSTEAD else "SMA"
    print(f"\nCalculating {ma_type}s on ratio series...")
    for window in MA_WINDOWS:
        out_col = f"{ma_type}{window}"
        if USE_EMA_INSTEAD:
            span = int(window * EMA_SPAN_FACTOR)
            indicators.add_ema(ratio_df, span=span, price_col="close", out_col=out_col)
            print(f"  Added {out_col} (span={span})")
        else:
            indicators.add_sma(ratio_df, window=window, price_col="close", out_col=out_col)
            print(f"  Added {out_col}")
    return ratio_df


def add_long_term_overlays(ratio_df: pd.DataFrame) -> pd.DataFrame:
    if ADD_LONG_MA and LONG_MA_WINDOW and LONG_MA_WINDOW > 1:
        min_periods = LONG_MA_MIN_PERIODS
        if min_periods is None:
            min_periods = max(30, LONG_MA_WINDOW // 2)
        min_periods = max(2, min(int(min_periods), int(LONG_MA_WINDOW), len(ratio_df)))
        col = f"LongSMA{LONG_MA_WINDOW}"
        ratio_df[col] = ratio_df["close"].rolling(window=int(LONG_MA_WINDOW), min_periods=min_periods).mean()
        valid = int(ratio_df[col].notna().sum())
        print(f"\nLong-term overlay: {col}  ({valid:,} valid points, min_periods={min_periods})")
        if valid == 0:
            print("  [WARN] Not enough history for the long MA — line will be omitted.")
    if ADD_RANGE_ENVELOPE:
        if RANGE_WINDOW is None:
            ratio_df["RangeHigh"] = ratio_df["close"].cummax()
            ratio_df["RangeLow"] = ratio_df["close"].cummin()
            print("Range envelope: expanding high / low of the plotted window")
        else:
            window = int(RANGE_WINDOW)
            min_periods = max(5, window // 4)
            min_periods = min(min_periods, window, len(ratio_df))
            ratio_df["RangeHigh"] = ratio_df["close"].rolling(window, min_periods=min_periods).max()
            ratio_df["RangeLow"] = ratio_df["close"].rolling(window, min_periods=min_periods).min()
            print(f"Range envelope: {window}d rolling high / low")
    return ratio_df


def add_extremes_indicator(ratio_df: pd.DataFrame) -> pd.DataFrame:
    if not ADD_BOTTOM_INDICATOR or not BOTTOM_INDICATOR:
        return ratio_df
    print(f"\nAdding bottom extremes indicator ({BOTTOM_INDICATOR.upper()}) on the ratio...")
    if BOTTOM_INDICATOR == "zscore":
        out_col = f"ZScore{ZSCORE_WINDOW}"
        indicators.add_zscore(ratio_df, window=ZSCORE_WINDOW, price_col="close", out_col=out_col)
        print(f"  Added {out_col} (rolling {ZSCORE_WINDOW}d window)")
    elif BOTTOM_INDICATOR == "rsi":
        indicators.add_rsi(ratio_df, window=RSI_WINDOW, price_col="close", out_col="RSI")
        print(f"  Added RSI (Wilder smoothed, {RSI_WINDOW}-period)")
    else:
        print(f"  [WARN] BOTTOM_INDICATOR='{BOTTOM_INDICATOR}' not recognized. Skipping bottom panel.")
    return ratio_df


def draw_chart(ratio_df: pd.DataFrame):
    has_bottom = bool(ADD_BOTTOM_INDICATOR and BOTTOM_INDICATOR in ("zscore", "rsi"))
    plt.style.use("fast")
    if has_bottom:
        fig, axs = plt.subplots(2, 1, figsize=FIGURE_SIZE, sharex=True, gridspec_kw={"height_ratios": [3.0, 1.15]})
        ax_top = axs[0]
        ax_bot = axs[1]
    else:
        fig, ax_top = plt.subplots(figsize=FIGURE_SIZE)
        ax_bot = None

    if ADD_RANGE_ENVELOPE and "RangeHigh" in ratio_df.columns and "RangeLow" in ratio_df.columns:
        high_label = "Peak (window high)" if RANGE_WINDOW is None else f"{RANGE_WINDOW}d high"
        low_label = "Bottom (window low)" if RANGE_WINDOW is None else f"{RANGE_WINDOW}d low"
        ax_top.fill_between(ratio_df.index, ratio_df["RangeLow"], ratio_df["RangeHigh"], color=RANGE_FILL_COLOR, alpha=RANGE_FILL_ALPHA, zorder=1)
        ax_top.plot(ratio_df.index, ratio_df["RangeHigh"], label=high_label, color=RANGE_HIGH_COLOR, linewidth=RANGE_LINE_WIDTH, linestyle=RANGE_LINE_STYLE, alpha=RANGE_LINE_ALPHA, zorder=2)
        ax_top.plot(ratio_df.index, ratio_df["RangeLow"], label=low_label, color=RANGE_LOW_COLOR, linewidth=RANGE_LINE_WIDTH, linestyle=RANGE_LINE_STYLE, alpha=RANGE_LINE_ALPHA, zorder=2)

    ax_top.plot(ratio_df.index, ratio_df["close"], label=RATIO_NAME, color=RATIO_COLOR, linewidth=RATIO_WIDTH, alpha=0.92, zorder=4)

    long_col = f"LongSMA{LONG_MA_WINDOW}"
    if ADD_LONG_MA and long_col in ratio_df.columns and ratio_df[long_col].notna().any():
        ax_top.plot(ratio_df.index, ratio_df[long_col], label=f"SMA{LONG_MA_WINDOW} (long)", color=LONG_MA_COLOR, linewidth=LONG_MA_WIDTH, linestyle=LONG_MA_STYLE, alpha=LONG_MA_ALPHA, zorder=3)

    ma_cols = [c for c in ratio_df.columns if c.startswith(("SMA", "EMA"))]
    for idx, col in enumerate(ma_cols):
        ax_top.plot(ratio_df.index, ratio_df[col], label=col, color=MA_COLORS[idx % len(MA_COLORS)], linewidth=MA_WIDTH, linestyle=MA_LINESTYLES[idx % len(MA_LINESTYLES)], alpha=0.88, zorder=5)

    start_date = ratio_df.index.min().strftime("%Y-%m-%d")
    end_date = ratio_df.index.max().strftime("%Y-%m-%d")
    ma_desc = " + ".join([f"{w}d {'EMA' if USE_EMA_INSTEAD else 'SMA'}" for w in MA_WINDOWS])
    title = f"{TITLE_PREFIX}  •  {start_date} to {end_date}"
    if DAYS_BACK:
        title += f"  (last {DAYS_BACK} days)"
    title += f"\n{ma_desc} overlay"
    if ADD_LONG_MA:
        title += f"  +  {LONG_MA_WINDOW}d long SMA"
    if ADD_RANGE_ENVELOPE:
        title += "  +  peak/bottom envelope" if RANGE_WINDOW is None else f"  +  {RANGE_WINDOW}d high/low"
    if has_bottom:
        if BOTTOM_INDICATOR == "zscore":
            title += f"   •   Z-Score {ZSCORE_WINDOW}d (ratio extremes)"
        elif BOTTOM_INDICATOR == "rsi":
            title += f"   •   RSI {RSI_WINDOW} (ratio momentum)"
    if LOG_SCALE:
        ax_top.set_yscale("log")
        title += "  (LOG scale)"

    ax_top.set_title(title, fontsize=12, pad=12, fontweight="medium")
    ax_top.set_ylabel(Y_LABEL, fontsize=11)
    if not has_bottom:
        ax_top.set_xlabel("Date", fontsize=10)
    ax_top.legend(loc="upper left", framealpha=0.92, fontsize=9)
    if TOP_GRID:
        ax_top.grid(True, color=TOP_GRID_COLOR, linewidth=TOP_GRID_WIDTH, alpha=TOP_GRID_ALPHA, linestyle=TOP_GRID_STYLE)
    if ratio_df["close"].max() > 1000:
        ax_top.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f"{x:,.0f}"))
    else:
        ax_top.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f"{x:,.2f}"))
    current = ratio_df["close"].iloc[-1]
    ax_top.annotate(
        f"Current: {current:,.2f}",
        xy=(ratio_df.index[-1], current),
        xytext=(12, 12),
        textcoords="offset points",
        fontsize=9,
        bbox=dict(boxstyle="round,pad=0.25", facecolor="white", alpha=0.9, edgecolor="gray"),
        arrowprops=dict(arrowstyle="->", color="gray", lw=0.7),
    )

    if has_bottom and ax_bot is not None:
        if BOTTOM_INDICATOR == "zscore":
            z_col = f"ZScore{ZSCORE_WINDOW}"
            if z_col in ratio_df.columns:
                zseries = ratio_df[z_col]
                ax_bot.plot(ratio_df.index, zseries, label=z_col, color=BOTTOM_LINE_COLOR_Z, linewidth=ZSCORE_LINE_WIDTH, alpha=0.95)
                ax_bot.axhline(0, color=ZSCORE_MEAN_COLOR, linewidth=ZSCORE_MEAN_WIDTH, linestyle="-", alpha=ZSCORE_MEAN_ALPHA, label="Mean (0)")
                ax_bot.axhline(ZSCORE_OVER, color=THRESHOLD_COLOR_HIGH, linewidth=ZSCORE_THRESHOLD_WIDTH, linestyle="--", alpha=0.9, label=f"High (+{ZSCORE_OVER}σ)")
                ax_bot.axhline(ZSCORE_UNDER, color=THRESHOLD_COLOR_LOW, linewidth=ZSCORE_THRESHOLD_WIDTH, linestyle="--", alpha=0.9, label=f"Low ({ZSCORE_UNDER}σ)")
                for level in (1.0, -1.0):
                    ax_bot.axhline(level, color=BOTTOM_GRID_COLOR, linewidth=BOTTOM_GRID_WIDTH, linestyle=BOTTOM_GRID_STYLE, alpha=BOTTOM_GRID_ALPHA)
                for level in ZSCORE_EXTRA_LEVELS:
                    if level == 0:
                        continue
                    color = ZSCORE_EXTRA_COLOR_HIGH if level > 0 else ZSCORE_EXTRA_COLOR_LOW
                    ax_bot.axhline(level, color=color, linewidth=ZSCORE_EXTRA_WIDTH, linestyle=":", alpha=0.55)
                all_levels = [0.0, ZSCORE_OVER, ZSCORE_UNDER, 1.0, -1.0] + list(ZSCORE_EXTRA_LEVELS)
                ylim_top = max(zseries.max() + 0.3, max(all_levels) + 0.8)
                ylim_bot = min(zseries.min() - 0.3, min(all_levels) - 0.8)
                ax_bot.axhspan(ZSCORE_OVER, ylim_top, alpha=0.06, color="red")
                ax_bot.axhspan(ylim_bot, ZSCORE_UNDER, alpha=0.06, color="green")
                ax_bot.set_ylabel(f"Z-Score\n({ZSCORE_WINDOW}d)", fontsize=9)
                ax_bot.set_ylim(ylim_bot, ylim_top)
                current_z = zseries.iloc[-1]
                ax_bot.annotate(
                    f"Current Z: {current_z:.2f}",
                    xy=(ratio_df.index[-1], current_z),
                    xytext=(10, -12 if current_z > 0 else 12),
                    textcoords="offset points",
                    fontsize=8,
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.92, edgecolor="gray"),
                    arrowprops=dict(arrowstyle="->", color="gray", lw=0.6),
                )
                ax_bot.legend(loc="upper left", fontsize=7.5, framealpha=0.88, ncol=1)
        elif BOTTOM_INDICATOR == "rsi":
            rseries = ratio_df["RSI"]
            ax_bot.plot(ratio_df.index, rseries, label="RSI", color=BOTTOM_LINE_COLOR_RSI, linewidth=1.35, alpha=0.95)
            ax_bot.axhline(RSI_OVERBOUGHT, color=THRESHOLD_COLOR_HIGH, linewidth=1.15, linestyle="--", alpha=0.9, label=f"Overbought ({RSI_OVERBOUGHT})")
            ax_bot.axhline(RSI_OVERSOLD, color=THRESHOLD_COLOR_LOW, linewidth=1.15, linestyle="--", alpha=0.9, label=f"Oversold ({RSI_OVERSOLD})")
            ax_bot.axhline(50, color="#5D6D7E", linewidth=0.9, linestyle="-", alpha=0.55, label="Neutral (50)")
            ax_bot.set_ylabel("RSI", fontsize=10)
            ax_bot.set_ylim(0, 100)
            current_r = rseries.iloc[-1]
            ax_bot.annotate(
                f"Current: {current_r:.1f}",
                xy=(ratio_df.index[-1], current_r),
                xytext=(10, 8),
                textcoords="offset points",
                fontsize=8,
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.92, edgecolor="gray"),
                arrowprops=dict(arrowstyle="->", color="gray", lw=0.6),
            )
            ax_bot.legend(loc="upper left", fontsize=7.5, framealpha=0.88)
        if BOTTOM_GRID:
            ax_bot.grid(True, color=BOTTOM_GRID_COLOR, linewidth=BOTTOM_GRID_WIDTH, alpha=BOTTOM_GRID_ALPHA, linestyle=BOTTOM_GRID_STYLE)
        ax_bot.set_xlabel("Date", fontsize=10)
        ax_bot.xaxis.set_major_locator(mdates.AutoDateLocator())
        ax_bot.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        fig.autofmt_xdate(rotation=30, ha="right")
    else:
        ax_top.xaxis.set_major_locator(mdates.AutoDateLocator())
        ax_top.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        fig.autofmt_xdate(rotation=30, ha="right")

    plt.tight_layout()
    plt.show(block=BLOCK_WINDOW)


def main():
    print("=" * 72)
    print("COIN RATIO CHART  (offline mode - existing data only)")
    print("This script strictly uses pre-existing cryptocompare_data/ CSVs.")
    if ADD_BOTTOM_INDICATOR and BOTTOM_INDICATOR:
        print(f"Bottom panel enabled: {BOTTOM_INDICATOR.upper()}")
    print("=" * 72)
    try:
        prompt_user_for_pair()
        ratio_df = load_and_align_data()
        ratio_df = add_moving_averages(ratio_df)
        ratio_df = add_long_term_overlays(ratio_df)
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
