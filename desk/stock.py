from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping

from .config import get_float, get_int
from .massive import DailyBar, fetch_grouped_daily

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "output"
PAPER_DIR = ROOT / "paper"


@dataclass
class Candidate:
    ticker: str
    signal_date: str
    close: float
    previous_close: float
    change_pct: float
    volume: float
    dollar_volume: float
    close_vs_open_pct: float
    score: float


def screen_stocks(current: Mapping[str, DailyBar], previous: Mapping[str, DailyBar], *,
                  min_price: float | None = None, max_price: float | None = None,
                  min_volume: float | None = None, min_dollar_volume: float | None = None,
                  min_change_pct: float | None = None, max_change_pct: float | None = None,
                  max_candidates: int | None = None, signal_date: str = "") -> list[Candidate]:
    min_price = get_float("STOCK_MIN_PRICE", 5) if min_price is None else min_price
    max_price = get_float("STOCK_MAX_PRICE", 500) if max_price is None else max_price
    min_volume = get_float("STOCK_MIN_VOLUME", 500_000) if min_volume is None else min_volume
    min_dollar_volume = get_float("STOCK_MIN_DOLLAR_VOLUME", 10_000_000) if min_dollar_volume is None else min_dollar_volume
    min_change_pct = get_float("STOCK_MIN_CHANGE_PCT", 2) if min_change_pct is None else min_change_pct
    max_change_pct = get_float("STOCK_MAX_CHANGE_PCT", 15) if max_change_pct is None else max_change_pct
    max_candidates = get_int("STOCK_MAX_CANDIDATES", 5) if max_candidates is None else max_candidates

    candidates: list[Candidate] = []
    for ticker, bar in current.items():
        prev = previous.get(ticker)
        if not prev or prev.close <= 0 or bar.close < min_price or bar.close > max_price:
            continue
        if bar.volume < min_volume or bar.dollar_volume < min_dollar_volume:
            continue
        change_pct = (bar.close / prev.close - 1.0) * 100.0
        close_vs_open = (bar.close / bar.open - 1.0) * 100.0 if bar.open > 0 else 0.0
        if not (min_change_pct <= change_pct <= max_change_pct and close_vs_open > 0):
            continue
        score = change_pct + min(math.log10(max(bar.dollar_volume, 1)) - 7, 3) * 0.25
        candidates.append(Candidate(ticker, signal_date, bar.close, prev.close, change_pct,
                                   bar.volume, bar.dollar_volume, close_vs_open, score))
    candidates.sort(key=lambda c: (c.score, c.dollar_volume), reverse=True)
    return candidates[:max(0, max_candidates)]


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("No qualifying rows.\n", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def scan_and_save(signal_date: str, previous_date: str) -> list[Candidate]:
    print(f"Fetching Massive grouped daily bars: {previous_date} and {signal_date} (end-of-day data)...")
    previous = fetch_grouped_daily(previous_date)
    current = fetch_grouped_daily(signal_date)
    candidates = screen_stocks(current, previous, signal_date=signal_date)
    rows = [asdict(c) for c in candidates]
    path = OUT_DIR / f"stock_scan_{signal_date}.csv"
    _write_csv(path, rows)
    print(f"Universe: {len(current):,} symbols on {signal_date}; {len(candidates)} candidates passed filters.")
    print(f"Saved: {path}")
    if not candidates:
        print("No candidates qualified. This is a valid result; do not loosen filters just to force a trade.")
    else:
        print(f"{'Ticker':<8} {'Change':>8} {'Close':>10} {'Volume':>14} {'$ Volume':>16}")
        for c in candidates:
            print(f"{c.ticker:<8} {c.change_pct:>7.2f}% {c.close:>10.2f} {c.volume:>14,.0f} {c.dollar_volume:>16,.0f}")
    return candidates


def simulate_candidates(candidates: list[Candidate], next_day_bars: Mapping[str, DailyBar],
                        signal_date: str, execution_date: str, *, starting_cash: float | None = None,
                        max_allocation_pct: float | None = None, fee_bps: float | None = None,
                        slippage_bps: float | None = None) -> dict:
    cash = get_float("STOCK_STARTING_CASH", 10_000) if starting_cash is None else starting_cash
    max_alloc = get_float("STOCK_MAX_ALLOCATION_PCT", 0.10) if max_allocation_pct is None else max_allocation_pct
    fee = (get_float("STOCK_FEE_BPS", 5) if fee_bps is None else fee_bps) / 10_000
    slip = (get_float("STOCK_SLIPPAGE_BPS", 5) if slippage_bps is None else slippage_bps) / 10_000
    starting_equity = cash
    trades: list[dict] = []
    per_trade_budget = starting_equity * max(0, min(max_alloc, 1.0))

    for candidate in candidates:
        bar = next_day_bars.get(candidate.ticker)
        if not bar or bar.open <= 0 or bar.close <= 0:
            continue
        entry = bar.open * (1 + slip)
        exit_price = bar.close * (1 - slip)
        qty = math.floor(per_trade_budget / entry)
        if qty < 1:
            continue
        gross_cost = qty * entry
        entry_fee = gross_cost * fee
        total_debit = gross_cost + entry_fee
        if total_debit > cash:
            qty = math.floor(cash / (entry * (1 + fee)))
            if qty < 1:
                continue
            gross_cost = qty * entry
            entry_fee = gross_cost * fee
            total_debit = gross_cost + entry_fee
        gross_proceeds = qty * exit_price
        exit_fee = gross_proceeds * fee
        net_proceeds = gross_proceeds - exit_fee
        pnl = net_proceeds - total_debit
        cash += pnl
        trades.append({
            "ticker": candidate.ticker,
            "signal_date": signal_date,
            "execution_date": execution_date,
            "signal_change_pct": round(candidate.change_pct, 4),
            "quantity": qty,
            "entry_price_with_slippage": round(entry, 4),
            "exit_price_with_slippage": round(exit_price, 4),
            "entry_fee": round(entry_fee, 4),
            "exit_fee": round(exit_fee, 4),
            "net_pnl": round(pnl, 4),
            "return_on_trade_pct": round(pnl / total_debit * 100, 4),
            "status": "PAPER_CLOSED",
        })

    total_pnl = cash - starting_equity
    result = {
        "mode": "PAPER_ONLY",
        "strategy": "EOD momentum signal; next-session open entry; same-session close exit",
        "signal_date": signal_date,
        "execution_date": execution_date,
        "starting_equity": round(starting_equity, 2),
        "ending_equity": round(cash, 2),
        "net_pnl": round(total_pnl, 2),
        "return_pct": round(total_pnl / starting_equity * 100, 4) if starting_equity else 0,
        "trade_count": len(trades),
        "fees_and_slippage": "Included using configurable basis-point assumptions",
        "trades": trades,
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
    PAPER_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PAPER_DIR / f"stock_simulation_{signal_date}_to_{execution_date}.json"
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("\nPAPER SIMULATION (not a live trade)")
    print(f"Signal date: {signal_date} | Simulated execution date: {execution_date}")
    print(f"Starting equity: ${starting_equity:,.2f} | Ending equity: ${cash:,.2f}")
    print(f"Net P&L: ${total_pnl:,.2f} ({result['return_pct']:.2f}%) | Closed trades: {len(trades)}")
    for trade in trades:
        print(f"  {trade['ticker']}: {trade['quantity']} shares, ${trade['net_pnl']:+,.2f} net P&L")
    print(f"Saved ledger: {out_path}")
    if not trades:
        print("No paper trades were generated; the screener may have returned no candidates or next-day bars were unavailable.")
    return result


def run_simulation(signal_date: str, previous_date: str, execution_date: str) -> dict:
    candidates = scan_and_save(signal_date, previous_date)
    if not candidates:
        return simulate_candidates([], {}, signal_date, execution_date)
    print(f"Fetching execution-day bars for {execution_date}...")
    next_bars = fetch_grouped_daily(execution_date)
    return simulate_candidates(candidates, next_bars, signal_date, execution_date)


def demo() -> dict:
    prev = {
        "ALFA": DailyBar("ALFA", 48, 50, 47, 49, 1_500_000),
        "BETA": DailyBar("BETA", 90, 92, 88, 90, 2_000_000),
        "GAMM": DailyBar("GAMM", 20, 21, 19, 20, 800_000),
        "TINY": DailyBar("TINY", 2, 3, 2, 2.5, 10_000_000),
    }
    current = {
        "ALFA": DailyBar("ALFA", 50, 54, 49, 53, 1_800_000),
        "BETA": DailyBar("BETA", 90, 95, 89, 94, 2_500_000),
        "GAMM": DailyBar("GAMM", 20, 20.4, 19, 19.8, 1_000_000),
        "TINY": DailyBar("TINY", 2.5, 3.2, 2.4, 3.0, 12_000_000),
    }
    candidates = screen_stocks(current, prev, min_price=5, max_price=500, min_volume=500_000,
                               min_dollar_volume=10_000_000, min_change_pct=2, max_change_pct=15,
                               max_candidates=5, signal_date="DEMO_SIGNAL")
    print("OFFLINE DEMO: all prices below are synthetic test data, not market data.")
    print(f"Candidates: {[c.ticker for c in candidates]}")
    execution = {
        "ALFA": DailyBar("ALFA", 53, 56, 52, 55, 1_900_000),
        "BETA": DailyBar("BETA", 94, 95, 91, 92, 2_600_000),
    }
    return simulate_candidates(candidates, execution, "DEMO_SIGNAL", "DEMO_EXECUTION", starting_cash=10_000,
                               max_allocation_pct=0.10, fee_bps=5, slippage_bps=5)


def latest_weekday_pair() -> tuple[str, str]:
    today = date.today()
    latest = today - timedelta(days=1)
    while latest.weekday() >= 5:
        latest -= timedelta(days=1)
    previous = latest - timedelta(days=1)
    while previous.weekday() >= 5:
        previous -= timedelta(days=1)
    return previous.isoformat(), latest.isoformat()
