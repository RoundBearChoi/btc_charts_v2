# btc_charts_v2

Lightweight, highly configurable Python toolkit for Bitcoin & crypto technical analysis charts.

Built around **CryptoCompare** historical price data (with smart incremental caching), plus Binance / Hyperliquid funding rates and US spot Bitcoin ETF flows. Most charts support multi-coin selection (BTC, SOL, XMR, FARTCOIN, TROLL, or any custom ticker) and have a clear `CONFIG` section at the top for easy customization of windows, colors, date ranges, grid styling, etc.

**Requires Python ≥ 3.10**

---

## Quick Start

```bash
# Needed for interactive chart windows (Matplotlib TkAgg).
# Tkinter is an OS package — pip will not install it.
sudo apt install python3-tk

pip install -r requirements.txt

# First-time / update BTC price data (smart incremental — only downloads missing days)
python src/get_price_data_cryptocompare.py

# Popular charts
python src/zscore_chart.py
python src/21_50_200_chart.py
python src/ratio_between_coins.py
python src/funding_rates_btc_binance.py
python src/spot_etf_btc.py
python src/resistance_and_support.py

# Skip the coin prompt (21/50/200 chart)
python src/21_50_200_chart.py --coin BTC
python src/21_50_200_chart.py --all --log --days 365
```

Check that Tkinter imported:

```bash
python -c "import tkinter; print('tkinter OK')"
```

Other systems:

```bash
# Fedora
sudo dnf install python3-tkinter

# Arch
sudo pacman -S tk

# macOS (Homebrew Python — match your version)
brew install python-tk@3.12
```

On Windows, use the official python.org installer and leave **tcl/tk and IDLE** checked.

If Tkinter is missing, some scripts still run and save a PNG instead of opening a window.

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
├── coins.csv                         # Display name + CryptoCompare ticker for chart menus
├── coin_menu.py                      # Shared coins.csv loader + 1..N / ALL prompt
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
├── resistance_and_support.py         # MAs as live S/R + swing levels + volume
│
├── funding_rates_btc_binance.py      # BTC Price + Funding Rate + Z-Score (Binance)
├── funding_rates_fartcoin_hype.py    # FARTCOIN Price + Funding Rate + Z-Score (Hyperliquid)
└── spot_etf_btc.py                   # BTC Price + US spot ETF daily/cumulative flows
```

---

## Scripts Overview

### Data & Shared Modules

| Script | Description |
|--------|-------------|
| `get_price_data_cryptocompare.py` | Robust direct-API downloader. Supports **any ticker**. Smart incremental updates (only fetches missing recent days). Cleans zero-price pre-trading artifacts. Cache lives in `src/cryptocompare_data/`. Running the file directly updates BTC; pass another ticker through `get_price_data(coin=...)`. |
| `indicators.py` | Centralized, reusable indicators: Wilder RSI, SMA, EMA, rolling Z-Score, Pi Cycle Top/Bottom, last crossover helper. |
| `plotting_utils.py` | Shared helpers for 3-panel layouts, price/volume formatters, grid styling, and window-aware date ticks. |
| `coin_menu.py` | Shared `coins.csv` loader and `1)`–`N)` / `ALL` prompt used by `21_50_200_chart.py` and `resistance_and_support.py`. |
| `coins.csv` | `name,symbol` list used by `21_50_200_chart.py`, `resistance_and_support.py`, and `ratio_between_coins.py`. Menu / pair order is row order (BTC, ETH, SOLANA, MONERO, FARTCOIN, TROLL). `symbol` is the CryptoCompare ticker (`SOL`, `XMR`, …). |

### Price / Technical Charts

| Script | Description |
|--------|-------------|
| `zscore_chart.py` | Two-panel: Price (with optional 200 SMA) + Rolling Z-Score. Configurable window (default 365d). Multi-coin selector. Excellent for spotting statistical extremes. |
| `21_50_200_chart.py` | Classic three-panel: Price + EMA21/SMA50/SMA200 + Volume + RSI. Computes MAs/RSI on full history then slices the window. 21/50 trend cloud, 21/50 and 50/200 cross markers, up/down volume, last-value box, RSI zones, and a terminal snapshot (regime + last crosses). Prompt is `1)`–`N)` / `ALL` from `src/coins.csv`, or skip it with `--coin BTC` / `--all` / `--log` / `--days 365`. Headless runs save under `output/`. |
| `sma_vs_sma.py` | 111-day vs 50-day SMA + Volume + RSI. Same multi-coin + config pattern. |
| `ratio_between_coins.py` | Offline ratio chart. Builds every unique pair from `src/coins.csv` in row order (`BTC:ETH`, `BTC:SOLANA`, … then `ETH:SOLANA`, …) and skips reverse pairs (`ETH:BTC`). Configurable MAs (or EMAs) on top + Z-Score (or RSI) extremes panel on bottom. Uses existing CSVs only — download both tickers first if a file is missing (`SOL`, `XMR`, …). |
| `pi_bottom_top.py` | Dual-panel Pi Cycle indicators (Bottom: 471 SMA × factor + 150 EMA; Top: 350 SMA × 2 + 111 SMA). |
| `rsi_vs_halving.py` | Monthly RSI line colored by months remaining until next Bitcoin halving. Includes cycle progress markers, halving vertical lines, and horizontal RSI levels. |
| `interactive_classic_200_week_sma.py` | Interactive slider (3–250 weeks) for the classic weekly SMA. Uses Sunday weekly closes for accuracy. |
| `usd_m2_vs_btc.py` | Two-panel comparison of monthly BTC close vs US M2 money supply (FRED). |
| `resistance_and_support.py` | Two-panel chart: price with EMA21/SMA50/SMA200 labeled as live support or resistance, latest confirmed swing high/low, and up/down volume. Prints the current levels in the terminal. Same `coins.csv` menu as `21_50_200_chart.py`. |

### Funding Rate Charts

| Script | Description |
|--------|-------------|
| `funding_rates_btc_binance.py` | Three-panel: BTC Price (50/111 SMA) + Daily Funding Rate + Funding Z-Score. Data from Binance Futures. Local cache. |
| `funding_rates_fartcoin_hype.py` | Same layout for FARTCOIN on Hyperliquid. |

### ETF Flow Charts

| Script | Description |
|--------|-------------|
| `spot_etf_btc.py` | Three-panel: BTC Price + daily US spot Bitcoin ETF net flows (USD, green/red bars) + cumulative net flow / AUM. Prints a recent per-fund table (IBIT, FBTC, GBTC, ARKB, …). Primary source is the TFTC open JSON dataset; BGeometrics is the fallback. Cache: `src/spot_etf_data/`. |

---

## Common Patterns

Almost every chart script follows the same structure:

1. **CONFIG block** at the very top (DAYS_BACK, windows, colors, grid style, figure size, etc.)
2. Optional interactive selector (`21_50_200_chart.py` and `resistance_and_support.py` share `coin_menu.py` + `src/coins.csv`; `ratio_between_coins.py` also reads that CSV; other charts still use a hardcoded `1) BTC … type any ticker` menu)
3. `draw()` function that loads data → adds indicators → plots → `plt.show()`
4. Shared `indicators.py`, `plotting_utils.py`, and `coin_menu.py` to avoid duplication

This makes it very easy to tweak look-and-feel or analysis parameters without touching the plotting logic.

On a machine with Tkinter + a GUI backend (typically TkAgg), charts open in an interactive window. On headless / SSH sessions, or if Tkinter is missing, `21_50_200_chart.py` saves a PNG under `output/` instead of calling `plt.show()`.

---

## Notes

- **Tkinter** is required for interactive chart windows. On Debian/Ubuntu: `sudo apt install python3-tk`. It is not in `requirements.txt`.
- **Multi-coin support**: `21_50_200_chart.py`, `resistance_and_support.py`, and `ratio_between_coins.py` only offer coins listed in `src/coins.csv`. Other price charts still accept any CryptoCompare ticker (SOL, XMR, PEPE, DOGE, etc.).
- **Ratio chart** is offline-only. Cache files follow `cryptocompare_historic_{symbol}_price.csv` for every `symbol` in `coins.csv` (for example `btc`, `eth`, `sol`, `xmr`, `fartcoin`, `troll`).
- **Funding data** is cached separately (`binance_funding_data/`, `hyperliquid_fartcoin_funding_data/`).
- **ETF flow data** is cached in `src/spot_etf_data/` and refreshes at most every 12 hours.
- The `cryptocompare` package is **no longer used** — the downloader talks to the v2 API directly via `requests`.
- All scripts are designed to be run from the repo root: `python src/<script>.py`

---

## License

MIT
