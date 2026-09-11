#!/usr/bin/env python3
"""
resistance_and_support_btc.py

Two-panel chart for a coin from src/coins.csv:
  1. Price + EMA21 / SMA50 / SMA200 as *dynamic* support or resistance
     plus the latest swing high / swing low as *static* levels
  2. Volume (up-day / down-day bars) + volume SMA

Rule used for moving averages:
  price above the MA  -> that MA is treated as support
  price below the MA  -> that MA is treated as resistance

Swing levels are calculated, not eyeballed:
  a bar is a swing high if its high is the max of `SWING_LEFT` bars before
  and `SWING_RIGHT` bars after. Same idea inverted for swing lows.
  The most recent swing high above price is marked resistance.
  The most recent swing low below price is marked support.

Startup prompt matches 21_50_200_chart.py: 1..N from coins.csv, plus ALL.

Run from repo root:
    python src/resistance_and_support_btc.py
"""

from __future__ import annotations

import matplotlib

try:
    matplotlib.use("TkAgg")
except Exception:
    pass

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import pandas as pd

import get_price_data_cryptocompare as price_data
from indicators import add_ema, add_sma
from plotting_utils import add_date_formatters

# ====================== CONFIG ======================
DAYS_BACK = 360            # chart window; None = full history
BLOCK_WINDOW = True

EMA_FAST = 21
SMA_MID = 50
SMA_SLOW = 200

SWING_LEFT = 8             # bars on each side to confirm a pivot
SWING_RIGHT = 8

VOLUME_SMA_DAYS = 20

FIGURE_SIZE = (14, 9)
CLOSE_COLOR = "#1f77b4"
EMA_COLOR = "#E15FC3"
SMA50_COLOR = "#2ca02c"
SMA200_COLOR = "#C80C01"
SUPPORT_COLOR = "#2ca02c"
RESISTANCE_COLOR = "#d62728"

COINS_CSV = Path(__file__).with_name("coins.csv")
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


def load_coins(csv_path: Path = COINS_CSV) -> pd.DataFrame:
    """Load the coin list. Row order is menu order."""
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


def get_coin_choice() -> list[tuple[str, str]]:
    """Prompt 1..N from coins.csv, plus ALL as the last option.

    ALL means every coin listed above it, in that same order.
    Returns a list of (name, symbol) pairs.
    """
    coins = load_coins()
    n = len(coins)
    all_idx = n + 1

    print("\n" + "=" * 60)
    print("Resistance / Support + Volume - Coin Selection")
    print("=" * 60)
    for i, row in coins.iterrows():
        print(f"{i + 1}) {row['name']}")
    print(f"{all_idx}) ALL")
    print("=" * 60)

    while True:
        raw = input(f"\nEnter 1-{all_idx} (or ALL): ").strip()
        if raw.lower() == "all" or (raw.isdigit() and int(raw) == all_idx):
            chosen = [(row["name"], row["symbol"]) for _, row in coins.iterrows()]
            labels = ", ".join(name for name, _ in chosen)
            print(f"→ ALL ({labels})")
            return chosen
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= n:
                row = coins.iloc[idx - 1]
                name, symbol = row["name"], row["symbol"]
                print(f"→ {name} ({symbol})")
                return [(name, symbol)]
        print(f"✘ Invalid. Enter a number from 1 to {all_idx}, or ALL.")


def add_swing_points(df: pd.DataFrame, left: int = 8, right: int = 8) -> pd.DataFrame:
    """Mark confirmed swing highs / lows. Right window means the newest
    `right` bars cannot be confirmed yet (they still need future bars)."""
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


def latest_static_levels(df: pd.DataFrame) -> dict:
    """Most recent confirmed swing high above price, swing low below price."""
    last = df.iloc[-1]
    price = float(last["close"])
    highs = df[df["swing_high"]]
    lows = df[df["swing_low"]]

    res = highs[highs["high"] > price]
    sup = lows[lows["low"] < price]

    resistance = None
    support = None
    if not res.empty:
        row = res.iloc[-1]
        resistance = {"date": row.name, "price": float(row["high"])}
    if not sup.empty:
        row = sup.iloc[-1]
        support = {"date": row.name, "price": float(row["low"])}
    return {"price": price, "resistance": resistance, "support": support}


def print_levels(df: pd.DataFrame, swings: dict, coin_name: str, coin_ticker: str):
    last = df.iloc[-1]
    price = float(last["close"])
    print("=" * 64)
    print(f"{coin_name} ({coin_ticker})  dynamic S/R + latest swing levels")
    print("=" * 64)
    print(f"Latest close:    {format_price(price)}   ({df.index[-1].date()})")
    print()
    print(f"{'MA':<10}{'Value':>14}{'Role':>14}{'Distance':>12}")
    print("-" * 50)
    for label, col in (
        (f"EMA{EMA_FAST}", f"EMA{EMA_FAST}"),
        (f"SMA{SMA_MID}", f"SMA{SMA_MID}"),
        (f"SMA{SMA_SLOW}", f"SMA{SMA_SLOW}"),
    ):
        value = float(last[col]) if pd.notna(last[col]) else float("nan")
        role = classify_ma(price, value)
        dist = "n/a" if pd.isna(value) else f"{(price - value) / value * 100:+.1f}%"
        print(f"{label:<10}{format_price(value):>14}{role:>14}{dist:>12}")

    print()
    if swings["resistance"]:
        r = swings["resistance"]
        print(
            f"Latest swing resistance: {format_price(r['price'])}  "
            f"({r['date'].date()})   "
            f"{((price - r['price']) / r['price'] * 100):+.1f}% vs price"
        )
    else:
        print("Latest swing resistance: none above current price in this window")

    if swings["support"]:
        s = swings["support"]
        print(
            f"Latest swing support:    {format_price(s['price'])}  "
            f"({s['date'].date()})   "
            f"{((price - s['price']) / s['price'] * 100):+.1f}% vs price"
        )
    else:
        print("Latest swing support: none below current price in this window")
    print()
    print("MA rule: above the average = support, below = resistance.")
    print("Swing rule: last confirmed pivot high/low, not an eyeballed round number.")
    print("=" * 64 + "\n")


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
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df = df.sort_index()

    required = {"open", "high", "low", "close", "volumeto"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{coin_ticker} data is missing columns: {sorted(missing)}")

    if days_back:
        df = df.iloc[-days_back:]

    df = add_ema(df, EMA_FAST)
    df = add_sma(df, SMA_MID)
    df = add_sma(df, SMA_SLOW)
    df = add_swing_points(df, left=SWING_LEFT, right=SWING_RIGHT)
    df["vol_sma"] = df["volumeto"].rolling(window=VOLUME_SMA_DAYS).mean()
    df["up_day"] = df["close"] >= df["open"]

    swings = latest_static_levels(df)
    print_levels(df, swings, coin_name, coin_ticker)

    last = df.iloc[-1]
    price = float(last["close"])

    fig, (ax1, ax2) = plt.subplots(
        2, 1,
        figsize=FIGURE_SIZE,
        gridspec_kw={"height_ratios": [3.2, 1]},
        sharex=True,
    )
    plt.style.use("fast")

    ax1.plot(df.index, df["close"], color=CLOSE_COLOR, linewidth=1.25, label=f"{coin_name} Close")
    ax1.plot(df.index, df[f"EMA{EMA_FAST}"], color=EMA_COLOR, linewidth=1.2, label=f"EMA{EMA_FAST}")
    ax1.plot(df.index, df[f"SMA{SMA_MID}"], color=SMA50_COLOR, linewidth=1.2, label=f"SMA{SMA_MID}")
    ax1.plot(
        df.index, df[f"SMA{SMA_SLOW}"],
        color=SMA200_COLOR, linewidth=1.4, linestyle="--", label=f"SMA{SMA_SLOW}",
    )

    sh = df[df["swing_high"]]
    sl = df[df["swing_low"]]
    ax1.scatter(sh.index, sh["high"], color=RESISTANCE_COLOR, s=18, zorder=5, label="Swing high")
    ax1.scatter(sl.index, sl["low"], color=SUPPORT_COLOR, s=18, zorder=5, label="Swing low")

    if swings["resistance"]:
        ax1.axhline(
            swings["resistance"]["price"],
            color=RESISTANCE_COLOR, linestyle=":", linewidth=1.2, alpha=0.85,
            label=f"Swing R {format_price(swings['resistance']['price'])}",
        )
    if swings["support"]:
        ax1.axhline(
            swings["support"]["price"],
            color=SUPPORT_COLOR, linestyle=":", linewidth=1.2, alpha=0.85,
            label=f"Swing S {format_price(swings['support']['price'])}",
        )

    x_last = df.index[-1]
    for col, color in (
        (f"EMA{EMA_FAST}", EMA_COLOR),
        (f"SMA{SMA_MID}", SMA50_COLOR),
        (f"SMA{SMA_SLOW}", SMA200_COLOR),
    ):
        value = last[col]
        if pd.isna(value):
            continue
        role = classify_ma(price, float(value))
        tag = "S" if role == "support" else "R"
        ax1.annotate(
            f"{col} {tag} {format_price(float(value))}",
            xy=(x_last, value),
            xytext=(8, 0),
            textcoords="offset points",
            color=color,
            fontsize=8,
            va="center",
        )

    title = f"{coin_name} • Moving-average S/R + latest swing levels + volume"
    if days_back:
        title += f" — last {days_back} days"
    ax1.set_title(title, fontsize=14, pad=12)
    ax1.set_ylabel("Price (USD)")
    ax1.yaxis.set_major_formatter(ticker.FuncFormatter(price_axis_formatter))
    ax1.legend(loc="upper left", fontsize=8, ncol=2, framealpha=0.92)
    ax1.grid(True, alpha=0.3)

    vol_colors = ["#2ca02c" if up else "#d62728" for up in df["up_day"]]
    ax2.bar(df.index, df["volumeto"], color=vol_colors, width=1.0, alpha=0.75, label="Volume")
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
    ax2.grid(True, alpha=0.3)
    add_date_formatters(ax2)

    plt.tight_layout()

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
    choices = get_coin_choice()
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
