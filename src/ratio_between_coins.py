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
