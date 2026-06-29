import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

import get_price_data_cryptocompare as price_data


# ==================================================
# CONFIGURATION - Edit these values as needed
# ==================================================
BLOCK_WINDOW = True          # False = script continues immediately (non-blocking)


# ==================================================
# END OF CONFIGURATION
# ==================================================


def get_coin_choice() -> str:
    """Expanded & future-proof coin selector (shared pattern with other charts)"""
    print("\n" + "="*60)
    print("111/50 SMA Chart - Coin Selection")
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


def draw(block_window=BLOCK_WINDOW):
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
    
    plt.figure(figsize=(12, 6))

    data_frame['SMA111'] = data_frame['close'].rolling(window=111).mean()
    data_frame['SMA50'] = data_frame['close'].rolling(window=50).mean()

    plt.style.use('fast')
    plt.grid(False)

    plt.plot(data_frame.index, data_frame['close'], label=f'{coin_name} Close Price', linewidth=0.55)
    plt.plot(data_frame.index, data_frame['SMA111'], label='111-Day SMA', linewidth=0.85)
    plt.plot(data_frame.index, data_frame['SMA50'], label='50-Day SMA', linewidth=0.85)

    plt.title(f'{coin_name} • 111-Day SMA vs 50-Day SMA')
    plt.ylabel('Price (USD)')
    plt.legend()

    axis = plt.gca()
    # Improved price formatter that handles both large (BTC) and small (memecoin) values
    def price_formatter(x, p):
        if x >= 1:
            return f'${x:,.0f}'
        elif x >= 0.01:
            return f'${x:,.2f}'
        else:
            return f'${x:,.4f}'
    axis.yaxis.set_major_formatter(ticker.FuncFormatter(price_formatter))

    print('\nDrawing 111SMA vs 50SMA..')

    plt.show(block=block_window)


if __name__ == '__main__':   # ← Keeps standalone runs working
    draw()   # Uses default BLOCK_WINDOW = True
