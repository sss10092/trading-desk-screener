import unittest

from desk.massive import DailyBar
from desk.stock import screen_stocks, simulate_candidates


class StockModeTests(unittest.TestCase):
    def test_screener_filters_and_ranks(self):
        prev = {
            "AAA": DailyBar("AAA", 10, 11, 9.8, 10, 2_000_000),
            "BBB": DailyBar("BBB", 20, 21, 19, 20, 1_000_000),
            "PENNY": DailyBar("PENNY", 2, 2.2, 1.9, 2, 10_000_000),
        }
        current = {
            "AAA": DailyBar("AAA", 10.2, 10.8, 10.1, 10.6, 2_200_000),
            "BBB": DailyBar("BBB", 20, 21, 19.9, 20.8, 1_500_000),
            "PENNY": DailyBar("PENNY", 2.1, 2.4, 2.0, 2.3, 12_000_000),
        }
        candidates = screen_stocks(current, prev, min_price=5, max_price=500,
            min_volume=500_000, min_dollar_volume=10_000_000, min_change_pct=2,
            max_change_pct=15, max_candidates=5, signal_date="2026-01-05")
        self.assertEqual([c.ticker for c in candidates], ["AAA", "BBB"])

    def test_paper_simulation_only(self):
        from desk.stock import Candidate
        candidate = Candidate("AAA", "2026-01-05", 10.6, 10.0, 6.0, 2_200_000,
                              23_320_000, 3.9, 6.3)
        bars = {"AAA": DailyBar("AAA", 11, 12, 10.5, 11.5, 2_300_000)}
        result = simulate_candidates([candidate], bars, "2026-01-05", "2026-01-06",
            starting_cash=10_000, max_allocation_pct=0.10, fee_bps=5, slippage_bps=5)
        self.assertEqual(result["mode"], "PAPER_ONLY")
        self.assertEqual(result["trade_count"], 1)
        self.assertEqual(result["trades"][0]["status"], "PAPER_CLOSED")
        self.assertNotIn("live_order_id", result)

if __name__ == "__main__":
    unittest.main()
