# btc_charts_v2

Lightweight Python tools for Bitcoin & crypto charting using CryptoCompare data.

## Quick Start

```bash
pip install -r requirements.txt

# Download / update data
python src/get_price_data_cryptocompare.py

# Example charts
python src/price_zscore_chart.py
python src/21_50_200_chart.py
python src/rsi_vs_halving.py
```

## Scripts

| Script                              | Description                              |
|-------------------------------------|------------------------------------------|
| `price_zscore_chart.py`             | Price chart + rolling Z-Score            |
| `21_50_200_chart.py`                | Price + Volume + RSI (custom window)     |
| `rsi_vs_halving.py`                 | Monthly RSI colored by halving cycle     |
| `pi_bottom_top.py`                  | Pi Cycle Top & Bottom                    |
| `indicators.py`                     | Shared indicators (RSI, SMA, Z-Score…)   |
| `get_price_data_cryptocompare.py`   | Data downloader + cache                  |

Data cached in `src/cryptocompare_data/`.

Default branch: `incremental-coindesk-update`