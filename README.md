# btc_charts_v2

Bitcoin & crypto technical analysis toolkit (refactored v2).

> **This branch (`refactor/pyproject-indicators`) contains the first step of the modular refactor.**
> The `main` branch remains the original flat-script version for stability.

## What's New in This Refactor Branch

### 1. `pyproject.toml` (Modern Python Project Standard)
- Declarative dependencies, metadata, and tool configuration in one place.
- Enables `pip install -e .` (editable install) and clean dependency management.
- Ruff + Black configuration included.

### 2. Shared `src/indicators.py`
Centralized, reusable technical indicator functions:
- `add_rsi()` (Wilder's smoothing, no look-ahead bias)
- `add_sma()` / `add_ema()` with flexible column naming
- `add_pi_cycle_bottom()` and `add_pi_cycle_top()`

This eliminates duplication across chart scripts.

### 3. `src/plotting_utils.py`
Common styling, figure creation, and axis formatting helpers so all charts look consistent and are easier to maintain.

## How to Use the New Modules (Example)

```python
# In any chart script (same folder as indicators.py)
import pandas as pd
from indicators import add_rsi, add_sma, add_ema, add_pi_cycle_bottom

 df = pd.read_csv(...)  # or from get_price_data_cryptocompare
 df = add_rsi(df)
 df = add_sma(df, window=50)
 df = add_ema(df, span=21)
 df = add_pi_cycle_bottom(df)

# Then plot as usual
```

## Running Existing Scripts
All original scripts in `src/` continue to work unchanged on this branch.
You can gradually migrate them to use the shared modules.

## Next Refactor Ideas (Future Branches)
- Convert data layer into a proper `CryptoCompareProvider` class with incremental updates + logging
- Add CLI interface (argparse / typer)
- Make `src/` a proper package with `__init__.py`
- Add tests for indicators and data cleaning
- Optional Plotly backend for interactive web charts

## Original Goals
- Clean separation of data fetching vs visualization
- Support for BTC + any CryptoCompare ticker (great for memecoins)
- Classic on-chain/TA indicators popular in the BTC community

## Quick Start (any branch)

```bash
cd src
git checkout refactor/pyproject-indicators   # or stay on main
python get_price_data_cryptocompare.py
python 21_50_200_chart.py
python pi_bottom_top.py
```

## Dependencies
Managed via `pyproject.toml`. Install with:

```bash
pip install -e .
# or for dev tools
pip install -e ".[dev]"
```

---

**Main branch** = stable original scripts  
**This branch** = foundation for cleaner, more maintainable code

Feel free to merge pieces back to main as you like!
