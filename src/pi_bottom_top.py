import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

import get_price_data_cryptocompare as price_data


# ========================== CONFIG ==========================
# Figure size (width, height) - bigger = more detail
FIGSIZE = (16, 12)

# BTC Price line (used in BOTH panels for visual consistency)
PRICE_COLOR = 'black'
PRICE_WIDTH = 0.75

# === Pi Cycle Bottom Indicator lines ===
BOTTOM_471_COLOR = 'orange'
BOTTOM_471_WIDTH = 1.2
BOTTOM_150_COLOR = 'blue'
BOTTOM_150_WIDTH = 1.2

# === Pi Cycle Top Indicator lines ===
TOP_350_COLOR = 'red'
TOP_350_WIDTH = 1.2
TOP_111_COLOR = 'green'
TOP_111_WIDTH = 1.2

# Pi Cycle scaling factors (feel free to experiment)
PI_BOTTOM_FACTOR = 0.745   # Most common modern bottom factor
PI_TOP_FACTOR = 2.0        # Classic top factor

# Other styling
GRID_ALPHA = 0.3

# X-axis sharing (zoom & pan behavior)
#   True  = linked (both charts zoom/pan together - classic synchronized view)
#   False = independent (each chart can be zoomed/panned separately)
SHARE_X_AXIS = False

# === NaN handling for early data (Improvement #2) ===
# False = keep full BTC history (MAs start later - recommended for visualization)
# True  = drop early rows so chart starts only when all indicators are defined
DROP_EARLY_NANS = False
# ===========================================================


def draw(block_window):
    data_frame = price_data.get_btc_price_data()

    # === Pi Cycle Bottom Indicator ===
    data_frame['471_SMA_bottom'] = data_frame['close'].rolling(window=471).mean() * PI_BOTTOM_FACTOR
    data_frame['150_EMA_bottom'] = data_frame['close'].ewm(span=150, adjust=False).mean()

    # === Pi Cycle Top Indicator ===
    data_frame['350_SMA_top'] = data_frame['close'].rolling(window=350).mean() * PI_TOP_FACTOR
    data_frame['111_SMA_top'] = data_frame['close'].rolling(window=111).mean()

    # === NaN handling (Improvement #2) ===
    if DROP_EARLY_NANS:
        indicator_cols = ['471_SMA_bottom', '150_EMA_bottom', '350_SMA_top', '111_SMA_top']
        data_frame = data_frame.dropna(subset=indicator_cols)
        print(f'   → Dropped early NaN rows → chart now starts at {data_frame.index[0].date()}')
    else:
        print('   → Keeping full price history (NaNs in early MAs are normal and auto-skipped by matplotlib)')

    # === Plotting ===
    fig, (ax1, ax2) = plt.subplots(
        2, 1,
        figsize=FIGSIZE,
        sharex=SHARE_X_AXIS,
        gridspec_kw={'height_ratios': [1, 1]}
    )

    plt.style.use('fast')

    # Top panel: Pi Bottom
    ax1.plot(data_frame.index, data_frame['close'], '-',
             linewidth=PRICE_WIDTH, color=PRICE_COLOR, label='BTC Price')
    ax1.plot(data_frame.index, data_frame['471_SMA_bottom'], '-',
             linewidth=BOTTOM_471_WIDTH, color=BOTTOM_471_COLOR,
             label=f'471 SMA × {PI_BOTTOM_FACTOR}')
    ax1.plot(data_frame.index, data_frame['150_EMA_bottom'], '-',
             linewidth=BOTTOM_150_WIDTH, color=BOTTOM_150_COLOR, label='150 EMA')
    ax1.set_title('Pi Cycle Bottom Indicator', fontsize=14, fontweight='bold')
    ax1.set_ylabel('Price (USD)')
    ax1.legend(loc='upper left')
    ax1.grid(True, alpha=GRID_ALPHA)

    # Bottom panel: Pi Top
    ax2.plot(data_frame.index, data_frame['close'], '-',
             linewidth=PRICE_WIDTH, color=PRICE_COLOR, label='BTC Price')
    ax2.plot(data_frame.index, data_frame['350_SMA_top'], '-',
             linewidth=TOP_350_WIDTH, color=TOP_350_COLOR,
             label=f'350 SMA × {PI_TOP_FACTOR}')
    ax2.plot(data_frame.index, data_frame['111_SMA_top'], '-',
             linewidth=TOP_111_WIDTH, color=TOP_111_COLOR, label='111 SMA')
    ax2.set_title('Pi Cycle Top Indicator', fontsize=14, fontweight='bold')
    ax2.set_ylabel('Price (USD)')
    ax2.legend(loc='upper left')
    ax2.grid(True, alpha=GRID_ALPHA)

    # Ensure both panels start with the exact same full date range
    if not SHARE_X_AXIS:
        full_xlim = (data_frame.index[0], data_frame.index[-1])
        ax1.set_xlim(full_xlim)
        ax2.set_xlim(full_xlim)

    # Y-axis formatting (commas)
    for ax in [ax1, ax2]:
        ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: format(int(x), ',')))

    fig.suptitle('Bitcoin Pi Cycle Bottom & Top Indicators', fontsize=18, y=0.98)
    plt.xlabel('Date')

    print('\nDrawing Combined Pi Cycle Bottom & Top Indicators...')
    print(f'   → Bottom scaling factor: {PI_BOTTOM_FACTOR}')
    print(f'   → Top scaling factor:   {PI_TOP_FACTOR}')
    print(f'   → Figure size:          {FIGSIZE}')
    print(f'   → X-axis zoom behavior: {"Linked (synchronized)" if SHARE_X_AXIS else "Independent (separate zoom/pan)"}')
    print(f'   → Price line:           color={PRICE_COLOR}, width={PRICE_WIDTH}')

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.show(block=block_window)


if __name__ == '__main__':
    draw(True)
