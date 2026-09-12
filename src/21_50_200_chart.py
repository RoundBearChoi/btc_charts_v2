import argparse
import matplotlib

# Force an interactive backend as early as possible (must be before pyplot)
try:
    matplotlib.use("TkAgg")
except Exception:
    pass  # fall back to whatever is available (usually Agg on pure headless)

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import pandas as pd

import get_price_data_cryptocompare as price_data
from coin_menu import coins_as_pairs, get_coin_choice, resolve_coin_arg
from indicators import add_ema, add_rsi, add_sma, last_crossover
from plotting_utils import (
    add_window_date_formatters,
    apply_grid,
    create_price_volume_rsi_figure,
    format_price,
    price_axis_formatter,
    volume_axis_formatter,
)

# ==================================================
# CONFIGURATION - Edit these values as needed
# ==================================================
LOG_SCALE = False
DAYS_BACK = 360 * 2          # Set None for full history
BLOCK_WINDOW = True          # False = script continues immediately
SHOW_GRID = True

# Moving-average periods (filename stays 21_50_200_chart.py)
EMA_FAST = 21
SMA_MID = 50
SMA_SLOW = 200

# Grid line styling (applies identically to all 3 charts)
GRID_COLOR = "gray"          # e.g. 'gray', '#666666', 'black', '#444444'
GRID_LINEWIDTH = 1.0
GRID_ALPHA = 0.7
GRID_LINESTYLE = ":"         # e.g. '-', '--', '-.', ':', 'None'

FIGURE_SIZE = (14, 10)

# RSI Configuration
RSI_WINDOW = 14              # Change this to any value you want (e.g. 21, 28, 50)
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

# Overlay toggles
SHOW_TREND_CLOUD = True      # fill between EMA_FAST and SMA_MID
SHOW_CROSSES = True          # mark 50/200 and 21/50 crosses
COLOR_VOLUME_BY_DIRECTION = True
SHOW_LAST_LABELS = True
SHOW_RSI_ZONES = True

# Line styles
CLOSE_COLOR = "#9EB3DB"
CLOSE_WIDTH = 0.9
EMA21_COLOR = "#E15FC3"
SMA50_COLOR = "#00D118"
SMA200_COLOR = "#C80C01"
VOLUME_COLOR = "#8F8C57"
VOLUME_UP_COLOR = "#2ca02c"
VOLUME_DOWN_COLOR = "#d62728"
VOLUME_SMA_DAYS = 15
VOLUME_SMA_COLOR = "#263549"
CLOUD_UP_COLOR = "#00D118"
CLOUD_DOWN_COLOR = "#C80C01"
GOLDEN_CROSS_COLOR = "#00D118"
DEATH_CROSS_COLOR = "#C80C01"

# Headless PNG output (repo-root/output when run from repo root)
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"

# ==================================================
# END OF CONFIGURATION
# ==================================================


def _backend_is_interactive() -> bool:
    backend = matplotlib.get_backend().lower()
    # Note: 'TkAgg' contains the substring 'agg', so we must NOT use 'agg' in backend
    non_interactive = {"agg", "svg", "pdf", "ps", "cairo", "template"}
    return backend not in non_interactive


def _pct_from(price: float, level: float) -> str:
    if pd.isna(level) or level == 0:
        return "n/a"
    return f"{(price - level) / level * 100:+.1f}%"


def _regime_label(price: float, ema_fast: float, sma_mid: float, sma_slow: float) -> str:
    if any(pd.isna(v) for v in (price, ema_fast, sma_mid, sma_slow)):
        return "n/a"
    above_slow = price >= sma_slow
    fast_above_mid = ema_fast >= sma_mid
    if above_slow and fast_above_mid:
        return f"risk-on (above {SMA_SLOW} · {EMA_FAST}>{SMA_MID})"
    if above_slow:
        return f"above {SMA_SLOW} · {EMA_FAST}<{SMA_MID}"
    if fast_above_mid:
        return f"below {SMA_SLOW} · {EMA_FAST}>{SMA_MID}"
    return f"defensive (below {SMA_SLOW} · {EMA_FAST}<{SMA_MID})"


def _format_cross(ts, direction: str | None) -> str:
    if ts is None or direction is None:
        return "none in view"
    when = ts.date() if hasattr(ts, "date") else ts
    return f"{when} {direction}"


def print_snapshot(df: pd.DataFrame, coin_name: str, coin_ticker: str, rsi_window: int) -> None:
    last = df.iloc[-1]
    price = float(last["close"])
    ema_col = f"EMA{EMA_FAST}"
    mid_col = f"SMA{SMA_MID}"
    slow_col = f"SMA{SMA_SLOW}"
    ema = float(last[ema_col]) if pd.notna(last[ema_col]) else float("nan")
    mid = float(last[mid_col]) if pd.notna(last[mid_col]) else float("nan")
    slow = float(last[slow_col]) if pd.notna(last[slow_col]) else float("nan")
    rsi = float(last["RSI"]) if pd.notna(last["RSI"]) else float("nan")

    cross_fast = last_crossover(df[ema_col], df[mid_col])
    cross_slow = last_crossover(df[mid_col], df[slow_col])
    regime = _regime_label(price, ema, mid, slow)

    print("=" * 64)
    print(f"{coin_name} ({coin_ticker})  {EMA_FAST}/{SMA_MID}/{SMA_SLOW} snapshot")
    print("=" * 64)
    print(f"Latest close:    {format_price(price)}   ({df.index[-1].date()})")
    print(f"Regime:          {regime}")
    print()
    print(f"{'MA':<10}{'Value':>14}{'vs close':>12}")
    print("-" * 36)
    print(f"{'EMA' + str(EMA_FAST):<10}{format_price(ema):>14}{_pct_from(price, ema):>12}")
    print(f"{'SMA' + str(SMA_MID):<10}{format_price(mid):>14}{_pct_from(price, mid):>12}")
    print(f"{'SMA' + str(SMA_SLOW):<10}{format_price(slow):>14}{_pct_from(price, slow):>12}")
    print()
    rsi_txt = f"{rsi:.1f}" if pd.notna(rsi) else "n/a"
    print(f"RSI({rsi_window}):       {rsi_txt}")
    print(f"Last {EMA_FAST}/{SMA_MID} cross:  {_format_cross(*cross_fast)}")
    print(f"Last {SMA_MID}/{SMA_SLOW} cross: {_format_cross(*cross_slow)}")
    print("=" * 64 + "\n")


def _mark_crosses(ax, df: pd.DataFrame, fast_col: str, slow_col: str, *, size: int, label_prefix: str):
    prev_fast = df[fast_col].shift(1)
    prev_slow = df[slow_col].shift(1)
    golden = (df[fast_col] > df[slow_col]) & (prev_fast <= prev_slow)
    death = (df[fast_col] < df[slow_col]) & (prev_fast >= prev_slow)
    g = df.loc[golden]
    d = df.loc[death]
    if not g.empty:
        ax.scatter(
            g.index, g[fast_col],
            color=GOLDEN_CROSS_COLOR, s=size, marker="^", zorder=6,
            label=f"{label_prefix} golden",
        )
    if not d.empty:
        ax.scatter(
            d.index, d[fast_col],
            color=DEATH_CROSS_COLOR, s=size, marker="v", zorder=6,
            label=f"{label_prefix} death",
        )


def draw_one_chart(
    coin_name: str,
    coin_ticker: str,
    *,
    block_window=BLOCK_WINDOW,
    log_scale=LOG_SCALE,
    days_back=DAYS_BACK,
    rsi_window=RSI_WINDOW,
    close_after=True,
):
    print(f"\n\U0001F4CA Loading data for {coin_name} ({coin_ticker})...")
    data_frame = price_data.get_price_data(coin=coin_ticker).copy()
    data_frame = data_frame.sort_index()

    ema_col = f"EMA{EMA_FAST}"
    mid_col = f"SMA{SMA_MID}"
    slow_col = f"SMA{SMA_SLOW}"

    # Indicators on full history so a short window still has SMA200 / seeded RSI.
    data_frame = add_ema(data_frame, EMA_FAST, out_col=ema_col)
    data_frame = add_sma(data_frame, SMA_MID, out_col=mid_col)
    data_frame = add_sma(data_frame, SMA_SLOW, out_col=slow_col)
    if VOLUME_SMA_DAYS > 0 and "volumeto" in data_frame.columns:
        data_frame["VOLUME_SMA"] = data_frame["volumeto"].rolling(window=VOLUME_SMA_DAYS).mean()
    data_frame = add_rsi(data_frame, window=rsi_window)

    if days_back is not None:
        data_frame = data_frame.iloc[-days_back:]

    print_snapshot(data_frame, coin_name, coin_ticker, rsi_window)

    fig, (ax1, ax2, ax3) = create_price_volume_rsi_figure(figsize=FIGURE_SIZE)

    if SHOW_TREND_CLOUD:
        ax1.fill_between(
            data_frame.index,
            data_frame[ema_col],
            data_frame[mid_col],
            where=data_frame[ema_col] >= data_frame[mid_col],
            color=CLOUD_UP_COLOR,
            alpha=0.12,
            interpolate=True,
            zorder=0,
        )
        ax1.fill_between(
            data_frame.index,
            data_frame[ema_col],
            data_frame[mid_col],
            where=data_frame[ema_col] < data_frame[mid_col],
            color=CLOUD_DOWN_COLOR,
            alpha=0.12,
            interpolate=True,
            zorder=0,
        )

    ax1.plot(
        data_frame.index, data_frame["close"],
        label=f"{coin_name} Close",
        linewidth=CLOSE_WIDTH, color=CLOSE_COLOR, zorder=3,
    )
    ax1.plot(
        data_frame.index, data_frame[ema_col],
        label=f"{EMA_FAST} EMA", color=EMA21_COLOR, linewidth=1.3, zorder=4,
    )
    ax1.plot(
        data_frame.index, data_frame[mid_col],
        label=f"{SMA_MID} SMA", color=SMA50_COLOR, linewidth=1.3, zorder=4,
    )
    ax1.plot(
        data_frame.index, data_frame[slow_col],
        label=f"{SMA_SLOW} SMA (Long-term)",
        color=SMA200_COLOR, linewidth=1.6, linestyle="--", zorder=4,
    )

    if SHOW_CROSSES:
        _mark_crosses(ax1, data_frame, mid_col, slow_col, size=36, label_prefix=f"{SMA_MID}/{SMA_SLOW}")
        _mark_crosses(ax1, data_frame, ema_col, mid_col, size=18, label_prefix=f"{EMA_FAST}/{SMA_MID}")

    last = data_frame.iloc[-1]
    price = float(last["close"])
    ema = float(last[ema_col]) if pd.notna(last[ema_col]) else float("nan")
    mid = float(last[mid_col]) if pd.notna(last[mid_col]) else float("nan")
    slow = float(last[slow_col]) if pd.notna(last[slow_col]) else float("nan")
    regime = _regime_label(price, ema, mid, slow)

    title = (
        f"{coin_name} • {EMA_FAST} EMA vs {SMA_MID} SMA + {SMA_SLOW} SMA "
        f"+ Volume + RSI({rsi_window})"
    )
    if log_scale:
        ax1.set_yscale("log")
        title += " (LOG)"
    if days_back:
        title += f" — Last {days_back} days"
    title += f"\n{regime}"

    ax1.set_title(title, fontsize=13, pad=16)
    ax1.set_ylabel("Price (USD)")
    ax1.legend(loc="upper left", fontsize=8, ncol=2, framealpha=0.92)
    apply_grid(
        ax1,
        enabled=SHOW_GRID,
        color=GRID_COLOR,
        linewidth=GRID_LINEWIDTH,
        alpha=GRID_ALPHA,
        linestyle=GRID_LINESTYLE,
    )
    ax1.yaxis.set_major_formatter(ticker.FuncFormatter(price_axis_formatter))

    if SHOW_LAST_LABELS:
        rsi_val = float(last["RSI"]) if pd.notna(last["RSI"]) else float("nan")
        rsi_line = f"RSI({rsi_window}) {rsi_val:.1f}" if pd.notna(rsi_val) else f"RSI({rsi_window}) n/a"
        box = (
            f"Close  {format_price(price)}\n"
            f"EMA{EMA_FAST}  {format_price(ema)}  ({_pct_from(price, ema)})\n"
            f"SMA{SMA_MID}  {format_price(mid)}  ({_pct_from(price, mid)})\n"
            f"SMA{SMA_SLOW} {format_price(slow)}  ({_pct_from(price, slow)})\n"
            f"{rsi_line}"
        )
        ax1.text(
            0.99, 0.02, box,
            transform=ax1.transAxes,
            ha="right", va="bottom",
            fontsize=8, family="monospace",
            bbox=dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor="#cccccc", alpha=0.9),
        )

    # Volume
    if COLOR_VOLUME_BY_DIRECTION and "open" in data_frame.columns:
        vol_colors = [
            VOLUME_UP_COLOR if up else VOLUME_DOWN_COLOR
            for up in data_frame["close"] >= data_frame["open"]
        ]
    elif COLOR_VOLUME_BY_DIRECTION:
        vol_colors = [
            VOLUME_UP_COLOR if up else VOLUME_DOWN_COLOR
            for up in data_frame["close"] >= data_frame["close"].shift(1)
        ]
    else:
        vol_colors = VOLUME_COLOR
    ax2.bar(data_frame.index, data_frame["volumeto"], color=vol_colors, alpha=0.75, width=0.9)
    if "VOLUME_SMA" in data_frame.columns:
        ax2.plot(
            data_frame.index, data_frame["VOLUME_SMA"],
            color=VOLUME_SMA_COLOR, linewidth=1.5, label=f"{VOLUME_SMA_DAYS}d Vol SMA",
        )
    ax2.set_ylabel("Volume (USD)")
    ax2.legend(loc="upper left")
    apply_grid(
        ax2,
        enabled=SHOW_GRID,
        color=GRID_COLOR,
        linewidth=GRID_LINEWIDTH,
        alpha=GRID_ALPHA,
        linestyle=GRID_LINESTYLE,
    )
    ax2.yaxis.set_major_formatter(ticker.FuncFormatter(volume_axis_formatter))

    # RSI
    if SHOW_RSI_ZONES:
        ax3.axhspan(RSI_OVERBOUGHT, 100, color="#E15FC3", alpha=0.08, zorder=0)
        ax3.axhspan(0, RSI_OVERSOLD, color="#00D118", alpha=0.08, zorder=0)
    ax3.plot(
        data_frame.index, data_frame["RSI"], color="#FF9900", linewidth=1.5,
        label=f"RSI({rsi_window})",
    )
    ax3.axhline(RSI_OVERBOUGHT, color="#E15FC3", linestyle="--", alpha=0.6, label="Overbought")
    ax3.axhline(RSI_OVERSOLD, color="#00D118", linestyle="--", alpha=0.6, label="Oversold")
    ax3.axhline(50, color="gray", linestyle=":", alpha=0.5)
    ax3.set_ylabel("RSI")
    ax3.set_ylim(0, 100)
    ax3.legend(loc="upper left")
    apply_grid(
        ax3,
        enabled=SHOW_GRID,
        color=GRID_COLOR,
        linewidth=GRID_LINEWIDTH,
        alpha=GRID_ALPHA,
        linestyle=GRID_LINESTYLE,
    )
    add_window_date_formatters(ax3, days_back)

    plt.xlabel("Date")
    plt.tight_layout()

    print(f"Drawing {coin_name} chart with RSI({rsi_window})...")

    if not _backend_is_interactive():
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = coin_ticker.lower().replace(" ", "_")
        output_file = OUTPUT_DIR / f"{safe_name}_21_50_200_rsi{rsi_window}.png"
        plt.savefig(output_file, dpi=150, bbox_inches="tight", facecolor="white")
        print(f"✅ Chart saved to: {output_file}")
        plt.close(fig)
        return

    print(f"🖥️  Using interactive backend: {matplotlib.get_backend()}")
    plt.show(block=block_window)
    if close_after and block_window:
        plt.close(fig)


def draw(
    block_window=BLOCK_WINDOW,
    log_scale=LOG_SCALE,
    days_back=DAYS_BACK,
    rsi_window=RSI_WINDOW,
    choices: list[tuple[str, str]] | None = None,
):
    if choices is None:
        choices = get_coin_choice("21/50/200 + Volume + RSI Chart - Coin Selection")
    total = len(choices)

    for i, (coin_name, coin_ticker) in enumerate(choices, start=1):
        is_last = i == total
        if total > 1:
            print(f"\n[{i}/{total}] {coin_name}")

        per_coin_block = block_window if total == 1 else True
        try:
            draw_one_chart(
                coin_name,
                coin_ticker,
                block_window=per_coin_block,
                log_scale=log_scale,
                days_back=days_back,
                rsi_window=rsi_window,
                close_after=True,
            )
        except Exception as exc:
            print(f"✘ {coin_name} ({coin_ticker}) failed: {exc}")
            if is_last and total > 1:
                print(f"\nDone. Stopped after last coin ({coin_name}).")
            continue
        if is_last and total > 1:
            print(f"\nDone. Stopped after last coin ({coin_name}).")


def _parse_args():
    parser = argparse.ArgumentParser(
        description="EMA/SMA stack + volume + RSI chart (default 21/50/200).",
    )
    parser.add_argument("--log", action="store_true", help="Use a log price axis.")
    parser.add_argument(
        "--days", type=int, default=None,
        help="Visible history in days. Omit to use DAYS_BACK from CONFIG.",
    )
    parser.add_argument(
        "--rsi", type=int, default=None,
        help="RSI window. Omit to use RSI_WINDOW from CONFIG.",
    )
    parser.add_argument(
        "--coin", type=str, default=None,
        help="Ticker, display name, or 1-based coins.csv index. Skips the prompt.",
    )
    parser.add_argument(
        "--all", action="store_true", dest="all_coins",
        help="Chart every coin in coins.csv, in file order. Skips the prompt.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    choices = None
    if args.all_coins:
        choices = coins_as_pairs()
        labels = ", ".join(name for name, _ in choices)
        print(f"→ ALL ({labels})")
    elif args.coin:
        name, symbol = resolve_coin_arg(args.coin)
        print(f"→ {name} ({symbol})")
        choices = [(name, symbol)]

    draw(
        log_scale=True if args.log else LOG_SCALE,
        days_back=args.days if args.days is not None else DAYS_BACK,
        rsi_window=args.rsi if args.rsi is not None else RSI_WINDOW,
        choices=choices,
    )
