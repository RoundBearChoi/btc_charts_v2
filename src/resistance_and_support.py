#!/usr/bin/env python3
"""
resistance_and_support.py

Price + MA role sheet + RSI(14) for a coin from src/coins.csv:
  1. Price + EMA21 / SMA50 / SMA200 as *dynamic* support or resistance
     plus recent swing highs / lows as *static* levels
  2. Role sheet: MA value, support/resistance role, % distance from close
  3. RSI(14) with the same 70 / 50 / 30 treatment as 21_50_200_chart.py

Volume lives on the 21/50/200 and SMA-vs-SMA scripts, not here.

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
from indicators import add_ema, add_rsi, add_sma

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

RSI_WINDOW = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
SHOW_RSI_ZONES = True

FIGURE_SIZE = (14, 10.8)   # extra height reserved for the MA role sheet
SHOW_MA_FOOTER = True      # table under price: value / role / distance
SHOW_DISTANCE_ON_LABELS = True  # also append % distance to right-edge MA tags
HEIGHT_RATIOS = (3.4, 0.78, 1.05)  # price, role sheet, RSI
# Gaps are GridSpec row weights in the same units as HEIGHT_RATIOS.
# Matplotlib's single hspace cannot differ per pair of panes, so empty
# spacer rows are used instead.
SPACE_PRICE_TO_ROLES = 0.50    # wider gap under the price pane
SPACE_ROLES_TO_RSI = 0.10      # tighter gap above RSI

CLOSE_COLOR = "#1f77b4"
EMA_COLOR = "#E15FC3"
SMA50_COLOR = "#2ca02c"
SMA200_COLOR = "#C80C01"
SUPPORT_COLOR = "#2ca02c"
RESISTANCE_COLOR = "#d62728"
RSI_COLOR = "#FF9900"
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
    """Readable calendar dates on the 1st and 15th of each month."""
    if days_back is None or days_back > 900:
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_minor_locator(mdates.MonthLocator(bymonthday=[1, 15]))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    else:
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonthday=[1, 15]))
        ax.xaxis.set_minor_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(ticker.FuncFormatter(format_axis_date))
    ax.tick_params(axis="x", which="major", labelsize=8, rotation=30)
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


def format_rsi(value) -> str:
    if pd.isna(value):
        return "n/a"
    return f"{float(value):.1f}"


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

    return {
        "price": price,
        "label": label,
        "last_highs": last_highs,
        "last_lows": last_lows,
    }


def print_levels(df: pd.DataFrame, structure: dict, coin_name: str, coin_ticker: str):
    last = df.iloc[-1]
    price = float(last["close"])
    rsi = last["RSI"] if "RSI" in df.columns else float("nan")
    print("=" * 64)
    print(f"{coin_name} ({coin_ticker})  dynamic S/R + swing structure")
    print("=" * 64)
    print(f"Latest close:    {format_price(price)}   ({df.index[-1].date()})")
    print(f"Structure:       {structure['label']}")
    print(f"RSI({RSI_WINDOW}):        {format_rsi(rsi)}")
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
    print("MA rule: above the average = support, below = resistance.")
    print("Swing rule: confirmed pivot only after SWING_RIGHT extra bars.")
    print("Structure uses the last two confirmed highs and last two lows.")
    print("Distance to each MA is on the role sheet / right-edge labels.")
    print("=" * 64 + "\n")


def draw_ma_rolesheet(ax, df: pd.DataFrame, structure: dict):
    """Compact table under the price pane. Not a time-series plot."""
    ax.set_axis_off()
    last_date = df.index[-1].date()
    price = float(df.iloc[-1]["close"])
    rsi = df.iloc[-1]["RSI"] if "RSI" in df.columns else float("nan")
    rows = ma_snapshot_rows(df)

    ax.set_title(
        f"Close {format_price(price)}  ({last_date})   ·   {structure['label']}   ·   "
        f"RSI({RSI_WINDOW}) {format_rsi(rsi)}   ·   "
        "distance = (close − MA) / MA",
        fontsize=9,
        loc="left",
        pad=8,
        color="#333333",
    )

    cell_text = [
        [row["label"], format_price(row["value"]), row["role"], row["dist"]]
        for row in rows
    ]
    table = ax.table(
        cellText=cell_text,
        colLabels=["MA", "Value", "Role", "Distance"],
        loc="upper center",
        cellLoc="center",
        colLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1.0, 1.35)

    header_bg = "#263549"
    support_bg = "#e8f6e8"
    resist_bg = "#fdecea"
    na_bg = "#f4f4f4"

    for col in range(4):
        cell = table[0, col]
        cell.set_facecolor(header_bg)
        cell.set_text_props(color="white", weight="bold")
        cell.set_edgecolor("#ffffff")

    for i, row in enumerate(rows, start=1):
        if row["role"] == "support":
            role_bg = support_bg
            role_fg = SUPPORT_COLOR
        elif row["role"] == "resistance":
            role_bg = resist_bg
            role_fg = RESISTANCE_COLOR
        else:
            role_bg = na_bg
            role_fg = "#555555"

        table[i, 0].set_text_props(color=row["color"], weight="bold")
        table[i, 2].set_facecolor(role_bg)
        table[i, 2].set_text_props(color=role_fg, weight="bold")
        table[i, 3].set_facecolor(role_bg)
        table[i, 3].set_text_props(color=role_fg, weight="bold")
        for col in range(4):
            table[i, col].set_edgecolor("#dddddd")


def draw_rsi(ax, df: pd.DataFrame):
    """RSI pane styled like 21_50_200_chart.py."""
    if SHOW_RSI_ZONES:
        ax.axhspan(RSI_OVERBOUGHT, 100, color="#E15FC3", alpha=0.08, zorder=0)
        ax.axhspan(0, RSI_OVERSOLD, color="#00D118", alpha=0.08, zorder=0)
    ax.plot(
        df.index, df["RSI"], color=RSI_COLOR, linewidth=1.5,
        label=f"RSI({RSI_WINDOW})",
    )
    ax.axhline(RSI_OVERBOUGHT, color="#E15FC3", linestyle="--", alpha=0.6, label="Overbought")
    ax.axhline(RSI_OVERSOLD, color="#00D118", linestyle="--", alpha=0.6, label="Oversold")
    ax.axhline(50, color="gray", linestyle=":", alpha=0.5)
    ax.set_ylabel("RSI")
    ax.set_ylim(0, 100)
    ax.legend(loc="upper left", fontsize=8)
    if SHOW_GRID:
        ax.grid(True, alpha=0.3)


def draw_one_chart(
    coin_name: str,
    coin_ticker: str,
    *,
    days_back: int | None = DAYS_BACK,
    block_window: bool = BLOCK_WINDOW,
    close_after: bool = True,
):
    print(f"\nLoading {coin_name} ({coin_ticker}) price data...")
    df = price_data.get_price_data(coin=coin_ticker).copy()
    df = naive_index(df).sort_index()

    required = {"high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{coin_ticker} data is missing columns: {sorted(missing)}")

    # Indicators on full history so a short window still has SMA200 / seeded RSI.
    df = add_ema(df, EMA_FAST)
    df = add_sma(df, SMA_MID)
    df = add_sma(df, SMA_SLOW)
    df = add_rsi(df, window=RSI_WINDOW)
    df = add_swing_points(df, left=SWING_LEFT, right=SWING_RIGHT)

    if days_back:
        df = df.iloc[-days_back:]

    structure = structure_from_swings(df)
    print_levels(df, structure, coin_name, coin_ticker)

    ma_rows = ma_snapshot_rows(df)

    fig = plt.figure(figsize=FIGURE_SIZE)
    plt.style.use("fast")
    price_h, roles_h, rsi_h = HEIGHT_RATIOS
    if SHOW_MA_FOOTER:
        gs = fig.add_gridspec(
            5, 1,
            height_ratios=[
                price_h,
                SPACE_PRICE_TO_ROLES,
                roles_h,
                SPACE_ROLES_TO_RSI,
                rsi_h,
            ],
            hspace=0.0,
        )
        ax1 = fig.add_subplot(gs[0])
        ax_roles = fig.add_subplot(gs[2])
        ax_rsi = fig.add_subplot(gs[4], sharex=ax1)
    else:
        gs = fig.add_gridspec(
            3, 1,
            height_ratios=[price_h, SPACE_PRICE_TO_ROLES, rsi_h],
            hspace=0.0,
        )
        ax1 = fig.add_subplot(gs[0])
        ax_roles = None
        ax_rsi = fig.add_subplot(gs[2], sharex=ax1)

    ax1.plot(df.index, df["close"], color=CLOSE_COLOR, linewidth=1.25, label=f"{coin_name} Close")
    ax1.plot(df.index, df[f"EMA{EMA_FAST}"], color=EMA_COLOR, linewidth=1.2, label=f"EMA{EMA_FAST}")
    ax1.plot(df.index, df[f"SMA{SMA_MID}"], color=SMA50_COLOR, linewidth=1.2, label=f"SMA{SMA_MID}")
    ax1.plot(df.index, df[f"SMA{SMA_SLOW}"], color=SMA200_COLOR, linewidth=1.4, linestyle="--", label=f"SMA{SMA_SLOW}")
    if LOG_SCALE:
        ax1.set_yscale("log")

    sh = df[df["swing_high"]]
    sl = df[df["swing_low"]]
    ax1.scatter(sh.index, sh["high"], color=RESISTANCE_COLOR, s=18, zorder=5, label="Swing high")
    ax1.scatter(sl.index, sl["low"], color=SUPPORT_COLOR, s=18, zorder=5, label="Swing low")

    if structure["last_highs"]:
        ax1.axhline(structure["last_highs"][-1]["price"], color=RESISTANCE_COLOR, linestyle=":", linewidth=1.2, alpha=0.9)
    if structure["last_lows"]:
        ax1.axhline(structure["last_lows"][-1]["price"], color=SUPPORT_COLOR, linestyle=":", linewidth=1.2, alpha=0.9)

    if len(df) > SWING_RIGHT:
        unconfirmed_from = df.index[-SWING_RIGHT]
        ax1.axvspan(unconfirmed_from, df.index[-1], color="#888888", alpha=UNCONFIRMED_ALPHA)
        ax_rsi.axvspan(unconfirmed_from, df.index[-1], color="#888888", alpha=UNCONFIRMED_ALPHA)

    x_last = df.index[-1]
    for row in ma_rows:
        if pd.isna(row["value"]):
            continue
        tag = "S" if row["role"] == "support" else "R"
        label = f"{row['label']} {tag} {format_price(float(row['value']))}"
        if SHOW_DISTANCE_ON_LABELS and row["dist"] != "n/a":
            label += f"  {row['dist']}"
        ax1.annotate(label, xy=(x_last, row["value"]), xytext=(8, 0), textcoords="offset points", color=row["color"], fontsize=8, va="center")

    title = f"{coin_name} • S/R + swings + RSI({RSI_WINDOW}) • {structure['label']}"
    if days_back:
        title += f" — last {days_back} days"
    if LOG_SCALE:
        title += " (LOG)"
    ax1.set_title(title, fontsize=13, pad=12)
    ax1.set_ylabel("Price (USD)")
    ax1.yaxis.set_major_formatter(ticker.FuncFormatter(price_axis_formatter))
    ax1.legend(loc="upper left", fontsize=8, ncol=2, framealpha=0.92)
    if SHOW_GRID:
        ax1.grid(True, alpha=0.3)
    add_window_date_formatters(ax1, days_back)
    ax1.tick_params(axis="x", labelbottom=True)

    if ax_roles is not None:
        draw_ma_rolesheet(ax_roles, df, structure)

    draw_rsi(ax_rsi, df)
    add_window_date_formatters(ax_rsi, days_back)
    plt.setp(ax_rsi.get_xticklabels(), visible=False)
    ax_rsi.tick_params(axis="x", labelbottom=False)

    fig.subplots_adjust(left=0.07, right=0.96, top=0.93, bottom=0.06)

    if not _backend_is_interactive():
        safe = coin_ticker.lower().replace(" ", "_")
        out = f"{safe}_resistance_and_support.png"
        plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
        print(f"Chart saved to: {out}")
        plt.close(fig)
        return

    print(f"Using interactive backend: {matplotlib.get_backend()}")
    plt.show(block=block_window)
    if close_after and block_window:
        plt.close(fig)


def draw(days_back: int | None = DAYS_BACK, block_window: bool = BLOCK_WINDOW):
    choices = get_coin_choice("Resistance / Support + RSI - Coin Selection")
    total = len(choices)
    for i, (coin_name, coin_ticker) in enumerate(choices, start=1):
        is_last = i == total
        if total > 1:
            print(f"\n[{i}/{total}] {coin_name}")
        per_coin_block = block_window if total == 1 else True
        draw_one_chart(coin_name, coin_ticker, days_back=days_back, block_window=per_coin_block, close_after=True)
        if is_last and total > 1:
            print(f"\nDone. Stopped after last coin ({coin_name}).")


if __name__ == "__main__":
    draw()
