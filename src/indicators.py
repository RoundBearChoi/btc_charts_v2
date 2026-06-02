"""Shared technical indicators for BTC/crypto charts.

This module centralizes common calculations so they can be reused
across all chart scripts without duplication.
"""

import pandas as pd
from typing import Optional


def add_rsi(
    df: pd.DataFrame,
    window: int = 14,
    price_col: str = "close",
    out_col: str = "RSI",
) -> pd.DataFrame:
    """Add Relative Strength Index (RSI) using Wilder's smoothing.

    This implementation avoids look-ahead bias by using iterative calculation
    after the initial rolling mean.
    """
    if price_col not in df.columns:
        raise ValueError(f"Column '{price_col}' not found in DataFrame")

    delta = df[price_col].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    avg_gain = gain.rolling(window=window, min_periods=window).mean()
    avg_loss = loss.rolling(window=window, min_periods=window).mean()

    # Wilder's smoothing (more accurate than simple rolling mean for RSI)
    for i in range(window, len(df)):
        avg_gain.iloc[i] = (avg_gain.iloc[i - 1] * (window - 1) + gain.iloc[i]) / window
        avg_loss.iloc[i] = (avg_loss.iloc[i - 1] * (window - 1) + loss.iloc[i]) / window

    rs = avg_gain / avg_loss
    df[out_col] = 100 - (100 / (1 + rs))
    return df


def add_sma(
    df: pd.DataFrame,
    window: int,
    price_col: str = "close",
    out_col: Optional[str] = None,
) -> pd.DataFrame:
    """Add Simple Moving Average."""
    if out_col is None:
        out_col = f"SMA{window}"
    df[out_col] = df[price_col].rolling(window=window).mean()
    return df


def add_ema(
    df: pd.DataFrame,
    span: int,
    price_col: str = "close",
    out_col: Optional[str] = None,
) -> pd.DataFrame:
    """Add Exponential Moving Average."""
    if out_col is None:
        out_col = f"EMA{span}"
    df[out_col] = df[price_col].ewm(span=span, adjust=False).mean()
    return df


def add_pi_cycle_bottom(
    df: pd.DataFrame,
    sma_window: int = 471,
    ema_window: int = 150,
    factor: float = 0.745,
) -> pd.DataFrame:
    """Add Pi Cycle Bottom indicators (471 SMA × factor + 150 EMA)."""
    sma_col = f"{sma_window}_SMA_bottom"
    ema_col = f"{ema_window}_EMA_bottom"
    df[sma_col] = df["close"].rolling(window=sma_window).mean() * factor
    df[ema_col] = df["close"].ewm(span=ema_window, adjust=False).mean()
    return df


def add_pi_cycle_top(
    df: pd.DataFrame,
    sma_350_window: int = 350,
    sma_111_window: int = 111,
    factor: float = 2.0,
) -> pd.DataFrame:
    """Add Pi Cycle Top indicators (350 SMA × factor + 111 SMA)."""
    df[f"{sma_350_window}_SMA_top"] = df["close"].rolling(window=sma_350_window).mean() * factor
    df[f"{sma_111_window}_SMA_top"] = df["close"].rolling(window=sma_111_window).mean()
    return df
