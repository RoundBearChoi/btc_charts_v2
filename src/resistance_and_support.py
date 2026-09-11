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

FIGURE_SIZE = (14, 10)     # extra height reserved for the MA footer
SHOW_MA_FOOTER = True      # table under volume: value / role / distance
SHOW_DISTANCE_ON_LABELS = True  # also append % distance to right-edge MA tags

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


def add_window_date_formatters(ax, days_back: int | None):
    """Year ticks are too sparse on a 1-year window."""
    if days_back is None or days_back > 900:
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_minor_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    elif days_back > 240:
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        ax.xaxis.set_minor_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    else:
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        ax.xaxis.set_minor_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.tick_params(axis="x", which="major", labelsize=9)


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
        pad=2,
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

    required = {"open", "high", "low", "close", "volumeto"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{coin_ticker} data is missing columns: {sorted(missing)}")

    # Indicators and swings on full history so a short window still has SMA200
    # and pivots that were confirmed before the visible start date.
    df = add_ema(df, EMA_FAST)
    df = add_sma(df, SMA_MID)
    df = add_sma(df, SMA_SLOW)
    df = add_swing_points(df, left=SWING_LEFT, right=SWING_RIGHT)
    df["vol_sma"] = df["volumeto"].rolling(window=VOLUME_SMA_DAYS).mean()
    df["up_day"] = df["close"] >= df["open"]

    if days_back:
        df = df.iloc[-days_back:]

    structure = structure_from_swings(df)
    print_levels(df, structure, coin_name, coin_ticker)

    last = df.iloc[-1]
    price = float(last["close"])
    ma_rows = ma_snapshot_rows(df)

    if SHOW_MA_FOOTER:
        fig = plt.figure(figsize=FIGURE_SIZE)
        gs = fig.add_gridspec(3, 1, height_ratios=[3.2, 1.0, 0.72], hspace=0.14)
        ax1 = fig.add_subplot(gs[0])
        ax2 = fig.add_subplot(gs[1], sharex=ax1)
        ax3 = fig.add_subplot(gs[2])
        plt.setp(ax1.get_xticklabels(), visible=False)
    else:
        fig, (ax1, ax2) = plt.subplots(
            2, 1,
            figsize=FIGURE_SIZE,
            gridspec_kw={"height_ratios": [3.2, 1]},
            sharex=True,
        )
        ax3 = None
    plt.style.use("fast")

    ax1.plot(df.index, df["close"], color=CLOSE_COLOR, linewidth=1.25, label=f"{coin_name} Close")
    ax1.plot(df.index, df[f"EMA{EMA_FAST}"], color=EMA_COLOR, linewidth=1.2, label=f"EMA{EMA_FAST}")
    ax1.plot(df.index, df[f"SMA{SMA_MID}"], color=SMA50_COLOR, linewidth=1.2, label=f"SMA{SMA_MID}")
    ax1.plot(
        df.index, df[f"SMA{SMA_SLOW}"],
        color=SMA200_COLOR, linewidth=1.4, linestyle="--", label=f"SMA{SMA_SLOW}",
    )
    if LOG_SCALE:
        ax1.set_yscale("log")

    sh = df[df["swing_high"]]
    sl = df[df["swing_low"]]
    ax1.scatter(sh.index, sh["high"], color=RESISTANCE_COLOR, s=18, zorder=5, label="Swing high")
    ax1.scatter(sl.index, sl["low"], color=SUPPORT_COLOR, s=18, zorder=5, label="Swing low")

    # Prior swing vs latest swing: shows whether the floor/ceiling moved
    if len(structure["last_highs"]) == 2:
        prev_h = structure["last_highs"][0]["price"]
    ax1.axhline(prev_h, color=RESISTANCE_COLOR, linestyle=":", linewidth=0.9, alpha=0.35)
    if structure["nearest_resistance"]:
        ax1.axhline(
            structure["nearest_resistance"]["price"],
            color=RESISTANCE_COLOR, linestyle=":", linewidth=1.2, alpha=0.9,
            label=f"Swing R {format_price(structure['nearest_resistance']['price'])}",
        )
    if len(structure["last_lows"]) == 2:
        prev_l = structure["last_lows"][0]["price"]
        ax1.axhline(prev_l, color=SUPPORT_COLOR, linestyle=":", linewidth=0.9, alpha=0.35)
    if structure["nearest_support"]:
        ax1.axhline(
            structure["nearest_support"]["price"],
            color=SUPPORT_COLOR, linestyle=":", linewidth=1.2, alpha=0.9,
            label=f"Swing S {format_price(structure['nearest_support']['price'])}",
        )

    if len(df) > SWING_RIGHT:
        unconfirmed_from = df.index[-SWING_RIGHT]
        ax1.axvspan(unconfirmed_from, df.index[-1], color="#888888", alpha=UNCONFIRMED_ALPHA)
        ax2.axvspan(unconfirmed_from, df.index[-1], color="#888888", alpha=UNCONFIRMED_ALPHA)

    x_last = df.index[-1]
    for row in ma_rows:
        if pd.isna(row["value"]):
            continue
        tag = "S" if row["role"] == "support" else "R"
        label = f"{row['label']} {tag} {format_price(float(row['value']))}"
        if SHOW_DISTANCE_ON_LABELS and row["dist"] != "n/a":
            label += f"  {row['dist']}"
        ax1.annotate(
            label,
            xy=(x_last, row["value"]),
            xytext=(8, 0),
            textcoords="offset points",
            color=row["color"],
            fontsize=8,
            va="center",
        )

    title = f"{coin_name} • S/R + swings • {structure['label']}"
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

    vol_colors = ["#2ca02c" if up else "#d62728" for up in df["up_day"]]
    ax2.bar(df.index, df["volumeto"], color=vol_colors, width=0.9, alpha=0.75, label="Volume")
    ax2.plot(
        df.index, df["vol_sma"],
        color="#263549", linewidth=1.4, label=f"{VOLUME_SMA_DAYS}d vol SMA",
    )
    ax2.set_ylabel("Volume (USD)")
    ax2.set_xlabel("Date")
    ax2.yaxis.set_major_formatter(
        ticker.FuncFormatter(
            lambda x, _p: f"${x/1e9:.1f}B" if x >= 1e9 else f"${x/1e6:.0f}M" if x >= 1e6 else f"${x:,.0f}"
        )
    )
    ax2.legend(loc="upper left", fontsize=8)
    if SHOW_GRID:
        ax2.grid(True, alpha=0.3)
    add_window_date_formatters(ax2, days_back)

    if ax3 is not None:
        draw_ma_footer(ax3, df, structure)

    fig.tight_layout()

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
    choices = get_coin_choice("Resistance / Support + Volume - Coin Selection")
    total = len(choices)

    for i, (coin_name, coin_ticker) in enumerate(choices, start=1):
        is_last = i == total
        if total > 1:
            print(f"\n[{i}/{total}] {coin_name}")

        per_coin_block = block_window if total == 1 else True
        draw_one_chart(
            coin_name,
            coin_ticker,
            days_back=days_back,
            block_window=per_coin_block,
            close_after=True,
        )
        if is_last and total > 1:
            print(f"\nDone. Stopped after last coin ({coin_name}).")


if __name__ == "__main__":
    draw()
