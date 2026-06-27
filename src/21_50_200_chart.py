import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as ticker
import pandas as pd
import get_price_data_cryptocompare as price_data

# ==================================================
# CONFIGURATION - Edit these values as needed
# ==================================================
LOG_SCALE = False
DAYS_BACK = 360 * 8          # Set None for full history
BLOCK_WINDOW = True          # False = script continues immediately
SHOW_GRID = True
FIGURE_SIZE = (14, 10)

# RSI Configuration
RSI_WINDOW = 14              # ← Change this to any value you want (e.g. 21, 28, 50)

# Line styles
CLOSE_COLOR = '#9EB3DB'
CLOSE_WIDTH = 0.9
EMA21_COLOR = '#E15FC3'
SMA50_COLOR = '#00D118'
SMA200_COLOR = '#C80C01'
VOLUME_COLOR = '#8F8C57'
VOLUME_SMA_DAYS = 15
VOLUME_SMA_COLOR = '#263549'

# ==================================================
# END OF CONFIGURATION
# ==================================================

def get_coin_choice() -> str:
    """Expanded & future-proof coin selector"""
    print("\n" + "="*60)
    print("21/50/200 + Volume + RSI Chart - Coin Selection")
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

def add_rsi(data_frame, window=14):
    delta = data_frame['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=window, min_periods=window).mean()
    avg_loss = loss.rolling(window=window, min_periods=window).mean()
    
    for i in range(window, len(data_frame)):
        avg_gain.iloc[i] = (avg_gain.iloc[i-1] * (window - 1) + gain.iloc[i]) / window
        avg_loss.iloc[i] = (avg_loss.iloc[i-1] * (window - 1) + loss.iloc[i]) / window
    
    rs = avg_gain / avg_loss
    data_frame['RSI'] = 100 - (100 / (1 + rs))
    return data_frame

def draw(block_window=BLOCK_WINDOW, log_scale=LOG_SCALE, days_back=DAYS_BACK, rsi_window=RSI_WINDOW):
    coin_ticker = get_coin_choice()
   
    # Beautiful display names
    coin_display_names = {
        "BTC": "Bitcoin",
        "FARTCOIN": "Fartcoin",
        "TROLL": "Troll",
    }
    coin_name = coin_display_names.get(coin_ticker, coin_ticker)
    
    print(f"\n📊 Loading data for {coin_name} ({coin_ticker})...")
    data_frame = price_data.get_price_data(coin=coin_ticker)
    
    if days_back is not None:
        data_frame = data_frame.sort_index().iloc[-days_back:]

    # Indicators
    data_frame['EMA21'] = data_frame['close'].ewm(span=21, adjust=False).mean()
    data_frame['SMA50'] = data_frame['close'].rolling(window=50).mean()
    data_frame['SMA200'] = data_frame['close'].rolling(window=200).mean()
    
    if VOLUME_SMA_DAYS > 0:
        data_frame['VOLUME_SMA'] = data_frame['volumeto'].rolling(window=VOLUME_SMA_DAYS).mean()
    
    # RSI with configurable window
    data_frame = add_rsi(data_frame, window=rsi_window)

    # Plot
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=FIGURE_SIZE,
                                        gridspec_kw={'height_ratios': [3, 1, 1]},
                                        sharex=True)
    plt.style.use('fast')

    ax1.plot(data_frame.index, data_frame['close'], label=f'{coin_name} Close',
             linewidth=CLOSE_WIDTH, color=CLOSE_COLOR)
    ax1.plot(data_frame.index, data_frame['EMA21'], label='21 EMA', color=EMA21_COLOR, linewidth=1.3)
    ax1.plot(data_frame.index, data_frame['SMA50'], label='50 SMA', color=SMA50_COLOR, linewidth=1.3)
    ax1.plot(data_frame.index, data_frame['SMA200'], label='200 SMA (Long-term)',
             color=SMA200_COLOR, linewidth=1.6, linestyle='--')

    title = f'{coin_name} • 21 EMA vs 50 SMA + 200 SMA Filter + Volume + RSI({rsi_window})'
    if log_scale:
        ax1.set_yscale('log')
        title += ' (LOG)'
    if days_back:
        title += f' — Last {days_back} days'

    ax1.set_title(title, fontsize=14, pad=20)
    ax1.set_ylabel('Price (USD)')
    ax1.legend(loc='upper left')
    if SHOW_GRID: 
        ax1.grid(True, alpha=0.3)
    ax1.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f'${int(x):,}'))

    # Volume
    ax2.bar(data_frame.index, data_frame['volumeto'], color=VOLUME_COLOR, alpha=0.75, width=0.9)
    if 'VOLUME_SMA' in data_frame.columns:
        ax2.plot(data_frame.index, data_frame['VOLUME_SMA'],
                 color=VOLUME_SMA_COLOR, linewidth=1.5, label=f'{VOLUME_SMA_DAYS}d Vol SMA')
    ax2.set_ylabel('Volume (USD)')
    ax2.legend(loc='upper left')
    if SHOW_GRID: 
        ax2.grid(True, alpha=0.3)
    ax2.yaxis.set_major_formatter(ticker.FuncFormatter(
        lambda x, pos: f'${x/1e9:.1f}B' if x >= 1e9 else f'${x/1e6:.0f}M' if x >= 1e6 else f'${x:,.0f}'))

    # RSI
    ax3.plot(data_frame.index, data_frame['RSI'], color='#FF9900', linewidth=1.5, 
             label=f'RSI({rsi_window})')
    ax3.axhline(70, color='#E15FC3', linestyle='--', alpha=0.6, label='Overbought')
    ax3.axhline(30, color='#00D118', linestyle='--', alpha=0.6, label='Oversold')
    ax3.axhline(50, color='gray', linestyle=':', alpha=0.5)
    ax3.set_ylabel('RSI')
    ax3.set_ylim(0, 100)
    ax3.legend(loc='upper left')
    if SHOW_GRID: 
        ax3.grid(True, alpha=0.3)

    # ==================================================
    # IMPROVED X-AXIS DATE LABELING
    # Problem: YearLocator() + DateFormatter('%Y-%m') only placed major ticks at January of each year,
    #          so only January-ish labels (e.g. 2020-01) appeared in text on the x-axis.
    # Solution: Switch major locator to MonthLocator(interval=3) so ticks every 3 months (Jan/Apr/Jul/Oct),
    #           and format as '%b %Y' (e.g. "Jan 2024", "Apr 2024") to show actual month names.
    #           This displays *more months* as readable text labels while keeping the chart clean.
    #           Minor locator still provides every-month ticks (useful for grid alignment if extended).
    # Nuances & alternatives explored:
    #   - interval=1 (every month): too dense for 8-year view (~100 labels) → labels would overlap heavily.
    #   - interval=6 (Jan/Jul only): sparser, still shows month names but fewer.
    #   - mdates.AutoDateLocator() + mdates.ConciseDateFormatter(): smart/auto density + nice short labels
    #     (e.g. "2020", "Jan '21", "Jul"); great for interactive/zoomable but here static plot benefits from explicit.
    #   - For shorter ranges (small DAYS_BACK) you could use interval=1 + rotation=45 + smaller fontsize.
    #   - Edge case: full history (DAYS_BACK=None) or very long spans → consider lowering to interval=6 or using Auto.
    #   - sharex=True means only bottom axis (ax3) shows labels; this is standard and correct.
    # Recommendation: Run with your usual DAYS_BACK=360*8 first. If labels feel crowded, change interval=6.
    # ==================================================
    ax3.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax3.xaxis.set_minor_locator(mdates.MonthLocator())
    ax3.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    ax3.tick_params(axis='x', which='major', labelsize=9)

    plt.xlabel('Date')
    plt.tight_layout()

    print(f"Drawing {coin_name} chart with RSI({rsi_window})...")
    plt.show(block=block_window)


if __name__ == '__main__':
    draw()
