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
    'interval_percent': 10,             # ← Change this! (5, 10, 20, 25, 50, etc.)
    'color': 'black',
    'linestyle': '--',                  # '--' dashed, ':' dotted, '-.' dash-dot, '-' solid
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
        f'({CYCLE_PROGRESS_LINES["interval_percent"]}% markers + halving lines)'
    )

    print(
        f'\nDrawing Monthly RSI vs Next Halving '
        f'(with {CYCLE_PROGRESS_LINES["interval_percent"]}% cycle markers + halving lines)..'
    )

    plt.show(block=block_window)


if __name__ == '__main__':   # ← Keeps standalone runs working
    draw(True)
