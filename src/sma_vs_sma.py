import argparse

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as ticker

import get_price_data_cryptocompare as price_data
from coin_menu import coins_as_pairs, get_coin_choice, resolve_coin_arg
from indicators import add_rsi, add_sma


# ==================================================
# CONFIGURATION - Edit these values as needed
# ==================================================
BLOCK_WINDOW = True          # False = script continues immediately (non-blocking)

RSI_WINDOW = 14              # Standard RSI period; try 7, 21, 28 for different sensitivity
DAYS_BACK = 365 * 2          # None = full history
FIGURE_SIZE = (14, 8)
SHOW_GRID = True
HEIGHT_RATIOS = (3, 1)       # price | RSI

# Colors (consistent with 21_50_200_chart where possible)
CLOSE_COLOR = '#9EB3DB'
CLOSE_WIDTH = 1.1
SMA111_COLOR = '#E15FC3'     # Pink/magenta for 111
SMA50_COLOR = '#00D118'      # Green for 50
RSI_COLOR = '#FF9900'

# ==================================================
# END OF CONFIGURATION
# ==================================================


def draw_one_chart(
    coin_name: str,
    coin_ticker: str,
    *,
    block_window=BLOCK_WINDOW,
    rsi_window=RSI_WINDOW,
    days_back=DAYS_BACK,
    close_after=True,
):
    print(f"\n\U0001F4CA Loading data for {coin_name} ({coin_ticker})...")
    data_frame = price_data.get_price_data(coin=coin_ticker)

    if days_back is not None:
        data_frame = data_frame.sort_index().iloc[-days_back:]

    # Add indicators via shared module (DRY, consistent, maintainable)
    data_frame = add_sma(data_frame, window=111, out_col='SMA111')
    data_frame = add_sma(data_frame, window=50, out_col='SMA50')
    data_frame = add_rsi(data_frame, window=rsi_window)

    fig, (ax1, ax2) = plt.subplots(
        2, 1,
        figsize=FIGURE_SIZE,
        gridspec_kw={"height_ratios": list(HEIGHT_RATIOS)},
        sharex=True,
    )
    plt.style.use("fast")

    # === AX1: Price + SMAs ===
    ax1.plot(data_frame.index, data_frame['close'], label=f'{coin_name} Close Price',
             linewidth=CLOSE_WIDTH, color=CLOSE_COLOR)
    ax1.plot(data_frame.index, data_frame['SMA111'], label='111-Day SMA',
             linewidth=0.95, color=SMA111_COLOR)
    ax1.plot(data_frame.index, data_frame['SMA50'], label='50-Day SMA',
             linewidth=0.95, color=SMA50_COLOR)

    title = f'{coin_name} • 111-Day SMA vs 50-Day SMA + RSI({rsi_window})'
    if days_back:
        title += f' — Last {days_back} days'
    ax1.set_title(title, fontsize=14, pad=20)
    ax1.set_ylabel('Price (USD)')
    ax1.legend(loc='upper left')
    if SHOW_GRID:
        ax1.grid(True, alpha=0.3)

    # Flexible price formatter (handles BTC $100k+ and memecoins $0.000x)
    # This is kept from original sma_vs_sma.py because this script explicitly
    # supports low-priced altcoins/memecoins via the coin selector.
    def price_formatter(x, p):
        if x >= 1:
            return f'${x:,.0f}'
        elif x >= 0.01:
            return f'${x:,.2f}'
        else:
            return f'${x:,.4f}'
    ax1.yaxis.set_major_formatter(ticker.FuncFormatter(price_formatter))

    # === AX2: RSI ===
    ax2.plot(data_frame.index, data_frame['RSI'], color=RSI_COLOR, linewidth=1.5,
             label=f'RSI({rsi_window})')
    ax2.axhline(70, color='#E15FC3', linestyle='--', alpha=0.6, label='Overbought (70)')
    ax2.axhline(30, color='#00D118', linestyle='--', alpha=0.6, label='Oversold (30)')
    ax2.axhline(50, color='gray', linestyle=':', alpha=0.5, label='Midline (50)')
    ax2.set_ylabel('RSI')
    ax2.set_ylim(0, 100)
    ax2.legend(loc='upper left')
    if SHOW_GRID:
        ax2.grid(True, alpha=0.3)

    # ==================================================
    # X-AXIS DATE FORMATTING (improved for long histories)
    # Uses MonthLocator(interval=3) so major ticks/labels every 3 months
    # (e.g. at Jan/Apr/Jul/Oct positions) with clear '%Y-%m' format
    # (example: 2027-07 for July 2027). This keeps labels readable and
    # avoids overcrowding on 5-10+ year charts. Minor ticks (every month)
    # help with grid alignment. sharex=True means x-labels only appear
    # on the bottom panel (ax2).
    # ==================================================
    ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax2.xaxis.set_minor_locator(mdates.MonthLocator())
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax2.tick_params(axis='x', which='major', labelsize=9)

    plt.xlabel('Date')
    plt.tight_layout()

    print(f"\nDrawing {coin_name} chart with 111/50 SMAs + RSI({rsi_window})...")
    plt.show(block=block_window)
    if close_after and block_window:
        plt.close(fig)


def draw(
    block_window=BLOCK_WINDOW,
    rsi_window=RSI_WINDOW,
    days_back=DAYS_BACK,
    choices: list[tuple[str, str]] | None = None,
):
    if choices is None:
        choices = get_coin_choice("111/50 SMA + RSI Chart - Coin Selection")
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
                rsi_window=rsi_window,
                days_back=days_back,
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
        description="111/50 SMA + RSI chart.",
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


if __name__ == '__main__':
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

    draw(choices=choices)
