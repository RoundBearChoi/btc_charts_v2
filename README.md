# btc_charts_v2

Lightweight, highly configurable Python toolkit for Bitcoin & crypto technical analysis charts.

Built around **CryptoCompare** historical price data (with smart incremental caching), plus Binance / Hyperliquid funding rates. Most charts support multi-coin selection (BTC, SOL, XMR, FARTCOIN, TROLL, or any custom ticker) and have a clear `CONFIG` section at the top for easy customization of windows, colors, date ranges, grid styling, etc.

**Requires Python ≥ 3.10**

---

## Quick Start

```bash
pip install -r requirements.txt

# First-time / update BTC price data (smart incremental — only downloads missing days)
python src/get_price_data_cryptocompare.py

# Popular charts
python src/zscore_chart.py
python src/21_50_200_chart.py
python src/ratio_between_coins.py
python src/funding_rates_btc_binance.py
```

Optional free CryptoCompare API key (higher rate limits):
```bash
export CRYPTOCOMPARE_API_KEY="your_key_here"
```

Data is cached under `src/cryptocompare_data/` (one CSV per coin).

The standalone downloader updates **BTC**. Other tickers are fetched the first time you run a chart that calls `get_price_data(coin=...)` (for example choosing SOL or XMR in `21_50_200_chart.py`).

---

## Project Structure

```
src/
├── get_price_data_cryptocompare.py   # Smart data downloader + cache (any coin)
├── indicators.py                     # Shared indicators (RSI, SMA, EMA, Z-Score, Pi Cycle)
├── plotting_utils.py                 # Common figure helpers & date formatters
│
├── zscore_chart.py                   # Price + Rolling Z-Score
├── 21_50_200_chart.py                # EMA21 / SMA50 / SMA200 + Volume + RSI
├── sma_vs_sma.py                     # 111 SMA vs 50 SMA + Volume + RSI
├── ratio_between_coins.py            # Offline coin-pair ratio + MAs + Z-Score/RSI extremes
├── pi_bottom_top.py                  # Pi Cycle Bottom & Top indicators
├── rsi_vs_halving.py                 # Monthly RSI colored by time-to-next-halving
├── interactive_classic_200_week_sma.py  # Interactive weekly SMA slider
├── usd_m2_vs_btc.py                  # BTC vs US M2 money supply (FRED)
│
├── funding_rates_btc_binance.py      # BTC Price + Funding Rate + Z-Score (Binance)
└── funding_rates_fartcoin_hype.py    # FARTCOIN Price + Funding Rate + Z-Score (Hyperliquid)
```

---

## Scripts Overview

### Data & Shared Modules

| Script | Description |
|--------|-------------|
| `get_price_data_cryptocompare.py` | Robust direct-API downloader. Supports **any ticker**. Smart incremental updates (only fetches missing recent days). Cleans zero-price pre-trading artifacts. Cache lives in `src/cryptocompare_data/`. Running the file directly updates BTC; pass another ticker through `get_price_data(coin=...)`. |
| `indicators.py` | Centralized, reusable indicators: Wilder RSI, SMA, EMA, rolling Z-Score, Pi Cycle Top/Bottom. |
| `plotting_utils.py` | Shared helpers for consistent 3-panel layouts and date axis formatting. |

### Price / Technical Charts

| Script | Description |
|--------|-------------|
| `zscore_chart.py` | Two-panel: Price (with optional 200 SMA) + Rolling Z-Score. Configurable window (default 365d). Multi-coin selector. Excellent for spotting statistical extremes. |
| `21_50_200_chart.py` | Classic three-panel: Price + EMA21/SMA50/SMA200 + Volume bars + RSI. Menu includes BTC, SOL, XMR, FARTCOIN, TROLL, or any custom ticker. Fully configurable RSI window, grid styling, date range. |
| `sma_vs_sma.py` | 111-day vs 50-day SMA + Volume + RSI. Same multi-coin + config pattern. |
| `ratio_between_coins.py` | Offline ratio chart. Prompts for **BTC:FARTCOIN**, **BTC:MONERO**, or **SOLANA:FARTCOIN**. Configurable MAs (or EMAs) on top + Z-Score (or RSI) extremes panel on bottom. Uses existing CSVs only — download the pair first if a file is missing (Monero ticker is `XMR`, Solana is `SOL`). |
| `pi_bottom_top.py` | Dual-panel Pi Cycle indicators (Bottom: 471 SMA × factor + 150 EMA; Top: 350 SMA × 2 + 111 SMA). |
| `rsi_vs_halving.py` | Monthly RSI line colored by months remaining until next Bitcoin halving. Includes cycle progress markers, halving vertical lines, and horizontal RSI levels. |
| `interactive_classic_200_week_sma.py` | Interactive slider (3–250 weeks) for the classic weekly SMA. Uses Sunday weekly closes for accuracy. |
| `usd_m2_vs_btc.py` | Two-panel comparison of monthly BTC close vs US M2 money supply (pulled live from FRED). |

### Funding Rate Charts

| Script | Description |
|--------|-------------|
| `funding_rates_btc_binance.py` | Three-panel: BTC Price (50/111 SMA) + Daily Funding Rate + Funding Z-Score. Data from Binance Futures. Local cache. |
| `funding_rates_fartcoin_hype.py` | Same layout for FARTCOIN on Hyperliquid. |

---

## Common Patterns

Almost every chart script follows the same structure:

1. **CONFIG block** at the very top (DAYS_BACK, windows, colors, grid style, figure size, etc.)
2. Optional interactive coin selector (`1) BTC  2) SOLANA  3) MONERO  4) FARTCOIN  5) TROLL  6) type any ticker`)
3. `draw()` function that loads data → adds indicators → plots → `plt.show()`
4. Shared `indicators.py` and `plotting_utils.py` to avoid duplication

This makes it very easy to tweak look-and-feel or analysis parameters without touching the plotting logic.

On a machine with a GUI backend (typically TkAgg), charts open in an interactive window. On headless / SSH sessions some scripts save a PNG instead of calling `plt.show()`.

---

## Notes

- **Multi-coin support**: Most price charts accept any CryptoCompare ticker (SOL, XMR, PEPE, DOGE, etc.).
- **Ratio chart** is offline-only. Expected cache names include `cryptocompare_historic_btc_price.csv`, `cryptocompare_historic_fartcoin_price.csv`, `cryptocompare_historic_xmr_price.csv`, and `cryptocompare_historic_sol_price.csv`.
- **Funding data** is cached separately (`binance_funding_data/`, `hyperliquid_fartcoin_funding_data/`).
- The `cryptocompare` package is **no longer used** — the downloader talks to the v2 API directly via `requests`.
- All scripts are designed to be run from the repo root: `python src/<script>.py`

---

## License

MIT
