# coingecko_data

Local CoinGecko cache, next to `src/cryptocompare_data/`.

```
src/coingecko_data/
  daily/{gecko_id}.csv     # close + volume (21/50/200 and overlays)
  hourly/{gecko_id}.csv    # raw hourly snapshots (resistance OHLC)
```

CSV files are gitignored. First run of a chart creates them.

Env:

```
export COINGECKO_PLAN=demo          # demo | basic | analyst
export COINGECKO_API_KEY=...        # Demo or Pro key matching the plan
```

Do not mix these files with CryptoCompare CSVs. Prices will not match bar-for-bar.
