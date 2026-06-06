import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.widgets import Slider
import pandas as pd
from get_price_data_cryptocompare import get_btc_price_data   # ← your existing fetcher


# ==================== CONFIG SECTION ====================
MIN_WEEKS      = 3
MAX_WEEKS      = 250
DEFAULT_WEEKS  = 195 # classic 200-week SMA (slightly pulled back)

FIGURE_SIZE    = (12, 8)
BLOCK_WINDOW   = True
# ======================================================


def draw(initial_weeks=DEFAULT_WEEKS,
         min_weeks=MIN_WEEKS,
         max_weeks=MAX_WEEKS,
         block_window=BLOCK_WINDOW):
    """
    Bitcoin price chart with real-time adjustable WEEKLY Simple Moving Average.
    Now uses Sunday weekly closes to exactly match the famous 200-week SMA.
    """
    # === Load daily data ===
    data_frame = get_btc_price_data()

    # === Ensure datetime index ===
    if not isinstance(data_frame.index, pd.DatetimeIndex):
        data_frame = data_frame.set_index(pd.to_datetime(data_frame.index))

    # === Resample to weekly closes (Sunday) — this is the key fix ===
    weekly = data_frame['close'].resample('W-SUN').last()
    weekly_df = weekly.to_frame(name='close')

    # === Create figure ===
    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    plt.style.use('fast')
    plt.grid(False)

    # Daily price line
    price_line, = ax.plot(data_frame['close'], label='Bitcoin Price', linewidth=1.2)

    # Weekly SMA
    ma_series = weekly_df['close'].rolling(window=initial_weeks).mean()
    ma_line, = ax.plot(ma_series,
                       label=f'{initial_weeks}-Week Moving Average',
                       linewidth=1.5,
                       color='orange')

    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: format(int(x), ',')))

    plt.title('Bitcoin Price with Real-Time Adjustable Weekly Moving Average')
    plt.ylabel('Price (USD)')
    plt.xlabel('Time')
    plt.legend()

    # === Slider ===
    slider_ax = plt.axes([0.20, 0.02, 0.60, 0.03], facecolor='lightgray')
    weeks_slider = Slider(
        ax=slider_ax,
        label='Moving Average (weeks)',
        valmin=min_weeks,
        valmax=max_weeks,
        valinit=initial_weeks,
        valstep=1,
        valfmt='%d weeks'
    )

    def update(val):
        weeks = int(weeks_slider.val)
        ma_series = weekly_df['close'].rolling(window=weeks).mean()
        ma_line.set_ydata(ma_series)
        ma_line.set_label(f'{weeks}-Week Moving Average')
        ax.legend()
        fig.canvas.draw_idle()

    weeks_slider.on_changed(update)

    # === Diagnostic print for the 2018-2019 bottom (helpful for verification) ===
    bottom_period = weekly['2018-12-01':'2019-02-28']
    if not bottom_period.empty:
        min_idx = bottom_period.idxmin()
        min_price = bottom_period.min()
        sma_at_min = ma_series[min_idx] if min_idx in ma_series.index else None
        print(f"\n=== 2018-2019 Bottom Diagnostic ===")
        print(f"Lowest weekly close : {min_price:,.2f} on {min_idx.date()}")
        print(f"200-week SMA at that date : {sma_at_min:,.2f}" if sma_at_min is not None else "N/A")
        print(f"Price dipped below SMA? → {'YES' if sma_at_min is not None and min_price < sma_at_min else 'NO (very close)'}")

    print(f'\nDrawing interactive Weekly Moving Average (range: {min_weeks}-{max_weeks} weeks)')
    print('   → Sunday weekly closes used for maximum accuracy')

    plt.show(block=block_window)


if __name__ == '__main__':
    draw()
