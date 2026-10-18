# Trading Desk Screener

An end-of-day US stock screener and next-session paper simulator, plus a simple crypto pair screener. Nothing here connects to a broker or wallet.

## What it does

1. Pulls grouped daily OHLCV bars for US stocks from Massive (formerly Polygon.io), which works on the free plan.
2. Screens on close-to-close momentum, close above open, price, volume and dollar volume.
3. Writes candidates to `output/`.
4. Simulates buying candidates at the next session's open and selling at its close, with fees and slippage, and saves a JSON ledger to `paper/`. The signal only sees the signal-day close, so there is no same-bar look-ahead.
5. The crypto mode screens DexScreener pairs by liquidity and 24h volume. It does not trade.

This is a simple rule-based starting point, not a profitable strategy. It has no intraday stops, partial fills or corporate-action handling, and the default filters are examples, not tuned values.

## Run

```bash
pip install -r requirements.txt
cp .env.example .env
python main.py stock demo
python -m unittest discover -s tests -v
python main.py crypto --query SOL --min-liquidity 100000 --min-volume 50000
python main.py stock scan --date 2026-10-09 --previous-date 2026-10-08
python main.py stock simulate --previous-date 2026-10-08 --signal-date 2026-10-09 --execution-date 2026-10-12
```

The demo uses synthetic prices and needs no key. The scan and simulate commands need `MASSIVE_API_KEY` in `.env`. Use real adjacent trading sessions as dates.
