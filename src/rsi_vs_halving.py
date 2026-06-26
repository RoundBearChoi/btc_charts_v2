import matplotlib.pyplot as plt
import matplotlib.colors as colors
import dateutil.relativedelta as rel
import pandas
import numpy

import get_price_data_cryptocompare as price_data


# ========================== CONFIG ==========================
# Configuration for the thin vertical cycle-progress lines
CYCLE_PROGRESS_LINES = {
    'enabled': True,                    # Set to False to hide all % markers
    'interval_percent': 5,             # ← Change this! (5, 10, 20, 25, 50, etc.)
    'color': 'black',
    'linestyle': '--',                  # '--' dashed, ':' dotted, '-. ' dash-dot, '-' solid
    'linewidth': 0.8,
    'alpha': 0.5,
    'zorder': 0
}

# Configuration for the halving-date marker lines (new!)
HALVING_MARKERS = {
    'enabled': True,                    # Set to False to hide halving lines
    'color': 'blue',
    'linestyle': '--',                   # solid line to stand out
    'linewidth': 1.7,                   # thicker than progress lines
    'alpha': 0.5,
    'zorder': 2                         # drawn on top of progress lines
}

# Configuration for horizontal grid lines on the RSI y-axis (new!)
HORIZONTAL_GRID_LINES = {
    'enabled': True,                    # Set to False to hide horizontal reference lines
    'levels': [20, 30, 40, 50, 60, 70, 80],     # RSI psychological levels: 30=oversold, 50=neutral, 70=overbought
    'color': 'gray',
    'linestyle': ':',                   # dotted for clean, non-distracting reference
    'linewidth': 1.3,
    'alpha': 0.4,
    'zorder': 1                         # behind data lines but visible; adjust if needed
}

# Bitcoin halving dates (update future ones as needed)
HALVING_DATES = [
    '2012-11-28',
    '2016-07-09',
    '2020-05-11',
    '2024-04-20',
    '2028-04-11'
]
# ===========================================================


def draw(block_window):
    # === Load data using the new unified data module ===
    data_frame = price_data.get_btc_price_data()

    # === Original draw logic (100% unchanged) ===
    plt.figure(figsize=(12, 6))

    plt.style.use('fast')
    plt.grid(False)

    data_frame = data_frame.resample('ME').last().asfreq('ME')

    # Calculate RSI
    delta = data_frame['close'].diff()
    up = delta.clip(lower=0)
    down = -1*delta.clip(upper=0)
    ema_up = up.ewm(com=13, adjust=False).mean()
    ema_down = down.ewm(com=13, adjust=False).mean()
    rs = ema_up/ema_down

    data_frame['RSI'] = 100 - (100/(1 + rs))

    __plot(data_frame, block_window)


def __plot(data_frame, block_window):
    halving_dates = pandas.to_datetime(HALVING_DATES)
    halving_dates = pandas.DatetimeIndex(halving_dates)

    # === 1. Cycle progress lines (every X%) ===
    if CYCLE_PROGRESS_LINES['enabled']:
        interval = CYCLE_PROGRESS_LINES['interval_percent']
        for i in range(len(halving_dates) - 1):
            start = halving_dates[i]
            end = halving_dates[i + 1]
            duration = end - start
            for k in range(1, 100 // interval):
                progress_date = start + (k * interval / 100.0) * duration
                plt.axvline(
                    x=progress_date,
                    color=CYCLE_PROGRESS_LINES['color'],
                    linestyle=CYCLE_PROGRESS_LINES['linestyle'],
                    linewidth=CYCLE_PROGRESS_LINES['linewidth'],
                    alpha=CYCLE_PROGRESS_LINES['alpha'],
                    zorder=CYCLE_PROGRESS_LINES['zorder']
                )

    # === 2. Halving date markers (new!) ===
    if HALVING_MARKERS['enabled']:
        for hd in halving_dates:
            plt.axvline(
                x=hd,
                color=HALVING_MARKERS['color'],
                linestyle=HALVING_MARKERS['linestyle'],
                linewidth=HALVING_MARKERS['linewidth'],
                alpha=HALVING_MARKERS['alpha'],
                zorder=HALVING_MARKERS['zorder']
            )

    # === 3. Horizontal RSI grid / reference lines (new!) ===
    if HORIZONTAL_GRID_LINES['enabled']:
        for y_level in HORIZONTAL_GRID_LINES['levels']:
            plt.axhline(
                y=y_level,
                color=HORIZONTAL_GRID_LINES['color'],
                linestyle=HORIZONTAL_GRID_LINES['linestyle'],
                linewidth=HORIZONTAL_GRID_LINES['linewidth'],
                alpha=HORIZONTAL_GRID_LINES['alpha'],
                zorder=HORIZONTAL_GRID_LINES['zorder']
            )

    # Improve y-axis for RSI (bounded 0-100) so horizontal lines display cleanly
    plt.ylim(0, 100)
    plt.ylabel('RSI')

    # plot RSI (original logic unchanged)
    norm = plt.Normalize(0, 50)

    for i in numpy.arange(1, len(data_frame)):
        x_values = data_frame.index[i - 1:i + 1]
        y_values = data_frame['RSI'][i - 1:i + 1]

        months_left = None

        for halving_date in halving_dates:
            if x_values[1] < halving_date:
                diff = rel.relativedelta(halving_date, x_values[0])
                months_left = diff.years * 12 + diff.months
                break

        cmap = colors.LinearSegmentedColormap.from_list('my_cmap', ['lightgreen', 'red'])
        color_value = cmap(norm(months_left))

        plt.plot(x_values, y_values, color=color_value)

    plt.title(
        f'Monthly RSI vs Next Halving '
        f'({CYCLE_PROGRESS_LINES["interval_percent"]}% markers + halving lines + horizontal grids)'
    )

    print(
        f'\nDrawing Monthly RSI vs Next Halving '
        f'(with {CYCLE_PROGRESS_LINES["interval_percent"]}% cycle markers + halving lines + horizontal grids)..'
    )

    plt.show(block=block_window)


if __name__ == '__main__':   # ← Keeps standalone runs working
    draw(True)
