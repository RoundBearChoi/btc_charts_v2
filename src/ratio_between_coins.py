#!/usr/bin/env python3

import os
from itertools import combinations
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as ticker

# Import the shared indicators module (sibling import works when running
# `python src/ratio_between_coins.py` from repo root, same as other scripts)
import indicators

# =============================================================================
# CONFIGURATION - Edit these values as needed (no code changes below required)
# =============================================================================
# Data paths (relative to this script's location - same structure as repo)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "cryptocompare_data")
COINS_CSV = Path(SCRIPT_DIR) / "coins.csv"

# Defaults overwritten by prompt_user_for_pair() after the user picks a pair.
# CSVs must already exist locally (this script does not download).
BASE_NAME = "BTC"
QUOTE_NAME = "FARTCOIN"
BASE_CSV = os.path.join(DATA_DIR, "cryptocompare_historic_btc_price.csv")
QUOTE_CSV = os.path.join(DATA_DIR, "cryptocompare_historic_fartcoin_price.csv")

# Chart behavior
BLOCK_WINDOW = True          # True = script waits for you to close plot window
DAYS_BACK = None             # e.g. 365*2 for last 2 years; None = full overlapping history
FIGURE_SIZE = (14, 9)        # (14, 8) original single panel; (14, 9-10) recommended when bottom indicator enabled for better proportions

# Moving Average settings (you can add more by extending the list)
MA_WINDOWS = [7, 30]         # SMA windows in days. 7=short-term noise filter, 30=monthly trend
USE_EMA_INSTEAD = False      # If True, uses EMA instead of SMA for all windows above
EMA_SPAN_FACTOR = 1.0        # For EMA, effective span = window * factor (1.0 = standard)

# Ratio calculation
RATIO_INVERTED = False       # False = BASE/QUOTE. True = QUOTE/BASE
RATIO_NAME = "BTC / FARTCOIN" if not RATIO_INVERTED else "FARTCOIN / BTC"

# Styling (consistent with other charts in the repo)
RATIO_COLOR = '#2E86AB'      # Nice blue for main ratio line
RATIO_WIDTH = 1.1
MA_COLORS = ['#E8871E', '#C73E1D', '#6B4226']  # Distinct warm colors for MAs (cycle if more windows)
MA_WIDTH = 1.6
MA_LINESTYLES = ['-', '--', '-.']  # Solid, dashed, dash-dot

# -----------------------------------------------------------------------------
# LONG-TERM CONTEXT (lighter overlays on the top panel)
# Analogous to interactive_classic_200_week_sma.py, but kept CONFIG-driven
# (no slider) so this script stays consistent with the rest of the toolkit.
#
# Do NOT reuse Pi Cycle 0.745 / 2.0 scale factors here. Those were calibrated
# on BTC-USD price cycles, not on a coin/coin ratio. On a ratio they would
# just draw two arbitrary bands.
# -----------------------------------------------------------------------------
ADD_LONG_MA = True
LONG_MA_WINDOW = 365          # days. 200 = classic daily long MA; 365 = 1y; 1400 ≈ 200 weeks
LONG_MA_MIN_PERIODS = None    # None → max(30, window // 2). Lets the line appear before the full window fills
LONG_MA_COLOR = '#8FA3B8'     # light steel — quieter than the warm 7/30 MAs
LONG_MA_WIDTH = 2.0
LONG_MA_ALPHA = 0.42
LONG_MA_STYLE = '-'

# Highest peak vs lowest bottom of the *plotted* ratio.
# RANGE_WINDOW = None  → expanding all-time high / low (staircase; only moves on new extremes)
# RANGE_WINDOW = 1461  → 4-year rolling Donchian channel (cycle highs/lows that can decay)
ADD_RANGE_ENVELOPE = True
RANGE_WINDOW = None
RANGE_HIGH_COLOR = '#9AA7B5'
RANGE_LOW_COLOR = '#9AA7B5'
RANGE_LINE_WIDTH = 1.05
RANGE_LINE_ALPHA = 0.50
RANGE_LINE_STYLE = ':'
RANGE_FILL_COLOR = '#8FA3B8'
RANGE_FILL_ALPHA = 0.07
