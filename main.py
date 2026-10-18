from __future__ import annotations

import argparse
import sys

from desk.config import load_env_file
from desk.crypto import scan_crypto
from desk.massive import MassiveAPIError
from desk.stock import demo, latest_weekday_pair, run_simulation, scan_and_save


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local multi-agent trading desk — paper trading only")
    sub = parser.add_subparsers(dest="mode", required=True)

    crypto = sub.add_parser("crypto", help="Crypto pair screener using public DexScreener data")
    crypto.add_argument("--query", default="SOL", help="Search term for DexScreener (default: SOL)")
    crypto.add_argument("--min-liquidity", type=float, default=100000, help="Minimum USD liquidity")
    crypto.add_argument("--min-volume", type=float, default=50000, help="Minimum 24-hour USD volume")
    crypto.add_argument("--max-results", type=int, default=10, help="Maximum results")

    stock = sub.add_parser("stock", help="US stocks screener and paper simulator")
    stock_sub = stock.add_subparsers(dest="stock_command", required=True)
    scan = stock_sub.add_parser("scan", help="Screen a completed market day using Massive EOD data")
    scan.add_argument("--date", help="Signal date YYYY-MM-DD (defaults to most recent weekday)")
    scan.add_argument("--previous-date", help="Previous trading date YYYY-MM-DD (defaults to prior weekday)")

    sim = stock_sub.add_parser("simulate", help="Screen on one day; enter next session open and exit that session close")
    sim.add_argument("--signal-date", required=True, help="Completed date used to create the signal, YYYY-MM-DD")
    sim.add_argument("--previous-date", required=True, help="Prior trading date for close-to-close return, YYYY-MM-DD")
    sim.add_argument("--execution-date", required=True, help="Next trading date used for simulated open/close, YYYY-MM-DD")

    stock_sub.add_parser("demo", help="Run an offline deterministic simulation with synthetic fixture data")

    return parser.parse_args()


def main() -> int:
    load_env_file()
    args = parse_args()
    try:
        if args.mode == "crypto":
            scan_crypto(args.query, args.min_liquidity, args.min_volume, args.max_results)
        elif args.mode == "stock" and args.stock_command == "demo":
            demo()
        elif args.mode == "stock" and args.stock_command == "scan":
            default_prev, default_day = latest_weekday_pair()
            signal_date = args.date or default_day
            previous_date = args.previous_date or default_prev
            scan_and_save(signal_date, previous_date)
        elif args.mode == "stock" and args.stock_command == "simulate":
            run_simulation(args.signal_date, args.previous_date, args.execution_date)
        return 0
    except (MassiveAPIError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
