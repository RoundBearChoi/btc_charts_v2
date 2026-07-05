import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as ticker

import get_price_data_cryptocompare as price_data
from indicators import add_rsi, add_sma
from plotting_utils import create_price_volume_rsi_figure


# ==================================================
# CONFIGURATION - Edit these values as needed
# ==================================================
BLOCK_WINDOW = True          # False = script continues immediately (non-blocking)

RSI_WINDOW = 14              # Standard RSI period; try 7, 21, 28 for different sensitivity
VOLUME_SMA_DAYS = 15         # SMA on volume bars; set 0 to disable
DAYS_BACK = None             # e.g. 365*2 for last 2 years; None = full history
FIGURE_SIZE = (14, 10)
SHOW_GRID = True

# Colors (consistent with 21_50_200_chart where possible)
CLOSE_COLOR = '#9EB3DB'
SMA111_COLOR = '#E15FC3'     # Pink/magenta for 111
SMA50_COLOR = '#00D118'      # Green for 50
VOLUME_COLOR = '#8F8C57'
VOLUME_SMA_COLOR = '#263549'
RSI_COLOR = '#FF9900'

# ==================================================
# END OF CONFIGURATION
# ==================================================


def get_coin_choice() -> str:
    """Expanded & future-proof coin selector (shared pattern with other charts)"""
    print("\n" + "="*60)
    print("111/50 SMA + Volume + RSI Chart - Coin Selection")
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
            print("✘ Invalid. Try 1, 2, 3 or type a ticker.")


def draw(block_window=BLOCK_WINDOW, rsi_window=RSI_WINDOW, volume_sma_days=VOLUME_SMA_DAYS, days_back=DAYS_BACK):
    coin_ticker = get_coin_choice()
   
    # Beautiful display names
    coin_display_names = {
        "BTC": "Bitcoin",
        "FARTCOIN": "Fartcoin",
        "TROLL": "Troll",
    }
    coin_name = coin_display_names.get(coin_ticker, coin_ticker)
    
    print(f"\n\U0001F4CA Loading data for {coin_name} ({coin_ticker})...")
    data_frame = price_data.get_price_data(coin=coin_ticker)
    
    if days_back is not None:
        data_frame = data_frame.sort_index().iloc[-days_back:]

    # Add indicators via shared module (DRY, consistent, maintainable)
    data_frame = add_sma(data_frame, window=111, out_col='SMA111')
    data_frame = add_sma(data_frame, window=50, out_col='SMA50')
    
    if volume_sma_days > 0:
        data_frame['VOLUME_SMA'] = data_frame['volumeto'].rolling(window=volume_sma_days).mean()
    
    data_frame = add_rsi(data_frame, window=rsi_window)

    # Create the standard 3-panel figure (price taller | volume | rsi)
    fig, (ax1, ax2, ax3) = create_price_volume_rsi_figure(figsize=FIGURE_SIZE)

    # === AX1: Price + SMAs ===
    ax1.plot(data_frame.index, data_frame['close'], label=f'{coin_name} Close Price',
             linewidth=0.6, color=CLOSE_COLOR)
    ax1.plot(data_frame.index, data_frame['SMA111'], label='111-Day SMA',
             linewidth=0.95, color=SMA111_COLOR)
    ax1.plot(data_frame.index, data_frame['SMA50'], label='50-Day SMA',
             linewidth=0.95, color=SMA50_COLOR)

    title = f'{coin_name} • 111-Day SMA vs 50-Day SMA + Volume + RSI({rsi_window})'
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

    # === AX2: Volume (bar + optional SMA) ===
    ax2.bar(data_frame.index, data_frame['volumeto'], color=VOLUME_COLOR, alpha=0.75, width=0.9)
    if 'VOLUME_SMA' in data_frame.columns:
        ax2.plot(data_frame.index, data_frame['VOLUME_SMA'],
                 color=VOLUME_SMA_COLOR, linewidth=1.5, label=f'{volume_sma_days}d Vol SMA')
    ax2.set_ylabel('Volume (USD)')
    ax2.legend(loc='upper left')
    if SHOW_GRID:
        ax2.grid(True, alpha=0.3)
    ax2.yaxis.set_major_formatter(ticker.FuncFormatter(
        lambda x, pos: f'${x/1e9:.1f}B' if x >= 1e9 else f'${x/1e6:.0f}M' if x >= 1e6 else f'${x:,.0f}'))

    # === AX3: RSI ===
    ax3.plot(data_frame.index, data_frame['RSI'], color=RSI_COLOR, linewidth=1.5, 
             label=f'RSI({rsi_window})')
    ax3.axhline(70, color='#E15FC3', linestyle='--', alpha=0.6, label='Overbought (70)')
    ax3.axhline(30, color='#00D118', linestyle='--', alpha=0.6, label='Oversold (30)')
    ax3.axhline(50, color='gray', linestyle=':', alpha=0.5, label='Midline (50)')
    ax3.set_ylabel('RSI')
    ax3.set_ylim(0, 100)
    ax3.legend(loc='upper left')
    if SHOW_GRID:
        ax3.grid(True, alpha=0.3)

    # ==================================================
    # X-AXIS DATE FORMATTING (improved for long histories)
    # Uses MonthLocator(interval=3) so major ticks/labels every 3 months
    # (e.g. at Jan/Apr/Jul/Oct positions) with clear '%Y-%m' format
    # (example: 2027-07 for July 2027). This keeps labels readable and
    # avoids overcrowding on 5-10+ year charts. Minor ticks (every month)
    # help with grid alignment. sharex=True means x-labels only appear
    # on the bottom panel (ax3).
    # ==================================================
    ax3.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax3.xaxis.set_minor_locator(mdates.MonthLocator())
    ax3.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax3.tick_params(axis='x', which='major', labelsize=9)

    plt.xlabel('Date')
    plt.tight_layout()

    print(f"\nDrawing {coin_name} chart with 111/50 SMAs + Volume + RSI({rsi_window})...")
    plt.show(block=block_window)


if __name__ == '__main__':   # ← Keeps standalone runs working
    draw()   # Uses defaults from CONFIG
