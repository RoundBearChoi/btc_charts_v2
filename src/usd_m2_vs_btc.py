import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import matplotlib.dates as mdates
import pandas as pd
from pandas.tseries.offsets import MonthEnd
import requests
from io import StringIO

import get_price_data_cryptocompare as price_data


def draw(block_window):
    # === Load data using the new unified data module ===
    # (No more dependency on deleted btc_data_loader.py)
    data_frame = price_data.get_btc_price_data()

    # === Original plotting logic (100% unchanged) ===
    # Resample daily BTC data to monthly (last close of the month)
    monthly_btc = data_frame.resample('ME').agg({'close': 'last'})

    # === Reliable FRED CSV endpoint ===
    m2_url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=M2SL"
    
    print("\nDownloading latest US M2 data from FRED (CSV)...")
    response = requests.get(m2_url)
    if response.status_code != 200:
        print(f"❌ Failed to download M2 data (status {response.status_code})")
        return

    # Read the CSV from memory (this is the fix)
    us_m2 = pd.read_csv(
        StringIO(response.text),           # ← critical change
        parse_dates=['observation_date'],  # ← FRED now uses this column name
        index_col='observation_date'
    )['M2SL']

    # Align index to month-end to match BTC data
    us_m2.index = us_m2.index + MonthEnd(0)

    # Combine with BTC and drop NaNs
    df = pd.DataFrame({'BTC': monthly_btc['close'], 'US_M2': us_m2})
    df = df.dropna()

    # Create the plot with shared x-axis for linked zooming/panning
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), gridspec_kw={'height_ratios': [3, 1]}, sharex=True)
    plt.style.use('fast')

    # Top: BTC price
    ax1.plot(df.index, df['BTC'], label='BTC Monthly Close', color='green', linewidth=0.55)
    ax1.set_title('BTC Price vs US M2 (FRED M2SL)')
    ax1.set_ylabel('Price (USD)')
    ax1.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: format(int(x), ',')))
    ax1.legend(loc='upper left')
    ax1.grid(False)

    # Format x-axis: years major, every 3 months minor with labels
    ax1.xaxis.set_major_locator(mdates.YearLocator())
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    ax1.xaxis.set_minor_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))  # Jan, Apr, Jul, Oct
    ax1.xaxis.set_minor_formatter(mdates.DateFormatter('%b'))

    # Bottom: US M2
    ax2.plot(df.index, df['US_M2'], label='US M2 (Billions USD)', color='blue', linewidth=0.85)
    ax2.set_ylabel('M2 (Billions USD)')
    ax2.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: format(int(x), ',')))
    ax2.legend(loc='upper left')
    ax2.grid(False)

    # Same x-axis formatting for bottom (sharex ensures sync)
    ax2.xaxis.set_major_locator(mdates.YearLocator())
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    ax2.xaxis.set_minor_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
    ax2.xaxis.set_minor_formatter(mdates.DateFormatter('%b'))

    # Optional: rotate x labels if crowded
    # plt.setp(ax2.get_xticklabels(which='both'), rotation=45, ha='right')

    plt.tight_layout()
    print('Drawing US M2 (bottom) vs BTC Price (top) — quarterly month markers on x-axis')
    plt.show(block=block_window)


if __name__ == '__main__':   # ← Keeps standalone runs working
    draw(True)   # True = block until you close the plot window
