# resistance_and_support.py

```bash
python src/resistance_and_support.py
```

Same `coins.csv` menu as `21_50_200_chart.py`. No CLI — change `DAYS_BACK` / `LOG_SCALE` in the `CONFIG` block.

## Chart

1. Price — EMA21 / SMA50 / SMA200, swing dots, last swing lines, `S`/`R` tags
2. Table — MA value, role, `%` from close  
   distance = `(close − MA) / MA`
3. RSI(14) — 70 / 50 / 30

Gray band = last `SWING_RIGHT` bars (default 8). Those bars cannot confirm a pivot yet. No volume on this chart.

## Rules

- Close ≥ MA → **support**. Close < MA → **resistance**.
- Swing high/low = extreme of 8 bars left and 8 bars right.
- Structure from the last two confirmed highs and lows: `HH+HL`, `LH+LL`, or mixed.

Terminal print: close, structure, RSI, MA roles, last two swing highs/lows.

Headless: `{ticker}_resistance_and_support.png` in the current directory.

Useful `CONFIG`: `DAYS_BACK` (360), `SWING_LEFT` / `SWING_RIGHT` (8), `SHOW_MA_FOOTER`, `UNCONFIRMED_ALPHA`.
